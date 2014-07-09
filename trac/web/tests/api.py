# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os.path
import shutil
import tempfile
import unittest
from StringIO import StringIO

from trac import perm
from trac.test import EnvironmentStub, Mock, locale_en
from trac.util import create_file
from trac.util.datefmt import utc
from trac.web.api import Request, RequestDone, parse_arg_list
from tracopt.perm.authz_policy import AuthzPolicy


class RequestHandlerPermissionsTestCaseBase(unittest.TestCase):

    authz_policy = None

    def setUp(self, module_class):
        self.path = tempfile.mkdtemp(prefix='trac-')
        if self.authz_policy is not None:
            self.authz_file = os.path.join(self.path, 'authz_policy.conf')
            create_file(self.authz_file, self.authz_policy)
            self.env = EnvironmentStub(enable=['trac.*', AuthzPolicy],
                                       path=self.path)
            self.env.config.set('authz_policy', 'authz_file', self.authz_file)
            self.env.config.set('trac', 'permission_policies',
                                'AuthzPolicy, DefaultPermissionPolicy')
        else:
            self.env = EnvironmentStub(path=self.path)
        self.req_handler = module_class(self.env)

    def tearDown(self):
        self.env.reset_db()
        shutil.rmtree(self.path)

    def create_request(self, authname='anonymous', **kwargs):
        kw = {'perm': perm.PermissionCache(self.env, authname), 'args': {},
              'href': self.env.href, 'abs_href': self.env.abs_href,
              'tz': utc, 'locale': None, 'lc_time': locale_en,
              'chrome': {'notices': [], 'warnings': []},
              'method': None, 'get_header': lambda v: None}
        kw.update(kwargs)
        return Mock(**kw)

    def get_navigation_items(self, req):
        return self.req_handler.get_navigation_items(req)

    def grant_perm(self, username, *actions):
        permsys = perm.PermissionSystem(self.env)
        for action in actions:
            permsys.grant_permission(username, action)

    def process_request(self, req):
        self.assertTrue(self.req_handler.match_request(req))
        return self.req_handler.process_request(req)


class RequestTestCase(unittest.TestCase):

    def _make_environ(self, scheme='http', server_name='example.org',
                      server_port=80, method='GET', script_name='/trac',
                      **kwargs):
        environ = {'wsgi.url_scheme': scheme, 'wsgi.input': StringIO(''),
                   'REQUEST_METHOD': method, 'SERVER_NAME': server_name,
                   'SERVER_PORT': server_port, 'SCRIPT_NAME': script_name}
        environ.update(kwargs)
        return environ

    def test_base_url(self):
        environ = self._make_environ()
        req = Request(environ, None)
        self.assertEqual('http://example.org/trac', req.base_url)

    def test_base_url_host(self):
        environ = self._make_environ(server_port=8080, HTTP_HOST='example.com')
        req = Request(environ, None)
        self.assertEqual('http://example.com/trac', req.base_url)

    def test_base_url_nondefaultport(self):
        environ = self._make_environ(server_port=8080)
        req = Request(environ, None)
        self.assertEqual('http://example.org:8080/trac', req.base_url)

    def test_base_url_https(self):
        environ = self._make_environ(scheme='https', server_port=443)
        req = Request(environ, None)
        self.assertEqual('https://example.org/trac', req.base_url)

    def test_base_url_https_host(self):
        environ = self._make_environ(scheme='https', server_port=443,
                                     HTTP_HOST='example.com')
        req = Request(environ, None)
        self.assertEqual('https://example.com/trac', req.base_url)

    def test_base_url_https_nondefaultport(self):
        environ = self._make_environ(scheme='https', server_port=8443)
        req = Request(environ, None)
        self.assertEqual('https://example.org:8443/trac', req.base_url)

    def test_base_url_proxy(self):
        environ = self._make_environ(HTTP_HOST='localhost',
                                     HTTP_X_FORWARDED_HOST='example.com')
        req = Request(environ, None)
        self.assertEqual('http://localhost/trac', req.base_url)

    def test_languages(self):
        environ = self._make_environ()
        environ['HTTP_ACCEPT_LANGUAGE'] = 'en-us,en;q=0.5'
        req = Request(environ, None)
        self.assertEqual(['en-us', 'en'], req.languages)

    def test_redirect(self):
        status_sent = []
        headers_sent = {}
        def start_response(status, headers):
            status_sent.append(status)
            headers_sent.update(dict(headers))
        environ = self._make_environ(method='HEAD')
        req = Request(environ, start_response)
        req.session = Mock(save=lambda: None)
        self.assertRaises(RequestDone, req.redirect, '/trac/test')
        self.assertEqual('302 Found', status_sent[0])
        self.assertEqual('http://example.org/trac/test',
                         headers_sent['Location'])

    def test_redirect_absolute(self):
        status_sent = []
        headers_sent = {}
        def start_response(status, headers):
            status_sent.append(status)
            headers_sent.update(dict(headers))
        environ = self._make_environ(method='HEAD')
        req = Request(environ, start_response,)
        req.session = Mock(save=lambda: None)
        self.assertRaises(RequestDone, req.redirect,
                          'http://example.com/trac/test')
        self.assertEqual('302 Found', status_sent[0])
        self.assertEqual('http://example.com/trac/test',
                         headers_sent['Location'])

    def test_write_unicode(self):
        buf = StringIO()
        def write(data):
            buf.write(data)
        def start_response(status, headers):
            return write
        environ = self._make_environ(method='HEAD')

        req = Request(environ, start_response)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.send_header('Content-Length', 0)
        # anyway we're not supposed to send unicode, so we get a ValueError
        self.assertRaises(ValueError, req.write, u'Föö')

    def test_invalid_cookies(self):
        environ = self._make_environ(HTTP_COOKIE='bad:key=value;')
        req = Request(environ, None)
        self.assertEqual('', str(req.incookie))

    def test_multiple_cookies(self):
        environ = self._make_environ(HTTP_COOKIE='key=value1; key=value2;')
        req = Request(environ, None)
        self.assertEqual('Set-Cookie: key=value1',
                         str(req.incookie).rstrip(';'))

    def test_read(self):
        environ = self._make_environ(**{'wsgi.input': StringIO('test input')})
        req = Request(environ, None)
        self.assertEqual('test input', req.read())

    def test_read_size(self):
        environ = self._make_environ(**{'wsgi.input': StringIO('test input')})
        req = Request(environ, None)
        self.assertEqual('test', req.read(size=4))

    def test_qs_on_post(self):
        """Make sure req.args parsing is consistent even after the backwards
        incompatible change introduced in Python 2.6.
        """
        environ = self._make_environ(method='GET',
                                     **{'QUERY_STRING': 'action=foo'})
        req = Request(environ, None)
        self.assertEqual('foo', req.args['action'])
        environ = self._make_environ(method='POST',
                                     **{'wsgi.input': StringIO('action=bar'),
                                        'CONTENT_LENGTH': '10',
                                        'CONTENT_TYPE': 'application/x-www-form-urlencoded',
                                        'QUERY_STRING': 'action=foo'})
        req = Request(environ, None)
        self.assertEqual('bar', req.args['action'])


class ParseArgListTestCase(unittest.TestCase):

    def test_qs_str(self):
        args = parse_arg_list('k%C3%A9y=resum%C3%A9&r%C3%A9sum%C3%A9')
        self.assertTrue(unicode, type(args[0][0]))
        self.assertTrue(unicode, type(args[0][1]))
        self.assertEqual(u'kéy', args[0][0])
        self.assertEqual(u'resumé', args[0][1])
        self.assertTrue(unicode, type(args[1][0]))
        self.assertEqual(u'résumé', args[1][0])

    def test_qs_str_with_prefix(self):
        """The leading `?` should be stripped from the query string."""
        args = parse_arg_list('?k%C3%A9y=resum%C3%A9&r%C3%A9sum%C3%A9')
        self.assertTrue(unicode, type(args[0][0]))
        self.assertTrue(unicode, type(args[0][1]))
        self.assertEqual(u'kéy', args[0][0])
        self.assertEqual(u'resumé', args[0][1])
        self.assertTrue(unicode, type(args[1][0]))
        self.assertEqual(u'résumé', args[1][0])

    def test_qs_unicode(self):
        args = parse_arg_list(u'ké%3Dy=re%26su=mé&résu%26mé')
        self.assertTrue(unicode, type(args[0][0]))
        self.assertTrue(unicode, type(args[0][1]))
        self.assertEqual(u'ké=y', args[0][0])
        self.assertEqual(u're&su=mé', args[0][1])
        self.assertTrue(unicode, type(args[1][0]))
        self.assertEqual(u'résu&mé', args[1][0])


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(RequestTestCase))
    suite.addTest(unittest.makeSuite(ParseArgListTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
