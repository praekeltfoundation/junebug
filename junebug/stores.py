from twisted.internet.defer import inlineCallbacks, succeed, returnValue
from vumi.message import TransportUserMessage


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
    def save_property(self, prop):
        yield self.redis.hset(self.id, prop, self.properties.get(prop))

    @inlineCallbacks
    def load_all(self):
        self.properties = (yield self.redis.hgetall(self.id)) or {}

    @inlineCallbacks
    def load_property(self, prop):
        self.properties[prop] = yield self.redis.hget(self.id, prop)

    def set_property(self, prop, value):
        self.properties[prop] = value
        return succeed(None)

    def get_property(self, prop):
        return succeed(self.properties.get(prop))

    @classmethod
    @inlineCallbacks
    def from_id(cls, id, redis, ttl):
        store = cls(id, {}, redis, ttl)
        yield store.load_all()
        returnValue(store)

class InboundMessage(BaseStore):
    '''Stores the entire inbound message, in order to later construct
    replies'''
    @classmethod
    def from_vumi_message(cls, message, redis, ttl):
        props = {
            'message': message.to_json(),
        }
        msg = cls(message.get('message_id'), props, redis, ttl)
        return succeed(msg)

    @property
    def vumi_message(self):
        return TransportUserMessage.from_json(self.properties.get('message'))
