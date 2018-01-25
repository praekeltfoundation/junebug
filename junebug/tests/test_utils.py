import json
from datetime import date

from twisted.web import http
from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

import treq
from klein import Klein

from junebug.tests.utils import ToyServer
from junebug.utils import (
    response, json_body, conjoin, omit,
    message_from_api, api_from_message, api_from_event, api_from_status,
    channel_public_http_properties, convert_unicode)

from vumi.message import TransportUserMessage, TransportEvent, TransportStatus


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

    def test_conjoin(self):
        a = {
            'foo': 21,
            'bar': 23,
        }

        b = {
            'bar': 'baz',
            'quux': 'corge',
        }

        self.assertEqual(conjoin(a, b), {
            'foo': 21,
            'bar': 'baz',
            'quux': 'corge',
        })

        self.assertEqual(a, {
            'foo': 21,
            'bar': 23,
        })

        self.assertEqual(b, {
            'bar': 'baz',
            'quux': 'corge',
        })

    def test_omit(self):
        coll = {
            'foo': 'bar',
            'baz': 'quux',
            'corge': 'grault',
            'garply': 'waldo',
        }

        self.assertEqual(omit(coll, 'foo', 'garply'), {
            'baz': 'quux',
            'corge': 'grault',
        })

        self.assertEqual(coll, {
            'foo': 'bar',
            'baz': 'quux',
            'corge': 'grault',
            'garply': 'waldo',
        })

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
            'group': None,
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

    def test_api_from_event_ack(self):
        self.assertEqual(api_from_event('channel-23', TransportEvent(
            event_type='ack',
            user_message_id='msg-21',
            sent_message_id='msg-21',
            timestamp=date(2321, 2, 3),
        )), {
            'event_type': 'submitted',
            'channel_id': 'channel-23',
            'message_id': 'msg-21',
            'timestamp': date(2321, 2, 3),
            'event_details': {},
        })

    def test_api_from_event_nack(self):
        self.assertEqual(api_from_event('channel-23', TransportEvent(
            event_type='nack',
            user_message_id='msg-21',
            timestamp=date(2321, 2, 3),
            nack_reason='too many lemons',
        )), {
            'event_type': 'rejected',
            'channel_id': 'channel-23',
            'message_id': 'msg-21',
            'timestamp': date(2321, 2, 3),
            'event_details': {'reason': 'too many lemons'},
        })

    def test_api_from_event_dr_pending(self):
        self.assertEqual(api_from_event('channel-23', TransportEvent(
            event_type='delivery_report',
            user_message_id='msg-21',
            timestamp=date(2321, 2, 3),
            delivery_status='pending',
        )), {
            'event_type': 'delivery_pending',
            'channel_id': 'channel-23',
            'message_id': 'msg-21',
            'timestamp': date(2321, 2, 3),
            'event_details': {},
        })

    def test_api_from_event_dr_delivered(self):
        self.assertEqual(api_from_event('channel-23', TransportEvent(
            event_type='delivery_report',
            user_message_id='msg-21',
            timestamp=date(2321, 2, 3),
            delivery_status='delivered',
        )), {
            'event_type': 'delivery_succeeded',
            'channel_id': 'channel-23',
            'message_id': 'msg-21',
            'timestamp': date(2321, 2, 3),
            'event_details': {},
        })

    def test_api_from_event_dr_failed(self):
        self.assertEqual(api_from_event('channel-23', TransportEvent(
            event_type='delivery_report',
            user_message_id='msg-21',
            timestamp=date(2321, 2, 3),
            delivery_status='failed',
        )), {
            'event_type': 'delivery_failed',
            'channel_id': 'channel-23',
            'message_id': 'msg-21',
            'timestamp': date(2321, 2, 3),
            'event_details': {},
        })

    def test_api_from_event_dr_unknown(self):
        event = TransportEvent(
            event_type='delivery_report',
            user_message_id='msg-21',
            timestamp=date(2321, 2, 3),
            delivery_status='pending')

        event['delivery_status'] = 'unknown'

        self.assertEqual(api_from_event('channel-23', event), {
            'event_type': None,
            'channel_id': 'channel-23',
            'message_id': 'msg-21',
            'timestamp': date(2321, 2, 3),
            'event_details': {},
        })

    def test_api_from_event_unknown_type(self):
        event = TransportEvent(
            event_type='ack',
            user_message_id='msg-21',
            sent_message_id='msg-21',
            timestamp=date(2321, 2, 3))

        event['event_type'] = 'unknown'

        self.assertEqual(api_from_event('channel-23', event), {
            'event_type': None,
            'channel_id': 'channel-23',
            'message_id': 'msg-21',
            'timestamp': date(2321, 2, 3),
            'event_details': {},
        })

    def test_api_from_status(self):
        status = TransportStatus(
            component='foo',
            status='ok',
            type='bar',
            message='Bar',
            details={'baz': 'quux'})

        self.assertEqual(api_from_status('channel-23', status), {
            'channel_id': 'channel-23',
            'status': 'ok',
            'component': 'foo',
            'type': 'bar',
            'message': 'Bar',
            'details': {'baz': 'quux'}
        })

    def test_public_http_properties_explicit(self):
        result = channel_public_http_properties({
            'config': {
                'web_path': '/baz/quux',
                'web_port': 2121,
            },
            'public_http': {
                'web_path': '/foo/bar',
                'web_port': 2323,
            },
        })

        self.assertEqual(result, {
            'enabled': True,
            'web_path': '/foo/bar',
            'web_port': 2323
        })

    def test_public_http_properties_explicit_enable(self):
        result = channel_public_http_properties({
            'public_http': {
                'enabled': True,
                'web_path': '/foo/bar',
                'web_port': 2323,
            }
        })

        self.assertTrue(result['enabled'])

    def test_public_http_properties_explicit_disable(self):
        result = channel_public_http_properties({
            'public_http': {
                'enabled': False,
                'web_path': '/foo/bar',
                'web_port': 2323
            }
        })

        self.assertFalse(result['enabled'])

    def test_public_http_properties_explicit_no_port(self):
        result = channel_public_http_properties({
            'public_http': {'web_path': '/foo/bar'}
        })

        self.assertEqual(result, None)

    def test_public_http_properties_explicit_no_path(self):
        result = channel_public_http_properties({
            'public_http': {'web_port': 2323}
        })

        self.assertEqual(result, None)

    def test_public_http_properties_explicit_implicit_path(self):
        result = channel_public_http_properties({
            'config': {
                'web_path': '/foo/bar',
            },
            'public_http': {
                'web_port': 2323
            },
        })

        self.assertEqual(result, {
            'enabled': True,
            'web_path': '/foo/bar',
            'web_port': 2323
        })

    def test_public_http_properties_explicit_implicit_port(self):
        result = channel_public_http_properties({
            'config': {
                'web_port': 2323,
            },
            'public_http': {
                'web_path': '/foo/bar',
            },
        })

        self.assertEqual(result, {
            'enabled': True,
            'web_path': '/foo/bar',
            'web_port': 2323
        })

    def test_public_http_properties_implicit(self):
        result = channel_public_http_properties({
            'config': {
                'web_port': 2323,
                'web_path': '/foo/bar',
            },
        })

        self.assertEqual(result, {
            'enabled': True,
            'web_path': '/foo/bar',
            'web_port': 2323
        })

    def test_public_http_properties_implicit_no_port(self):
        result = channel_public_http_properties({'web_path': '/foo/bar'})
        self.assertEqual(result, None)

    def test_public_http_properties_implicit_no_path(self):
        result = channel_public_http_properties({'web_port': 2323})
        self.assertEqual(result, None)

    def test_convert_unicode(self):
        resp = convert_unicode({
            u'both': u'unicode',
            u'key': 'unicode',
            'value': u'unicode',
            'nested': {
                u'unicode': u'nested'
                },
            })
        for key, value in resp.iteritems():
            self.assertTrue(isinstance(key, str))
            if not isinstance(value, dict):
                self.assertTrue(isinstance(value, str))
        for key, value in resp['nested'].iteritems():
            self.assertTrue(isinstance(key, str))
            self.assertTrue(isinstance(value, str))

        self.assertTrue(isinstance(convert_unicode(1), int))
