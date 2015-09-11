from copy import deepcopy
import json
from twisted.internet.defer import inlineCallbacks
from vumi.message import TransportUserMessage
from vumi.transports.telnet import TelnetServerTransport
from vumi.application.base import ApplicationWorker

from junebug.channel import Channel, ChannelNotFound, InvalidChannelType
from junebug.tests.helpers import JunebugTestBase


class TestChannel(JunebugTestBase):
    @inlineCallbacks
    def setUp(self):
        self.patch_logger()

        self.redis = yield self.get_redis()
        yield self.start_server()

    @inlineCallbacks
    def test_save_channel(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        properties = yield self.redis.get('%s:properties' % channel.id)
        expected = deepcopy(self.default_channel_config)
        expected['config']['transport_name'] = channel.id
        self.assertEqual(json.loads(properties), expected)

    @inlineCallbacks
    def test_delete_channel(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        properties = yield self.redis.get('%s:properties' % channel.id)
        expected = deepcopy(self.default_channel_config)
        expected['config']['transport_name'] = channel.id
        self.assertEqual(json.loads(properties), expected)

        yield channel.delete()
        properties = yield self.redis.get('%s:properties' % channel.id)
        self.assertEqual(properties, None)

    @inlineCallbacks
    def test_start_channel(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)

        self.assertEqual(
            self.service.namedServices[channel.id],
            channel.transport_worker)

    @inlineCallbacks
    def test_start_channel_application(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)

        self.assertEqual(
            channel.application_worker,
            self.service.namedServices['application:%s' % (channel.id,)])

        self.assertTrue(isinstance(
            channel.application_worker,
            ApplicationWorker))

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
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)

        update = yield channel.update({'foo': 'bar'})
        expected = deepcopy(self.default_channel_config)
        expected.update({
            'foo': 'bar',
            'status': {},
            'id': channel.id,
            })
        expected['config']['transport_name'] = channel.id
        self.assertEqual(update, expected)

    @inlineCallbacks
    def test_update_channel_restart_transport_on_config_change(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        worker1 = channel.transport_worker

        self.assertEqual(self.service.namedServices[channel.id], worker1)
        yield channel.update({'foo': 'bar'})
        self.assertEqual(self.service.namedServices[channel.id], worker1)

        config = self.create_channel_config()
        config['config']['foo'] = ['bar']
        yield channel.update(config)

        worker2 = channel.transport_worker
        self.assertEqual(self.service.namedServices[channel.id], worker2)
        self.assertNotEqual(worker1, worker2)

    @inlineCallbacks
    def test_update_channel_restart_application_on_config_change(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        worker1 = channel.application_worker
        id = 'application:%s' % (channel.id,)

        self.assertEqual(self.service.namedServices[id], worker1)
        yield channel.update({'foo': 'bar'})
        self.assertEqual(self.service.namedServices[id], worker1)

        config = self.create_channel_config()
        config['config']['foo'] = ['bar']
        yield channel.update(config)

        worker2 = channel.application_worker
        self.assertEqual(self.service.namedServices[id], worker2)
        self.assertNotEqual(worker1, worker2)

    @inlineCallbacks
    def test_stop_channel(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        self.assertEqual(
            self.service.namedServices[channel.id], channel.transport_worker)

        yield channel.stop()
        self.assertEqual(self.service.namedServices.get(channel.id), None)

    @inlineCallbacks
    def test_create_channel_from_id(self):
        channel1 = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)

        channel2 = yield self.create_channel_from_id(
            self.service, self.redis, channel1.id)

        self.assertEqual((yield channel1.status()), (yield channel2.status()))

        self.assertEqual(
            channel1.transport_worker,
            channel2.transport_worker)

        self.assertEqual(
            channel1.application_worker,
            channel2.application_worker)

    @inlineCallbacks
    def test_create_channel_from_unknown_id(self):
        yield self.assertFailure(
            self.create_channel_from_id(
                self.service, self.redis, 'unknown-id'),
            ChannelNotFound)

    @inlineCallbacks
    def test_channel_status(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')
        expected = deepcopy(self.default_channel_config)
        expected.update({
            'id': 'channel-id',
            'status': {},
            })
        expected['config']['transport_name'] = channel.id
        self.assertEqual((yield channel.status()), expected)

    @inlineCallbacks
    def test_get_all_channels(self):
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
        yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')
        msg = yield Channel.send_message(
            'channel-id', self.api.message_sender, {
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
    def test_api_from_message(self):
        '''The api from message function should take a vumi message, and
        return a dict with the appropriate values'''
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')
        message = TransportUserMessage.send(
            content=None, from_addr='+1234', to_addr='+5432',
            transport_name='testtransport', continue_session=True,
            helper_metadata={'voice': {}})
        dct = channel.api_from_message(message)
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

    @inlineCallbacks
    def test_message_from_api(self):
        yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')
        msg = Channel.message_from_api(
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
