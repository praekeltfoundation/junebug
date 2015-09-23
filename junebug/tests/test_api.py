import json
import treq
from twisted.internet.defer import inlineCallbacks
from twisted.web import http

from vumi.message import TransportUserMessage

from junebug.channel import Channel
from junebug.utils import api_from_message
from junebug.tests.helpers import JunebugTestBase
from junebug.utils import conjoin, omit


class TestJunebugApi(JunebugTestBase):
    @inlineCallbacks
    def setUp(self):
        self.patch_logger()
        yield self.start_server()

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
        redis = yield self.get_redis()
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()

        resp = yield self.get('/channels/')
        yield self.assert_response(resp, http.OK, 'channels listed', [])

        yield Channel(redis, config, properties, u'test-channel-1').save()

        resp = yield self.get('/channels/')
        yield self.assert_response(resp, http.OK, 'channels listed', [
            u'test-channel-1',
        ])

        yield Channel(redis, config, properties, u'test-channel-2').save()

        resp = yield self.get('/channels/')
        yield self.assert_response(resp, http.OK, 'channels listed', [
            u'test-channel-1',
            u'test-channel-2',
        ])

    @inlineCallbacks
    def test_create_channel(self):
        properties = self.create_channel_properties()
        resp = yield self.post('/channels/', properties)

        yield self.assert_response(
            resp, http.OK, 'channel created',
            conjoin(properties, {'status': {}}),
            ignore=['id'])

    @inlineCallbacks
    def test_create_channel_transport(self):
        properties = self.create_channel_properties()
        resp = yield self.post('/channels/', properties)

        # Check that the transport is created with the correct config
        id = (yield resp.json())['result']['id']
        transport = self.service.namedServices[id]

        self.assertEqual(transport.parent, self.service)

        self.assertEqual(transport.config, conjoin(properties['config'], {
            'transport_name': id,
        }))

    @inlineCallbacks
    def test_create_channel_application(self):
        properties = self.create_channel_properties()
        resp = yield self.post('/channels/', properties)

        channel_id = (yield resp.json())['result']['id']
        id = Channel.APPLICATION_ID % (channel_id,)
        worker = self.service.namedServices[id]

        self.assertEqual(worker.parent, self.service)
        self.assertEqual(worker.config['transport_name'], channel_id)
        self.assertEqual(worker.config['mo_message_url'], 'http://foo.bar')

    @inlineCallbacks
    def test_create_channel_invalid_parameters(self):
        resp = yield self.post('/channels/', {
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
    def test_get_missing_channel(self):
        resp = yield self.get('/channels/foo-bar')
        yield self.assert_response(
            resp, http.NOT_FOUND, 'channel not found', {
                'errors': [{
                    'message': '',
                    'type': 'ChannelNotFound',
                }]
            })

    @inlineCallbacks
    def test_get_channel(self):
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()
        redis = yield self.get_redis()
        channel = Channel(redis, config, properties, u'test-channel')
        yield channel.save()
        yield channel.start(self.service)
        resp = yield self.get('/channels/test-channel')

        yield self.assert_response(
            resp, http.OK, 'channel found', conjoin(properties, {
                'status': {},
                'id': 'test-channel',
            }))

    @inlineCallbacks
    def test_modify_unknown_channel(self):
        resp = yield self.post('/channels/foo-bar', {})
        yield self.assert_response(
            resp, http.NOT_FOUND, 'channel not found', {
                'errors': [{
                    'message': '',
                    'type': 'ChannelNotFound',
                }]
            })

    @inlineCallbacks
    def test_modify_channel_no_config_change(self):
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()
        redis = yield self.get_redis()

        channel = Channel(redis, config, properties, 'test-channel')
        yield channel.save()
        yield channel.start(self.service)

        resp = yield self.post(
            '/channels/test-channel', {'metadata': {'foo': 'bar'}})

        yield self.assert_response(
            resp, http.OK, 'channel updated', conjoin(properties, {
                'status': {},
                'id': 'test-channel',
                'metadata': {'foo': 'bar'},
            }))

    @inlineCallbacks
    def test_modify_channel_config_change(self):
        redis = yield self.get_redis()
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()

        channel = Channel(redis, config, properties, 'test-channel')
        yield channel.save()
        yield channel.start(self.service)

        properties['config']['name'] = 'bar'
        resp = yield self.post('/channels/test-channel', properties)

        yield self.assert_response(
            resp, http.OK, 'channel updated', conjoin(properties, {
                'status': {},
                'id': 'test-channel',
            }))

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
        config = yield self.create_channel_config()
        properties = self.create_channel_properties()
        channel = Channel(self.redis, config, properties, 'test-channel')
        yield channel.save()
        yield channel.start(self.service)

        self.assertTrue('test-channel' in self.service.namedServices)
        properties = yield self.redis.get('test-channel:properties')
        self.assertNotEqual(properties, None)

        resp = yield self.delete('/channels/test-channel')
        yield self.assert_response(resp, http.OK, 'channel deleted', {})

        self.assertFalse('test-channel' in self.service.namedServices)
        properties = yield self.redis.get('test-channel:properties')
        self.assertEqual(properties, None)

        resp = yield self.delete('/channels/test-channel')
        yield self.assert_response(
            resp, http.NOT_FOUND, 'channel not found', {
                'errors': [{
                    'message': '',
                    'type': 'ChannelNotFound',
                }]
            })

        self.assertFalse('test-channel' in self.service.namedServices)
        properties = yield self.redis.get('test-channel:properties')
        self.assertEqual(properties, None)

    @inlineCallbacks
    def test_send_message_invalid_channel(self):
        resp = yield self.post('/channels/foo-bar/messages/', {
            'to': '+1234', 'from': '', 'content': None})
        yield self.assert_response(
            resp, http.NOT_FOUND, 'channel not found', {
                'errors': [{
                    'message': '',
                    'type': 'ChannelNotFound',
                    }]
                })

    @inlineCallbacks
    def test_send_message(self):
        '''Sending a message should place the message on the queue for the
        channel'''
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()
        redis = yield self.get_redis()
        channel = Channel(redis, config, properties, 'test-channel')
        yield channel.save()
        yield channel.start(self.service)
        resp = yield self.post('/channels/test-channel/messages/', {
            'to': '+1234', 'content': 'foo', 'from': None})
        yield self.assert_response(
            resp, http.OK, 'message sent', {
                'to': '+1234',
                'channel_id': 'test-channel',
                'from': None,
                'reply_to': None,
                'channel_data': {},
                'content': 'foo',
            }, ignore=['timestamp', 'message_id'])

        [message] = self.get_dispatched_messages('test-channel.outbound')
        message_id = (yield resp.json())['result']['message_id']
        self.assertEqual(message['message_id'], message_id)

        event_url = yield self.api.outbounds.load_event_url(
            'test-channel', message['message_id'])
        self.assertEqual(event_url, None)

    @inlineCallbacks
    def test_send_message_event_url(self):
        '''Sending a message with a specified event url should store the event
        url for sending events in the future'''
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()
        redis = yield self.get_redis()
        channel = Channel(redis, config, properties, 'test-channel')
        yield channel.save()
        yield channel.start(self.service)
        resp = yield self.post('/channels/test-channel/messages/', {
            'to': '+1234', 'content': 'foo', 'from': None,
            'event_url': 'http://test.org'})
        yield self.assert_response(
            resp, http.OK, 'message sent', {
                'to': '+1234',
                'channel_id': 'test-channel',
                'from': None,
                'reply_to': None,
                'channel_data': {},
                'content': 'foo',
            }, ignore=['timestamp', 'message_id'])

        event_url = yield self.api.outbounds.load_event_url(
            'test-channel', (yield resp.json())['result']['message_id'])
        self.assertEqual(event_url, 'http://test.org')

    @inlineCallbacks
    def test_send_message_reply(self):
        '''Sending a reply message should fetch the relevant inbound message,
        use it to construct a reply message, and place the reply message on the
        queue for the channel'''
        channel = Channel(
            redis_manager=(yield self.get_redis()),
            config=(yield self.create_channel_config()),
            properties=self.create_channel_properties(),
            id='test-channel')

        yield channel.save()
        yield channel.start(self.service)

        in_msg = TransportUserMessage(
            from_addr='+2789',
            to_addr='+1234',
            transport_name='test-channel',
            transport_type='_',
            transport_metadata={'foo': 'bar'})

        yield self.api.inbounds.store_vumi_message('test-channel', in_msg)
        expected = in_msg.reply(content='testcontent')
        expected = api_from_message(expected)

        resp = yield self.post('/channels/test-channel/messages/', {
            'reply_to': in_msg['message_id'],
            'content': 'testcontent',
        })

        yield self.assert_response(
            resp, http.OK,
            'message sent',
            omit(expected, 'timestamp', 'message_id'),
            ignore=['timestamp', 'message_id'])

        [message] = self.get_dispatched_messages('test-channel.outbound')
        message_id = (yield resp.json())['result']['message_id']
        self.assertEqual(message['message_id'], message_id)

    @inlineCallbacks
    def test_send_message_no_to_or_reply_to(self):
        resp = yield self.post(
            '/channels/foo-bar/messages/', {'from': None, 'content': None})
        yield self.assert_response(
            resp, http.BAD_REQUEST, 'api usage error', {
                'errors': [{
                    'message': 'Either "to" or "reply_to" must be specified',
                    'type': 'ApiUsageError',
                }]
            })

    @inlineCallbacks
    def test_send_message_additional_properties(self):
        '''Additional properties should result in an error being returned.'''
        resp = yield self.post(
            '/channels/foo-bar/messages/', {
                'from': None, 'content': None, 'to': '', 'foo': 'bar'})
        yield self.assert_response(
            resp, http.BAD_REQUEST, 'api usage error', {
                'errors': [{
                    'message': "Additional properties are not allowed (u'foo' "
                    "was unexpected)",
                    'type': 'invalid_body',
                }]
            })

    @inlineCallbacks
    def test_send_message_both_to_and_reply_to(self):
        resp = yield self.post('/channels/foo-bar/messages/', {
            'from': None,
            'to': '+1234',
            'reply_to': '2e8u9ua8',
            'content': None,
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
    def test_send_message_from_and_reply_to(self):
        resp = yield self.post('/channels/foo-bar/messages/', {
            'from': '+1234',
            'reply_to': '2e8u9ua8',
            'content': None,
        })

        yield self.assert_response(
            resp, http.BAD_REQUEST, 'api usage error', {
                'errors': [{
                    'message': 'Only one of "from" and "reply_to" may be '
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
