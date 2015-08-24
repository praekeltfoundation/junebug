import json
import logging
import treq
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from twisted.web import http
from vumi.tests.helpers import PersistenceHelper

from junebug.service import JunebugService


class TestJunebugApi(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.logging_handler = logging.handlers.MemoryHandler(100)
        logging.getLogger().addHandler(self.logging_handler)
        self.persistencehelper = PersistenceHelper()
        yield self.persistencehelper.setup()
        self.redis = yield self.persistencehelper.get_redis_manager()
        yield self.start_server()

    @inlineCallbacks
    def tearDown(self):
        self.logging_handler.close()
        logging.getLogger().removeHandler(self.logging_handler)
        yield self.stop_server()

    @inlineCallbacks
    def start_server(self):
        self.service = JunebugService('localhost', 0, self.redis._config)
        self.server = yield self.service.startService()
        addr = self.server.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

    @inlineCallbacks
    def stop_server(self):
        yield self.service.stopService()

    def get(self, url):
        return treq.get("%s%s" % (self.url, url), persistent=False)

    def post(self, url, data, headers=None):
        return treq.post(
            "%s%s" % (self.url, url),
            json.dumps(data),
            persistent=False,
            headers=headers)

    def delete(self, url):
        return treq.delete("%s%s" % (self.url, url), persistent=False)

    @inlineCallbacks
    def assert_response(self, response, code, description, result, ignore=[]):
        data = yield response.json()
        self.assertEqual(response.code, code)
        for field in ignore:
            data['result'].pop(field)
        self.assertEqual(data, {
            'status': code,
            'code': http.RESPONSES[code],
            'description': description,
            'result': result,
        })

    @inlineCallbacks
    def test_http_error(self):
        resp = yield self.get('/foobar')
        yield self.assert_response(
            resp, http.NOT_FOUND,
            'The requested URL was not found on the server.  If you entered '
            'the URL manually please check your spelling and try again.', {
                'errors': [{
                    'message': '404: Not Found',
                    'type': 'Not Found',
                    }]
                })

    @inlineCallbacks
    def test_get_channel_list(self):
        resp = yield self.get('/channels')
        yield self.assert_response(
            resp, http.INTERNAL_SERVER_ERROR, 'generic error', {
                'errors': [{
                    'message': '',
                    'type': 'NotImplementedError',
                    }]
                })

    @inlineCallbacks
    def test_create_channel(self):
        resp = yield self.post('/channels', {
            'type': 'telnet',
            'config': {
                'transport_name': 'dummy_transport1',
                'twisted_endpoint': 'tcp:0',
            },
            'mo_url': 'http://foo.bar',
        })
        yield self.assert_response(
            resp, http.OK, 'channel created', {
                'config': {
                    'transport_name': 'dummy_transport1',
                    'twisted_endpoint': 'tcp:0',
                },
                'mo_url': 'http://foo.bar',
                'status': {},
                'type': 'telnet',
            }, ignore=['id'])
        # Check that the transport is created with the correct config
        [transport] = self.service.services
        self.assertEqual(transport.parent, self.service)
        self.assertEqual(transport.config, {
            'transport_name': 'dummy_transport1',
            'twisted_endpoint': 'tcp:0',
            })

        # Check that the transport starts up and is listening
        yield transport.setup_transport()
        telnet_server = transport.telnet_server.getHost()
        self.assertEqual(telnet_server.host, '0.0.0.0')
        self.assertEqual(telnet_server.type, 'TCP')
        self.assertTrue(telnet_server.port > 0)
        yield transport.teardown_transport()

    @inlineCallbacks
    def test_create_channel_invalid_parameters(self):
        resp = yield self.post('/channels', {
            'type': 'smpp',
            'config': {},
            'rate_limit_count': -3,
            'character_limit': 'a',
        })
        yield self.assert_response(
            resp, http.BAD_REQUEST, 'api usage error', {
                'errors': [
                    {
                        'message': "'mo_url' is a required property",
                        'type': 'invalid_body',
                    },
                    {
                        'message': '-3 is less than the minimum of 0',
                        'type': 'invalid_body',
                    },
                    {
                        'message': "u'a' is not of type 'integer'",
                        'type': 'invalid_body',
                    },
                ]
            })

    @inlineCallbacks
    def test_get_channel(self):
        resp = yield self.get('/channels/foo-bar')
        yield self.assert_response(
            resp, http.INTERNAL_SERVER_ERROR, 'generic error', {
                'errors': [{
                    'message': '',
                    'type': 'NotImplementedError',
                }]
            })

    @inlineCallbacks
    def test_modify_channel(self):
        resp = yield self.post('/channels/foo-bar', {})
        yield self.assert_response(
            resp, http.INTERNAL_SERVER_ERROR, 'generic error', {
                'errors': [{
                    'message': '',
                    'type': 'NotImplementedError',
                }]
            })

    @inlineCallbacks
    def test_modify_channel_invalid_parameters(self):
        resp = yield self.post('/channels/foo-bar', {
            'rate_limit_count': -3,
            'character_limit': 'a',
        })
        yield self.assert_response(
            resp, http.BAD_REQUEST, 'api usage error', {
                'errors': [
                    {
                        'message': '-3 is less than the minimum of 0',
                        'type': 'invalid_body',
                    },
                    {
                        'message': "u'a' is not of type 'integer'",
                        'type': 'invalid_body',
                    },
                ]
            })

    @inlineCallbacks
    def test_delete_channel(self):
        resp = yield self.delete('/channels/foo-bar')
        yield self.assert_response(
            resp, http.INTERNAL_SERVER_ERROR, 'generic error', {
                'errors': [{
                    'message': '',
                    'type': 'NotImplementedError',
                }]
            })

    @inlineCallbacks
    def test_send_message(self):
        resp = yield self.post('/channels/foo-bar/messages', {
            'to': '+1234'})
        yield self.assert_response(
            resp, http.INTERNAL_SERVER_ERROR, 'generic error', {
                'errors': [{
                    'message': '',
                    'type': 'NotImplementedError',
                }]
            })

    @inlineCallbacks
    def test_send_message_no_to_or_reply_to(self):
        resp = yield self.post('/channels/foo-bar/messages', {})
        yield self.assert_response(
            resp, http.BAD_REQUEST, 'api usage error', {
                'errors': [{
                    'message': 'Either "to" or "reply_to" must be specified',
                    'type': 'ApiUsageError',
                }]
            })

    @inlineCallbacks
    def test_send_message_both_to_and_reply_to(self):
        resp = yield self.post('/channels/foo-bar/messages', {
            'to': '+1234',
            'reply_to': '2e8u9ua8',
        })
        yield self.assert_response(
            resp, http.BAD_REQUEST, 'api usage error', {
                'errors': [{
                    'message': 'Only one of "to" and "reply_to" may be '
                    'specified',
                    'type': 'ApiUsageError',
                }]
            })

    @inlineCallbacks
    def test_get_message_status(self):
        resp = yield self.get('/channels/foo-bar/messages/j98qfj9aw')
        yield self.assert_response(
            resp, http.INTERNAL_SERVER_ERROR, 'generic error', {
                'errors': [{
                    'message': '',
                    'type': 'NotImplementedError',
                }]
            })

    @inlineCallbacks
    def test_get_health_check(self):
        resp = yield self.get('/health')
        yield self.assert_response(
            resp, http.OK, 'health ok', {})
