from twisted.internet.defer import inlineCallbacks, returnValue

from junebug.stores import BaseStore
from junebug.tests.helpers import JunebugTestBase


class TestBaseStore(JunebugTestBase):
    @inlineCallbacks
    def create_store(self, id='testid', ttl=60, properties={}):
        redis = yield self.get_redis()
        store = BaseStore(id, properties, redis, ttl)
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
    def test_set_property(self):
        '''Set the property in redis and on the store properties'''
        store = yield self.create_store()
        yield store.set_property('foo', 'bar')
        self.assertEqual((yield self.redis.hget('testid', 'foo')), 'bar')

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
