from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web import http
from vumi.message import TransportUserMessage

from junebug.error import JunebugError


class MessageNotFound(JunebugError):
    '''Raised when a message cannot be found.'''
    name = 'MessageNotFound'
    description = 'message not found'
    code = http.NOT_FOUND


class BaseStore(object):
    '''Base class for store objects. Stores data in redis in a hash.
    redis: redis manager
    ttl: expiry for the key
    '''

    def __init__(self, redis, ttl):
        self.redis, self.ttl = redis, ttl

    @inlineCallbacks
    def _redis_op(self, func, id, *args, **kwargs):
        val = yield func(id, *args, **kwargs)
        yield self.redis.expire(id, self.ttl)
        returnValue(val)

    def store_all(self, id, properties):
        '''Stores all of the keys and values given in the dict `properties` as
        a hash at the key `id`'''
        return self._redis_op(self.redis.hmset, id, properties)

    def store_property(self, id, key, value):
        '''Stores a single key with a value as a hash at the key `id`'''
        return self._redis_op(self.redis.hset, id, key, value)

    @inlineCallbacks
    def load_all(self, id):
        '''Retrieves all the keys and values stored as a hash at the key
        `id`'''
        returnValue((yield self._redis_op(self.redis.hgetall, id)) or {})

    def load_property(self, id, key):
        return self._redis_op(self.redis.hget, id, key)


class InboundMessageStore(BaseStore):
    '''Stores the entire inbound message, in order to later construct
    replies'''
    def store_vumi_message(self, message):
        '''Stores the given vumi message'''
        return self.store_property(
            message.get('message_id'), 'message', message.to_json())

    @inlineCallbacks
    def load_vumi_message(self, message_id):
        '''Retrieves the stored vumi message, given its unique id'''
        msg_json = yield self.load_property(message_id, 'message')
        if msg_json is None:
            raise MessageNotFound(
                'Cannot find message with id %s' % (message_id,))
        returnValue(TransportUserMessage.from_json(msg_json))
