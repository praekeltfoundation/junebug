from math import ceil
import time
from twisted.internet.defer import inlineCallbacks, returnValue

from vumi.message import TransportEvent, TransportUserMessage, TransportStatus


class BaseStore(object):
    '''
    Base class for store classes. Stores data in redis as a hash.

    :param redis: Redis manager
    :type redis: :class:`vumi.persist.redis_manager.RedisManager`
    :param ttl: Expiry time for keys in the store
    :type ttl: integer
    '''

    USE_DEFAULT_TTL = object()

    def __init__(self, redis, ttl=None):
        self.redis = redis
        self.ttl = ttl

    @inlineCallbacks
    def _redis_op(self, func, id, *args, **kwargs):
        ttl = kwargs.pop('ttl')
        if ttl is self.USE_DEFAULT_TTL:
            ttl = self.ttl
        val = yield func(id, *args, **kwargs)
        if ttl is not None:
            yield self.redis.expire(id, ttl)
        returnValue(val)

    def get_key(self, *args):
        '''Returns a key given strings'''
        return ':'.join(args)

    def store_all(self, id, properties, ttl=USE_DEFAULT_TTL):
        '''Stores all of the keys and values given in the dict `properties` as
        a hash at the key `id`'''
        return self._redis_op(self.redis.hmset, id, properties, ttl=ttl)

    def store_property(self, id, key, value, ttl=USE_DEFAULT_TTL):
        '''Stores a single key with a value as a hash at the key `id`'''
        return self._redis_op(self.redis.hset, id, key, value, ttl=ttl)

    @inlineCallbacks
    def load_all(self, id, ttl=USE_DEFAULT_TTL):
        '''Retrieves all the keys and values stored as a hash at the key
        `id`'''
        returnValue((
            yield self._redis_op(self.redis.hgetall, id, ttl=ttl)) or {})

    def load_property(self, id, key, ttl=USE_DEFAULT_TTL):
        return self._redis_op(self.redis.hget, id, key, ttl=ttl)

    def increment_id(self, id, ttl=USE_DEFAULT_TTL):
        '''Increments the value stored at `id` by 1.'''
        return self._redis_op(self.redis.incr, id, 1, ttl=ttl)

    def get_id(self, id, ttl=USE_DEFAULT_TTL):
        '''Returns the value stored at `id`.'''
        return self._redis_op(self.redis.get, id, ttl=ttl)


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
    def get_statuses(self, channel_id):
        '''Returns the latest status message for each component in a
        dictionary'''
        key = self.get_key(channel_id)
        statuses = yield self.load_all(key)
        returnValue(dict(
            (k, TransportStatus.from_json(v))
            for k, v in statuses.iteritems()
        ))


class MessageRateStore(BaseStore):
    '''Gets called everytime a message should be counted, and can return the
    current messages per second.'''

    def get_seconds(self):
        return time.time()

    def get_key(self, channel_id, label, bucket):
        return super(MessageRateStore, self).get_key(
            channel_id, label, str(bucket))

    def _get_current_key(self, channel_id, label, bucket_size):
        bucket = int(self.get_seconds() / bucket_size)
        return self.get_key(channel_id, label, bucket)

    def _get_last_key(self, channel_id, label, bucket_size):
        bucket = int(self.get_seconds() / bucket_size) - 1
        return self.get_key(channel_id, label, bucket)

    def increment(self, channel_id, label, bucket_size):
        '''Increments the correct counter. Should be called whenever a message
        that should be counted is received.

        Note: bucket_size should be kept constant for each channel_id and label
        combination. Changing bucket sizes results in undefined behaviour.'''
        key = self._get_current_key(channel_id, label, bucket_size)
        return self.increment_id(key, ttl=int(ceil(bucket_size * 2)))

    @inlineCallbacks
    def get_messages_per_second(self, channel_id, label, bucket_size):
        '''Gets the current message rate in messages per second.

        Note: bucket_size should be kept constant for each channel_id and label
        combination. Changing bucket sizes results in undefined behaviour.'''
        key = self._get_last_key(channel_id, label, bucket_size)
        rate = yield self.get_id(key, ttl=None)
        if rate is None:
            returnValue(0)
        returnValue(float(rate) / bucket_size)
