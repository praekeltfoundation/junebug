from twisted.application.service import MultiService
from twisted.internet import reactor
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

    def startService(self):
        '''Starts the HTTP server, and returns the port object that the server
        is listening on'''
        self._port = reactor.listenTCP(
            self.port, Site(
                JunebugApi(
                    self, self.redis_config, self.amqp_config
                    ).app.resource()),
            interface=self.interface)
        log.msg('Junebug is listening on %s:%s' % (self.interface, self.port))
        return self._port

    def stopService(self):
        '''Stops the HTTP server.'''
        return self._port.stopListening()
