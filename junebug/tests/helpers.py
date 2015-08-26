import logging
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase
from vumi.tests.helpers import PersistenceHelper, WorkerHelper

from junebug.channel import Channel
from junebug.service import JunebugService


class JunebugTestBase(TestCase):
    '''Base test case that all junebug tests inherit from. Contains useful
    helper functions'''

    default_channel_config = {
            'type': 'telnet',
            'config': {
                'transport_name': 'dummy_transport1',
                'twisted_endpoint': 'tcp:0',
            },
            'mo_url': 'http://foo.bar',
        }

    def patch_logger(self):
        ''' Patches the logger with an in-memory logger, which is acccessable
        at "self.logging_handler".'''
        self.logging_handler = logging.handlers.MemoryHandler(100)
        logging.getLogger().addHandler(self.logging_handler)
        self.addCleanup(self._cleanup_logging_patch)

    def _cleanup_logging_patch(self):
        self.logging_handler.close()
        logging.getLogger().removeHandler(self.logging_handler)

    @inlineCallbacks
    def create_channel(
            self, service, redis, transport_class,
            config=default_channel_config, id=None):
        '''Creates and starts, and saves a channel, with a
        TelnetServerTransport transport'''
        channel = Channel(redis._config, {}, config, id=id)
        config['config']['worker_name'] = channel.id
        transport_worker = yield WorkerHelper().get_worker(
            transport_class, config['config'])
        yield channel.start(self.service, transport_worker)
        yield channel.save()
        self.addCleanup(channel.stop)
        returnValue(channel)

    def create_channel_from_id(self, service, redis, id):
        '''Creates an existing channel given the channel id'''
        return Channel.from_id(redis._config, {}, id, service)

    @inlineCallbacks
    def get_redis(self):
        '''Creates and returns a redis manager'''
        if hasattr(self, 'redis'):
            returnValue(self.redis)
        persistencehelper = PersistenceHelper()
        yield persistencehelper.setup()
        self.redis = yield persistencehelper.get_redis_manager()
        returnValue(self.redis)

    @inlineCallbacks
    def start_server(self):
        '''Starts a junebug server. Stores the service to "self.service", and
        the url at "self.url"'''
        redis = yield self.get_redis()
        self.service = JunebugService('localhost', 0, redis._config, {})
        server = yield self.service.startService()
        addr = server.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)
        self.addCleanup(self.service.stopService)

    @inlineCallbacks
    def patch_worker_creation(
            self, transport_class, config=default_channel_config):
        '''Patches the channel start function to start a worker with the given
        worker class and config using a worker helper.'''
        worker_helper = WorkerHelper()
        transport_worker = yield worker_helper.get_worker(
            transport_class, config['config'])
        yield transport_worker.startService()
        self.addCleanup(transport_worker.stopService)
        self._original_channel_start = old_start = Channel.start

        def new_start(self, service):
            return old_start(
                self, service, transport_worker)

        Channel.start = new_start
        self.addCleanup(self._unpatch_worker_creation)

    def _unpatch_worker_creation(self):
        Channel.start = self._original_channel_start
