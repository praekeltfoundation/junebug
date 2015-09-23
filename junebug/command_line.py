from copy import deepcopy
import argparse
import logging
import logging.handlers
import sys
import yaml

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

from junebug.service import JunebugService
from junebug.config import JunebugConfig


def parse_arguments(args):
    '''Parse and return the command line arguments'''

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

    return config_from_args(vars(parser.parse_args(args)))


def logging_setup(filename):
    '''Sets up the logging system to output to stdout and filename,
    if filename is not None'''

    LOGGING_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'

    # Send Twisted Logs to python logger
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


@inlineCallbacks
def start_server(config):
    '''Starts a new Junebug HTTP API server on the specified resource and
    port'''
    service = JunebugService(config)
    yield service.startService()
    returnValue(service)


def main():
    config = parse_arguments(sys.argv[1:])
    logging_setup(config.logfile)
    start_server(config)
    reactor.run()


def config_from_args(args):
    args = omit_nones(args)
    config = load_config(args.pop('config_filename', None))
    config['redis'] = parse_redis(config.get('redis', {}), args)
    config['amqp'] = parse_amqp(config.get('amqp', {}), args)
    return JunebugConfig(conjoin(config, args))


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
    return yaml.safe_load(filename) if filename is not None else {}


if __name__ == '__main__':
    main()
