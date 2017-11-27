import treq
import urllib

from treq.client import HTTPClient
from twisted.internet import reactor, defer
from twisted.web.client import Agent, HTTPConnectionPool


TPS_LIMIT = 20


class RabbitmqManagementClient(object):

    clock = reactor

    @classmethod
    def pool_factory(self, reactor):
        pool = HTTPConnectionPool(reactor, persistent=True)
        pool.maxPersistentPerHost = TPS_LIMIT

    @classmethod
    def agent_factory(self, reactor, pool=None):
        return Agent(reactor, pool=pool)

    def __init__(self,  base_url, username, password):
        self.base_url = base_url
        self.username = username
        self.password = password

        self.http_client = HTTPClient(self.agent_factory(
            self.clock, pool=self.pool_factory(self.clock)))

        self.semaphore = defer.DeferredSemaphore(TPS_LIMIT)

    def get_queue(self, vhost, queue_name):

        url = 'http://%s/api/queues/%s/%s' % (
            self.base_url,
            urllib.quote(vhost, safe=''),
            queue_name
        )

        def _get_queue():
            d = self.http_client.get(url, auth=(self.username, self.password))
            d.addCallback(treq.json_content)
            return d

        return self.semaphore.run(_get_queue)
