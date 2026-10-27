import io
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

from test_page_content import isolated_app
from Utils import database, page_content as pc, site_log as sl
from Utils.migrate_storage import import_database
from unittest.mock import Mock, patch


class SQLiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.module = isolated_app()
        self.module.PPath = str(self.root)
        self.module.CONFIG_PATH = str(self.root / 'LadySite.config')
        self.module.load_config = lambda: {'SQLITE_PATH':'lady.db','ONLINE_APPOINTMENT_ENABLED':'0'}
        self.module.ensure_schema()
        self.client = self.module.app.test_client()
        self.content_patch = patch.object(pc, 'CONTENT_PATH', self.root / 'pages.json')
        self.content_patch.start()
        self.password_hash = generate_password_hash('test-password')
        with self.module.db_cursor(commit=True) as cur:
            cur.execute('INSERT INTO Users(Login,Pass,Role) VALUES(?,?,?)',('tester',self.password_hash,'admin'))

    def tearDown(self):
        self.content_patch.stop()
        self.temp.cleanup()

    def test_authentication_navigation_and_password_not_returned(self):
        response = self.client.post('/login', data={'login':'tester','password':'test-password'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.headers['Location'],'/')
        html = self.client.get('/').get_data(as_text=True)
        self.assertNotIn('>Записи</a>',html)
        self.assertNotIn('>Відвідини сайту</a>',html)
        self.assertNotIn('>Користувачі</a>',html)
        self.assertIn('href="/admin/visits"',html)
        settings = self.client.get('/settings').get_data(as_text=True)
        self.assertNotIn('MySQL',settings)
        self.assertIn('href="/settings/users"',settings)
        self.assertEqual(self.client.get('/settings/users').status_code,200)
        self.assertEqual(self.client.get('/admin/visits').status_code,200)
        self.client.get('/logout')
        html = self.client.get('/login').get_data(as_text=True)
        self.assertNotIn('test-password',html)
        self.assertNotIn(self.password_hash,html)
        with self.module.db_cursor(commit=True) as cur:
            cur.execute('UPDATE Users SET IsBlocked=1 WHERE Login=?',('tester',))
        self.client.post('/login',data={'login':'tester','password':'test-password'})
        self.assertEqual(self.client.get('/settings').status_code,302)

    def test_visits_distinct_counts_dates_and_transaction_rollback(self):
        now = datetime.now()
        self.module.load_config = lambda: {'SQLITE_PATH':'lady.db','VISITOR_PERIOD_VALUE':'7','VISITOR_PERIOD_UNIT':'days'}
        with self.module.db_cursor(commit=True) as cur:
            for key, when in [('a',now),('a',now-timedelta(days=1)),('b',now-timedelta(days=30)),('future',now+timedelta(days=1))]:
                cur.execute('INSERT INTO PageVisits(VisitorKey,Path,CreatedAt) VALUES(?,?,?)',(key,'/',when))
        self.assertEqual(self.module.total_visit_count(),1)
        self.assertEqual(self.module.all_time_visit_count(),2)
        with self.assertRaises(RuntimeError):
            with self.module.db_cursor(commit=True) as cur:
                cur.execute('DELETE FROM Users')
                raise RuntimeError('rollback')
        with self.module.db_cursor() as cur:
            cur.execute('SELECT Pass FROM Users WHERE Login=?',('tester',))
            self.assertEqual(cur.fetchone()['Pass'],self.password_hash)

    def test_footer_summary_distinct_periods_and_api_cache(self):
        now = datetime(2026,10,27,12)
        with self.module.db_cursor(commit=True) as cur:
            for key, when in [('a',datetime(2026,10,26,23,59)),('a',datetime(2026,10,27)),
                              ('b',datetime(2026,10,26)),('c',datetime(2026,10,1)),
                              ('d',datetime(2026,1,1)),('e',datetime(2025,12,31)),
                              ('future',datetime(2026,10,27,13))]:
                cur.execute('INSERT INTO PageVisits(VisitorKey,Path,CreatedAt) VALUES(?,?,?)',(key,'/',when))
        summary = self.module.read_visit_summary(now)
        self.assertEqual(summary,{'yesterday':2,'today':1,'month':3,'year':4,'total':5,'month_number':10,'year_number':2026})
        self.module.read_visit_summary = Mock(return_value=summary)
        for _ in range(2):
            response = self.client.get('/api/visits/summary')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json,summary)
            self.assertIn('max-age=30',response.headers['Cache-Control'])
        self.module.read_visit_summary.assert_called_once()
        self.module.current_user = lambda: None
        self.module.record_page_visit = lambda: None
        self.module.total_visit_count = Mock(side_effect=AssertionError('Footer counts must load in browser'))
        self.module.all_time_visit_count = self.module.total_visit_count
        self.assertEqual(self.client.get('/login').status_code,200)
        self.module.total_visit_count.assert_not_called()

    def test_appointments_datetime_and_notifications_flags(self):
        visit = datetime(2026,11,1,10,30)
        with self.module.db_cursor(commit=True) as cur:
            cur.execute('INSERT INTO Appointments(VisitAt,ClientName,VisitPurpose) VALUES(?,?,?)',(visit,'Клієнт','Консультація'))
        with self.module.db_cursor() as cur:
            cur.execute('SELECT * FROM Appointments')
            row = cur.fetchone()
        self.assertEqual(row['VisitAt'],visit)
        self.assertIsInstance(row['create_at'],datetime)
        self.assertEqual(row['SendNow'],0)
        self.assertIn('01.11.2026 о 10:30',self.module.build_appointment_text(row,'Запис'))

    def test_migration_preserves_hashes_ids_and_refuses_overwrite(self):
        snapshot = {'Users':[{'Login':'old','Pass':self.password_hash,'Role':'admin','IsBlocked':1,'ActiveSessionId':'session-preserved'}],
                    'PageVisits':[{'Id':42,'VisitorKey':'visitor','Path':'/services','CreatedAt':'2026-10-26 10:00:00'}]}
        target = self.root / 'import.db'
        import_database(snapshot,target)
        conn = database.connect(target)
        self.assertEqual(conn.execute('SELECT * FROM Users').fetchone()['Pass'],self.password_hash)
        self.assertEqual(conn.execute('SELECT * FROM Users').fetchone()['ActiveSessionId'],'session-preserved')
        self.assertEqual(conn.execute('SELECT * FROM PageVisits').fetchone()['Id'],42)
        self.assertEqual(conn.execute('SELECT * FROM PageVisits').fetchone()['CreatedAt'],datetime(2026,10,26,10))
        conn.close()
        with self.assertRaises(ValueError):
            import_database(snapshot,target)

    def test_log_month_and_custom_zip_select_same_rows(self):
        self.module.current_user = lambda: {'Login':'tester','Role':'admin'}
        sl.write_event(self.root,'one','October',when=datetime(2026,10,1))
        sl.write_event(self.root,'two','November',when=datetime(2026,11,1))
        response = self.client.get('/logs?period=month&month=2026-10')
        self.assertEqual(response.status_code,200)
        html = response.get_data(as_text=True)
        self.assertIn('October',html)
        self.assertNotIn('November',html)
        self.assertLess(html.index('Завантажити ZIP'),html.index('log-filename'))
        response = self.client.get('/logs/download/range?period=custom&start_date=2026-10-01&end_date=2026-10-01')
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(archive.namelist(),['Lady_2026-10-01_log.csv'])
        self.assertEqual(self.client.get('/logs?period=custom&start_date=2026-11-02&end_date=2026-11-01').status_code,400)


if __name__ == '__main__':
    unittest.main()
