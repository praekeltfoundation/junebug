from twisted.internet.defer import inlineCallbacks, succeed, returnValue


class BaseStore(object):
    '''Base class for store objects. Stores data in redis in a hash.
    redis: redis manager
    ttl: expiry for the key
    id: key to store the hash under
    properties: the keys and values of the hash
    '''

    def __init__(self, id, properties, redis, ttl):
        self.id, self.properties, self.redis, self.ttl = (
            id, properties, redis, ttl)

    @inlineCallbacks
    def save_all(self):
        yield self.redis.hmset(self.id, self.properties)
        yield self.redis.expire(self.id, self.ttl)

    @inlineCallbacks
    def load_all(self):
        self.properties = (yield self.redis.hgetall(self.id)) or {}

    @inlineCallbacks
    def set_property(self, prop, value):
        yield self.redis.hset(self.id, prop, value)
        self.properties[prop] = value

    def get_property(self, prop):
        return succeed(self.properties.get(prop))

    @classmethod
    @inlineCallbacks
    def from_id(cls, id, redis, ttl):
        store = cls(id, {}, redis, ttl)
        yield store.load_all()
        returnValue(store)
