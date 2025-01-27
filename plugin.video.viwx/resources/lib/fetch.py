# ----------------------------------------------------------------------------------------------------------------------
#  Copyright (c) 2022-2023 Dimitri Kroon.
#  This file is part of plugin.video.viwx.
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt
# ----------------------------------------------------------------------------------------------------------------------

import os
import logging
import requests
import pickle
import time
from requests.cookies import RequestsCookieJar
import json

from codequick import Script
from codequick.support import logger_id

from resources.lib.errors import *
from resources.lib import utils


WEB_TIMEOUT = (3.5, 7)
USER_AGENT = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/118.0'


logger = logging.getLogger('.'.join((logger_id, __name__.split('.', 2)[-1])))


class PersistentCookieJar(RequestsCookieJar):
    def __init__(self, filename, policy=None):
        RequestsCookieJar.__init__(self, policy)
        self.filename = filename
        self._has_changed = False

    def save(self):
        if not self._has_changed:
            return
        self.clear_expired_cookies()
        self._has_changed = False
        with open(self.filename, 'wb') as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("Saved cookies to file %s", self.filename)

    def set_cookie(self, cookie, *args, **kwargs):
        super(PersistentCookieJar, self).set_cookie(cookie, *args, **kwargs)
        logger.debug("Cookiejar sets cookie %s for %s%s to %s", cookie.name, cookie.domain, cookie.path, cookie.value)
        self._has_changed |= cookie.name != 'hdntl'

    def clear(self, domain=None, path=None, name=None) -> None:
        try:
            super(PersistentCookieJar, self).clear(domain, path, name)
            logger.debug("Cookies cleared for domain: %s, path: %s, name %s", domain, path, name)
            self._has_changed = True
        except KeyError:
            logger.debug("No cookies to clear for domain: %s, path: %s, name: %s ", domain, path, name)
            pass


class HttpSession(requests.sessions.Session):
    instance = None

    def __new__(cls):
        if cls.instance is None:
            cls.instance = super(HttpSession, cls).__new__(cls)
        return cls.instance

    def __init__(self):
        if hasattr(self, 'cookies'):
            # prevent re-initialization when __new__ returns an existing instance
            return

        super(HttpSession, self).__init__()
        self.headers.update({
            'User-Agent': USER_AGENT,
            'Origin': 'https://www.itv.com',
            'Referer': 'https://www.itv.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        })
        self.cookies = _create_cookiejar()

    # noinspection PyShadowingNames
    def request(
            self, method, url,
            params=None, data=None, headers=None, cookies=None, files=None,
            auth=None, timeout=None, allow_redirects=True, proxies=None,
            hooks=None, stream=None, verify=None, cert=None, json=None):

        resp = super(HttpSession, self).request(
                method, url,
                params=params, data=data, headers=headers, cookies=cookies, files=files,
                auth=auth, timeout=timeout, allow_redirects=allow_redirects, proxies=proxies,
                hooks=hooks, stream=stream, verify=verify, cert=cert, json=json)

        # noinspection PyUnresolvedReferences
        self.cookies.save()
        return resp


def _create_cookiejar():
    """Restore a cookiejar from file. If the file does not exist create new one and
    apply the default cookies.

    """
    cookie_file = os.path.join(utils.addon_info.profile, 'cookies')

    try:
        with open(cookie_file, 'rb') as f:
            # TODO: handle expired consent cookies
            cj = pickle.load(f)
            # The internally stored filename of the saved file may be different to the current filename
            # if the file has been copied from another system.
            cj.filename = cookie_file
            logger.info("Restored cookies from file")
    except (FileNotFoundError, pickle.UnpicklingError):
        cj = set_default_cookies(PersistentCookieJar(cookie_file))
        logger.info("Created new cookiejar")
    return cj


def set_default_cookies(cookiejar: RequestsCookieJar = None):
    """Make a request to reject all cookies.

    Ironically, the response sets third-party cookies to store that data.
    Because of that they are rejected by requests, so the cookies are added
    manually to the cookiejar.

    Return the cookiejar

    """
    # noinspection PyBroadException
    try:
        s = requests.Session()
        if isinstance(cookiejar, RequestsCookieJar):
            s.cookies = cookiejar
        elif cookiejar is not None:
            raise ValueError("Parameter cookiejar must be an instance of RequestCookiejar")

        # Make a request to reject all cookies.
        resp = s.get(
            'https://identityservice.syrenis.com/Home/SaveConsent',
            params={'accessKey': '213aea86-31e5-43f3-8d6b-e01ba0d420c7',
                    'domain': '*.itv.com',
                    'consentedCookieIds': [],
                    'cookieFormConsent': '[{"FieldID":"s122_c113","IsChecked":0},{"FieldID":"s135_c126","IsChecked":0},'
                                         '{"FieldID":"s134_c125","IsChecked":0},{"FieldID":"s138_c129","IsChecked":0},'
                                         '{"FieldID":"s157_c147","IsChecked":0},{"FieldID":"s136_c127","IsChecked":0},'
                                         '{"FieldID":"s137_c128","IsChecked":0}]',
                    'runFirstCookieIds': '[]',
                    'privacyCookieIds': '[]',
                    'custom1stPartyData': '[]',
                    'privacyLink': '1'},
            headers={'User-Agent': USER_AGENT,
                     'Accept': 'application/json',
                     'Origin': 'https://www.itv.com/',
                     'Referer': 'https://www.itv.com/'},
            timeout=WEB_TIMEOUT
        )
        s.close()
        resp.raise_for_status()
        consent = resp.json()['CassieConsent']
        cookie_data = json.loads(consent)
        jar = s.cookies

        std_cookie_args = {'domain': '.itv.com', 'expires': time.time() + 3650 * 86400, 'discard': False}
        for cookie_name, cookie_value in cookie_data.items():
            jar.set(cookie_name, cookie_value, **std_cookie_args)
        logger.info("updated cookies consent")

        # set other cookies
        import uuid
        jar.set('Itv.Cid', str(uuid.uuid4()), **std_cookie_args)
        jar.set('Itv.Region', 'ITV|null', **std_cookie_args)
        jar.set("Itv.ParentalControls", '{"active":false,"pin":null,"question":null,"answer":null}', **std_cookie_args)
        return jar
    except:
        logger.error("Unexpected exception while updating cookie consent", exc_info=True)
        return cookiejar


def web_request(method, url, headers=None, data=None, **kwargs):
    http_session = HttpSession()
    kwargs.setdefault('timeout', WEB_TIMEOUT)
    logger.debug("Making %s request to %s", method, url)
    try:
        resp = http_session.request(method, url, json=data, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp
    except requests.HTTPError as e:
        # noinspection PyUnboundLocalVariable
        logger.info("HTTP error %s for url %s: '%s'",
                    e.response.status_code,
                    url,
                    resp.content[:500] if resp.content is not None else '')

        if 400 <= e.response.status_code < 500:
            # noinspection PyBroadException
            try:
                resp_data = resp.json()
            except:
                # Intentional broad exception as requests can raise various types of errors
                # depending on python, etc.
                pass
            else:
                if resp_data.get('error') in ('invalid_grant', 'invalid_request'):
                    descr = resp_data.get("error_description", 'Login failed')
                    raise AuthenticationError(descr)
                # Errors from https://magni.itv.com/playlist/itvonline:
                if 'User does not have entitlements' in resp_data.get('Message', ''):
                    raise AccessRestrictedError()
                if 'Outside Of Allowed Geographic Region' in resp_data.get('Message', ''):
                    raise GeoRestrictedError

        if e.response.status_code == 401:
            raise AuthenticationError()
        else:
            resp = e.response
            raise HttpError(resp.status_code, resp.reason) from None
    except requests.RequestException as e:
        logger.error('Error connecting to %s: %r', url, e)
        raise FetchError(str(e)) from None
    finally:
        http_session.close()


def post_json(url, data, headers=None, **kwargs):
    """Post JSON data and expect JSON data back."""
    dflt_headers = {'Accept': 'application/json'}
    if headers:
        dflt_headers.update(headers)
    resp = web_request('POST', url, dflt_headers, data, **kwargs)
    try:
        return resp.json()
    except json.JSONDecodeError:
        raise FetchError(Script.localize(30920))


def get_json(url, headers=None, **kwargs):
    """Make a GET reguest and expect JSON data back."""
    dflt_headers = {'Accept': 'application/json'}
    if headers:
        dflt_headers.update(headers)
    resp = web_request('GET', url, dflt_headers, **kwargs)
    if resp.status_code == 204:     # No Content
        return None
    try:
        return resp.json()
    except json.JSONDecodeError:
        raise FetchError(Script.localize(30920))


def put_json(url, data, headers=None, **kwargs):
    """PUT JSON data and return the HTTP response, which can be inspected by the
    caller for status, etc."""
    resp = web_request('PUT', url, headers, data, **kwargs)
    return resp


def get_document(url, headers=None, **kwargs):
    """GET any document. Expects the document to be UTF-8 encoded and returns
    the contents as string.
    It may be necessary to provide and 'Accept' header.
    """
    resp = web_request('GET', url, headers, **kwargs)
    resp.encoding = 'utf8'
    return resp.text
