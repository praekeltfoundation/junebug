from confmodel import Config
from confmodel.fields import ConfigList
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
from vumi.worker import BaseWorker

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


class DestinationNotFound(JunebugError):
    """Raised when we cannot find a destinatino for the given ID"""
    name = "DestinationNotFound"
    description = "destination not found"
    code = http.NOT_FOUND


class Router(object):
    """
    Represents a Junebug Router.
    """
    def __init__(self, api, router_config, destinations=[]):
        self.api = api
        self.router_config = router_config
        self.router_worker = None

        if self.router_config.get('id', None) is None:
            self.router_config['id'] = str(uuid4())

        self.vumi_options = deepcopy(VumiOptions.default_vumi_options)
        self.vumi_options.update(self.api.config.amqp)

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
        router_save = self.api.router_store.save_router(self.router_config)
        dest_save = DeferredList(
            [d.save() for d in self.destinations.values()])
        return DeferredList([router_save, dest_save])

    def delete(self):
        """
        Removes the router data from the router store
        """
        return self.api.router_store.delete_router(self.id)

    @property
    def _available_router_types(self):
        if self.api.config.replace_routers:
            return self.api.config.routers
        else:
            routers = {}
            routers.update(default_router_types)
            routers.update(self.api.config.routers)
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
            worker_class.validate_router_config, self.api, self._worker_config)

    def validate_destination_config(self, config):
        """
        Passes the config to the specified worker class for validation
        """
        worker_class = load_class_by_string(self._worker_class_name)
        return maybeDeferred(
            worker_class.validate_destination_config, self.api, config)

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
    def from_id(cls, api, router_id):
        """
        Restores an existing router, given the router's ID
        """

        def create_router(store_result):
            [router_config, destination_configs] = store_result
            if router_config is None:
                raise RouterNotFound(
                    "Router with ID {} cannot be found".format(router_id))
            return cls(api, router_config, destination_configs)

        d_router = api.router_store.get_router_config(router_id)

        d_dests = api.router_store.get_router_destination_list(router_id)
        d_dests.addCallback(partial(
            map, partial(
                api.router_store.get_router_destination_config, router_id)))
        d_dests.addCallback(gatherResults)

        d = gatherResults([d_router, d_dests])
        d.addCallback(create_router)
        d.addCallback(lambda router: router._restore(api.service))
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

    def get_destination(self, destination_id):
        destination = self.destinations.get(destination_id)
        if destination is None:
            raise DestinationNotFound(
                'Cannot find destination with ID {} for router {}'.format(
                    destination_id, self.id))
        return destination


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
        return self.router.api.router_store.save_router_destination(
            self.router.id, self.destination_config)

    def status(self):
        """
        Returns the config and status of this destination
        """
        return succeed(self.destination_config)

    def delete(self):
        """
        Removes this destination from the store and from the router.
        """
        self.router.destinations.pop(self.id)
        return self.router.api.router_store.delete_router_destination(
            self.router.id, self.id)


class BaseRouterConfig(BaseWorker.CONFIG_CLASS):
    destinations = ConfigList(
        "The list of configs for the configured destinations of this router",
        required=True, static=True)


class BaseDestinationConfig(Config):
    pass


class BaseRouterWorker(BaseWorker):
    """
    The base class that all Junebug routers should inherit from.
    """
    UNPAUSE_CONNECTORS = True
    CONFIG_CLASS = BaseRouterConfig
    DESTINATION_CONFIG_CLASS = BaseDestinationConfig

    @classmethod
    def validate_router_config(cls, api, config):
        """
        Should raise an InvalidRouterConfig if the supplied router config is
        not valid. Should be implemented by router implementation.
        """

    @classmethod
    def validate_destination_config(cls, api, config):
        """
        Should raise an InvalidRouterDestinationConfig if the supplied
        destination config is invalid. Should be implemented by router
        implementation.
        """

    def setup_router(self):
        """
        Any startup that the router implementation needs to perform should be
        done here. May return a deferred.
        """

    def teardown_router(self):
        """
        Any teardown that the router implementation needs to perform should be
        done here. May return a deferred.
        """

    def setup_connectors(self):
        # Connector setup is performed by the class implementation in
        # setup_router
        pass

    def setup_worker(self):
        """
        Logic to start the router. Should not be overridden by router
        implementation. Router setup should rather be performed in
        ``setup_router``.
        """
        self.log.msg('Starting a {} router with config: {}'.format(
            self.__class__.__name__, self.config))

        config = self.get_static_config()
        self.destinations = [
            self.DESTINATION_CONFIG_CLASS(d) for d in config.destinations]

        d = maybeDeferred(self.setup_router)

        if self.UNPAUSE_CONNECTORS:
            d.addCallback(lambda r: self.unpause_connectors())

        return d

    def teardown_worker(self):
        """
        Logic to stop the router. Should not be overridden by router
        implementation. Router shutdown should rather be implemented in
        ``teardown_router``.
        """
        d = self.pause_connectors()
        return d.addCallback(lambda r: self.teardown_router())
