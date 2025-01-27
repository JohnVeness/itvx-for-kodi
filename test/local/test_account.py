
# ----------------------------------------------------------------------------------------------------------------------
#  Copyright (c) 2022-2023 Dimitri Kroon.
#  This file is part of plugin.video.viwx.
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt
# ----------------------------------------------------------------------------------------------------------------------

from test.support import fixtures
fixtures.global_setup()

import json
import time
import unittest
from copy import deepcopy
from unittest.mock import patch, mock_open, MagicMock

from resources.lib import errors
from resources.lib import itv_account
from resources.lib import fetch

from test.support.object_checks import has_keys
from test.support.testutils import HttpResponse

# noinspection PyPep8Naming
setUpModule = fixtures.setup_local_tests
tearDownModule = fixtures.tear_down_local_tests


account_data_v0 = {'uname': 'my_uname', 'passw': 'my_passw',
                   "refreshed": time.time(),
                   'itv_session': {'access_token': 'my-token',
                                   'refresh_token': 'my-refresh-token'},
                   'cookies': {'Itv.Cid': 'xxxxxxxxxxxx'}
                   }

account_data_v2 = {
                   'refreshed': account_data_v0['refreshed'],
                   'itv_session': {'access_token': 'my-token',
                                   'refresh_token': 'my-refresh-token'},
                   'cookies': {'Itv.Session': '{"sticky": true, "tokens": {"content": {"access_token": "my-token", '
                                              '"refresh_token": "my-refresh-token"}}}'},
                   'vers': 2
                   }


class TestSession(unittest.TestCase):
    # noinspection PyMethodMayBeStatic
    def test_instantiate_session_class(self):
        sess = itv_account.ItvSession()
        self.assertIsInstance(sess, itv_account.ItvSession)

    @patch('resources.lib.itv_account.open', side_effect=OSError)
    def test_instantiate_session_class_with_missing_data_file(self, _):
        sess = itv_account.ItvSession()
        self.assertIsInstance(sess, itv_account.ItvSession)

    def test_session(self):
        itv_account._session_obj = None
        sess_1 = itv_account.itv_session()
        self.assertIsInstance(sess_1, itv_account.ItvSession)
        sess_2 = itv_account.itv_session()
        self.assertIs(sess_1, sess_2)


@patch("resources.lib.itv_account.ItvSession.save_account_data")
class TestLogin(unittest.TestCase):
    @patch('resources.lib.fetch.post_json', return_value={'access_token': 'new_token', 'refresh_token': 'new_refresh'})
    def test_login_requires_both_uname_and_password(self, _, __):
        ct_sess = itv_account.ItvSession()
        self.assertRaises(TypeError, ct_sess.login)
        self.assertRaises(TypeError, ct_sess.login, uname="my name")
        self.assertRaises(TypeError, ct_sess.login, passw="my password")
        self.assertTrue(ct_sess.login(uname="my name", passw="my password"))

    @patch('resources.lib.fetch.post_json', return_value={'access_token': 'new_token', 'refresh_token': 'new_refresh'})
    def test_login_with_credentials(self, p_post, _):
        ct_sess = itv_account.ItvSession()
        self.assertTrue(ct_sess.login('my_name', 'my_passw'))
        post_kwargs = p_post.call_args[0][1]
        has_keys(post_kwargs, 'username', 'password', 'nonce', 'grant_type', obj_name='post_json kwargs')
        self.assertEqual('my_name', post_kwargs['username'])
        self.assertEqual('my_passw', post_kwargs['password'])
        self.assertEqual(itv_account.SESS_DATA_VERS, ct_sess.account_data['vers'])

    def test_login_encounters_http_errors(self, p_save):
        with patch('resources.lib.fetch.post_json', side_effect=errors.AuthenticationError):
            ct_sess = itv_account.ItvSession()
            p_save.reset_mock()
            self.assertRaises(errors.AuthenticationError, ct_sess.login, 'my name', 'my password')
            p_save.assert_not_called()

        with patch('resources.lib.fetch.post_json', side_effect=errors.HttpError(400, '')):
            ct_sess = itv_account.ItvSession()
            p_save.reset_mock()
            self.assertRaises(errors.AuthenticationError, ct_sess.login, 'my name', 'my password')
            p_save.assert_not_called()

        with patch('resources.lib.fetch.post_json', side_effect=errors.HttpError(401, '')):
            ct_sess = itv_account.ItvSession()
            p_save.reset_mock()
            self.assertRaises(errors.AuthenticationError, ct_sess.login, 'my name', 'my password')
            p_save.assert_not_called()

        with patch('resources.lib.fetch.post_json', side_effect=errors.HttpError(403, '')):
            ct_sess = itv_account.ItvSession()
            p_save.reset_mock()
            self.assertRaises(errors.AuthenticationError, ct_sess.login, 'my name', 'my password')
            p_save.assert_not_called()

        with patch('resources.lib.fetch.post_json', side_effect=errors.HttpError(404, '')):
            ct_sess = itv_account.ItvSession()
            p_save.reset_mock()
            self.assertRaises(errors.HttpError, ct_sess.login, 'my name', 'my password')
            p_save.assert_not_called()

        with patch('resources.lib.fetch.post_json', side_effect=errors.GeoRestrictedError):
            ct_sess = itv_account.ItvSession()
            p_save.reset_mock()
            self.assertRaises(errors.GeoRestrictedError, ct_sess.login, 'my name', 'my password')
            p_save.assert_not_called()


@patch("resources.lib.itv_account.ItvSession.save_account_data")
class Refresh(unittest.TestCase):
    def setUp(self) -> None:
        self.ct_sess = itv_account.ItvSession()
        self.ct_sess.account_data = {'itv_session': {'access_token': '1st_token', 'refresh_token': '1st_refresh'},
                                     'cookies': {'Itv.Cid': 'aaaa-bbbb-11'}
                                     }

    @patch('resources.lib.fetch.get_json', return_value={'access_token': '2nd_token', 'refresh_token': '2nd_refresh'})
    def test_refresh(self, _, p_save):
        self.assertTrue(self.ct_sess.refresh())
        self.assertTrue(p_save.called_once())
        self.assertEqual(self.ct_sess.account_data['itv_session'],
                         {'access_token': '2nd_token', 'refresh_token': '2nd_refresh'})

    def test_refresh_with_http_errors(self, p_save):
        with patch('resources.lib.fetch.get_json', side_effect=errors.HttpError(400, 'Bad request')):
            self.assertFalse(self.ct_sess.refresh())
        with patch('resources.lib.fetch.get_json', side_effect=errors.HttpError(401, 'Unauthorized')):
            self.assertFalse(self.ct_sess.refresh())
        with patch('resources.lib.fetch.get_json', side_effect=errors.HttpError(403, 'Forbidden')):
            self.assertFalse(self.ct_sess.refresh())
        with patch('resources.lib.fetch.get_json', side_effect=errors.HttpError(404, 'Not found')):
            self.assertFalse(self.ct_sess.refresh())
        p_save.assert_not_called()

    @patch('resources.lib.fetch.get_json', return_value={'token': '2nd_token', 'refreshToken': '2nd_refresh'})
    def test_refresh_without_account_data(self, p_post, p_save):
        ct_sess = itv_account.ItvSession()
        p_save.reset_mock()
        ct_sess.account_data = None
        self.assertFalse(ct_sess.refresh())
        p_post.assert_not_called()
        p_save.assert_not_called()


class PropAccessToken(unittest.TestCase):
    @patch('resources.lib.itv_account.ItvSession.login')
    @patch('resources.lib.itv_account.ItvSession.refresh')
    def test_prop_access_token(self, p_refresh, p_login):
        ct_sess = itv_account.ItvSession()
        ct_sess.account_data = account_data_v2
        self.assertEqual(account_data_v2['itv_session']['access_token'], ct_sess.access_token)
        p_refresh.assert_not_called()
        p_login.assert_not_called()

    @patch('resources.lib.itv_account.ItvSession.login')
    @patch('resources.lib.itv_account.ItvSession.refresh', return_value=True)
    def test_prop_access_token_raises_auth_error_on_no_account_data(self, p_refresh, p_login):
        ct_sess = itv_account.ItvSession()
        ct_sess.account_data = None
        with self.assertRaises(errors.AuthenticationError):
            _ = ct_sess.access_token    # TypeError as mocked login does not update account_data
        p_login.assert_not_called()
        p_refresh.assert_not_called()

    @patch('resources.lib.itv_account.ItvSession.login')
    @patch('resources.lib.itv_account.ItvSession.refresh', return_value=True)
    def test_prop_access_token_with_cache_timed_out_invokes_refresh(self, p_refresh, p_login):
        ct_sess = itv_account.ItvSession()
        ct_sess.account_data = deepcopy(account_data_v2)
        ct_sess.account_data['refreshed'] = time.time() - 13 * 3600     # force a timeout
        _ = ct_sess.access_token
        p_login.assert_not_called()
        p_refresh.assert_called_once()


class PropCookie(unittest.TestCase):
    @patch('resources.lib.itv_account.ItvSession.login')
    @patch('resources.lib.itv_account.ItvSession.refresh')
    def test_prop_cookie(self, p_refresh, p_login):
        ct_sess = itv_account.ItvSession()
        ct_sess.account_data = account_data_v2
        self.assertEqual(account_data_v2['cookies'], ct_sess.cookie)
        p_refresh.assert_not_called()
        p_login.assert_not_called()

    @patch('resources.lib.itv_account.ItvSession.login')
    @patch('resources.lib.itv_account.ItvSession.refresh', return_value=True)
    def test_prop_cookie_auth_error_on_no_account_data(self, p_refresh, p_login):
        ct_sess = itv_account.ItvSession()
        ct_sess.account_data = None
        with self.assertRaises(errors.AuthenticationError):
            _ = ct_sess.cookie    # TypeError as mocked login does not update account_data
        p_login.assert_not_called()
        p_refresh.assert_not_called()

    @patch('resources.lib.itv_account.ItvSession.login')
    @patch('resources.lib.itv_account.ItvSession.refresh', return_value=True)
    def test_prop_cookie_with_cache_timed_out_invokes_refresh(self, p_refresh, p_login):
        ct_sess = itv_account.ItvSession()
        ct_sess.account_data = deepcopy(account_data_v2)
        ct_sess.account_data['refreshed'] = time.time() - 13 * 3600     # force a timeout
        _ = ct_sess.cookie
        p_login.assert_not_called()
        p_refresh.assert_called_once()


class Misc(unittest.TestCase):
    def test_read_account_data(self):
        with patch('resources.lib.itv_account.open', mock_open(read_data=json.dumps(account_data_v2))):
            # test data is being read at class instantiation
            ct_sess = itv_account.ItvSession()
            has_keys(ct_sess.account_data, 'itv_session', 'cookies', 'refreshed', 'vers')
            self.assertEqual(account_data_v2, ct_sess.account_data)
            ct_sess.account_data = None
            # test manual read
            ct_sess.read_account_data()
            self.assertEqual(account_data_v2, ct_sess.account_data)
        # Account data file not presents
        with patch('resources.lib.itv_account.open', side_effect=OSError):
            ct_sess.read_account_data()
            self.assertEqual({}, ct_sess.account_data)
        # Account data file is an empty dict, e.g. after logout
        with patch('resources.lib.itv_account.open', mock_open(read_data=json.dumps({})), create=True) as patched_open:
            ct_sess.read_account_data()
            self.assertTrue('vers' in ct_sess.account_data.keys())
            self.assertTrue('cookies' in ct_sess.account_data.keys())
            self.assertFalse('itv_session' in ct_sess.account_data.keys())
            # Check if converted account data has been saved correctly
            data_str = patched_open.return_value.write.call_args[0][0]
            data_written = json.loads(data_str)
            self.assertEqual(itv_account.SESS_DATA_VERS, data_written['vers'])

    def test_read_account_converts_to_new_format(self):
        with patch('resources.lib.itv_account.open', mock_open(read_data=json.dumps(account_data_v0))):
            ct_sess = itv_account.ItvSession()
            has_keys(ct_sess.account_data, 'itv_session', 'cookies', 'refreshed', 'vers')
            self.assertEqual(account_data_v2, ct_sess.account_data)

    def test_save_account_data(self):
        ct_sess = itv_account.ItvSession()
        with patch("resources.lib.itv_account.open") as p_open:
            ct_sess.save_account_data()
            p_open.assert_called_once()
            self.assertGreater(len(p_open.mock_calls), 2)   # at least calls to __enter__, write , __exit__

    @patch("resources.lib.itv_account.ItvSession.save_account_data")
    def test_logout(self, p_save):
        ct_sess = itv_account.ItvSession()
        p_save.reset_mock()
        ct_sess.account_data = {"some data"}
        ct_sess.log_out()
        self.assertEqual(ct_sess.account_data, {})
        p_save.assert_called_once()


class AccountMock:
    access_token = '123abc'

    def __init__(self):
        self.refresh = MagicMock()
        self.login = MagicMock()
        self.cookie = MagicMock()


URL = 'https://mydoc'


class GetAuthenticated(unittest.TestCase):
    @patch("resources.lib.itv_account.itv_session", return_value=AccountMock())
    @patch("resources.lib.fetch.get_json", return_value={'a': 1})
    def test_authenticated_get(self, mocked_get, _):
        resp = itv_account.fetch_authenticated(fetch.get_json, URL)
        self.assertEqual({'a': 1}, resp)
        mocked_get.assert_called_once_with(url=URL, cookies={})

    @patch('resources.lib.settings.login')
    @patch("resources.lib.itv_account.itv_session", return_value=AccountMock())
    @patch("resources.lib.fetch.get_json", side_effect=[errors.AuthenticationError, {'a': 1}])
    def test_authenticated_meets_auth_error_response(self, mocked_get, mocked_account, mocked_login):
        """Refresh tokens on authentication error and try again"""
        resp = itv_account.fetch_authenticated(fetch.get_json, URL)
        mocked_account.return_value.refresh.assert_called_once()
        mocked_login.assert_not_called()
        self.assertEqual(2, mocked_get.call_count)
        self.assertEqual({'a': 1}, resp)

    @patch('resources.lib.settings.login')
    @patch("resources.lib.itv_account.itv_session", return_value=AccountMock())
    @patch('resources.lib.fetch.HttpSession.request',
           return_value=HttpResponse(status_code=403,
                                     content=b'{"Message": "UserTokenValidationFailed for user: Some(92a3bfde-bfe1-'
                                             b'40ea-ad43-09b8b522b7cb) message: User does not have entitlements"}'))
    def test_authenticated_meets_auth_error_no_subscription(self, mocked_get, mocked_account, mocked_login):
        """Caused by trying to play a premium stream without a premium account
        Should raise a AccessRestrictedError without attempts to refresh or login.
        """
        self.assertRaises(errors.AccessRestrictedError, itv_account.fetch_authenticated, fetch.get_json, URL)
        mocked_account.return_value.refresh.assert_not_called()
        mocked_login.login.assert_not_called()
        self.assertEqual(1, mocked_get.call_count)

    @patch('resources.lib.settings.login')
    @patch("resources.lib.itv_account.itv_session", return_value=AccountMock())
    @patch("resources.lib.fetch.get_json", side_effect=[errors.AuthenticationError, {'a': 1}])
    def test_authenticated_refresh_fails_login_succeeds(self, mocked_get, mocked_account, mocked_login):
        """Refresh tokens on authentication error and try again"""
        mocked_account.return_value.refresh.return_value = False

        resp = itv_account.fetch_authenticated(fetch.get_json, URL)
        mocked_account.return_value.refresh.assert_called_once()
        mocked_login.assert_called_once()
        self.assertEqual(2, mocked_get.call_count)
        self.assertEqual({'a': 1}, resp)

    @patch('resources.lib.settings.login')
    @patch("resources.lib.itv_account.itv_session", return_value=AccountMock())
    @patch("resources.lib.fetch.get_json", side_effect=[errors.AuthenticationError, {'a': 1}])
    def test_authenticated_refresh_fails_login_rejectd(self, mocked_get, mocked_account, mocked_login):
        """Refresh tokens failed and the user canceled the request to log in."""
        mocked_account.return_value.refresh.return_value = False
        with patch("resources.lib.kodi_utils.show_msg_not_logged_in", return_value=False):
            self.assertRaises(errors.AuthenticationError, itv_account.fetch_authenticated, fetch.get_json, URL)
        mocked_account.return_value.refresh.assert_called_once()
        mocked_login.login.assert_not_called()
        self.assertEqual(1, mocked_get.call_count)

    @patch("resources.lib.itv_account.itv_session", return_value=AccountMock())
    @patch("resources.lib.fetch.get_json", side_effect=errors.AuthenticationError)
    def test_authenticated_login_fails(self, mocked_get, mocked_account):
        """If refresh and login fail, do not try again"""
        mocked_account.return_value.refresh.return_value = False
        mocked_account.return_value.login.side_effect = errors.AuthenticationError

        with patch("resources.lib.settings.login", return_value=False) as p_login:
            self.assertRaises(errors.AuthenticationError, itv_account.fetch_authenticated, fetch.get_json, URL)
            mocked_account.return_value.refresh.assert_called_once()
            p_login.assert_called_once()
            mocked_get.assert_called_once()

            mocked_account.return_value.refresh.reset_mock()
            mocked_get.reset_mock()
        with patch("resources.lib.settings.login", side_effect=errors.HttpError(500, '')) as p_login:
            self.assertRaises(errors.HttpError, itv_account.fetch_authenticated, fetch.get_json, URL)
            mocked_account.return_value.refresh.assert_called_once()
            p_login.assert_called_once()
            mocked_get.assert_called_once()

    @patch("resources.lib.itv_account.itv_session", return_value=AccountMock())
    @patch("resources.lib.fetch.get_json", side_effect=errors.AuthenticationError)
    def test_authenticated_not_authenticated_even_after_successful_refresh(self, mocked_get, mocked_account):
        self.assertRaises(errors.AccessRestrictedError, itv_account.fetch_authenticated, fetch.get_json, URL)
        mocked_account.return_value.refresh.assert_called_once()
        self.assertEqual(2, mocked_get.call_count)
