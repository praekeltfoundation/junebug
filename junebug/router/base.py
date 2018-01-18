from confmodel.fields import ConfigDict, ConfigFloat, ConfigInt, ConfigList
from copy import deepcopy
from functools import partial
from uuid import uuid4

from junebug.error import JunebugError
from junebug.utils import convert_unicode
from junebug.workers import MessageForwardingWorker
from junebug.logging_service import JunebugLoggerService, read_logs
from twisted.internet.defer import (
    DeferredList, gatherResults, succeed, maybeDeferred, inlineCallbacks)
from twisted.web import http
from vumi.servicemaker import VumiOptions, WorkerCreator
from vumi.utils import load_class_by_string
from vumi.worker import BaseWorker

default_router_types = {
    'from_address': "junebug.router.FromAddressRouter",
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
    JUNEBUG_LOGGING_SERVICE_CLS = JunebugLoggerService

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

    def _create_junebug_logger_service(self):
        return self.JUNEBUG_LOGGING_SERVICE_CLS(
            self.id, self.api.config.logging_path,
            self.api.config.log_rotate_size,
            self.api.config.max_log_files)

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
        config['redis_manager'] = self.api.redis_config
        config['inbound_ttl'] = self.api.config.inbound_message_ttl
        config['outbound_ttl'] = self.api.config.outbound_message_ttl
        config['metric_window'] = self.api.config.metric_window
        config['worker_name'] = self.id
        config = convert_unicode(config)
        return config

    def validate_config(self):
        """
        Passes the config to the specified worker class for validation
        """
        worker_class = load_class_by_string(self._worker_class_name)
        return maybeDeferred(
            worker_class.validate_router_config, self.api, self._worker_config,
            self.router_config.get('id'))

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

        logging_service = self._create_junebug_logger_service()
        worker.addService(logging_service)

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
    @inlineCallbacks
    def start_all_routers(cls, api):
        for r_id in (yield api.router_store.get_router_list()):
            if r_id not in api.service.namedServices:
                router = yield cls.from_id(api, r_id)
                yield router.start(api.service)

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

    def get_logs(self, n):
        '''Returns the last `n` logs. If `n` is greater than the configured
        limit, only returns the configured limit amount of logs. If `n` is
        None, returns the configured limit amount of logs.'''
        if n is None:
            n = self.api.config.max_logs
        n = min(n, self.api.config.max_logs)
        logfile = self.router_worker.getServiceNamed(
            'Junebug Worker Logger').logfile
        return read_logs(logfile, n)


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


class BaseRouterWorkerConfig(BaseWorker.CONFIG_CLASS):
    destinations = ConfigList(
        "The list of configs for the configured destinations of this router",
        required=True, static=True)
    redis_manager = ConfigDict(
        "Redis config.",
        required=True, static=True)
    inbound_ttl = ConfigInt(
        "Maximum time (in seconds) allowed to reply to messages",
        required=True, static=True)
    outbound_ttl = ConfigInt(
        "Maximum time (in seconds) allowed for events to arrive for messages",
        required=True, static=True)
    metric_window = ConfigFloat(
        "Size of the buckets to use (in seconds) for metrics",
        required=True, static=True)


class BaseRouterWorker(BaseWorker):
    """
    The base class that all Junebug routers should inherit from.
    """
    CONFIG_CLASS = BaseRouterWorkerConfig
    DESTINATION_WORKER_CLASS = MessageForwardingWorker

    @classmethod
    def validate_router_config(cls, api, config, router_id=None):
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

    def get_destination_channel(self, destination_id, message_body):
        """
        Gets the channel associated with the specified destination. The
        message_body will always be supplied. Should be implemented by router
        implementation.
        """

    def setup_connectors(self):
        # Connector setup is performed by the class implementation in
        # setup_router
        pass

    def _create_worker(self, worker_class, config):
        return WorkerCreator(self.options).create_worker_by_class(
            worker_class, config)

    def _destination_worker_config(self, config):
        router_config = self.get_static_config()
        return {
            'transport_name': config['id'],
            'mo_message_url': config.get('mo_url'),
            'mo_message_auth_token': config.get('mo_url_auth_token'),
            'message_queue': config.get('amqp_queue'),
            'redis_manager': router_config.redis_manager,
            'inbound_ttl': router_config.inbound_ttl,
            'outbound_ttl': router_config.outbound_ttl,
            'metric_window': router_config.metric_window,
        }

    def _start_destinations(self, destinations):
        destination_connectors = []
        destination_workers = []

        for d in destinations:
            worker = maybeDeferred(
                self._create_worker,
                self.DESTINATION_WORKER_CLASS,
                self._destination_worker_config(d)
            )
            worker.addCallback(lambda w: w.setName(d['id']) or w)
            worker.addCallback(lambda w: w.setServiceParent(self))
            destination_workers.append(worker)

            connector = self.setup_ro_connector(d['id'])
            destination_connectors.append(connector)

        return gatherResults(destination_workers + destination_connectors)

    def setup_worker(self):
        """
        Logic to start the router. Should not be overridden by router
        implementation. Router setup should rather be performed in
        ``setup_router``.
        """
        self.log.msg('Starting a {} router with config: {}'.format(
            self.__class__.__name__, self.config))

        config = self.get_static_config()
        d1 = self._start_destinations(config.destinations)

        d2 = maybeDeferred(self.setup_router)

        d = gatherResults([d1, d2])
        d.addCallback(lambda _: self.unpause_connectors())
        return d

    def teardown_worker(self):
        """
        Logic to stop the router. Should not be overridden by router
        implementation. Router shutdown should rather be implemented in
        ``teardown_router``.
        """
        d = self.pause_connectors()
        return d.addCallback(lambda r: self.teardown_router())

    def consume_channel(self, channel_id, message_callback, event_callback):
        """
        Attaches callback functions for inbound messages and events for the
        specified channel ID. Callback functions take 2 args, the channel id
        and the message or event. Will only work for channels that do not have
        an amqp_queue or mo_url defined.
        """
        d = self.setup_ri_connector(channel_id)

        inbound_handler = partial(message_callback, channel_id)
        event_handler = partial(event_callback, channel_id)

        def attach_callbacks(connector):
            connector.set_inbound_handler(inbound_handler)
            connector.set_event_handler(event_handler)
            return connector

        return d.addCallback(attach_callbacks)

    def consume_destination(self, destination_id, message_callback):
        """
        Attaches a callback function for outbound messages from the specified
        destination ID. Callback functions will take 2 args, the destination id
        and the message.
        """
        outbound_handler = partial(message_callback, destination_id)
        self.connectors[destination_id].set_outbound_handler(outbound_handler)

    def send_inbound_to_destination(self, destination_id, message):
        """
        Publishes a message to the specified message forwarding worker.
        """
        return self.connectors[destination_id].publish_inbound(message)

    def send_event_to_destination(self, destination_id, event):
        """
        Publishes an event to the specified message forwarding worker.
        """
        return self.connectors[destination_id].publish_event(event)

    def send_outbound_to_channel(self, channel_id, message):
        """
        Publishes a message to the provided channel. Channel needs to first be
        set up using ``consume_channel`` before you can publish to it.
        """
        return self.connectors[channel_id].publish_outbound(message)
