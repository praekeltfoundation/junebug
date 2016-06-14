from twisted.application.service import MultiService
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.python import log
from twisted.web.server import Site

from junebug import JunebugApi


class JunebugService(MultiService, object):
    '''Base service that runs the HTTP API, and contains transports as child
    services'''
    def __init__(self, config):
        super(JunebugService, self).__init__()
        self.config = config

    @inlineCallbacks
    def startService(self):
        '''Starts the HTTP server, and returns the port object that the server
        is listening on'''
        super(JunebugService, self).startService()
        self.api = JunebugApi(self, self.config)
        yield self.api.setup()
        self._port = reactor.listenTCP(
            self.config.port, Site(self.api.app.resource()),
            interface=self.config.interface)
        log.msg(
            'Junebug is listening on %s:%s' %
            (self.config.interface, self.config.port))

    @inlineCallbacks
    def stopService(self):
        '''Stops the HTTP server.'''
        yield self.api.teardown()
        yield self._port.stopListening()
        super(JunebugService, self).stopService()
