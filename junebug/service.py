from twisted.application.service import MultiService
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.python import log
from twisted.web.server import Site

from junebug import JunebugApi


class JunebugService(MultiService, object):
    '''Base service that runs the HTTP API, and contains transports as child
    services'''
    def __init__(self, interface, port, redis_config, amqp_config):
        super(JunebugService, self).__init__()
        self.interface = interface
        self.port = port
        self.redis_config = redis_config
        self.amqp_config = amqp_config

    @inlineCallbacks
    def startService(self):
        '''Starts the HTTP server, and returns the port object that the server
        is listening on'''
        self.api = JunebugApi(
            self, self.redis_config, self.amqp_config)
        yield self.api.setup()
        self._port = reactor.listenTCP(
            self.port, Site(self.api.app.resource()),
            interface=self.interface)
        log.msg('Junebug is listening on %s:%s' % (self.interface, self.port))

    @inlineCallbacks
    def stopService(self):
        '''Stops the HTTP server.'''
        yield self.api.teardown()
        yield self._port.stopListening()
