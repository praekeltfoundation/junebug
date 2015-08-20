import json
import logging
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from vumi.tests.helpers import PersistenceHelper

from junebug.channel import Channel, ChannelNotFound


class TestJunebugApi(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.persistencehelper = PersistenceHelper()
        yield self.persistencehelper.setup()
        self.redis = yield self.persistencehelper.get_redis_manager()
        self.logging_handler = logging.handlers.MemoryHandler(100)
        logging.getLogger().addHandler(self.logging_handler)

    def tearDown(self):
        self.logging_handler.close()
        logging.getLogger().removeHandler(self.logging_handler)

    @inlineCallbacks
    def test_save_channel(self):
        channel = Channel(self.redis, {'label': 'test'})
        yield channel.save()
        properties = yield self.redis.get('%s:properties' % channel.id)
        self.assertEqual(json.loads(properties), {'label': 'test'})

    @inlineCallbacks
    def test_delete_channel(self):
        channel = Channel(self.redis, {'label': 'test'})
        yield channel.save()
        properties = yield self.redis.get('%s:properties' % channel.id)
        self.assertEqual(json.loads(properties), {'label': 'test'})

        yield channel.delete()
        properties = yield self.redis.get('%s:properties' % channel.id)
        self.assertEqual(properties, None)

    @inlineCallbacks
    def test_create_channel_from_id(self):
        channel1 = Channel(self.redis, {'label': 'test'})
        yield channel1.save()

        channel2 = yield Channel.from_id(self.redis, channel1.id)
        self.assertEqual(channel1.status, channel2.status)

    @inlineCallbacks
    def test_create_channel_from_unknown_id(self):
        yield self.assertFailure(
            Channel.from_id(self.redis, 'foobar'), ChannelNotFound)

    def test_channel_status(self):
        channel = Channel(self.redis, {'label': 'test'}, 'channel-id')
        self.assertEqual(channel.status, {
            'id': 'channel-id',
            'label': 'test',
            'status': {}
        })
