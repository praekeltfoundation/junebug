from copy import deepcopy
import json
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase
from vumi.tests.helpers import PersistenceHelper, WorkerHelper
from vumi.transports.telnet import TelnetServerTransport

from junebug.channel import Channel, ChannelNotFound
from junebug.service import JunebugService
from junebug.tests.helpers import JunebugTestBase


class TestChannel(JunebugTestBase):
    @inlineCallbacks
    def setUp(self):
        self.patch_logger()

        redis = yield self.get_redis()
        self.service = JunebugService(
            'localhost', 0, redis._config, {})
        yield self.service.startService()
        self.addCleanup(self.service.stopService)

    @inlineCallbacks
    def test_save_channel(self):
        redis = yield self.get_redis()
        channel = yield self.create_channel(
            self.service, redis, TelnetServerTransport)
        properties = yield redis.get('%s:properties' % channel.id)
        self.assertEqual(json.loads(properties), self.default_channel_config)

    @inlineCallbacks
    def test_delete_channel(self):
        redis = yield self.get_redis()
        channel = yield self.create_channel(
            self.service, redis, TelnetServerTransport)
        properties = yield redis.get('%s:properties' % channel.id)
        self.assertEqual(json.loads(properties), self.default_channel_config)

        yield channel.delete()
        properties = yield redis.get('%s:properties' % channel.id)
        self.assertEqual(properties, None)

    @inlineCallbacks
    def test_start_channel(self):
        redis = yield self.get_redis()
        channel = yield self.create_channel(
            self.service, redis, TelnetServerTransport)
        self.assertEqual(
            self.service.namedServices[channel.id], channel.transport_worker)

    @inlineCallbacks
    def test_update_channel(self):
        self.maxDiff = None
        redis = yield self.get_redis()
        channel = yield self.create_channel(
            self.service, redis, TelnetServerTransport)
        self.assertEqual(
            self.service.namedServices[channel.id], channel.transport_worker)

        update = yield channel.update({'foo': 'bar'})
        expected = deepcopy(self.default_channel_config)
        expected.update({
            'foo': 'bar',
            'status': {},
            'id': channel.id,
            })
        self.assertEqual(update, expected)

    @inlineCallbacks
    def test_stop_channel(self):
        redis = yield self.get_redis()
        channel = yield self.create_channel(
            self.service, redis, TelnetServerTransport)
        self.assertEqual(
            self.service.namedServices[channel.id], channel.transport_worker)

        yield channel.stop()
        self.assertEqual(self.service.namedServices.get(channel.id), None)

    @inlineCallbacks
    def test_create_channel_from_id(self):
        redis = yield self.get_redis()
        channel1 = yield self.create_channel(
            self.service, redis, TelnetServerTransport)

        channel2 = yield self.create_channel_from_id(
            self.service, redis, channel1.id)
        self.assertEqual((yield channel1.status()), (yield channel2.status()))

    @inlineCallbacks
    def test_create_channel_from_unknown_id(self):
        redis = yield self.get_redis()
        yield self.assertFailure(
            self.create_channel_from_id(
                self.service, redis, 'unknown-id'),
            ChannelNotFound)

    @inlineCallbacks
    def test_channel_status(self):
        redis = yield self.get_redis()
        channel = yield self.create_channel(
            self.service, redis, TelnetServerTransport, id='channel-id')
        expected_response = deepcopy(self.default_channel_config)
        expected_response['id'] = 'channel-id'
        expected_response['status'] = {}
        self.assertEqual((yield channel.status()), expected_response)

    @inlineCallbacks
    def test_get_all_channels(self):
        redis = yield self.get_redis()
        channels = yield Channel.get_all(redis._config)
        self.assertEqual(channels, set())

        channel1 = yield self.create_channel(
            self.service, redis, TelnetServerTransport)
        channels = yield Channel.get_all(redis._config)
        self.assertEqual(channels, set([channel1.id]))

        channel2 = yield self.create_channel(
            self.service, redis, TelnetServerTransport)
        channels = yield Channel.get_all(redis._config)
        self.assertEqual(channels, set([channel1.id, channel2.id]))
