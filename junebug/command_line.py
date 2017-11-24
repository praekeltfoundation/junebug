from copy import deepcopy
import argparse
import json
import logging
import logging.handlers
import os
import sys
import yaml

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log
from raven import Client
from raven.transport.twisted import TwistedHTTPTransport

from junebug.service import JunebugService
from junebug.config import JunebugConfig


def create_parser():
    parser = argparse.ArgumentParser(
        description=(
            'Junebug. A system for managing text messaging transports via a '
            'RESTful HTTP interface'))

    parser.add_argument(
        '--config', '-c', dest='config_filename', type=str,
        help='Path to config file. Optional. Command line options override '
             'config options')
    parser.add_argument(
        '--interface', '-i', dest='interface', type=str,
        help='The interface to expose the API on. Defaults to "localhost"')
    parser.add_argument(
        '--port', '-p', dest='port', type=int,
        help='The port to expose the API on, defaults to "8080"')
    parser.add_argument(
        '--log-file', '-l', dest='logfile', type=str,
        help='The file to log to. Defaults to not logging to a file')
    parser.add_argument(
        '--sentry-dsn', '-sd', dest='sentry_dsn', type=str,
        help='The DSN to log exceptions to. Defaults to not logging')
    parser.add_argument(
        '--redis-host', '-redish', dest='redis_host', type=str,
        help='The hostname of the redis instance. Defaults to "localhost"')
    parser.add_argument(
        '--redis-port', '-redisp', dest='redis_port', type=int,
        help='The port of the redis instance. Defaults to "6379"')
    parser.add_argument(
        '--redis-db', '-redisdb', dest='redis_db', type=int,
        help='The database to use for the redis instance. Defaults to "0"')
    parser.add_argument(
        '--redis-password', '-redispass', dest='redis_pass', type=str,
        help='The password to use for the redis instance. Defaults to "None"')
    parser.add_argument(
        '--amqp-host', '-amqph', dest='amqp_host', type=str,
        help='The hostname of the amqp endpoint. Defaults to "127.0.0.1"')
    parser.add_argument(
        '--amqp-vhost', '-amqpvh', dest='amqp_vhost', type=str,
        help='The amqp vhost. Defaults to "/"')
    parser.add_argument(
        '--amqp-port', '-amqpp', dest='amqp_port', type=int,
        help='The port of the amqp endpoint. Defaults to "5672"')
    parser.add_argument(
        '--amqp-user', '-amqpu', dest='amqp_user', type=str,
        help='The username to use for the amqp auth. Defaults to "guest"')
    parser.add_argument(
        '--amqp-password', '-amqppass', dest='amqp_pass', type=str,
        help='The password to use for the amqp auth. Defaults to "guest"')
    parser.add_argument(
        '--inbound-message-ttl', '-ittl', dest='inbound_message_ttl', type=int,
        help='The maximum time allowed to reply to a message (in seconds).'
        'Defaults to 600 seconds (10 minutes).')
    parser.add_argument(
        '--outbound-message-ttl', '-ottl', dest='outbound_message_ttl',
        type=int, help='The maximum time allowed for events to arrive for '
        'messages (in seconds). Defaults to 172800 seconds (2 days)')
    parser.add_argument(
        '--allow-expired-replies', '-aer',
        dest='allow_expired_replies', action='store_true', default=False,
        help="If enabled messages with a reply_to that arrive for which "
        "the original inbound cannot be found (possible of the TTL "
        "expiring) are sent as normal outbound messages. ")
    parser.add_argument(
        '--channels', '-ch', dest='channels', type=str, action='append',
        help='Add a mapping to the list of channels, in the format '
        '"channel_type:python_class".')
    parser.add_argument(
        '--replace-channels', '-rch', dest='replace_channels', type=bool,
        help='If True, replaces the default channels with `channels`. '
        'If False, adds `channels` to the list of default channels. Defaults'
        ' to False.')
    parser.add_argument(
        '--routers', dest='routers', type=str, action='append',
        help='Add a mapping to the list of routers, in the format '
        '"router_type:python_class".')
    parser.add_argument(
        '--replace-routers', dest='replace_routers', type=bool,
        help='If True, replaces the default routers with `routers`. '
        'If False, adds `routers` to the list of default routers. Defaults'
        ' to False.')
    parser.add_argument(
        '--plugin', '-pl', dest='plugins', type=str, action='append',
        help='Add a plugins to the list of plugins, as a json blob of the '
        'plugin config. Must contain a `type` key, with the full python class '
        'path of the plugin')
    parser.add_argument(
        '--metric-window', '-mw', type=float,
        dest='metric_window', help='The size of each bucket '
        '(in seconds) to use for metrics. Defaults to 10 seconds.')
    parser.add_argument(
        '--logging-path', '-lp', type=str,
        dest='logging_path', help='The path to place log files for each '
        'channel. Defaults to `logs/`')
    parser.add_argument(
        '--log-rotate-size', '-lrs', type=int,
        dest='log_rotate_size', help='The maximum size (in bytes) for each '
        'log file before it gets rotated. Defaults to 1000000.')
    parser.add_argument(
        '--max-log-files', '-mlf', type=int,
        dest='max_log_files', help='the maximum number of log files to '
        'keep before deleting old files. defaults to 5. 0 is unlimited.')
    parser.add_argument(
        '--max-logs', '-ml', type=int,
        dest='max_logs', help='the maximum number of log entries to '
        'to allow to be fetched through the API. Defaults to 100.')
    parser.add_argument(
        '--rabbitmq-management-interface', '-rmi',
        dest='rabbitmq_management_interface', type=str,
        help='This should be the url string of the rabbitmq management '
        'interface. If set, the health of each individual queue will be '
        'checked. This is only available for RabbitMQ')

    return parser


def parse_arguments(args):
    '''Parse and return the command line arguments'''
    parser = create_parser()
    return config_from_args(vars(parser.parse_args(args)))


class PythonExceptionFilteringLoggingObserver(log.PythonLoggingObserver):

    def emit(self, eventDict):
        if not eventDict.get('isError') or 'failure' not in eventDict:
            super(PythonExceptionFilteringLoggingObserver, self).emit(
                eventDict)


def logging_setup(filename, sentry_dsn):
    '''Sets up the logging system to output to stdout and filename,
    if filename is not None'''

    LOGGING_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'

    if not os.environ.get('JUNEBUG_DISABLE_LOGGING'):
        # Send Twisted Logs to python logger
        if sentry_dsn:
            PythonExceptionFilteringLoggingObserver().start()
        else:
            log.PythonLoggingObserver().start()

        # Set up stdout logger
        logging.basicConfig(
            level=logging.INFO, format=LOGGING_FORMAT, stream=sys.stdout)

    # Set up file logger
    if filename:
        handler = logging.handlers.RotatingFileHandler(
            filename, maxBytes=1024 * 1024, backupCount=5)
        handler.setFormatter(logging.Formatter(LOGGING_FORMAT))
        logging.getLogger().addHandler(handler)


def sentry_setup(sentry_dsn):
    '''Sets up the exception logging to the provided DSN'''

    if sentry_dsn:
        client = Client(dsn=sentry_dsn, transport=TwistedHTTPTransport)

        def logToSentry(event):
            if not event.get('isError') or 'failure' not in event:
                return

            f = event['failure']
            client.captureException((f.type, f.value, f.getTracebackObject()))

        log.addObserver(logToSentry)


@inlineCallbacks
def start_server(config):
    '''Starts a new Junebug HTTP API server on the specified resource and
    port'''
    service = JunebugService(config)
    yield service.startService()
    returnValue(service)


def main():
    config = parse_arguments(sys.argv[1:])
    logging_setup(config.logfile, config.sentry_dsn)
    sentry_setup(config.sentry_dsn)
    start_server(config)
    reactor.run()


def config_from_args(args):
    args = omit_nones(args)
    config = load_config(args.pop('config_filename', None))
    config['redis'] = parse_redis(config.get('redis', {}), args)
    config['amqp'] = parse_amqp(config.get('amqp', {}), args)
    parse_channels(args)
    parse_routers(args)
    args['plugins'] = parse_plugins(config.get('plugins', []), args)

    combined = conjoin(config, args)

    # max_log_files == 0 means that no limit should be set, so we need to set
    # it to `None` for that case
    combined['max_log_files'] = combined.get('max_log_files') or None

    return JunebugConfig(combined)


def parse_redis(config, args):
    config = conjoin(deepcopy(JunebugConfig.redis.default), config)

    overrides(config, args, {
        'host': 'redis_host',
        'port': 'redis_port',
        'db': 'redis_db',
        'password': 'redis_pass',
    })

    return config


def parse_amqp(config, args):
    config = conjoin(deepcopy(JunebugConfig.amqp.default), config)

    overrides(config, args, {
        'hostname': 'amqp_host',
        'vhost': 'amqp_vhost',
        'port': 'amqp_port',
        'username': 'amqp_user',
        'password': 'amqp_pass',
    })

    return config


def parse_channels(args):
    channels = {}
    for ch in args.get('channels', {}):
        key, value = ch.split(':')
        channels[key] = value

    if len(channels) > 0:
        args['channels'] = channels


def parse_routers(args):
    routers = {}
    for router in args.get('routers', {}):
        key, value = router.split(':')
        routers[key] = value

    # If there are command line arguments, use that to override the config file
    # arguments
    if len(routers) > 0:
        args['routers'] = routers


def parse_plugins(config, args):
    for plugin in args.get('plugins', []):
        plugin = json.loads(plugin)
        config.append(plugin)
    return config


def omit_nones(d):
    return dict((k, v) for k, v in d.iteritems() if v is not None)


def conjoin(a, b):
    result = {}
    result.update(a)
    result.update(b)
    return result


def overrides(target, source, mappings):
    for to_key, from_key in mappings.iteritems():
        if from_key in source:
            target[to_key] = source[from_key]


def load_config(filename):
    if filename is None:
        return {}
    with open(filename) as f:
        config = yaml.safe_load(f)
    return config


if __name__ == '__main__':
    main()
