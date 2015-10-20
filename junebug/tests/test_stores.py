from twisted.internet.defer import inlineCallbacks, returnValue
from vumi.message import TransportEvent, TransportUserMessage, TransportStatus

from junebug.stores import (
    BaseStore, InboundMessageStore, OutboundMessageStore, StatusStore)
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
    def test_load_event_url_not_exist(self):
        '''`None` should be returned if the message cannot be found'''
        store = yield self.create_store()
        self.assertEqual((yield store.load_event_url(
            'bad-channel', 'bad-id')), None)

    @inlineCallbacks
    def test_store_event(self):
        '''Stores the event under the message ID'''
        store = yield self.create_store()
        event = TransportEvent(
            user_message_id='message_id', sent_message_id='message_id',
            event_type='ack')
        yield store.store_event('channel_id', 'message_id', event)

        event_json = yield self.redis.hget(
            'channel_id:outbound_messages:message_id', event['event_id'])
        self.assertEqual(event_json, event.to_json())

    @inlineCallbacks
    def test_load_event(self):
        store = yield self.create_store()
        event = TransportEvent(
            user_message_id='message_id', sent_message_id='message_id',
            event_type='nack', nack_reason='error error')
        yield self.redis.hset(
            'channel_id:outbound_messages:message_id', event['event_id'],
            event.to_json())

        stored_event = yield store.load_event(
            'channel_id', 'message_id', event['event_id'])
        self.assertEqual(stored_event, event)

    @inlineCallbacks
    def test_load_event_not_exist(self):
        '''`None` should be returned if the event doesn't exist'''
        store = yield self.create_store()
        stored_event = yield store.load_event(
            'channel_id', 'message_id', 'bad_event_id')
        self.assertEqual(stored_event, None)

    @inlineCallbacks
    def test_load_all_events_none(self):
        '''Returns an empty list'''
        store = yield self.create_store()
        events = yield store.load_all_events('channel_id', 'message_id')
        self.assertEqual(events, [])

    @inlineCallbacks
    def test_load_all_events_one(self):
        '''Returns a list with one event inside'''
        store = yield self.create_store()
        event = TransportEvent(
            user_message_id='message_id', sent_message_id='message_id',
            event_type='delivery_report', delivery_status='pending')
        yield self.redis.hset(
            'channel_id:outbound_messages:message_id', event['event_id'],
            event.to_json())

        events = yield store.load_all_events('channel_id', 'message_id')
        self.assertEqual(events, [event])

    @inlineCallbacks
    def test_load_all_events_multiple(self):
        '''Returns a list of all the stored events'''
        store = yield self.create_store()
        events = []
        for i in range(5):
            event = TransportEvent(
                user_message_id='message_id', sent_message_id='message_id',
                event_type='delivery_report', delivery_status='pending')
            events.append(event)
            yield self.redis.hset(
                'channel_id:outbound_messages:message_id', event['event_id'],
                event.to_json())

        stored_events = yield store.load_all_events('channel_id', 'message_id')
        self.assertEqual(
            sorted(events, key=lambda e: e['event_id']),
            sorted(stored_events, key=lambda e: e['event_id']))

    @inlineCallbacks
    def test_load_all_events_with_other_stored_fields(self):
        '''Should return just the stored events'''
        store = yield self.create_store()
        event = TransportEvent(
            user_message_id='message_id', sent_message_id='message_id',
            event_type='delivery_report', delivery_status='pending')
        yield self.redis.hset(
            'channel_id:outbound_messages:message_id', event['event_id'],
            event.to_json())
        yield self.redis.hset(
            'channel_id:outbound_messages:message_id', 'event_url',
            'test_url')

        stored_events = yield store.load_all_events('channel_id', 'message_id')
        self.assertEqual(stored_events, [event])


class TestStatusStore(JunebugTestBase):
    @inlineCallbacks
    def create_store(self, ttl=60):
        redis = yield self.get_redis()
        store = StatusStore(redis, ttl)
        returnValue(store)

    @inlineCallbacks
    def test_store_single_status(self):
        '''The single status is stored under the correct key'''
        store = yield self.create_store()
        status = TransportStatus(status='ok', component='foo')
        yield store.store_status('channelid', status)

        status_redis = yield self.redis.hget('channelid:status', 'foo')
        self.assertEqual(status_redis, status.to_json())

        self.assertEqual((yield self.redis.ttl('channelid:status')), None)

    @inlineCallbacks
    def test_store_status_overwrite(self):
        '''New statuses override old statuses with the same component, but do
        not affect statuses of different components'''
        store = yield self.create_store()
        status_old = TransportStatus(status='ok', component='foo')
        status_new = TransportStatus(status='down', component='foo')
        status_other = TransportStatus(status='ok', component='bar')

        yield store.store_status('channelid', status_other)
        yield store.store_status('channelid', status_old)
        yield store.store_status('channelid', status_new)

        status_new_redis = yield self.redis.hget('channelid:status', 'foo')
        self.assertEqual(status_new_redis, status_new.to_json())

        status_other_redis = yield self.redis.hget('channelid:status', 'bar')
        self.assertEqual(status_other_redis, status_other.to_json())
