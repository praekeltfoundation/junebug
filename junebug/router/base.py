from copy import deepcopy
from uuid import uuid4

from junebug.error import JunebugError
from junebug.utils import convert_unicode
from twisted.internet.defer import succeed, maybeDeferred
from twisted.web import http
from vumi.servicemaker import VumiOptions, WorkerCreator
from vumi.utils import load_class_by_string

default_router_types = {
}


class InvalidRouterType(JunebugError):
    '''Raised when an invalid router type is specified'''
    name = 'InvalidRouterType',
    description = 'invalid router type'
    code = http.BAD_REQUEST


class InvalidRouterConfig(JunebugError):
    """Raised when an invalid config is passed to a router worker"""
    name = "InvalidRouterConfig"
    description = "invalid router config"
    code = http.BAD_REQUEST


class Router(object):
    """
    Represents a Junebug Router.
    """
    def __init__(self, router_store, junebug_config, router_config):
        self.router_store = router_store
        self.junebug_config = junebug_config
        self.router_config = router_config

        if self.router_config.get('id', None) is None:
            self.router_config['id'] = str(uuid4())

        self.vumi_options = deepcopy(VumiOptions.default_vumi_options)
        self.vumi_options.update(self.junebug_config.amqp)

    @staticmethod
    def get_all(router_store):
        """
        Returns a list of stored router UUIDs
        """
        return router_store.get_router_list()

    def save(self):
        """
        Saves the router data into the router store.
        """
        return self.router_store.save_router(self.router_config)

    @property
    def _available_router_types(self):
        if self.junebug_config.replace_routers:
            return self.junebug_config.routers
        else:
            routers = {}
            routers.update(default_router_types)
            routers.update(self.junebug_config.routers)
            return routers

    @property
    def _worker_class_name(self):
        cls_name = self._available_router_types.get(self.router_config['type'])

        if cls_name is None:
            raise InvalidRouterType(
                "Invalid router type {}, must be one of: {}".format(
                    self.router_config['type'],
                    ', '.join(self._available_router_types.keys())
                )
            )
        return cls_name

    @property
    def _worker_config(self):
        config = self.router_config['config']
        config = convert_unicode(config)
        return config

    def validate_config(self):
        """
        Passes the config to the specified worker class for validation
        """
        worker_class = load_class_by_string(self._worker_class_name)
        return maybeDeferred(
            worker_class.validate_config, self._worker_config)

    def start(self, service):
        """
        Starts running the router worker as a child of ``service``.
        """
        creator = WorkerCreator(self.vumi_options)
        worker = creator.create_worker(
            self._worker_class_name, self._worker_config)
        worker.setName(self.router_config['id'])
        worker.setServiceParent(service)
        self.router_worker = worker

    def status(self):
        """
        Returns the config and status of this router
        """
        return succeed(self.router_config)
