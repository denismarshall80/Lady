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
