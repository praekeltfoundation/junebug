from twisted.application.internet import TCPClient
from twisted.application.service import MultiService
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.python import log
from twisted.web import http
from txamqp.client import TwistedDelegate
from txamqp.content import Content
from txamqp.protocol import AMQClient
from vumi.utils import vumi_resource_path
from vumi.service import get_spec

from junebug.error import JunebugError


class AmqpConnectionError(JunebugError):
    '''Exception that is raised whenever a message is attempted to be send,
    but no amqp connection is available to send it on'''
    name = 'AmqpConnectionError'
    description = 'amqp connection error'
    code = http.INTERNAL_SERVER_ERROR


class MessageSender(MultiService):
    '''Keeps track of the amqp connection and can send messages. Raises an
    exception if a message is sent when there is no amqp connection'''
    def __init__(self, specfile, amqp_config):
        super(MessageSender, self).__init__()
        self.amqp_config = amqp_config
        self.factory = AmqpFactory(
            specfile, amqp_config, self._connected_callback,
            self._disconnected_callback)

    def startService(self):
        super(MessageSender, self).startService()
        self.amqp_service = TCPClient(
            self.amqp_config['hostname'], self.amqp_config['port'],
            self.factory)
        self.amqp_service.setServiceParent(self)

    def _connected_callback(self, client):
        self.client = client

    def _disconnected_callback(self):
        self.client = None

    def send_message(self, message, **kwargs):
        if not hasattr(self, 'client') or self.client is None:
            raise AmqpConnectionError(
                'Message not sent, AMQP connection error.')
        return self.client.publish_message(message, **kwargs)


class AmqpFactory(ReconnectingClientFactory, object):
    def __init__(
            self, specfile, amqp_config, connected_callback,
            disconnected_callback):
        '''Factory that creates JunebugAMQClients.
        specfile - string of specfile name
        amqp_config - connection details for amqp server
        '''
        self.connected_callback, self.disconnected_callback = (
            connected_callback, disconnected_callback)
        self.amqp_config = amqp_config
        self.spec = get_spec(vumi_resource_path(specfile))
        self.delegate = TwistedDelegate()
        super(AmqpFactory, self).__init__()

    def buildProtocol(self, addr):
        amqp_client = JunebugAMQClient(
            self.delegate, self.amqp_config['vhost'],
            self.spec, self.amqp_config.get('heartbeat', 0))
        amqp_client.factory = self
        self.resetDelay()
        return amqp_client

    def clientConnectionFailed(self, connector, reason):
        log.err("AmqpFactory connection failed (%s)" % (
            reason.getErrorMessage(),))
        super(AmqpFactory, self).clientConnectionFailed(connector, reason)

    def clientConnectionLost(self, connector, reason):
        log.err("AmqpFactory client connection lost (%s)" % (
            reason.getErrorMessage(),))
        self.disconnected_callback()
        super(AmqpFactory, self).clientConnectionLost(connector, reason)


class RoutingKeyError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class JunebugAMQClient(AMQClient, object):
    exchange_name = "vumi"
    routing_key = "routing_key"
    delivery_mode = 2  # save to disk

    @inlineCallbacks
    def connectionMade(self):
        super(JunebugAMQClient, self).connectionMade()
        yield self.authenticate(self.factory.amqp_config['username'],
                                self.factory.amqp_config['password'])
        # authentication was successful
        log.msg("Got an authenticated AMQP connection")
        self.factory.connected_callback(self)

    @inlineCallbacks
    def get_channel(self):
        """If channel is None a new channel is created"""
        if not hasattr(self, 'cached_channel'):
            channel_id = self.get_new_channel_id()
            channel = yield self.channel(channel_id)
            yield channel.channel_open()
            self.cached_channel = channel
        else:
            channel = self.cached_channel
        returnValue(channel)

    def get_new_channel_id(self):
        """
        AMQClient keeps track of channels in a dictionary. The
        channel ids are the keys, get the highest number and up it
        or just return zero for the first channel
        """
        return (max(self.channels) + 1) if self.channels else 0

    def check_routing_key(self, routing_key):
        if(routing_key != routing_key.lower()):
            raise RoutingKeyError("The routing_key: %s is not all lower case!"
                                  % (routing_key))

    def publish_message(self, message, **kwargs):
        d = self.publish_raw(message.to_json(), **kwargs)
        d.addCallback(lambda r: message)
        return d

    def publish_raw(self, data, **kwargs):
        amq_message = Content(data)
        amq_message['delivery mode'] = kwargs.pop(
            'delivery_mode', self.delivery_mode)
        return self.publish(amq_message, **kwargs)

    @inlineCallbacks
    def publish(self, message, **kwargs):
        exchange_name = kwargs.get('exchange_name') or self.exchange_name
        routing_key = kwargs.get('routing_key') or self.routing_key
        self.check_routing_key(routing_key)
        channel = yield self.get_channel()
        yield channel.basic_publish(
            exchange=exchange_name, content=message, routing_key=routing_key)
