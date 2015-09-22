from twisted.internet.defer import inlineCallbacks, returnValue
from vumi.message import TransportUserMessage

from junebug.stores import BaseStore, InboundMessageStore, OutboundMessageStore
from junebug.tests.helpers import JunebugTestBase


class TestBaseStore(JunebugTestBase):
    @inlineCallbacks
    def create_store(self, ttl=60):
        redis = yield self.get_redis()
        store = BaseStore(redis, ttl)
        returnValue(store)

    @inlineCallbacks
    def test_store_all(self):
        '''Stores all the keys and values in a hash in redis, and sets the
        expiry time'''
        store = yield self.create_store()
        properties = {
            'foo': 'bar',
            'bar': 'foo',
        }
        yield store.store_all('testid', properties)

        props = yield self.redis.hgetall('testid')
        self.assertEqual(properties, props)

        ttl = yield self.redis.ttl('testid')
        self.assertEqual(ttl, 60)

    @inlineCallbacks
    def test_store_property(self):
        '''Saves a single property into redis, and sets the expiry time'''
        store = yield self.create_store()
        yield store.store_property('testid', 'foo', 'bar')
        self.assertEqual((yield self.redis.hget('testid', 'foo')), 'bar')
        self.assertEqual((yield self.redis.ttl('testid')), 60)

    @inlineCallbacks
    def test_load_all_empty(self):
        '''If no data exists in redis, properties should be an empty dict'''
        store = yield self.create_store()
        properties = yield store.load_all('testid')

        self.assertEqual(properties, {})

    @inlineCallbacks
    def test_load_all(self):
        '''If data exists in redis, properties should contain that data'''
        store = yield self.create_store()

        properties = {
            'foo': 'bar',
            'bar': 'foo',
        }

        yield self.redis.hmset('testid', properties)

        props = yield store.load_all('testid')
        self.assertEqual(properties, props)

    @inlineCallbacks
    def test_load_property(self):
        '''Loads a single property from redis'''
        store = yield self.create_store()

        yield self.redis.hset('testid', 'foo', 'bar')

        val = yield store.load_property('testid', 'foo')

        self.assertEqual(val, 'bar')

    @inlineCallbacks
    def test_load_property_empty(self):
        '''Loads None if property doesn't exist in redis'''
        store = yield self.create_store()

        val = yield store.load_property('testid', 'foo')

        self.assertEqual(val, None)


class TestInboundMessageStore(JunebugTestBase):
    @inlineCallbacks
    def create_store(self, ttl=60):
        redis = yield self.get_redis()
        store = InboundMessageStore(redis, ttl)
        returnValue(store)

    @inlineCallbacks
    def test_store_vumi_message(self):
        '''Stores the vumi message.'''
        store = yield self.create_store()
        vumi_msg = TransportUserMessage.send(to_addr='+213', content='foo')
        yield store.store_vumi_message('channel_id', vumi_msg)
        msg = yield self.redis.hget(
            'channel_id:inbound_messages:%s' % vumi_msg.get('message_id'),
            'message')
        self.assertEqual(vumi_msg, TransportUserMessage.from_json(msg))

    @inlineCallbacks
    def test_load_vumi_message(self):
        '''Returns a vumi message from the stored json'''
        store = yield self.create_store()
        vumi_msg = TransportUserMessage.send(to_addr='+213', content='foo')
        yield self.redis.hset(
            'channel_id:inbound_messages:%s' % vumi_msg.get('message_id'),
            'message', vumi_msg.to_json())

        message = yield store.load_vumi_message(
            'channel_id', vumi_msg.get('message_id'))
        self.assertEqual(message, vumi_msg)

    @inlineCallbacks
    def test_load_vumi_message_not_exist(self):
        '''`None` should be returned if the message cannot be found'''
        store = yield self.create_store()
        self.assertEqual((yield store.load_vumi_message(
            'bad-channel', 'bad-id')), None)


class TestOutboundMessageStore(JunebugTestBase):
    @inlineCallbacks
    def create_store(self, ttl=60):
        redis = yield self.get_redis()
        store = OutboundMessageStore(redis, ttl)
        returnValue(store)

    @inlineCallbacks
    def test_store_event_url(self):
        '''Stores the event URL under the message ID'''
        store = yield self.create_store()
        yield store.store_event_url(
            'channel_id', 'messageid', 'http://test.org')
        event_url = yield self.redis.hget(
            'channel_id:outbound_messages:messageid', 'event_url')
        self.assertEqual(event_url, 'http://test.org')

    @inlineCallbacks
    def test_load_event_url(self):
        '''Returns a vumi message from the stored json'''
        store = yield self.create_store()
        vumi_msg = TransportUserMessage.send(to_addr='+213', content='foo')
        yield self.redis.hset(
            'channel_id:outbound_messages:%s' % vumi_msg.get('message_id'),
            'event_url', 'http://test.org')

        event_url = yield store.load_event_url(
            'channel_id', vumi_msg.get('message_id'))
        self.assertEqual(event_url, 'http://test.org')

    @inlineCallbacks
    def test_load_vumi_message_not_exist(self):
        '''`None` should be returned if the message cannot be found'''
        store = yield self.create_store()
        self.assertEqual((yield store.load_event_url(
            'bad-channel', 'bad-id')), None)
