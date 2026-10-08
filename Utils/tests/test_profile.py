import io
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

from test_page_content import isolated_app
from Utils import myfunct as mf


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.previous_writer = mf.LogWriter
        self.module = isolated_app()
        self.temp = tempfile.TemporaryDirectory()
        self.module.SERVICE_IMAGE_DIR = self.temp.name
        self.user = {'Login': 'self', 'Role': 'manager', 'FullName': 'Old Name', 'Email': 'old@example.com', 'AvatarUrl': '/static/old.png'}
        self.module.current_user = lambda: self.user
        self.module.load_config = lambda: {'ONLINE_APPOINTMENT_ENABLED': '0'}
        self.module.log_action = Mock()
        self.module.record_page_visit = lambda: None
        self.module.total_visit_count = lambda: 0
        self.module.total_appointment_count = lambda: 0
        self.cursor = Mock()
        self.cursor.fetchone.return_value = {**self.user, 'Pass': self.module.generate_password_hash('old-password')}
        @contextmanager
        def fake_db(commit=False):
            yield self.cursor
        self.module.db_cursor = fake_db
        self.client = self.module.app.test_client()
        with self.client.session_transaction() as session:
            session['login'] = 'self'
            session['profile_csrf'] = 'profile-token'
            session['session_id'] = 'old-session'

    def tearDown(self):
        mf.LogWriter = self.previous_writer
        self.temp.cleanup()

    def submit(self, **data):
        return self.client.post('/profile', data={'csrf': 'profile-token', 'full_name': 'New Name', 'email': 'new@example.com', **data})

    def test_profile_requires_login_and_csrf(self):
        self.assertEqual(self.client.post('/profile', data={}).status_code, 400)
        self.cursor.execute.assert_not_called()
        self.user = None
        self.assertEqual(self.client.get('/profile').status_code, 302)
        self.assertEqual(self.submit().status_code, 302)
        self.cursor.execute.assert_not_called()

    def test_name_email_change_only_own_user_preserves_password_and_avatar(self):
        response = self.submit(login='other', role='admin')
        self.assertEqual(response.status_code, 302)
        updates = [call.args for call in self.cursor.execute.call_args_list if call.args[0].startswith('UPDATE')]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][1], ('New Name', 'new@example.com', '/static/old.png', 'self'))
        self.assertNotIn('Pass=', updates[0][0])
        self.assertNotIn('Role=', updates[0][0])

    def test_password_requires_current_password_and_matching_confirmation(self):
        self.submit(current_password='wrong', new_password='new-password', confirm_password='new-password')
        self.assertFalse(any(call.args[0].startswith('UPDATE') for call in self.cursor.execute.call_args_list))
        self.cursor.reset_mock()
        self.submit(current_password='old-password', new_password='new-password', confirm_password='different')
        self.cursor.execute.assert_not_called()

    def test_password_is_hashed_session_rotates_and_audit_has_no_secrets(self):
        self.submit(current_password='old-password', new_password='new-password', confirm_password='new-password')
        update = next(call for call in self.cursor.execute.call_args_list if call.args[0].startswith('UPDATE Users SET Pass='))
        password_hash, sid, login = update.args[1]
        self.assertTrue(self.module.check_password_hash(password_hash, 'new-password'))
        self.assertEqual(login, 'self')
        with self.client.session_transaction() as session:
            self.assertEqual(session['session_id'], sid)
            self.assertNotEqual(sid, 'old-session')
        audit = self.module.log_action.call_args.args[1]
        self.assertNotIn('old-password', audit)
        self.assertNotIn('new-password', audit)
        self.assertNotIn(password_hash, audit)

    def test_avatar_upload_and_removal(self):
        self.submit(avatar_file=(io.BytesIO(b'\x89PNG\r\n\x1a\n'), 'avatar.png'))
        upload = next(call for call in self.cursor.execute.call_args_list if call.args[0].startswith('UPDATE'))
        url = upload.args[1][2]
        self.assertTrue(url.startswith('/static/service_images/'))
        self.assertTrue((Path(self.temp.name) / url.rsplit('/', 1)[1]).exists())
        self.cursor.reset_mock()
        self.submit(remove_avatar='1')
        update = next(call for call in self.cursor.execute.call_args_list if call.args[0].startswith('UPDATE'))
        self.assertIsNone(update.args[1][2])


if __name__ == '__main__':
    unittest.main()
