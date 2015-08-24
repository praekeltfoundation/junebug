from copy import deepcopy
import json
import logging
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from vumi.tests.helpers import PersistenceHelper

from junebug.channel import Channel, ChannelNotFound
from junebug.service import JunebugService


class TestChannel(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.persistencehelper = PersistenceHelper()
        yield self.persistencehelper.setup()
        self.redis = yield self.persistencehelper.get_redis_manager()
        self.logging_handler = logging.handlers.MemoryHandler(100)
        logging.getLogger().addHandler(self.logging_handler)
        self.test_config = {
            'type': 'telnet',
            'config': {
                'transport_name': 'dummy_transport1',
                'twisted_endpoint': 'tcp:0',
            },
            'mo_url': 'http://foo.bar',
            }
        self.service = JunebugService('localhost', 0, self.redis._config, {})

    def tearDown(self):
        self.logging_handler.close()
        logging.getLogger().removeHandler(self.logging_handler)

    def create_channel(self, config=None, id=None):
        if config is None:
            config = self.test_config
        return Channel(
            self.redis._config, {}, config, id=id, parent=self.service)

    def create_channel_from_id(self, id):
        return Channel.from_id(self.redis._config, {}, id, self.service)

    @inlineCallbacks
    def test_save_channel(self):
        channel = self.create_channel()
        yield channel.save()
        properties = yield self.redis.get('%s:properties' % channel.id)
        self.assertEqual(json.loads(properties), self.test_config)

    @inlineCallbacks
    def test_delete_channel(self):
        channel = self.create_channel()
        yield channel.save()
        properties = yield self.redis.get('%s:properties' % channel.id)
        self.assertEqual(json.loads(properties), self.test_config)

        yield channel.delete()
        properties = yield self.redis.get('%s:properties' % channel.id)
        self.assertEqual(properties, None)

    @inlineCallbacks
    def test_create_channel_from_id(self):
        channel1 = self.create_channel()
        yield channel1.save()

        channel2 = yield self.create_channel_from_id(channel1.id)
        self.assertEqual((yield channel1.status()), (yield channel2.status()))

    @inlineCallbacks
    def test_create_channel_from_unknown_id(self):
        yield self.assertFailure(
            self.create_channel_from_id('unknown-id'),
            ChannelNotFound)

    @inlineCallbacks
    def test_channel_status(self):
        channel = self.create_channel(id='channel-id')
        expected_response = deepcopy(self.test_config)
        expected_response['id'] = 'channel-id'
        expected_response['status'] = {}
        self.assertEqual((yield channel.status()), expected_response)

    @inlineCallbacks
    def test_get_all_channels(self):
        channels = yield Channel.get_all(self.redis._config)
        self.assertEqual(channels, set())

        channel1 = self.create_channel()
        yield channel1.save()
        channels = yield Channel.get_all(self.redis._config)
        self.assertEqual(channels, set([channel1.id]))

        channel2 = self.create_channel()
        yield channel2.save()
        channels = yield Channel.get_all(self.redis._config)
        self.assertEqual(channels, set([channel1.id, channel2.id]))
