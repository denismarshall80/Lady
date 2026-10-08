import csv
import io
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from test_page_content import isolated_app
from Utils import site_log as sl
from Utils import myfunct as mf


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_writer = mf.LogWriter
        self.module = isolated_app()
        self.module.PPath = str(self.root)
        self.module.db_cursor = Mock(side_effect=AssertionError('Real DB forbidden'))
        self.module.load_config = lambda: {'ONLINE_APPOINTMENT_ENABLED': '0'}
        self.module.current_user = lambda: {'Login': 'denis', 'Role': 'admin'}
        self.module.total_visit_count = lambda: 0
        self.module.total_appointment_count = lambda: 0
        self.module.record_page_visit = lambda: None
        self.client = self.module.app.test_client()

    def tearDown(self):
        mf.LogWriter = self.old_writer
        self.temp.cleanup()

    def test_audit_and_system_use_same_csv_without_mysql(self):
        details = 'Text, "quoted"\nSecond line' + 'x' * 1500
        with self.module.app.test_request_context('/', headers={'X-Forwarded-For': '203.0.113.8'}):
            self.module.session['login'] = 'denis'
            self.module.log_action('page_update', details)
            mf.tolog('Очищення логів: видалено 0 файлів старіше 10 днів')
        files = list((self.root / 'logs').glob('*.csv'))
        self.assertEqual(len(files), 1)
        rows = sl.read_rows(files[0])
        self.assertEqual(rows[0]['Деталі'], details)
        self.assertEqual(rows[0]['Користувач'], 'denis')
        self.assertEqual(rows[1]['Користувач'], 'Я (сайт)')
        self.assertEqual(rows[1]['Дія'], 'Очищення логів')
        self.assertEqual(rows[1]['IP'], '203.0.113.8')
        self.module.db_cursor.assert_not_called()
        self.assertFalse(list((self.root / 'logs').glob('*.log')))

    def test_background_log_has_server_ip(self):
        with patch.object(sl, 'system_ip', return_value='192.0.2.5'):
            mf.tolog('Background job')
        row = sl.read_rows(next((self.root / 'logs').glob('*.csv')))[0]
        self.assertEqual(row['Користувач'], 'Я (сайт)')
        self.assertEqual(row['IP'], '192.0.2.5')

    def test_parallel_writes_preserve_header_and_all_rows(self):
        when = datetime(2026, 10, 8, 12)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: sl.write_event(self.root, 'event', str(i), when=when), range(80)))
        rows = sl.read_rows(sl.log_path(self.root, '2026-10-08'))
        self.assertEqual(len(rows), 80)
        self.assertEqual({row['Деталі'] for row in rows}, {str(i) for i in range(80)})

    def test_old_text_and_db_merge_without_duplicates_or_truncation(self):
        day = '2026-10-08'
        folder = self.root / 'logs'
        folder.mkdir()
        full = 'x' * 1300
        legacy = folder / f'{day}.log'
        legacy.write_text('2026/10/08 08:00:00 AUDIT action=page_update actor=denis ip=203.0.113.8 details=' + full[:1000] + '\n2026/10/08 08:38:19 Очищення логів: видалено 0 файлів старіше 10 днів\n', encoding='utf-8')
        cursor = Mock()
        cursor.fetchall.return_value = [{'CreatedAt': datetime(2026, 10, 8, 8), 'Actor': 'denis', 'Action': 'page_update', 'Details': full, 'Ip': '203.0.113.8'}]
        @contextmanager
        def old_db():
            yield cursor
        self.module.db_cursor = old_db
        rows = self.module.load_journal(day)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['Деталі'], full)
        self.assertEqual(len(self.module.load_journal(day)), 2)
        self.assertTrue(legacy.exists())
        self.assertTrue(cursor.execute.call_args.args[0].startswith('SELECT'))

    def test_view_and_zip_use_csv_and_selected_day(self):
        sl.write_event(self.root, 'first', 'First day', when=datetime(2026, 10, 8, 10))
        sl.write_event(self.root, 'second', 'Second day', when=datetime(2026, 10, 9, 10))
        response = self.client.get('/logs?date=2026-10-08')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('First day', html)
        self.assertNotIn('Second day', html)
        self.assertNotIn('AuditLog', html)
        response = self.client.get('/logs/download/range?start_date=2026-10-08&end_date=2026-10-09')
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(archive.namelist(), ['Lady_2026-10-08_log.csv', 'Lady_2026-10-09_log.csv'])
            rows = list(csv.DictReader(io.StringIO(archive.read(archive.namelist()[0]).decode('utf-8-sig'))))
            self.assertEqual(rows[0]['Деталі'], 'First day')
        self.module.db_cursor.assert_not_called()

    def test_cleanup_removes_only_old_named_csv_logs(self):
        today = datetime.now()
        old = sl.write_event(self.root, 'old', when=today - timedelta(days=30))
        recent = sl.write_event(self.root, 'recent', when=today)
        unrelated = old.parent / 'manual.csv'
        unrelated.write_text('keep', encoding='utf-8')
        self.assertEqual(mf.ClearOldLog(str(old.parent), 10), 1)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(unrelated.exists())


if __name__ == '__main__':
    unittest.main()
