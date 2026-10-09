"""Isolated checks: never import app's production startup or connect to MySQL."""
import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import Utils.page_content as pc


def isolated_app():
    spec = importlib.util.spec_from_file_location('lady_isolated', ROOT / 'app.py')
    module = importlib.util.module_from_spec(spec)
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    startup = '\ntry:\n    load_config()\n    ensure_schema()'
    assert startup in source
    exec(compile(source.split(startup)[0], str(ROOT / 'app.py'), 'exec'), module.__dict__)
    module.app.template_folder = str(ROOT / 'templates')
    module.app.static_folder = str(ROOT / 'static')
    return module


class ContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = isolated_app()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(pc, 'CONTENT_PATH', Path(self.temp.name) / 'pages.json')
        self.path_patch.start()
        self.module.load_config = lambda: {'ONLINE_APPOINTMENT_ENABLED': '0', 'SITE_MAINTENANCE_ENABLED': '0', 'SERVICES_PAGE_INTRO': 'Послуги'}
        self.user = {'Login': 'tester', 'Role': 'admin'}
        self.module.current_user = lambda: self.user
        self.module.record_page_visit = lambda: None
        self.module.ensure_schema = lambda: None
        self.module.log_action = lambda *args: None
        self.module.log_user_event = lambda *args: None
        self.module.total_visit_count = lambda: 0
        self.module.total_appointment_count = lambda: 0
        self.module.db_cursor = Mock(side_effect=AssertionError('Real database access is forbidden'))
        self.client = self.module.app.test_client()
        with self.client.session_transaction() as session:
            session['content_csrf'] = 'test-csrf'

    def tearDown(self):
        self.path_patch.stop()
        self.temp.cleanup()

    def test_public_footer_hides_appointments_when_enabled(self):
        self.user = None
        self.module.load_config = lambda: {'ONLINE_APPOINTMENT_ENABLED':'1', 'VISITOR_PERIOD_VALUE':'7', 'VISITOR_PERIOD_UNIT':'days'}
        self.module.total_appointment_count = Mock(side_effect=AssertionError('Public footer must not query appointments'))
        self.module.get_service_data = lambda: []
        html = self.client.get('/?preview=public').get_data(as_text=True)
        self.assertIn('footer-version', html)
        self.assertIn('Відвідало за останні 7 дн.:', html)
        self.assertNotIn('Записалось:', html)

    def test_visitor_period_query(self):
        from contextlib import nullcontext
        # Restore the real counting function in this isolated module only.
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        start = source.index('def total_visit_count()')
        end = source.index('def total_appointment_count()', start)
        scope = dict(self.module.__dict__)
        cursor = Mock()
        cursor.fetchone.return_value = {'cnt': 12}
        scope['db_cursor'] = lambda: nullcontext(cursor)
        scope['runtime_state'] = {'schema_ready':True}
        for unit, sql_unit, value in [('days','DAY','7'), ('months','MONTH','2')]:
            scope['load_config'] = lambda: {'VISITOR_PERIOD_UNIT':unit, 'VISITOR_PERIOD_VALUE':value}
            exec(source[start:end], scope)
            self.assertEqual(scope['total_visit_count'](), 12)
            sql, params = cursor.execute.call_args.args
            self.assertIn('CreatedAt >= DATE_SUB(NOW(), INTERVAL %s ' + sql_unit + ')', sql)
            self.assertEqual(params, (int(value),))

    def test_contact_columns_preserve_content_and_custom_groups(self):
        original = {'site_blocks':[{'layout':'text', 'nodes':[
            {'kind':'heading','value':{'text':'Контакти:'}},
            {'kind':'text','name':'Телефон','value':{'text':'123'}},
            {'kind':'social','value':{'align':'left'}},
            {'kind':'text','value':{'text':'Мій текст'}}]}]}
        result = pc.site_blocks(original, {})
        group = result[0]['nodes'][0]
        self.assertEqual(group['columns'], 2)
        self.assertEqual(group['nodes'][0]['nodes'][1]['value']['text'], '123')
        self.assertEqual(group['nodes'][1]['nodes'][0]['kind'], 'social')
        self.assertEqual(result[0]['nodes'][1]['value']['text'], 'Мій текст')
        self.assertEqual(original['site_blocks'][0]['nodes'][0]['kind'], 'heading')
        saved = pc.normalize_blocks(result)
        self.assertEqual(pc.site_blocks({'site_blocks':saved}, {}), saved)

    def test_home_appointment_and_editor(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('id="appointment"', html)
        self.assertIn('id="page-editor"', html)
        self.assertEqual(html.count('ca-pub-2294227136369675'), 1)
        self.assertNotIn('id="page-editor"', self.client.get('/?preview=public').get_data(as_text=True))
        self.module.load_config = lambda: {'ONLINE_APPOINTMENT_ENABLED':'1'}
        self.assertIn('id="appointment"', self.client.get('/').get_data(as_text=True))

    def test_save_and_reload(self):
        blocks = [{'layout':'text','heading':{'text':'Новий заголовок'},'items':[{'text':{'text':'Текст'},'button':{'text':'Послуги','url':'/services'}}]}]
        response = self.client.post('/content/save', data={'csrf':'test-csrf','page_path':'/','page_title':'Головна','blocks':json.dumps(blocks)})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Новий заголовок', self.client.get('/').get_data(as_text=True))
        self.assertEqual(pc.read_content()['pages']['/']['title'], 'Головна')
        self.assertEqual(pc.read_content()['global_code']['head'], pc.DEFAULT_CODE)

    def test_delete_all_home_blocks_persists(self):
        response = self.client.post('/content/save', data={
            'csrf': 'test-csrf', 'page_path': '/',
            'page_title': 'Головна', 'blocks': '[]'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pc.read_content()['pages']['/']['blocks'], [])
        html = self.client.get('/?preview=public').get_data(as_text=True)
        self.assertNotIn('Тут дбають про деталі', html)
        self.assertNotIn('Консультація і підбір', html)
        self.assertEqual(pc.read_content()['pages']['/']['blocks'], [])

    def test_image_modes_save_reload_and_render(self):
        for mode in ('normal', 'stretch', 'tile', 'cover'):
            with self.subTest(mode=mode):
                blocks = [{'layout': 'text-image', 'items': [{
                    'image': '/static/test.png', 'alt': 'Малюнок',
                    'image_mode': mode, 'image_align': 'right', 'image_vertical': 'top'}]}]
                response = self.client.post('/content/save', data={
                    'csrf': 'test-csrf', 'page_path': '/', 'page_title': 'Тест',
                    'blocks': json.dumps(blocks)})
                self.assertEqual(response.status_code, 200)
                item = pc.read_content()['pages']['/']['blocks'][0]['items'][0]
                self.assertEqual((item['image_mode'], item['image_align'], item['image_vertical']),
                                 (mode, 'right', 'top'))
                html = self.client.get('/?preview=public').get_data(as_text=True)
                self.assertIn('image-mode-' + mode, html)
                self.assertIn('background-position:right top' if mode == 'tile' else 'object-position:right top', html)
                if mode == 'tile':
                    self.assertIn('role="img" aria-label="Малюнок"', html)
                    self.assertIn('background-image:url(', html)

    def test_legacy_image_defaults(self):
        item = pc.normalize_blocks([{'layout': 'image', 'items': [{'image': '/static/test.png'}]}])[0]['items'][0]
        self.assertEqual((item['image_mode'], item['image_align'], item['image_vertical']),
                         ('normal', 'center', 'center'))

    def test_nodes_order_carousel_empty_and_delete_persist(self):
        nodes = [{'kind':'text', 'value':{'text':'Перший текст'}},
                 {'kind':'heading', 'value':{'text':'Заголовок після тексту'}},
                 {'kind':'carousel', 'nodes':[{'kind':'image','image':'/static/one.png'},
                                              {'kind':'image','image':'/static/two.png'}]},
                 {'kind':'animation','effect':'Flowers'}]
        def save(nodes):
            return self.client.post('/content/save', data={
                'csrf':'test-csrf','page_path':'/','page_title':'Ноди',
                'blocks':json.dumps([{'layout':'text-image','nodes':nodes}])})
        self.assertEqual(save(nodes).status_code, 200)
        self.assertEqual(pc.read_content()['pages']['/']['blocks'][0]['nodes'][1]['kind'], 'heading')
        html = self.client.get('/?preview=public').get_data(as_text=True)
        self.assertLess(html.index('Перший текст'), html.index('Заголовок після тексту'))
        self.assertIn('data-carousel-step="1"', html)
        self.assertIn('data-block-effect="Flowers"', html)
        self.assertEqual(save([{'kind':'group','nodes':[]}]).status_code, 200)
        html = self.client.get('/?preview=public').get_data(as_text=True)
        self.assertNotIn('content-node-group', html.split('content-blocks site-blocks')[0])
        self.assertEqual(save([]).status_code, 200)
        self.assertEqual(pc.read_content()['pages']['/']['blocks'][0]['nodes'], [])
        self.assertNotIn('Заголовок після тексту', self.client.get('/?preview=public').get_data(as_text=True))

    def test_contacts_save_order_and_permissions(self):
        self.assertEqual(self.client.post('/settings/contacts',data={}).status_code,400)
        values = {'csrf':'test-csrf','address':'Адреса для тесту','comment':'У дворі',
                  'hours':'Пн: 10–18\nВт: вихідний','phone':'123',
                  'instagram':'https://instagram.com/test','map_embed_url':'https://www.google.com/maps?q=test&output=embed'}
        self.assertEqual(self.client.post('/settings/contacts',data=values).status_code,302)
        self.assertEqual(pc.read_content()['contacts']['hours'],values['hours'])
        html = self.client.get('/?preview=public').get_data(as_text=True)
        self.assertLess(html.index('Адреса для тесту'),html.index('Контакти:'))
        self.assertIn('У дворі',html)
        self.assertIn('https://instagram.com/test',html)
        self.assertEqual(self.client.get('/settings?tab=contacts').status_code,200)
        self.user = {'Role':'manager'}
        self.assertEqual(self.client.post('/settings/contacts',data=values).status_code,302)
        values['instagram'] = 'javascript:alert(1)'
        self.user = {'Role':'admin'}
        self.assertEqual(self.client.post('/settings/contacts',data=values).status_code,400)

    def test_shared_blocks_background_and_editor_last(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertLess(html.index('content-blocks site-blocks'), html.index('id="page-editor"'))
        self.assertIn('ознайомлювальних цілей', html)
        shared = pc.site_blocks(pc.read_content(), {'MAP_URL':'https://maps.google.com/',
                                                   'MAP_EMBED_URL':'https://www.google.com/maps?q=test&output=embed'})
        shared[0]['nodes'][1]['nodes'][0]['nodes'][0]['value']['text'] = 'Нова адреса'
        shared[0]['nodes'][1]['nodes'][0]['nodes'][3]['value']['text'] = 'Пн: 11–19'
        shared[1]['nodes'].append({'kind':'text','value':{'text':'Нові контакти'}})
        shared[2]['nodes'][0]['value']['text'] = 'Власний текст унизу'
        shared[2]['nodes'].append({'kind':'background','value':{'color':'#abcdef','image':'/static/pattern.png','mode':'tile'}})
        form = {'csrf':'test-csrf','page_path':'/','page_title':'Головна','blocks':'[]',
                'site_blocks':json.dumps(shared),
                'site_background':json.dumps({'image':'/static/site-pattern.png','mode':'tile'})}
        self.assertEqual(self.client.post('/content/save',data=form).status_code,200)
        html = self.client.get('/?preview=public').get_data(as_text=True)
        for value in ('Нова адреса','Пн: 11–19','Нові контакти','Власний текст унизу','/static/site-pattern.png','background-repeat:repeat','background-color:#abcdef'):
            self.assertIn(value, html)
        self.assertNotIn('id="page-editor"', html)
        self.assertNotIn('ознайомлювальних цілей', html)
        self.assertEqual(pc.read_content()['site_background']['mode'],'tile')
        form['site_blocks'] = '[]'
        self.assertEqual(self.client.post('/content/save',data=form).status_code,200)
        self.assertEqual(pc.site_blocks(pc.read_content(),{}),[])
        html = self.client.get('/').get_data(as_text=True)
        self.assertNotIn('Нова адреса',html)
        self.assertNotIn('Власний текст унизу',html)

    def test_background_rejects_css_and_script_injection_atomically(self):
        for raw in ({'color':'red;background:red'}, {'image':'javascript:alert(1)'}, {'color':'#12345'}):
            with self.subTest(raw=raw):
                response = self.client.post('/content/save',data={
                    'csrf':'test-csrf','page_path':'/','page_title':'Зміна','blocks':'[]',
                    'site_background':json.dumps(raw)})
                self.assertEqual(response.status_code,400)
                self.assertFalse(pc.CONTENT_PATH.exists())

    def test_invalid_save_and_permissions(self):
        for data in ['not JSON', '{}', '[{"layout":"unknown"}]', '[{"layout":"text","items":[{"text":{"url":"javascript:alert(1)"}}]}]']:
            response = self.client.post('/content/save', data={'csrf':'test-csrf','page_path':'/','page_title':'Тест','blocks':data})
            self.assertEqual(response.status_code, 400)
        self.assertFalse(pc.CONTENT_PATH.exists())
        self.assertEqual(self.client.post('/content/save', data={'page_path':'/'}).status_code, 400)
        self.user = None
        self.assertEqual(self.client.post('/content/save').status_code, 302)
        self.assertEqual(self.client.get('/services/unknown').status_code, 404)

    def test_creation_collision_edit_and_preservation(self):
        first = pc.save_service_metadata('section',1,'Пірсинг','Опис', {'page_action':'open', 'image_position':'right'})
        self.assertEqual(first, '/services/pirsing')
        second = pc.save_service_metadata('card',2,'Пірсинг','Інший опис', {'page_action':'open'})
        self.assertEqual(second, '/services/pirsing-2')
        self.assertEqual(self.client.get(first).status_code, 200)
        pc.update_content(lambda content: content['pages'][first].update(title='Ручна назва'))
        self.assertEqual(pc.save_service_metadata('section',1,'Нова назва','Опис', {'page_action':'open'}),first)
        self.assertEqual(pc.read_content()['pages'][first]['title'],'Ручна назва')
        self.assertEqual(pc.read_content()['services']['section-1']['title_url'], first)

    def test_service_edit_saves_database_then_page(self):
        cursor = Mock()
        cursor.fetchone.return_value = {'ImageUrl':'/static/original.png'}
        @contextmanager
        def fake_cursor(commit=False):
            yield cursor
        self.module.db_cursor = fake_cursor
        response = self.client.post('/services/item/section/8/edit', data={'title':'Пірсинг','description':'Оновлений опис','image_position':'right','page_action':'open'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/services/pirsing#page-editor')
        update = [call for call in cursor.execute.call_args_list if call.args[0].startswith('UPDATE')][0]
        self.assertEqual(update.args[1], ('Пірсинг','Оновлений опис','/static/original.png',8))
        metadata = pc.read_content()['services']['section-8']
        self.assertEqual(metadata['image_position'],'right')
        self.assertEqual(metadata['title_url'],'/services/pirsing')

    def test_code_multiline_and_admin_only(self):
        response = self.client.get('/settings/code')
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            csrf = session['code_csrf']
        code = '<script>\n// # comment\nconsole.log("ok");\n</script>'
        self.assertEqual(self.client.post('/settings/code',data={'csrf':csrf,'head':code,'body_end':'<!-- footer -->'}).status_code,302)
        self.assertIn(code,self.client.get('/').get_data(as_text=True))
        self.assertEqual(pc.read_content()['global_code']['head'],code)
        self.user = {'Role':'manager'}
        self.assertEqual(self.client.get('/settings/code').status_code,302)

    def test_maintenance_stays_enabled(self):
        self.module.load_config = lambda: {'SITE_MAINTENANCE_ENABLED':'1'}
        self.user = None
        response = self.client.get('/')
        self.assertEqual(response.status_code,503)
        self.assertIn(pc.DEFAULT_CODE,response.get_data(as_text=True))
        self.assertNotIn('id="page-editor"',response.get_data(as_text=True))

    def test_metadata_and_services_render(self):
        section = {'Id':1,'Title':'Пірсинг','Description':'Опис','ImageUrl':'/static/test.png','IsActive':True}
        card = {'Id':2,'SectionId':1,'Title':'Вухо','ShortDescription':'Опис','ImageUrl':'','PriceText':'100 грн','IsActive':True}
        cursor = Mock()
        cursor.fetchall.side_effect = [[section],[card]]
        @contextmanager
        def fake_cursor(commit=False):
            yield cursor
        self.module.db_cursor = fake_cursor
        pc.save_service_metadata('section',1,'Пірсинг','Опис', {'page_action':'open','image_position':'right'})
        response = self.client.get('/services')
        self.assertEqual(response.status_code,200)
        html = response.get_data(as_text=True)
        self.assertIn('service-section-head image-right',html)
        self.assertIn('href="/services/pirsing"',html)
        self.assertIn('Edit Page',html)


if __name__ == '__main__':
    unittest.main()
