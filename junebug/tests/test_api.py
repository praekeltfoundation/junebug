from copy import deepcopy
import logging
import json
import mock
import treq
from twisted.internet.defer import inlineCallbacks
from twisted.web import http

from treq.testing import StubTreq
from treq.testing import RequestSequence, StringStubbingResource

from vumi.message import TransportEvent, TransportUserMessage

from junebug.channel import Channel
from junebug.utils import api_from_message
from junebug.tests.helpers import JunebugTestBase, FakeJunebugPlugin
from junebug.utils import api_from_event, conjoin, omit


class TestJunebugApi(JunebugTestBase):

    maxDiff = None

    @inlineCallbacks
    def setUp(self):
        self.patch_logger()
        yield self.start_server()

    def get(self, url, params={}):
        return treq.get(
            "%s%s" % (self.url, url), params=params, persistent=False)

    def request(self, method, url, params={}):
        return treq.request(
            method, "%s%s" % (self.url, url), params=params, persistent=False)

    def post(self, url, data, headers=None):
        return treq.post(
            "%s%s" % (self.url, url),
            json.dumps(data),
            persistent=False,
            headers=headers)

    def put(self, url, data, headers=None):
        return treq.put(
            "%s%s" % (self.url, url),
            json.dumps(data),
            persistent=False,
            headers=headers)

    def patch_request(self, url, data, headers=None):
        return treq.patch(
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
                    'code': 404,
                    'message': ('404 Not Found: The requested URL was not '
                                'found on the server.  If you entered the URL'
                                ' manually please check your spelling and try'
                                ' again.'),
                    'type': 'Not Found',
                    }]
                })

    @inlineCallbacks
    def test_redirect_http_error(self):
        resp = yield self.get('/channels')
        [redirect] = resp.history()
        yield self.assert_response(
            redirect, http.MOVED_PERMANENTLY,
            None, {
                'errors': [{
                    'code': 301,
                    'message': '301 Moved Permanently: None',
                    'new_url': '%s/channels/' % self.url,
                    'type': 'Moved Permanently',
                }],
            })
        yield self.assert_response(
            resp, http.OK,
            'channels listed', [])

    @inlineCallbacks
    def test_startup_plugins_started(self):
        '''When the API starts, all the configured plugins should start'''
        yield self.stop_server()
        config = yield self.create_channel_config(
            plugins=[{
                'type': 'junebug.tests.helpers.FakeJunebugPlugin'
            }]
        )
        yield self.start_server(config=config)
        [plugin] = self.api.plugins

        self.assertEqual(type(plugin), FakeJunebugPlugin)
        [(name, [plugin_conf, junebug_conf])] = plugin.calls
        self.assertEqual(name, 'start_plugin')
        self.assertEqual(plugin_conf, {
            'type': 'junebug.tests.helpers.FakeJunebugPlugin'})
        self.assertEqual(junebug_conf, config)

    @inlineCallbacks
    def test_shutdown_plugins_stopped(self):
        '''When the API stops, all the configured plugins should stop'''
        yield self.stop_server()
        config = yield self.create_channel_config(
            plugins=[{
                'type': 'junebug.tests.helpers.FakeJunebugPlugin'
            }]
        )
        yield self.start_server(config=config)
        [plugin] = self.api.plugins
        plugin.calls = []
        yield self.stop_server()

        [(name, [])] = plugin.calls
        self.assertEqual(name, 'stop_plugin')

    @inlineCallbacks
    def test_startup_single_channel(self):
        properties = self.create_channel_properties()
        resp = yield self.post('/channels/', properties)
        id = (yield resp.json())['result']['id']

        yield self.stop_server()
        self.assertFalse(id in self.service.namedServices)

        yield self.start_server()
        self.assertTrue(id in self.service.namedServices)

    @inlineCallbacks
    def test_startup_multiple_channel(self):
        ids = []
        for i in range(5):
            properties = self.create_channel_properties()
            resp = yield self.post('/channels/', properties)
            id = (yield resp.json())['result']['id']
            ids.append(id)

        yield self.stop_server()
        for id in ids:
            self.assertFalse(id in self.service.namedServices)

        yield self.start_server()
        for id in ids:
            self.assertTrue(id in self.service.namedServices)

    @inlineCallbacks
    def test_get_channel_list(self):
        redis = yield self.get_redis()
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()

        resp = yield self.get('/channels/')
        yield self.assert_response(resp, http.OK, 'channels listed', [])

        yield Channel(redis, config, properties, id=u'test-channel-1').save()

        resp = yield self.get('/channels/')
        yield self.assert_response(resp, http.OK, 'channels listed', [
            u'test-channel-1',
        ])

        yield Channel(redis, config, properties, id=u'test-channel-2').save()

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
            resp, http.CREATED, 'channel created',
            conjoin(properties, {'status': self.generate_status()}),
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
            'worker_name': id,
            'publish_status': True,
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
            'mo_url': 'http://example.org',
        })
        yield self.assert_response(
            resp, http.BAD_REQUEST, 'api usage error', {
                'errors': sorted([
                    {
                        'message': '-3 is less than the minimum of 0',
                        'type': 'invalid_body',
                        'schema_path': [
                            'properties', 'rate_limit_count', 'minimum'],
                    },
                    {
                        'message': "u'a' is not of type 'integer'",
                        'type': 'invalid_body',
                        'schema_path': [
                            'properties', 'character_limit', 'type'],
                    },
                ])
            })

    @inlineCallbacks
    def test_create_channel_mo_destination(self):
        '''When creating a channel, one of or both of mo_url and mo_queue
        must be present.'''
        resp = yield self.post('/channels/', {
            'type': 'smpp',
            'config': {}
        })
        self.maxDiff = None
        yield self.assert_response(
            resp, http.BAD_REQUEST, 'api usage error', {
                'errors': [{
                    'message': 'One or both of "mo_url" and "amqp_queue" must'
                               ' be specified',
                    'type': 'ApiUsageError',
                }],
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
        channel = Channel(redis, config, properties, id=u'test-channel')
        yield channel.save()
        yield channel.start(self.service)
        resp = yield self.get('/channels/test-channel')

        yield self.assert_response(
            resp, http.OK, 'channel found', conjoin(properties, {
                'status': self.generate_status(),
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

        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)

        resp = yield self.post(
            '/channels/test-channel', {'metadata': {'foo': 'bar'}})

        yield self.assert_response(
            resp, http.OK, 'channel updated', conjoin(properties, {
                'status': self.generate_status(),
                'id': 'test-channel',
                'metadata': {'foo': 'bar'},
            }))

    @inlineCallbacks
    def test_modify_channel_config_change(self):
        redis = yield self.get_redis()
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()

        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)

        properties['config']['name'] = 'bar'
        resp = yield self.post('/channels/test-channel', properties)

        yield self.assert_response(
            resp, http.OK, 'channel updated', conjoin(properties, {
                'status': self.generate_status(),
                'id': 'test-channel',
            }))

    @inlineCallbacks
    def test_modify_channel_config_remove_mo_url(self):
        redis = yield self.get_redis()
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()

        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)

        properties['config']['name'] = 'bar'
        properties['mo_url'] = None
        resp = yield self.post('/channels/test-channel', properties)

        yield self.assert_response(
            resp, http.OK, 'channel updated', conjoin(properties, {
                'status': self.generate_status(),
                'id': 'test-channel',
            }))

    @inlineCallbacks
    def test_modify_channel_config_remove_status_url(self):
        redis = yield self.get_redis()
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()

        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)

        properties['config']['name'] = 'bar'
        properties['status_url'] = None
        resp = yield self.post('/channels/test-channel', properties)

        yield self.assert_response(
            resp, http.OK, 'channel updated', conjoin(properties, {
                'status': self.generate_status(),
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
                        'schema_path': [
                            'properties', 'rate_limit_count', 'minimum'],
                    },
                    {
                        'message': "u'a' is not of type 'integer'",
                        'type': 'invalid_body',
                        'schema_path': [
                            'properties', 'character_limit', 'type'],
                    },
                ]
            })

    @inlineCallbacks
    def test_delete_channel(self):
        config = yield self.create_channel_config()
        properties = self.create_channel_properties()
        channel = Channel(self.redis, config, properties, id='test-channel')
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

    def record_channel_methods(self, *methods):
        calls = []

        def method_recorder(meth):
            orig_method = getattr(Channel, meth)

            def record(self, *args, **kw):
                result = orig_method(self, *args, **kw)
                calls.append((meth, self.id))
                return result

            return record

        for meth in methods:
            self.patch(Channel, meth, method_recorder(meth))
        return calls

    @inlineCallbacks
    def test_restart_channel(self):
        config = yield self.create_channel_config()
        properties = self.create_channel_properties()
        channel = Channel(self.redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)

        actions = self.record_channel_methods('start', 'stop')

        resp = yield self.post('/channels/test-channel/restart', None)
        yield self.assert_response(resp, http.OK, 'channel restarted', {})

        self.assertEqual(actions, [
            ('stop', u'test-channel'),
            ('start', u'test-channel'),
        ])

    @inlineCallbacks
    def test_restart_missing_channel(self):
        resp = yield self.post('/channels/test-channel/restart', None)
        yield self.assert_response(
            resp, http.NOT_FOUND, 'channel not found', {
                'errors': [{
                    'message': '',
                    'type': 'ChannelNotFound',
                }]
            })

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
        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)
        resp = yield self.post('/channels/test-channel/messages/', {
            'to': '+1234', 'content': 'foo', 'from': None})
        yield self.assert_response(
            resp, http.CREATED, 'message submitted', {
                'to': '+1234',
                'channel_id': 'test-channel',
                'from': None,
                'group': None,
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
    def test_send_group_message(self):
        '''Sending a group message should place the message on the queue for the
        channel'''
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()
        redis = yield self.get_redis()
        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)
        resp = yield self.post('/channels/test-channel/messages/', {
            'to': '+1234', 'content': 'foo', 'from': None,
            'group': 'the-group'})
        yield self.assert_response(
            resp, http.CREATED, 'message submitted', {
                'to': '+1234',
                'channel_id': 'test-channel',
                'from': None,
                'group': 'the-group',
                'reply_to': None,
                'channel_data': {},
                'content': 'foo',
            }, ignore=['timestamp', 'message_id'])

        [message] = self.get_dispatched_messages('test-channel.outbound')
        message_id = (yield resp.json())['result']['message_id']
        self.assertEqual(message['message_id'], message_id)
        self.assertEqual(message['group'], 'the-group')

        event_url = yield self.api.outbounds.load_event_url(
            'test-channel', message['message_id'])
        self.assertEqual(event_url, None)

    @inlineCallbacks
    def test_send_message_message_rate(self):
        '''Sending a message should increment the message rate counter'''
        clock = yield self.patch_message_rate_clock()
        channel = Channel(
            (yield self.get_redis()), (yield self.create_channel_config()),
            self.create_channel_properties(), id='test-channel')
        yield channel.save()
        yield channel.start(self.service)

        yield self.post('/channels/test-channel/messages/', {
            'to': '+1234', 'content': 'foo', 'from': None})
        clock.advance(channel.config.metric_window)

        rate = yield self.api.message_rate.get_messages_per_second(
            'test-channel', 'outbound', channel.config.metric_window)
        self.assertEqual(rate, 1.0 / channel.config.metric_window)

    @inlineCallbacks
    def test_send_message_event_url(self):
        '''Sending a message with a specified event url should store the event
        url for sending events in the future'''
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()
        redis = yield self.get_redis()
        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)
        resp = yield self.post('/channels/test-channel/messages/', {
            'to': '+1234', 'content': 'foo', 'from': None,
            'event_url': 'http://test.org'})
        yield self.assert_response(
            resp, http.CREATED, 'message submitted', {
                'to': '+1234',
                'channel_id': 'test-channel',
                'from': None,
                'group': None,
                'reply_to': None,
                'channel_data': {},
                'content': 'foo',
            }, ignore=['timestamp', 'message_id'])

        event_url = yield self.api.outbounds.load_event_url(
            'test-channel', (yield resp.json())['result']['message_id'])
        self.assertEqual(event_url, 'http://test.org')

    @inlineCallbacks
    def test_send_message_event_auth_token(self):
        '''Sending a message with a specified event url and auth token should
        store the auth token for sending events in the future'''
        properties = self.create_channel_properties()
        config = yield self.create_channel_config()
        redis = yield self.get_redis()
        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)
        resp = yield self.post('/channels/test-channel/messages/', {
            'to': '+1234', 'content': 'foo', 'from': None,
            'event_url': 'http://test.org', 'event_auth_token': 'the_token'})
        yield self.assert_response(
            resp, http.CREATED, 'message submitted', {
                'to': '+1234',
                'channel_id': 'test-channel',
                'from': None,
                'group': None,
                'reply_to': None,
                'channel_data': {},
                'content': 'foo',
            }, ignore=['timestamp', 'message_id'])

        event_auth_token = yield self.api.outbounds.load_event_auth_token(
            'test-channel', (yield resp.json())['result']['message_id'])
        self.assertEqual(event_auth_token, 'the_token')

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
            resp, http.CREATED,
            'message submitted',
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
                    'schema_path': ['additionalProperties'],
                }]
            })

    @inlineCallbacks
    def test_send_message_both_to_and_reply_to(self):

        properties = self.create_channel_properties(character_limit=100)
        config = yield self.create_channel_config()
        redis = yield self.get_redis()
        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)

        resp = yield self.post('/channels/test-channel/messages/', {
            'from': None,
            'to': '+1234',
            'reply_to': '2e8u9ua8',
            'content': None,
        })
        yield self.assert_response(
            resp, http.BAD_REQUEST, 'message not found', {
                'errors': [{
                    'message': 'Inbound message with id 2e8u9ua8 not found',
                    'type': 'MessageNotFound',
                }]
            })

    @inlineCallbacks
    def test_send_message_both_to_and_reply_to_allowing_expiry(self):
        properties = self.create_channel_properties(character_limit=100)
        config = yield self.create_channel_config(
            allow_expired_replies=True)
        redis = yield self.get_redis()
        yield self.stop_server()
        yield self.start_server(config=config)

        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)

        resp = yield self.post('/channels/test-channel/messages/', {
            'from': None,
            'to': '+1234',
            'reply_to': '2e8u9ua8',
            'content': 'foo',
        })
        yield self.assert_response(
            resp, http.CREATED, 'message submitted', {
                'channel_data': {},
                'from': None,
                'to': '+1234',
                'content': 'foo',
                'group': None,
                'channel_id': u'test-channel',
                'reply_to': None,
            }, ignore=['timestamp', 'message_id'])

    @inlineCallbacks
    def test_send_message_from_and_reply_to(self):
        properties = self.create_channel_properties(character_limit=100)
        config = yield self.create_channel_config()
        redis = yield self.get_redis()
        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)

        resp = yield self.post('/channels/test-channel/messages/', {
            'from': None,
            'to': '+1234',
            'reply_to': '2e8u9ua8',
            'content': None,
        })
        yield self.assert_response(
            resp, http.BAD_REQUEST, 'message not found', {
                'errors': [{
                    'message': 'Inbound message with id 2e8u9ua8 not found',
                    'type': 'MessageNotFound',
                }]
            })

    @inlineCallbacks
    def test_send_message_under_character_limit(self):
        '''If the content length is under the character limit, no errors should
        be returned'''
        properties = self.create_channel_properties(character_limit=100)
        config = yield self.create_channel_config()
        redis = yield self.get_redis()
        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)
        resp = yield self.post('/channels/test-channel/messages/', {
            'to': '+1234', 'content': 'Under the character limit.',
            'from': None})
        yield self.assert_response(
            resp, http.CREATED, 'message submitted', {
                'to': '+1234',
                'channel_id': 'test-channel',
                'from': None,
                'group': None,
                'reply_to': None,
                'channel_data': {},
                'content': 'Under the character limit.',
            }, ignore=['timestamp', 'message_id'])

    @inlineCallbacks
    def test_send_message_equal_character_limit(self):
        '''If the content length is equal to the character limit, no errors
        should be returned'''
        content = 'Equal to the character limit.'
        properties = self.create_channel_properties(
            character_limit=len(content))
        config = yield self.create_channel_config()
        redis = yield self.get_redis()
        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)
        resp = yield self.post('/channels/test-channel/messages/', {
            'to': '+1234', 'content': content, 'from': None})
        yield self.assert_response(
            resp, http.CREATED, 'message submitted', {
                'to': '+1234',
                'channel_id': 'test-channel',
                'from': None,
                'group': None,
                'reply_to': None,
                'channel_data': {},
                'content': content,
            }, ignore=['timestamp', 'message_id'])

    @inlineCallbacks
    def test_send_message_over_character_limit(self):
        '''If the content length is over the character limit, an error should
        be returned'''
        properties = self.create_channel_properties(character_limit=10)
        config = yield self.create_channel_config()
        redis = yield self.get_redis()
        channel = Channel(redis, config, properties, id='test-channel')
        yield channel.save()
        yield channel.start(self.service)
        resp = yield self.post('/channels/test-channel/messages/', {
            'to': '+1234', 'content': 'Over the character limit.',
            'from': None})
        yield self.assert_response(
            resp, http.BAD_REQUEST, 'message too long', {
                'errors': [{
                    'message':
                        "Message content u'Over the character limit.' "
                        "is of length 25, which is greater than the character "
                        "limit of 10",
                    'type': 'MessageTooLong',
                }],
            })

    @inlineCallbacks
    def test_get_message_status_no_events(self):
        '''Returns `None` for last event fields, and empty list for events'''
        resp = yield self.get('/channels/foo-bar/messages/message-id')
        yield self.assert_response(
            resp, http.OK, 'message status', {
                'id': 'message-id',
                'last_event_type': None,
                'last_event_timestamp': None,
                'events': [],
            })

    @inlineCallbacks
    def test_get_message_status_one_event(self):
        '''Returns the event details for last event fields, and list with
        single event for `events`'''
        event = TransportEvent(
            user_message_id='message-id', sent_message_id='message-id',
            event_type='nack', nack_reason='error error')
        yield self.outbounds.store_event('channel-id', 'message-id', event)
        resp = yield self.get('/channels/channel-id/messages/message-id')
        event_dict = api_from_event('channel-id', event)
        event_dict['timestamp'] = str(event_dict['timestamp'])
        yield self.assert_response(
            resp, http.OK, 'message status', {
                'id': 'message-id',
                'last_event_type': 'rejected',
                'last_event_timestamp': str(event['timestamp']),
                'events': [event_dict],
            })

    @inlineCallbacks
    def test_get_message_status_multiple_events(self):
        '''Returns the last event details for last event fields, and list with
        all events for `events`'''
        events = []
        event_dicts = []
        for i in range(5):
            event = TransportEvent(
                user_message_id='message-id', sent_message_id='message-id',
                event_type='nack', nack_reason='error error')
            yield self.outbounds.store_event('channel-id', 'message-id', event)
            events.append(event)
            event_dict = api_from_event('channel-id', event)
            event_dict['timestamp'] = str(event_dict['timestamp'])
            event_dicts.append(event_dict)

        resp = yield self.get('/channels/channel-id/messages/message-id')
        yield self.assert_response(
            resp, http.OK, 'message status', {
                'id': 'message-id',
                'last_event_type': 'rejected',
                'last_event_timestamp': event_dicts[-1]['timestamp'],
                'events': event_dicts,
            })

    @inlineCallbacks
    def test_get_health_check(self):
        resp = yield self.get('/health')
        yield self.assert_response(
            resp, http.OK, 'health ok', {})

    @inlineCallbacks
    def test_get_channels_health_check(self):

        config = yield self.create_channel_config(
            rabbitmq_management_interface="rabbitmq:15672"
        )
        yield self.stop_server()
        yield self.start_server(config=config)

        channel = yield self.create_channel(self.service, self.redis)

        request_list = []

        for sub in ['inbound', 'outbound', 'event']:
            queue_name = "%s.%s" % (channel.id, sub)
            url = 'http://rabbitmq:15672/api/queues/%%2F/%s' % (queue_name)
            request_list.append(
                ((b'get', url, mock.ANY, mock.ANY, mock.ANY),
                 (http.OK, {b'Content-Type': b'application/json'},
                  b'{"messages": 1256, "messages_details": {"rate": 1.25}, "name": "%s"}' % queue_name)))  # noqa

        async_failures = []
        sequence_stubs = RequestSequence(request_list, async_failures.append)
        stub_treq = StubTreq(StringStubbingResource(sequence_stubs))

        def new_get(*args, **kwargs):
            return stub_treq.request("GET", args[0])

        with (mock.patch('treq.client.HTTPClient.get', side_effect=new_get)):
            with sequence_stubs.consume(self.fail):
                resp = yield self.request('GET', '/health')

            yield self.assertEqual(async_failures, [])
            yield self.assert_response(
                resp, http.OK, 'queues ok', [
                    {
                        'messages': 1256,
                        'name': '%s.inbound' % (channel.id),
                        'rate': 1.25,
                        'stuck': False
                    }, {
                        'messages': 1256,
                        'name': '%s.outbound' % (channel.id),
                        'rate': 1.25,
                        'stuck': False
                    }, {
                        'messages': 1256,
                        'name': '%s.event' % (channel.id),
                        'rate': 1.25,
                        'stuck': False
                    }])

    @inlineCallbacks
    def test_get_channels_health_check_stuck(self):

        config = yield self.create_channel_config(
            rabbitmq_management_interface="rabbitmq:15672"
        )
        yield self.stop_server()
        yield self.start_server(config=config)

        channel = yield self.create_channel(self.service, self.redis)

        request_list = []

        for sub in ['inbound', 'outbound', 'event']:
            queue_name = "%s.%s" % (channel.id, sub)
            url = 'http://rabbitmq:15672/api/queues/%%2F/%s' % (queue_name)
            request_list.append(
                ((b'get', url, mock.ANY, mock.ANY, mock.ANY),
                 (http.OK, {b'Content-Type': b'application/json'},
                  b'{"messages": 1256, "messages_details": {"rate": 0}, "name": "%s"}' % queue_name)))  # noqa

        async_failures = []
        sequence_stubs = RequestSequence(request_list, async_failures.append)
        stub_treq = StubTreq(StringStubbingResource(sequence_stubs))

        def new_get(*args, **kwargs):
            return stub_treq.request("GET", args[0])

        with (mock.patch('treq.client.HTTPClient.get', side_effect=new_get)):
            with sequence_stubs.consume(self.fail):
                resp = yield self.request('GET', '/health')

            yield self.assertEqual(async_failures, [])
            yield self.assert_response(
                resp, http.INTERNAL_SERVER_ERROR, 'queues stuck', [
                    {
                        'messages': 1256,
                        'name': '%s.inbound' % (channel.id),
                        'rate': 0,
                        'stuck': True
                    }, {
                        'messages': 1256,
                        'name': '%s.outbound' % (channel.id),
                        'rate': 0,
                        'stuck': True
                    }, {
                        'messages': 1256,
                        'name': '%s.event' % (channel.id),
                        'rate': 0,
                        'stuck': True
                    }])

    @inlineCallbacks
    def test_get_channel_logs_no_logs(self):
        '''If there are no logs, an empty list should be returned.'''
        channel = yield self.create_channel(self.service, self.redis)
        log_worker = channel.transport_worker.getServiceNamed(
            'Junebug Worker Logger')
        yield log_worker.startService()
        resp = yield self.get('/channels/%s/logs' % channel.id, params={
            'n': '3',
        })
        self.assert_response(
            resp, http.OK, 'logs retrieved', [])

    @inlineCallbacks
    def test_get_channel_logs_less_than_limit(self):
        '''If the amount of logs is less than the limit, all the logs should
        be returned.'''
        channel = yield self.create_channel(
            self.service, self.redis,
            'junebug.tests.helpers.LoggingTestTransport')
        worker_logger = channel.transport_worker.getServiceNamed(
            'Junebug Worker Logger')
        worker_logger.startService()

        channel.transport_worker.test_log('Test')
        resp = yield self.get('/channels/%s/logs' % channel.id, params={
            'n': '2',
        })
        self.assert_response(
            resp, http.OK, 'logs retrieved', [], ignore=[0])
        [log] = (yield resp.json())['result']
        self.assert_log(log, {
            'logger': channel.id,
            'message': 'Test',
            'level': logging.INFO})

    @inlineCallbacks
    def test_get_channel_logs_more_than_limit(self):
        '''If the amount of logs is more than the limit, only the latest n
        should be returned.'''
        channel = yield self.create_channel(
            self.service, self.redis,
            'junebug.tests.helpers.LoggingTestTransport')
        worker_logger = channel.transport_worker.getServiceNamed(
            'Junebug Worker Logger')
        worker_logger.startService()

        channel.transport_worker.test_log('Test1')
        channel.transport_worker.test_log('Test2')
        channel.transport_worker.test_log('Test3')
        resp = yield self.get('/channels/%s/logs' % channel.id, params={
            'n': '2',
        })
        self.assert_response(
            resp, http.OK, 'logs retrieved', [], ignore=[1, 0])
        [log1, log2] = (yield resp.json())['result']
        self.assert_log(log1, {
            'logger': channel.id,
            'message': 'Test3',
            'level': logging.INFO})
        self.assert_log(log2, {
            'logger': channel.id,
            'message': 'Test2',
            'level': logging.INFO})

    @inlineCallbacks
    def test_get_channel_logs_more_than_configured(self):
        '''If the amount of requested logs is more than what is
        configured, then only the configured amount of logs are returned.'''
        logpath = self.mktemp()
        config = yield self.create_channel_config(
            max_logs=2,
            channels={
                'logging': 'junebug.tests.helpers.LoggingTestTransport',
            },
            logging_path=logpath
        )
        properties = yield self.create_channel_properties(type='logging')
        yield self.stop_server()
        yield self.start_server(config=config)
        channel = yield self.create_channel(
            self.service, self.redis, config=config, properties=properties)
        worker_logger = channel.transport_worker.getServiceNamed(
            'Junebug Worker Logger')
        worker_logger.startService()

        channel.transport_worker.test_log('Test1')
        channel.transport_worker.test_log('Test2')
        channel.transport_worker.test_log('Test3')
        resp = yield self.get('/channels/%s/logs' % channel.id, params={
            'n': '3',
        })

        self.assert_response(
            resp, http.OK, 'logs retrieved', [], ignore=[1, 0])
        [log1, log2] = (yield resp.json())['result']
        self.assert_log(log1, {
            'logger': channel.id,
            'message': 'Test3',
            'level': logging.INFO})
        self.assert_log(log2, {
            'logger': channel.id,
            'message': 'Test2',
            'level': logging.INFO})

    @inlineCallbacks
    def test_get_channel_logs_no_n(self):
        '''If the number of logs is not specified, then the API should return
        the configured maximum number of logs.'''
        logpath = self.mktemp()
        config = yield self.create_channel_config(
            max_logs=2,
            channels={
                'logging': 'junebug.tests.helpers.LoggingTestTransport',
            },
            logging_path=logpath
        )
        properties = yield self.create_channel_properties(type='logging')
        yield self.stop_server()
        yield self.start_server(config=config)
        channel = yield self.create_channel(
            self.service, self.redis, config=config, properties=properties)
        worker_logger = channel.transport_worker.getServiceNamed(
            'Junebug Worker Logger')
        worker_logger.startService()

        channel.transport_worker.test_log('Test1')
        channel.transport_worker.test_log('Test2')
        channel.transport_worker.test_log('Test3')
        resp = yield self.get('/channels/%s/logs' % channel.id)

        self.assert_response(
            resp, http.OK, 'logs retrieved', [], ignore=[1, 0])
        [log1, log2] = (yield resp.json())['result']
        self.assert_log(log1, {
            'logger': channel.id,
            'message': 'Test3',
            'level': logging.INFO})
        self.assert_log(log2, {
            'logger': channel.id,
            'message': 'Test2',
            'level': logging.INFO})

    @inlineCallbacks
    def test_get_router_list(self):
        '''A GET request on the routers collection endpoint should result in
        the list of router UUIDs being returned'''
        redis = yield self.get_redis()

        resp = yield self.get('/routers/')
        yield self.assert_response(resp, http.OK, 'routers retrieved', [])

        yield redis.sadd('routers', '64f78582-8e83-40c9-be23-cc93d54e9dcd')

        resp = yield self.get('/routers/')
        yield self.assert_response(resp, http.OK, 'routers retrieved', [
            u'64f78582-8e83-40c9-be23-cc93d54e9dcd',
        ])

        yield redis.sadd('routers', 'ceee6a83-fa6b-42d2-b65f-1a1cf85ac6f8')

        resp = yield self.get('/routers/')
        yield self.assert_response(resp, http.OK, 'routers retrieved', [
            u'64f78582-8e83-40c9-be23-cc93d54e9dcd',
            u'ceee6a83-fa6b-42d2-b65f-1a1cf85ac6f8',
        ])

    @inlineCallbacks
    def test_create_router(self):
        """Creating a router with a valid config should succeed"""
        config = self.create_router_config()
        resp = yield self.post('/routers/', config)

        yield self.assert_response(
            resp, http.CREATED, 'router created', config, ignore=['id'])

    @inlineCallbacks
    def test_create_router_invalid_worker_config(self):
        """The worker config should be sent to the router for validation"""
        config = self.create_router_config(config={'test': 'fail'})
        resp = yield self.post('/routers/', config)

        yield self.assert_response(
            resp, http.BAD_REQUEST, 'invalid router config', {
                'errors': [{
                    'message': 'test must be pass',
                    'type': 'InvalidRouterConfig',
                }]
            })

    @inlineCallbacks
    def test_create_router_worker(self):
        """When creating a new router, the router worker should successfully
        be started"""
        config = self.create_router_config()
        resp = yield self.post('/routers/', config)

        # Check that the worker is created with the correct config
        id = (yield resp.json())['result']['id']
        transport = self.service.namedServices[id]

        self.assertEqual(transport.parent, self.service)

        worker_config = config['config']
        worker_config['destinations'] = []
        self.assertEqual(transport.config, worker_config)

    @inlineCallbacks
    def test_create_router_saves_config(self):
        """When creating a worker, the config should be saved inside the router
        store"""
        config = self.create_router_config()
        resp = yield self.post('/routers/', config)

        routers = yield self.api.router_store.get_router_list()
        self.assertEqual(routers, [(yield resp.json())['result']['id']])

    @inlineCallbacks
    def test_get_router(self):
        """The get router endpoint should return the config and status of the
        specified router"""
        config = self.create_router_config()
        resp = yield self.post('/routers/', config)

        router_id = (yield resp.json())['result']['id']
        resp = yield self.get('/routers/{}'.format(router_id))
        self.assert_response(
            resp, http.OK, 'router found', config, ignore=['id'])

    @inlineCallbacks
    def test_get_non_existing_router(self):
        """If a router for the given ID does not exist, then a not found error
        should be returned"""
        resp = yield self.get('/routers/bad-router-id')
        self.assert_response(resp, http.NOT_FOUND, 'router not found', {
            'errors': [{
                'message': 'Router with ID bad-router-id cannot be found',
                'type': 'RouterNotFound',
            }]
        })

    @inlineCallbacks
    def test_replace_router_config(self):
        """When creating a PUT request, the router configuration should be
        replaced"""
        old_config = self.create_router_config(label='test', config={
            'test': 'pass', 'foo': 'bar'})
        resp = yield self.post('/routers/', old_config)
        router_id = (yield resp.json())['result']['id']

        router_config = yield self.api.router_store.get_router_config(
            router_id)
        old_config['id'] = router_id
        self.assertEqual(router_config, old_config)
        router_worker = self.api.service.namedServices[router_id]
        router_worker_config = old_config['config']
        router_worker_config['destinations'] = []
        self.assertEqual(router_worker.config, router_worker_config)

        new_config = self.create_router_config(config={'test': 'pass'})
        new_config.pop('label', None)
        resp = yield self.put('/routers/{}'.format(router_id), new_config)
        new_config['id'] = router_id

        yield self.assert_response(
            resp, http.OK, 'router updated', new_config)

        router_config = yield self.api.router_store.get_router_config(
            router_id)
        self.assertEqual(router_config, new_config)
        router_worker = self.api.service.namedServices[router_id]
        router_worker_config = new_config['config']
        router_worker_config['destinations'] = []
        self.assertEqual(router_worker.config, router_worker_config)

        router_worker = self.api.service.namedServices[router_id]

    @inlineCallbacks
    def test_replace_router_config_invalid_worker_config(self):
        """Before replacing the worker config, the new config should be
        validated."""
        old_config = self.create_router_config(config={'test': 'pass'})
        resp = yield self.post('/routers/', old_config)
        router_id = (yield resp.json())['result']['id']

        new_config = self.create_router_config(config={'test': 'fail'})
        resp = yield self.put('/routers/{}'.format(router_id), new_config)

        yield self.assert_response(
            resp, http.BAD_REQUEST, 'invalid router config', {
                'errors': [{
                    'message': 'test must be pass',
                    'type': 'InvalidRouterConfig',
                }]
            })

        resp = yield self.get('/routers/{}'.format(router_id))
        yield self.assert_response(
            resp, http.OK, 'router found', old_config, ignore=['id'])

    @inlineCallbacks
    def test_update_router_config(self):
        """When creating a PATCH request, the router configuration should be
        updated"""
        old_config = self.create_router_config(
            label='old', config={'test': 'pass'})
        resp = yield self.post('/routers/', old_config)
        router_id = (yield resp.json())['result']['id']

        router_config = yield self.api.router_store.get_router_config(
            router_id)
        old_config['id'] = router_id
        self.assertEqual(router_config, old_config)
        router_worker = self.api.service.namedServices[router_id]
        router_worker_config = old_config['config']
        router_worker_config['destinations'] = []
        self.assertEqual(router_worker.config, router_worker_config)

        update = {'config': {'test': 'pass', 'new': 'new'}}
        new_config = deepcopy(old_config)
        new_config.update(update)
        self.assertEqual(new_config['label'], 'old')
        resp = yield self.patch_request(
            '/routers/{}'.format(router_id), update)

        yield self.assert_response(
            resp, http.OK, 'router updated', new_config)

        router_config = yield self.api.router_store.get_router_config(
            router_id)
        self.assertEqual(router_config, new_config)
        router_worker = self.api.service.namedServices[router_id]
        router_worker_config = new_config['config']
        router_worker_config['destinations'] = []
        self.assertEqual(router_worker.config, new_config['config'])

        router_worker = self.api.service.namedServices[router_id]

    @inlineCallbacks
    def test_update_router_config_invalid_worker_config(self):
        """Before updating the worker config, the new config should be
        validated."""
        old_config = self.create_router_config(config={'test': 'pass'})
        resp = yield self.post('/routers/', old_config)
        router_id = (yield resp.json())['result']['id']

        update = {'config': {'test': 'fail'}}
        resp = yield self.patch_request(
            '/routers/{}'.format(router_id), update)

        yield self.assert_response(
            resp, http.BAD_REQUEST, 'invalid router config', {
                'errors': [{
                    'message': 'test must be pass',
                    'type': 'InvalidRouterConfig',
                }]
            })

        resp = yield self.get('/routers/{}'.format(router_id))
        yield self.assert_response(
            resp, http.OK, 'router found', old_config, ignore=['id'])

    @inlineCallbacks
    def test_delete_router(self):
        """Should stop the router from running, and delete its config"""
        config = self.create_router_config()
        resp = yield self.post('/routers/', config)
        router_id = (yield resp.json())['result']['id']

        self.assertTrue(router_id in self.service.namedServices)
        routers = yield self.api.router_store.get_router_list()
        self.assertEqual(routers, [router_id])

        resp = yield self.delete('/routers/{}'.format(router_id))
        self.assert_response(resp, http.OK, 'router deleted', {})
        self.assertFalse(router_id in self.service.namedServices)
        routers = yield self.api.router_store.get_router_list()
        self.assertEqual(routers, [])

    @inlineCallbacks
    def test_delete_non_existing_router(self):
        """Should return a router not found"""
        resp = yield self.delete('/routers/bad-id')
        self.assert_response(resp, http.NOT_FOUND, 'router not found', {
            'errors': [{
                'message': 'Router with ID bad-id cannot be found',
                'type': 'RouterNotFound',
            }]
        })

    @inlineCallbacks
    def test_create_destination_invalid_router_id(self):
        """If the router specified by the router ID doesn't exist, a not found
        error should be returned"""
        resp = yield self.post('/routers/bad-router-id/destinations/', {
            'config': {}
        })
        self.assert_response(resp, http.NOT_FOUND, 'router not found', {
            'errors': [{
                'message': 'Router with ID bad-router-id cannot be found',
                'type': 'RouterNotFound',
            }]
        })

    @inlineCallbacks
    def test_create_destination_invalid_config(self):
        """The destination config should be sent to the router worker to
        validate before the destination is created"""
        router_config = self.create_router_config()
        resp = yield self.post('/routers/', router_config)
        router_id = (yield resp.json())['result']['id']

        dest_config = self.create_destination_config(config={
            'target': 'invalid',
        })
        resp = yield self.post(
            '/routers/{}/destinations/'.format(router_id), dest_config)
        self.assert_response(
            resp, http.BAD_REQUEST, 'invalid router destination config', {
                'errors': [{
                    'message': 'target must be valid',
                    'type': 'InvalidRouterDestinationConfig',
                }]
            }
        )

    @inlineCallbacks
    def test_create_destination(self):
        """A created destination should be saved in the router store, and be
        passed to the router worker config"""
        router_config = self.create_router_config()
        resp = yield self.post('/routers/', router_config)
        router_id = (yield resp.json())['result']['id']

        dest_config = self.create_destination_config()
        resp = yield self.post(
            '/routers/{}/destinations/'.format(router_id), dest_config)
        self.assert_response(
            resp, http.CREATED, 'destination created', dest_config,
            ignore=['id'])
        dest_id = (yield resp.json())['result']['id']

        self.assertEqual(
            (yield self.api.router_store.get_router_destination_list(
                router_id)),
            [dest_id])

        dest_config['id'] = dest_id
        router_worker = self.api.service.namedServices[router_id]
        self.assertEqual(router_worker.config['destinations'], [dest_config])

    @inlineCallbacks
    def test_get_destination_list_non_existing_router(self):
        """If we try to get a destination list for a router that doesn't
        exist, we should get a not found error returned"""
        resp = yield self.get('/routers/bad-router-id/destinations/')
        self.assert_response(
            resp, http.NOT_FOUND, 'router not found', {
                'errors': [{
                    'message': 'Router with ID bad-router-id cannot be found',
                    'type': 'RouterNotFound',
                }]
            })

    @inlineCallbacks
    def test_get_destination_list(self):
        """A GET request on the destinations resource should return a list of
        destinations for that router"""
        router_config = self.create_router_config()
        resp = yield self.post('/routers/', router_config)
        router_id = (yield resp.json())['result']['id']

        dest_config = self.create_destination_config()
        resp = yield self.post(
            '/routers/{}/destinations/'.format(router_id), dest_config)
        dest_id = (yield resp.json())['result']['id']

        resp = yield self.get('/routers/{}/destinations/'.format(router_id))
        self.assert_response(
            resp, http.OK, 'destinations retrieved', [dest_id])
