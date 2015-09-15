from copy import deepcopy
from twisted.internet.defer import inlineCallbacks, returnValue
from vumi.message import TransportUserMessage

from junebug.stores import BaseStore, InboundMessage
from junebug.tests.helpers import JunebugTestBase


class TestBaseStore(JunebugTestBase):
    @inlineCallbacks
    def create_store(self, id='testid', ttl=60, properties={}):
        redis = yield self.get_redis()
        store = BaseStore(id, deepcopy(properties), redis, ttl)
        returnValue(store)

    @inlineCallbacks
    def test_save_all(self):
        '''Stores all the keys and values in a hash in redis, and sets the
        expiry time'''
        store = yield self.create_store()
        store.properties = {
            'foo': 'bar',
            'bar': 'foo',
        }
        yield store.save_all()

        props = yield self.redis.hgetall('testid')
        self.assertEqual(store.properties, props)

        ttl = yield self.redis.ttl('testid')
        self.assertEqual(ttl, 60)

    @inlineCallbacks
    def test_save_property(self):
        '''Saves a single property into redis'''
        store = yield self.create_store()
        store.properties['foo'] = 'bar'
        yield store.save_property('foo')
        self.assertEqual((yield self.redis.hget('testid', 'foo')), 'bar')

    @inlineCallbacks
    def test_save_property_empty(self):
        '''Should save None intp redis if no value for the property exists'''
        store = yield self.create_store()
        yield store.save_property('foo')
        self.assertEqual((yield self.redis.hget('testid', 'foo')), None)

    @inlineCallbacks
    def test_load_all_empty(self):
        '''If no data exists in redis, properties should be an empty dict'''
        store = yield self.create_store()
        yield store.load_all()

        self.assertEqual(store.properties, {})

    @inlineCallbacks
    def test_load_all(self):
        '''If data exists in redis, properties should contain that data'''
        store = yield self.create_store()

        values = {
            'foo': 'bar',
            'bar': 'foo',
        }

        yield self.redis.hmset('testid', values)

        yield store.load_all()
        self.assertEqual(store.properties, values)

    @inlineCallbacks
    def test_load_property(self):
        '''Loads a single property from redis'''
        store = yield self.create_store()

        yield self.redis.hset('testid', 'foo', 'bar')

        yield store.load_property('foo')

        self.assertEqual(store.properties['foo'], 'bar')

    @inlineCallbacks
    def test_load_property_empty(self):
        '''Loads None if property doesn't exist in redis'''
        store = yield self.create_store()

        yield store.load_property('foo')

        self.assertEqual(store.properties['foo'], None)

    @inlineCallbacks
    def test_set_property(self):
        '''Set the property on the store properties'''
        store = yield self.create_store()
        yield store.set_property('foo', 'bar')
        self.assertEqual(store.properties['foo'], 'bar')

    @inlineCallbacks
    def test_get_property(self):
        '''Gets the value of the property from the store'''
        store = yield self.create_store()
        store.properties = {
            'foo': 'bar',
            'bar': 'foo',
        }

        self.assertEqual((yield store.get_property('foo')), 'bar')
        self.assertEqual((yield store.get_property('bar')), 'foo')
        self.assertEqual((yield store.get_property('baz')), None)

    @inlineCallbacks
    def test_from_id(self):
        redis = yield self.get_redis()
        yield redis.hmset('testid', {
            'foo': 'bar',
            'bar': 'foo',
        })
        store = yield BaseStore.from_id('testid', redis, 60)

        self.assertEqual(store.id, 'testid')
        self.assertEqual(store.ttl, 60)
        self.assertEqual(store.properties, {
            'foo': 'bar',
            'bar': 'foo',
            })


class TestInboundMessage(JunebugTestBase):
    @inlineCallbacks
    def test_from_vumi_message(self):
        '''Creates an InboundMessage from a TransportUserMessage'''
        vumi_msg = TransportUserMessage.send(to_addr='+213', content='foo')
        redis = yield self.get_redis()
        message = yield InboundMessage.from_vumi_message(vumi_msg, redis, 60)
        self.assertEqual(vumi_msg.to_json(), message.properties['message'])

    @inlineCallbacks
    def test_vumi_message_property(self):
        '''Returns a vumi message from the stored json'''
        vumi_msg = TransportUserMessage.send(to_addr='+213', content='foo')
        redis = yield self.get_redis()
        message = yield InboundMessage.from_vumi_message(vumi_msg, redis, 60)
        yield message.save_all()

        message = yield InboundMessage.from_id(
            vumi_msg.get('message_id'), redis, 60)
        self.assertEqual(message.vumi_message, vumi_msg)
