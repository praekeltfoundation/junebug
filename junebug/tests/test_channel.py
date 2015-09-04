from copy import deepcopy
import json
from twisted.internet.defer import inlineCallbacks
from vumi.transports.telnet import TelnetServerTransport

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
            self.service.namedServices[channel.id], channel.transport_worker)

    @inlineCallbacks
    def test_create_channel_invalid_type(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        channel._properties['type'] = 'foo'
        err = self.assertRaises(InvalidChannelType, channel.start, None)
        self.assertTrue(all(
            s in err.message for s in ('xmpp', 'telnet', 'foo')))

    @inlineCallbacks
    def test_update_channel(self):
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport)
        self.assertEqual(
            self.service.namedServices[channel.id], channel.transport_worker)

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
        channel = yield self.create_channel(
            self.service, self.redis, TelnetServerTransport, id='channel-id')
        amq_client = self.api.amqp_factory.get_client()
        msg = yield channel.send_message(amq_client, '+1234', 'testcontent')
        self.assertEqual(msg['transport_name'], 'channel-id')
        self.assertEqual(msg['to_addr'], '+1234')
        self.assertEqual(msg['content'], 'testcontent')

        [dispatched_message] = self.get_dispatched_messages(
            'channel-id.outbound')
        self.assertEqual(msg['message_id'], dispatched_message['message_id'])
