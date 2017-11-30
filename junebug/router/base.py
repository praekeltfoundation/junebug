from copy import deepcopy
from functools import partial
from uuid import uuid4

from junebug.error import JunebugError
from junebug.utils import convert_unicode
from twisted.internet.defer import (
    DeferredList, gatherResults, succeed, maybeDeferred)
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


class InvalidRouterDestinationConfig(JunebugError):
    """Raised when an invalid destination config is passed to a router worker
    """
    name = "InvalidRouterDestinationConfig"
    description = "invalid router destination config"
    code = http.BAD_REQUEST


class RouterNotFound(JunebugError):
    """Raised when we cannot find a router for the given ID"""
    name = "RouterNotFound"
    description = "router not found"
    code = http.NOT_FOUND


class Router(object):
    """
    Represents a Junebug Router.
    """
    def __init__(
            self, router_store, junebug_config, router_config,
            destinations=[]):
        self.router_store = router_store
        self.junebug_config = junebug_config
        self.router_config = router_config
        self.router_worker = None

        if self.router_config.get('id', None) is None:
            self.router_config['id'] = str(uuid4())

        self.vumi_options = deepcopy(VumiOptions.default_vumi_options)
        self.vumi_options.update(self.junebug_config.amqp)

        self.destinations = {
            d['id']: Destination(self, d) for d in destinations}

    @property
    def id(self):
        return self.router_config['id']

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
        router_save = self.router_store.save_router(self.router_config)
        dest_save = DeferredList(
            [d.save() for d in self.destinations.values()])
        return DeferredList([router_save, dest_save])

    def delete(self):
        """
        Removes the router data from the router store
        """
        return self.router_store.delete_router(self.id)

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
    def _destination_configs(self):
        return [d.destination_config for d in self.destinations.values()]

    @property
    def _worker_config(self):
        config = deepcopy(self.router_config['config'])
        config['destinations'] = self._destination_configs
        config = convert_unicode(config)
        return config

    def validate_config(self):
        """
        Passes the config to the specified worker class for validation
        """
        worker_class = load_class_by_string(self._worker_class_name)
        return maybeDeferred(
            worker_class.validate_config, self._worker_config)

    def validate_destination_config(self, config):
        """
        Passes the config to the specified worker class for validation
        """
        worker_class = load_class_by_string(self._worker_class_name)
        return maybeDeferred(
            worker_class.validate_destination_config, config)

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

    def stop(self):
        """
        Stops the router from running
        """
        if self.router_worker:
            worker = self.router_worker
            self.router_worker = None
            return worker.disownServiceParent()
        return succeed(None)

    def status(self):
        """
        Returns the config and status of this router
        """
        return succeed(self.router_config)

    def _restore(self, service):
        self.router_worker = service.namedServices.get(
            self.router_config['id'])
        return self

    @classmethod
    def from_id(cls, router_store, junebug_config, parent_service, router_id):
        """
        Restores an existing router, given the router's ID
        """

        def create_router(store_result):
            [router_config, destination_configs] = store_result
            if router_config is None:
                raise RouterNotFound(
                    "Router with ID {} cannot be found".format(router_id))
            return cls(
                router_store, junebug_config, router_config,
                destination_configs)

        d_router = router_store.get_router_config(router_id)

        d_dests = router_store.get_router_destination_list(router_id)
        d_dests.addCallback(partial(
            map, partial(
                router_store.get_router_destination_config, router_id)))
        d_dests.addCallback(gatherResults)

        d = gatherResults([d_router, d_dests])
        d.addCallback(create_router)
        d.addCallback(lambda router: router._restore(parent_service))
        return d

    def add_destination(self, destination_config):
        """
        Create a destination with the specified config
        """
        destination = Destination(self, destination_config)
        self.destinations[destination.id] = destination
        return destination

    def get_destination_list(self):
        """
        Returns a list of all the destinations for this router
        """
        return sorted(self.destinations.keys())


class Destination(object):
    """
    Represents a Junebug Router Destination.
    """
    def __init__(self, router, destination_config):
        self.router = router
        self.destination_config = destination_config

        if self.destination_config.get('id', None) is None:
            self.destination_config['id'] = str(uuid4())

    @property
    def id(self):
        return self.destination_config['id']

    def save(self):
        """
        Saves this destination to the router store
        """
        return self.router.router_store.save_router_destination(
            self.router.id, self.destination_config)

    def status(self):
        """
        Returns the config and status of this destination
        """
        return succeed(self.destination_config)
