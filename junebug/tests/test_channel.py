import json
from twisted.internet.defer import inlineCallbacks
from vumi.message import TransportUserMessage, TransportStatus
from vumi.transports.telnet import TelnetServerTransport

from junebug.utils import api_from_message, api_from_status, conjoin
from junebug.workers import ChannelStatusWorker, MessageForwardingWorker
from junebug.channel import (
    Channel, ChannelNotFound, InvalidChannelType, MessageNotFound)
from junebug.tests.helpers import JunebugTestBase


class TestChannel(JunebugTestBase):
    @inlineCallbacks
    def setUp(self):
        self.patch_logger()
        yield self.start_server()

    @inlineCallbacks
    def test_save_channel(self):
        properties = self.create_channel_properties()
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)

        props = yield self.redis.get('%s:properties' % channel.id)
        self.assertEqual(json.loads(props), conjoin(properties, {
            'config': conjoin(
                properties['config'], {'transport_name': channel.id})
        }))

        channel_list = yield self.redis.get('channels')
        self.assertEqual(channel_list, set([channel.id]))

    @inlineCallbacks
    def test_delete_channel(self):
        properties = self.create_channel_properties()
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)

        props = yield self.redis.get('%s:properties' % channel.id)
        self.assertEqual(json.loads(props), conjoin(properties, {
            'config': conjoin(
                properties['config'], {'transport_name': channel.id})
        }))

        channel_list = yield self.redis.get('channels')
        self.assertEqual(channel_list, set([channel.id]))

        yield channel.delete()
        properties = yield self.redis.get('%s:properties' % channel.id)
        self.assertEqual(properties, None)

        channel_list = yield self.redis.get('channels')
        self.assertEqual(channel_list, set())

    @inlineCallbacks
    def test_start_channel_transport(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)

        self.assertEqual(
            self.service.namedServices[channel.id],
            channel.transport_worker)

    @inlineCallbacks
    def test_transport_class_name_default(self):
        config = yield self.create_channel_config(channels={})
        properties = self.create_channel_properties(type='telnet')
        channel = Channel(self.redis, config, properties)
        self.assertEqual(
            channel._transport_cls_name,
            'vumi.transports.telnet.TelnetServerTransport')

    @inlineCallbacks
    def test_transport_class_name_specified(self):
        config = yield self.create_channel_config(channels={'foo': 'bar.baz'})
        properties = self.create_channel_properties(type='foo')
        channel = Channel(self.redis, config, properties)
        self.assertEqual(
            channel._transport_cls_name,
            'bar.baz')

    @inlineCallbacks
    def test_transport_class_name_overridden(self):
        config = yield self.create_channel_config(
            channels={'foo': 'bar.baz'}, replace_channels=True)
        properties = self.create_channel_properties(type='telnet')
        channel = Channel(self.redis, config, properties)
        err = self.assertRaises(
            InvalidChannelType, getattr, channel, '_transport_cls_name')
        self.assertTrue(all(cls in err.message for cls in ['telnet', 'foo']))

    @inlineCallbacks
    def test_start_channel_application(self):
        properties = self.create_channel_properties(mo_url='http://foo.org')

        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, properties)

        worker = channel.application_worker
        id = channel.application_id
        self.assertTrue(isinstance(worker, MessageForwardingWorker))
        self.assertEqual(self.service.namedServices[id], worker)

        self.assertEqual(worker.config, {
            'transport_name': channel.id,
            'mo_message_url': 'http://foo.org',
            'redis_manager': channel.config.redis,
            'inbound_ttl': channel.config.inbound_message_ttl,
            'outbound_ttl': channel.config.outbound_message_ttl,
        })

    @inlineCallbacks
    def test_start_channel_status_application(self):
        properties = self.create_channel_properties()

        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, properties)

        worker = channel.status_application_worker
        id = channel.status_application_id
        self.assertTrue(isinstance(worker, ChannelStatusWorker))
        self.assertEqual(self.service.namedServices[id], worker)

        self.assertEqual(worker.config, {
            'redis_manager': channel.config.redis,
            'status_connector_name': '%s.status' % channel.id,
            'channel_id': channel.id,
            'status_url': None,
        })

    @inlineCallbacks
    def test_start_channel_status_application_status_url(self):
        properties = self.create_channel_properties(status_url='example.org')

        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, properties)

        worker = channel.status_application_worker
        self.assertEqual(worker.config['status_url'], 'example.org')

    @inlineCallbacks
    def test_channel_character_limit(self):
        '''`character_limit` parameter should return the character limit, or
        `None` if no character limit was specified'''
        properties_limit = self.create_channel_properties(character_limit=100)
        properties_no_limit = self.create_channel_properties()

        channel_limit = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, properties_limit)
        channel_no_limit = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport,
            properties_no_limit)

        self.assertEqual(channel_limit.character_limit, 100)
        self.assertEqual(channel_no_limit.character_limit, None)

    @inlineCallbacks
    def test_create_channel_invalid_type(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        channel._properties['type'] = 'foo'
        err = self.assertRaises(InvalidChannelType, channel.start, None)
        self.assertTrue(all(
            s in err.message for s in ('xmpp', 'telnet', 'foo')))

    @inlineCallbacks
    def test_update_channel_config(self):
        properties = self.create_channel_properties()

        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)

        update = yield channel.update({'foo': 'bar'})

        self.assertEqual(update, conjoin(properties, {
            'foo': 'bar',
            'status': {},
            'id': channel.id,
            'config': conjoin(properties['config'], {
                'transport_name': channel.id
            })
        }))

    @inlineCallbacks
    def test_update_channel_restart_transport_on_config_change(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        worker1 = channel.transport_worker

        self.assertEqual(self.service.namedServices[channel.id], worker1)
        yield channel.update({'foo': 'bar'})
        self.assertEqual(self.service.namedServices[channel.id], worker1)

        properties = self.create_channel_properties()
        properties['config']['foo'] = ['bar']
        yield channel.update(properties)

        worker2 = channel.transport_worker
        self.assertEqual(self.service.namedServices[channel.id], worker2)
        self.assertTrue(worker1 not in self.service.services)

    @inlineCallbacks
    def test_update_channel_restart_application_on_config_change(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        worker1 = channel.application_worker
        id = channel.application_id

        self.assertEqual(self.service.namedServices[id], worker1)
        yield channel.update({'foo': 'bar'})
        self.assertEqual(self.service.namedServices[id], worker1)

        properties = self.create_channel_properties(mo_url='http://baz.org')
        yield channel.update(properties)

        worker2 = channel.application_worker
        self.assertEqual(self.service.namedServices[id], worker2)
        self.assertTrue(worker1 not in self.service.services)

    @inlineCallbacks
    def test_stop_channel(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        self.assertEqual(
            self.service.namedServices[channel.id], channel.transport_worker)

        yield channel.stop()
        self.assertEqual(self.service.namedServices.get(channel.id), None)

        application_id = channel.application_id
        self.assertEqual(self.service.namedServices.get(application_id), None)

        status_application_id = channel.status_application_id
        self.assertEqual(
            self.service.namedServices.get(status_application_id), None)

    @inlineCallbacks
    def test_create_channel_from_id(self):
        channel1 = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)

        channel2 = yield self.create_channel_from_id(
            self.redis, {}, channel1.id, self.service)

        self.assertEqual((yield channel1.status()), (yield channel2.status()))

        self.assertEqual(
            channel1.transport_worker,
            channel2.transport_worker)

        self.assertEqual(
            channel1.application_worker,
            channel2.application_worker)

        self.assertEqual(
            channel1.status_application_worker,
            channel2.status_application_worker)

    @inlineCallbacks
    def test_create_channel_from_unknown_id(self):
        yield self.assertFailure(
            self.create_channel_from_id(
                self.redis, {}, 'unknown-id', self.service),
            ChannelNotFound)

    @inlineCallbacks
    def test_channel_status_empty(self):
        properties = self.create_channel_properties()
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')

        self.assertEqual((yield channel.status()), conjoin(properties, {
            'status': {},
            'id': 'channel-id',
            'config': conjoin(properties['config'], {
                'transport_name': channel.id
            })
        }))

    @inlineCallbacks
    def test_channel_status_single_status(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')

        status = TransportStatus(
            status='ok',
            component='foo',
            type='bar',
            message='Bar')
        yield channel.sstore.store_status('channel-id', status)

        self.assertEqual((yield channel.status())['status'], {
            'status': 'ok',
            'components': {
                'foo': api_from_status('channel-id', status),
            }
        })

    @inlineCallbacks
    def test_channel_multiple_statuses_ok(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')

        components = {}

        for i in range(5):
            status = TransportStatus(
                status='ok',
                component=i,
                type='bar',
                message='Bar')
            yield channel.sstore.store_status('channel-id', status)
            components[str(i)] = api_from_status('channel-id', status)

        self.assertEqual((yield channel.status())['status'], {
            'status': 'ok',
            'components': components
        })

    @inlineCallbacks
    def test_channel_multiple_statuses_degraded(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')

        components = {}

        for i in range(5):
            status = TransportStatus(
                status='ok',
                component=i,
                type='bar',
                message='Bar')
            yield channel.sstore.store_status('channel-id', status)
            components[str(i)] = api_from_status('channel-id', status)

        status = TransportStatus(
            status='degraded',
            component=5,
            type='bar',
            message='Bar')
        yield channel.sstore.store_status('channel-id', status)
        components['5'] = api_from_status('channel-id', status)

        self.assertEqual((yield channel.status())['status'], {
            'status': 'degraded',
            'components': components
        })

    @inlineCallbacks
    def test_channel_multiple_statuses_down(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')

        components = {}

        for i in range(5):
            status = TransportStatus(
                status='ok',
                component=i,
                type='bar',
                message='Bar')
            yield channel.sstore.store_status('channel-id', status)
            components[str(i)] = api_from_status('channel-id', status)

        status = TransportStatus(
            status='degraded',
            component=5,
            type='bar',
            message='Bar')
        yield channel.sstore.store_status('channel-id', status)
        components['5'] = api_from_status('channel-id', status)

        status = TransportStatus(
            status='down',
            component=6,
            type='bar',
            message='Bar')
        yield channel.sstore.store_status('channel-id', status)
        components['6'] = api_from_status('channel-id', status)

        self.assertEqual((yield channel.status())['status'], {
            'status': 'down',
            'components': components
        })

    @inlineCallbacks
    def test_get_all(self):
        channels = yield Channel.get_all(self.redis)
        self.assertEqual(channels, set())

        channel1 = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        channels = yield Channel.get_all(self.redis)
        self.assertEqual(channels, set([channel1.id]))

        channel2 = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        channels = yield Channel.get_all(self.redis)
        self.assertEqual(channels, set([channel1.id, channel2.id]))

    @inlineCallbacks
    def test_start_all_channels(self):
        yield Channel.start_all_channels(
            self.redis, self.config, self.service)

        channel1 = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        self.assertTrue(channel1.id in self.service.namedServices)
        yield channel1.stop()
        self.assertFalse(channel1.id in self.service.namedServices)
        yield Channel.start_all_channels(
            self.redis, self.config, self.service)
        self.assertTrue(channel1.id in self.service.namedServices)

        channel2 = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        self.assertTrue(channel2.id in self.service.namedServices)
        channel1 = yield Channel.from_id(
            self.redis, self.config, channel1.id, self.service)
        yield channel1.stop()
        yield channel2.stop()
        self.assertFalse(channel1.id in self.service.namedServices)
        self.assertFalse(channel2.id in self.service.namedServices)
        yield Channel.start_all_channels(
            self.redis, self.config, self.service)
        self.assertTrue(channel1.id in self.service.namedServices)
        self.assertTrue(channel2.id in self.service.namedServices)

    @inlineCallbacks
    def test_convert_unicode(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')
        resp = channel._convert_unicode({
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

        self.assertTrue(isinstance(channel._convert_unicode(1), int))

    @inlineCallbacks
    def test_send_message(self):
        '''The send_message function should place the message on the correct
        queue'''
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')
        msg = yield channel.send_message(
            self.message_sender, self.outbounds, {
                'from': '+1234',
                'content': 'testcontent',
            })
        self.assertEqual(msg['channel_id'], 'channel-id')
        self.assertEqual(msg['from'], '+1234')
        self.assertEqual(msg['content'], 'testcontent')

        [dispatched_message] = self.get_dispatched_messages(
            'channel-id.outbound')
        self.assertEqual(msg['message_id'], dispatched_message['message_id'])

    @inlineCallbacks
    def test_send_message_event_url(self):
        '''Sending a message with a specified event url should store the event
        url for sending events in the future'''
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')

        msg = yield channel.send_message(
            self.message_sender, self.outbounds, {
                'from': '+1234',
                'content': 'testcontent',
                'event_url': 'http://test.org'
            })

        event_url = yield self.outbounds.load_event_url(
            'channel-id', msg['message_id'])

        self.assertEqual(event_url, 'http://test.org')

    @inlineCallbacks
    def test_send_reply_message(self):
        '''send_reply_message should place the correct reply message on the
        correct queue'''
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')

        in_msg = TransportUserMessage(
            from_addr='+2789',
            to_addr='+1234',
            transport_name='channel-id',
            transport_type='_',
            transport_metadata={'foo': 'bar'})

        yield self.api.inbounds.store_vumi_message('channel-id', in_msg)

        msg = yield channel.send_reply_message(
            self.message_sender, self.outbounds, self.inbounds, {
                'reply_to': in_msg['message_id'],
                'content': 'testcontent',
            })

        expected = in_msg.reply(content='testcontent')
        expected = conjoin(api_from_message(expected), {
            'timestamp': msg['timestamp'],
            'message_id': msg['message_id']
        })

        self.assertEqual(msg, expected)

        [dispatched] = self.get_dispatched_messages('channel-id.outbound')
        self.assertEqual(msg['message_id'], dispatched['message_id'])
        self.assertEqual(api_from_message(dispatched), expected)

    @inlineCallbacks
    def test_send_reply_message_inbound_not_found(self):
        '''send_reply_message should raise an error if the inbound message is
        not found'''
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')

        self.assertFailure(channel.send_reply_message(
            self.message_sender, self.outbounds, self.inbounds, {
                'reply_to': 'i-do-not-exist',
                'content': 'testcontent',
            }), MessageNotFound)

    @inlineCallbacks
    def test_send_reply_message_event_url(self):
        '''Sending a message with a specified event url should store the event
        url for sending events in the future'''
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')

        in_msg = TransportUserMessage(
            from_addr='+2789',
            to_addr='+1234',
            transport_name='channel-id',
            transport_type='_',
            transport_metadata={'foo': 'bar'})

        yield self.api.inbounds.store_vumi_message('channel-id', in_msg)

        msg = yield channel.send_reply_message(
            self.message_sender, self.outbounds, self.inbounds, {
                'reply_to': in_msg['message_id'],
                'content': 'testcontent',
                'event_url': 'http://test.org',
            })

        event_url = yield self.outbounds.load_event_url(
            'channel-id', msg['message_id'])

        self.assertEqual(event_url, 'http://test.org')
