from twisted.internet.defer import inlineCallbacks, returnValue, Deferred
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.python import log
from txamqp.client import TwistedDelegate
from txamqp.content import Content
from txamqp.protocol import AMQClient
from vumi.utils import vumi_resource_path
from vumi.service import get_spec


class AmqpFactory(ReconnectingClientFactory, object):
    def __init__(self, specfile, amqp_config):
        '''Factory that creates JunebugAMQClients.
        specfile - string of specfile name
        amqp_config - connection details for amqp server
        '''
        self.amqp_config = amqp_config
        self.spec = get_spec(vumi_resource_path(specfile))
        self.delegate = TwistedDelegate()
        self.amqp_client_d = Deferred()

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
        self.amqp_client_d = Deferred()
        super(AmqpFactory, self).clientConnectionLost(connector, reason)

    @inlineCallbacks
    def get_client(self):
        '''Returns a deferred that fires with a connected client'''
        if not self.amqp_client_d.called:
            yield self.amqp_client_d
        returnValue(self.amqp_client)


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
        self.factory.amqp_client = self
        self.factory.amqp_client_d.callback(None)

    @inlineCallbacks
    def get_channel(self, channel_id=None):
        """If channel_id is None a new channel is created"""
        if channel_id:
            channel = self.channels[channel_id]
        else:
            channel_id = self.get_new_channel_id()
            channel = yield self.channel(channel_id)
            yield channel.channel_open()
            self.channels[channel_id] = channel
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
