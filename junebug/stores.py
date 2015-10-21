import json
from twisted.internet.defer import inlineCallbacks, returnValue

from vumi.message import TransportEvent, TransportUserMessage


class BaseStore(object):
    '''
    Base class for store classes. Stores data in redis as a hash.

    :param redis: Redis manager
    :type redis: :class:`vumi.persist.redis_manager.RedisManager`
    :param ttl: Expiry time for keys in the store
    :type ttl: integer
    '''

    def __init__(self, redis, ttl=None):
        self.redis = redis
        self.ttl = ttl

    @inlineCallbacks
    def _redis_op(self, func, id, *args, **kwargs):
        val = yield func(id, *args, **kwargs)
        if self.ttl is not None:
            yield self.redis.expire(id, self.ttl)
        returnValue(val)

    def get_key(self, *args):
        '''Returns a key given strings'''
        return ':'.join(args)

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

    def get_key(self, channel_id, message_id):
        return super(InboundMessageStore, self).get_key(
            channel_id, 'inbound_messages', message_id)

    def store_vumi_message(self, channel_id, message):
        '''Stores the given vumi message'''
        key = self.get_key(channel_id, message.get('message_id'))
        return self.store_property(key, 'message', message.to_json())

    @inlineCallbacks
    def load_vumi_message(self, channel_id, message_id):
        '''Retrieves the stored vumi message, given its unique id'''
        key = self.get_key(channel_id, message_id)
        msg_json = yield self.load_property(key, 'message')
        if msg_json is None:
            returnValue(None)
        returnValue(TransportUserMessage.from_json(msg_json))


class OutboundMessageStore(BaseStore):
    '''Stores the event url, in order to look it up when deciding where events
    should go'''
    PROPERTY_KEYS = ['event_url']

    def get_key(self, channel_id, message_id):
        return super(OutboundMessageStore, self).get_key(
            channel_id, 'outbound_messages', message_id)

    def store_event_url(self, channel_id, message_id, event_url):
        '''Stores the event_url'''
        key = self.get_key(channel_id, message_id)
        return self.store_property(key, 'event_url', event_url)

    def load_event_url(self, channel_id, message_id):
        '''Retrieves a stored event url, given the channel and message ids'''
        key = self.get_key(channel_id, message_id)
        return self.load_property(key, 'event_url')

    def store_event(self, channel_id, message_id, event):
        '''Stores an event for a message'''
        key = self.get_key(channel_id, message_id)
        event_id = event['event_id']
        return self.store_property(key, event_id, event.to_json())

    @inlineCallbacks
    def load_event(self, channel_id, message_id, event_id):
        '''Loads the event with id event_id'''
        key = self.get_key(channel_id, message_id)
        event_json = yield self.load_property(key, event_id)
        if event_json is None:
            returnValue(None)
        returnValue(TransportEvent.from_json(event_json))

    @inlineCallbacks
    def load_all_events(self, channel_id, message_id):
        '''Returns a list of all the stored events'''
        key = self.get_key(channel_id, message_id)
        events_json = yield self.load_all(key)
        self._remove_property_keys(events_json)
        returnValue([
            TransportEvent.from_json(e) for e in events_json.values()])

    def _remove_property_keys(self, dct):
        '''If we remove all other property keys, we will be left with just the
        events.'''
        for k in self.PROPERTY_KEYS:
            dct.pop(k, None)


class StatusStore(BaseStore):
    '''Stores the most recent status message for each status component.'''

    def get_key(self, channel_id):
        return '%s:status' % channel_id

    def store_status(self, channel_id, status):
        '''Stores a single status. Overrides any previous status with the same
        component.'''
        key = self.get_key(channel_id)
        return self.store_property(key, status['component'], status.to_json())

    @inlineCallbacks
    def get_statuses_dict(self, channel_id):
        '''Returns the latest status message for each component in a
        dictionary'''
        key = self.get_key(channel_id)
        statuses = yield self.load_all(key)
        res = {}
        for k, v in statuses.iteritems():
            res[k] = json.loads(v)
        returnValue(res)
