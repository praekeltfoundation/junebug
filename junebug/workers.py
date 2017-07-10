import json
import logging
from urlparse import urlunparse

import treq

from twisted.internet.defer import inlineCallbacks, CancelledError
from twisted.web.client import ResponseFailed
from twisted.internet.error import (
    ConnectingCancelledError, ConnectionDone, ConnectionRefusedError)
from twisted.internet.task import TaskStopped

from vumi.application.base import ApplicationConfig, ApplicationWorker
from vumi.config import (
    ConfigDict, ConfigInt, ConfigText, ConfigFloat, ConfigUrl)
from vumi.message import JSONMessageEncoder
from vumi.persist.txredis_manager import TxRedisManager
from vumi.worker import BaseConfig, BaseWorker

from junebug.utils import api_from_message, api_from_event, api_from_status
from junebug.stores import (
    InboundMessageStore, OutboundMessageStore, StatusStore, MessageRateStore)


class MessageForwardingConfig(ApplicationConfig):
    '''Config for MessageForwardingWorker application worker'''

    mo_message_url = ConfigUrl(
        "The URL to send HTTP POST requests to for MO messages",
        default=None, static=True)

    mo_message_url_auth_token = ConfigText(
        "Authorization Token to use for the mo_message_url",
        default=None, static=True)

    mo_message_url_timeout = ConfigInt(
        "Maximum time (in seconds) a mo_message_url is allowed to take "
        "to process a message",
        default=10, static=True)

    event_url_timeout = ConfigInt(
        "Maximum time (in seconds) an event_url is allowed to take "
        "to process an event",
        default=10, static=True)

    message_queue = ConfigText(
        "The AMQP queue to forward messages on",
        default=None, static=True)

    redis_manager = ConfigDict(
        "Redis config.",
        required=True, static=True)

    inbound_ttl = ConfigInt(
        "Maximum time (in seconds) allowed to reply to messages",
        required=True, static=True)

    outbound_ttl = ConfigInt(
        "Maximum time (in seconds) allowed for events to arrive for messages",
        required=True, static=True)

    metric_window = ConfigFloat(
        "Size of the buckets to use (in seconds) for metrics",
        required=True, static=True)


class MessageForwardingWorker(ApplicationWorker):
    '''This application worker consumes vumi messages placed on a configured
    amqp queue, and sends them as HTTP requests with a JSON body to a
    configured URL'''
    CONFIG_CLASS = MessageForwardingConfig

    @inlineCallbacks
    def setup_application(self):
        self.redis = yield TxRedisManager.from_config(
            self.config['redis_manager'])

        self.inbounds = InboundMessageStore(
            self.redis, self.config['inbound_ttl'])

        self.outbounds = OutboundMessageStore(
            self.redis, self.config['outbound_ttl'])

        self.message_rate = MessageRateStore(self.redis)

        if self.config.get('message_queue') is not None:
            self.ro_connector = yield self.setup_ro_connector(
                self.config['message_queue'])
            self.ro_connector.set_outbound_handler(
                self._publish_message)

    @inlineCallbacks
    def teardown_application(self):
        if getattr(self, 'redis', None) is not None:
            yield self.redis.close_manager()

    @property
    def channel_id(self):
        return self.config['transport_name']

    @inlineCallbacks
    def consume_user_message(self, message):
        '''Sends the vumi message as an HTTP request to the configured URL'''
        yield self.inbounds.store_vumi_message(self.channel_id, message)

        msg = api_from_message(message)

        if self.config.get('mo_message_url') is not None:
            config = self.get_static_config()

            # Parse the basic auth username & password if available
            username = config.mo_message_url.username
            password = config.mo_message_url.password
            if any([username, password]):
                url = urlunparse((
                    config.mo_message_url.scheme,
                    '%s%s' % (
                        config.mo_message_url.hostname,
                        (':%s' % (config.mo_message_url.port,)
                         if config.mo_message_url.port is not None
                         else '')),
                    config.mo_message_url.path,
                    config.mo_message_url.params,
                    config.mo_message_url.query,
                    config.mo_message_url.fragment,
                ))
                auth = (username, password)
            else:
                url = config.mo_message_url.geturl()
                auth = None

            # Construct token auth headers if configured
            auth_token = config.mo_message_url_auth_token
            if auth_token:
                headers = {
                    'Authorization': [
                        'Token %s' % (auth_token,)]
                }
            else:
                headers = {}

            resp = yield post(url, msg,
                              timeout=config.mo_message_url_timeout,
                              auth=auth, headers=headers)
            if resp and request_failed(resp):
                logging.exception(
                    'Error sending message, received HTTP code %r with body %r'
                    '. Message: %r' % (resp.code, (yield resp.content()), msg))

        if self.config.get('message_queue') is not None:
            yield self.ro_connector.publish_inbound(message)

        yield self._increment_metric('inbound')

    @inlineCallbacks
    def store_and_forward_event(self, event):
        '''Store the event in the message store, POST it to the correct
        URL.'''
        yield self._store_event(event)
        yield self._forward_event(event)
        yield self._count_event(event)

    def _increment_metric(self, label):
        return self.message_rate.increment(
            self.channel_id, label, self.config['metric_window'])

    def _count_event(self, event):
        if event['event_type'] == 'ack':
            return self._increment_metric('submitted')
        if event['event_type'] == 'nack':
            return self._increment_metric('rejected')
        if event['event_type'] == 'delivery_report':
            if event['delivery_status'] == 'pending':
                return self._increment_metric('delivery_pending')
            if event['delivery_status'] == 'failed':
                return self._increment_metric('delivery_failed')
            if event['delivery_status'] == 'delivered':
                return self._increment_metric('delivery_succeeded')

    def _store_event(self, event):
        '''Stores the event in the message store'''
        message_id = event['user_message_id']
        if message_id is None:
            logging.warning(
                "Cannot store event, missing user_message_id: %r" % event)
        else:
            return self.outbounds.store_event(
                self.channel_id, message_id, event)

    @inlineCallbacks
    def _forward_event(self, event):
        '''Forward the event to the correct places.'''
        yield self._forward_event_http(event)
        yield self._forward_event_amqp(event)

    @inlineCallbacks
    def _forward_event_http(self, event):
        '''POST the event to the correct URL'''
        url = yield self._get_event_url(event)

        if url is None:
            return

        msg = api_from_event(self.channel_id, event)

        if msg['event_type'] is None:
            logging.exception("Discarding unrecognised event %r" % (event,))
            return

        config = self.get_static_config()
        resp = yield post(url, msg, timeout=config.event_url_timeout)

        if resp and request_failed(resp):
            logging.exception(
                'Error sending event, received HTTP code %r with body %r. '
                'Event: %r' % (resp.code, (yield resp.content()), event))

    def _forward_event_amqp(self, event):
        '''Put the event on the correct queue.'''
        if self.config.get('message_queue') is not None:
            return self.ro_connector.publish_event(event)

    def consume_ack(self, event):
        return self.store_and_forward_event(event)

    def consume_nack(self, event):
        return self.store_and_forward_event(event)

    def consume_delivery_report(self, event):
        return self.store_and_forward_event(event)

    def _get_event_url(self, event):
        msg_id = event['user_message_id']
        if msg_id is not None:
            return self.outbounds.load_event_url(self.channel_id, msg_id)
        else:
            logging.warning(
                "Cannot find event URL, missing user_message_id: %r" % event)


class ChannelStatusConfig(BaseConfig):
    '''Config for the ChannelStatusWorker'''
    redis_manager = ConfigDict(
        "Redis config.",
        required=True, static=True)

    channel_id = ConfigText(
        "The channel id which this worker is consuming statuses for",
        required=True, static=True)

    status_url = ConfigText(
        "Optional url to POST status events to",
        default=None, static=True)

    status_url_timeout = ConfigInt(
        "Maximum time (in seconds) a status_url is allowed to take "
        "to process a status update",
        default=10, static=True)


class ChannelStatusWorker(BaseWorker):
    '''This worker consumes status messages for the transport, and stores them
    in redis. Statuses with the same component are overwritten. It can also
    optionally forward the statuses to a URL'''
    CONFIG_CLASS = ChannelStatusConfig

    @inlineCallbacks
    def setup_connectors(self):
        connector = yield self.setup_receive_status_connector(
            "%s.status" % (self.config['channel_id'],))
        connector.set_status_handler(self.consume_status)

    @inlineCallbacks
    def setup_worker(self):
        redis = yield TxRedisManager.from_config(self.config['redis_manager'])
        self.store = StatusStore(redis, ttl=None)
        yield self.unpause_connectors()

    def teardown_worker(self):
        pass

    @inlineCallbacks
    def consume_status(self, status):
        '''Store the status in redis under the correct component'''
        yield self.store.store_status(self.config['channel_id'], status)

        if self.config.get('status_url') is not None:
            yield self.send_status(status)

    @inlineCallbacks
    def send_status(self, status):
        data = api_from_status(self.config['channel_id'], status)
        config = self.get_static_config()
        resp = yield post(config.status_url, data,
                          timeout=config.status_url_timeout)

        if resp and request_failed(resp):
            logging.exception(
                'Error sending status event, received HTTP code %r with '
                'body %r. Status event: %r'
                % (resp.code, (yield resp.content()), status))


def request_failed(resp):
    return resp.code < 200 or resp.code >= 300


def post_eb(reason, url):
    errors = (
        ResponseFailed,
        ConnectingCancelledError,
        ConnectionDone,
        ConnectionRefusedError,
        TaskStopped,
        # Raised when Deferred is cancelled because of timeouts
        CancelledError,
    )
    err_class = reason.trap(*errors)
    logging.exception('Post to %s failed because of %s: %s' % (
        url, err_class, reason.getErrorMessage()))


def post(url, data, timeout, auth=None, headers={}):
    request_headers = {'Content-Type': ['application/json']}
    request_headers.update(headers)
    d = treq.post(
        url.encode('utf-8'),
        data=json.dumps(data, cls=JSONMessageEncoder),
        headers=request_headers,
        timeout=timeout, auth=auth)
    d.addErrback(post_eb, url)
    return d
