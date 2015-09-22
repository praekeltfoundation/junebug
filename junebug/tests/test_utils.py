import json

from twisted.web import http
from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

import treq
from klein import Klein

from junebug.tests.utils import ToyServer
from junebug.utils import (
    response, json_body, message_from_api, api_from_message)

from vumi.message import TransportUserMessage


class TestUtils(TestCase):
    @inlineCallbacks
    def test_response_data(self):
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/')
        def route(req):
            return response(req, 'bar', {'foo': 23})

        resp = yield treq.get(srv.url, persistent=False)
        content = yield resp.json()
        self.assertEqual(content['result'], {'foo': 23})
        self.assertEqual(content['code'], 'OK')
        self.assertEqual(content['status'], 200)
        self.assertEqual(content['description'], 'bar')

    @inlineCallbacks
    def test_response_content_type(self):
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/')
        def route(req):
            return response(req, '', {})

        resp = yield treq.get(srv.url, persistent=False)

        self.assertEqual(
            resp.headers.getRawHeaders('Content-Type'),
            ['application/json'])

    @inlineCallbacks
    def test_response_code(self):
        srv = yield ToyServer.from_test(self)

        @srv.app.route('/')
        def route(req):
            return response(req, '', {}, http.BAD_REQUEST)

        resp = yield treq.get(srv.url, persistent=False)
        self.assertEqual(resp.code, http.BAD_REQUEST)

    @inlineCallbacks
    def test_json_body(self):
        class Api(object):
            app = Klein()

            @app.route('/')
            @json_body
            def route(self, req, body):
                bodies.append(body)

        bodies = []
        srv = yield ToyServer.from_test(self, Api().app)

        yield treq.get(
            srv.url,
            persistent=False,
            data=json.dumps({'foo': 23}))

        self.assertEqual(bodies, [{'foo': 23}])

    def test_api_from_message(self):
        '''The api from message function should take a vumi message, and
        return a dict with the appropriate values'''
        message = TransportUserMessage.send(
            content=None, from_addr='+1234', to_addr='+5432',
            transport_name='testtransport', continue_session=True,
            helper_metadata={'voice': {}})
        dct = api_from_message(message)
        [dct.pop(f) for f in ['timestamp', 'message_id']]
        self.assertEqual(dct, {
            'channel_data': {
                'continue_session': True,
                'voice': {},
                },
            'from': '+1234',
            'to': '+5432',
            'channel_id': 'testtransport',
            'content': None,
            'reply_to': None,
            })

    def test_message_from_api(self):
        msg = message_from_api(
            'channel-id', {
                'from': '+1234',
                'content': None,
                'channel_data': {
                    'continue_session': True,
                    'voice': {},
                    },
                })
        msg = TransportUserMessage.send(**msg)
        self.assertEqual(msg.get('continue_session'), True)
        self.assertEqual(msg.get('helper_metadata'), {'voice': {}})
        self.assertEqual(msg.get('from_addr'), '+1234')
        self.assertEqual(msg.get('content'), None)

    def test_message_from_api_reply(self):
        msg = message_from_api(
            'channel-id', {
                'reply_to': 1234,
                'content': 'foo',
                'channel_data': {
                    'continue_session': True,
                    'voice': {},
                },
            })

        self.assertFalse('to_addr' in msg)
        self.assertFalse('from_addr' in msg)
        self.assertEqual(msg['continue_session'], True)
        self.assertEqual(msg['helper_metadata'], {'voice': {}})
        self.assertEqual(msg['content'], 'foo')
