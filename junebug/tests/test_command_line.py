import json
import logging
import os.path
import sys
from twisted.internet.defer import inlineCallbacks
from twisted.python import log
from mock import patch
from raven import Client


import junebug
from junebug import JunebugApi
from junebug.command_line import (
    parse_arguments, logging_setup, start_server, sentry_setup)
from junebug.tests.helpers import JunebugTestBase
from junebug.config import JunebugConfig


class TestCommandLine(JunebugTestBase):
    def setUp(self):
        self.old_setup = JunebugApi.setup
        self.old_teardown = JunebugApi.teardown

        def do_nothing(self):
            pass

        JunebugApi.setup = do_nothing
        JunebugApi.teardown = do_nothing

    def tearDown(self):
        JunebugApi.setup = self.old_setup
        JunebugApi.teardown = self.old_teardown

    def patch_yaml_load(self, mappings):
        self.patch(junebug.command_line, 'load_config', mappings.get)

    def test_load_config(self):
        '''Given a filename with the file containing yaml content, the
        load_config function should load the yaml file.'''
        filename = self.mktemp()
        with open(filename, 'w') as f:
            f.write('''
                foo: bar
            ''')
        config = junebug.command_line.load_config(filename)
        self.assertEqual(config, {'foo': 'bar'})

    def test_load_config_none(self):
        '''If the filename is None, return an empty object'''
        config = junebug.command_line.load_config(None)
        self.assertEqual(config, {})

    def test_parse_arguments_interface(self):
        '''The interface command line argument can be specified by
        "--interface" and "-i" and has a default value of "localhost"'''
        config = parse_arguments([])
        self.assertEqual(config.interface, 'localhost')

        config = parse_arguments(['--interface', 'foobar'])
        self.assertEqual(config.interface, 'foobar')

        config = parse_arguments(['-i', 'foobar'])
        self.assertEqual(config.interface, 'foobar')

    def test_parse_arguments_port(self):
        '''The port command line argument can be specified by
        "--port" or "-p" and has a default value of 8080'''
        config = parse_arguments([])
        self.assertEqual(config.port, 8080)

        config = parse_arguments(['--port', '80'])
        self.assertEqual(config.port, 80)

        config = parse_arguments(['-p', '80'])
        self.assertEqual(config.port, 80)

    def test_parse_arguments_log_file(self):
        '''The log file command line argument can be specified by
        "--log-file" or "-l" and has a default value of None'''
        config = parse_arguments([])
        self.assertEqual(config.logfile, None)

        config = parse_arguments(['--log-file', 'foo.bar'])
        self.assertEqual(config.logfile, 'foo.bar')

        config = parse_arguments(['-l', 'foo.bar'])
        self.assertEqual(config.logfile, 'foo.bar')

    def test_parse_arguments_redis_host(self):
        '''The redis host command line argument can be specified by
        "--redis-host" or "-redish" and has a default value of "localhost"'''
        config = parse_arguments([])
        self.assertEqual(config.redis['host'], 'localhost')

        config = parse_arguments(['--redis-host', 'foo.bar'])
        self.assertEqual(config.redis['host'], 'foo.bar')

        config = parse_arguments(['-redish', 'foo.bar'])
        self.assertEqual(config.redis['host'], 'foo.bar')

    def test_parse_arguments_redis_config_port(self):
        '''The redis port command line argument can be specified by
        "--redis-port" or "-redisp" and has a default value of 6379'''
        config = parse_arguments([])
        self.assertEqual(config.redis['port'], 6379)

        config = parse_arguments(['--redis-port', '80'])
        self.assertEqual(config.redis['port'], 80)

        config = parse_arguments(['-redisp', '80'])
        self.assertEqual(config.redis['port'], 80)

    def test_parse_arguments_redis_database(self):
        '''The redis database command line argument can be specified by
        "--redis-db" or "-redisdb" and has a default value of 0'''
        config = parse_arguments([])
        self.assertEqual(config.redis['db'], 0)

        config = parse_arguments(['--redis-db', '80'])
        self.assertEqual(config.redis['db'], 80)

        config = parse_arguments(['-redisdb', '80'])
        self.assertEqual(config.redis['db'], 80)

    def test_parse_arguments_redis_password(self):
        '''The redis password command line argument can be specified by
        "--redis-password" or "-redispass" and has a default value of None'''
        config = parse_arguments([])
        self.assertEqual(config.redis['password'], None)

        config = parse_arguments(['--redis-password', 'foo.bar'])
        self.assertEqual(config.redis['password'], 'foo.bar')

        config = parse_arguments(['-redispass', 'foo.bar'])
        self.assertEqual(config.redis['password'], 'foo.bar')

    def test_parse_arguments_amqp_host(self):
        '''The amqp host command line argument can be specified by
        "--amqp-host" or "-amqph" and has a default value of "127.0.0.1"'''
        config = parse_arguments([])
        self.assertEqual(config.amqp['hostname'], '127.0.0.1')

        config = parse_arguments(['--amqp-host', 'foo.bar'])
        self.assertEqual(config.amqp['hostname'], 'foo.bar')

        config = parse_arguments(['-amqph', 'foo.bar'])
        self.assertEqual(config.amqp['hostname'], 'foo.bar')

    def test_parse_arguments_amqp_port(self):
        '''The amqp port command line argument can be specified by
        "--amqp-port" or "-amqpp" and has a default value of 5672'''
        config = parse_arguments([])
        self.assertEqual(config.amqp['port'], 5672)

        config = parse_arguments(['--amqp-port', '80'])
        self.assertEqual(config.amqp['port'], 80)

        config = parse_arguments(['-amqpp', '80'])
        self.assertEqual(config.amqp['port'], 80)

    def test_parse_arguments_amqp_username(self):
        '''The amqp username command line argument can be specified by
        "--amqp-user" or "-amqpu" and has a default value of "guest"'''
        config = parse_arguments([])
        self.assertEqual(config.amqp['username'], 'guest')

        config = parse_arguments(['--amqp-user', 'test'])
        self.assertEqual(config.amqp['username'], 'test')

        config = parse_arguments(['-amqpu', 'test'])
        self.assertEqual(config.amqp['username'], 'test')

    def test_parse_arguments_amqp_password(self):
        '''The amqp password command line argument can be specified by
        "--amqp-password" or "-amqppass" and has a default value of "guest"'''
        config = parse_arguments([])
        self.assertEqual(config.amqp['password'], 'guest')

        config = parse_arguments(['--amqp-password', 'foo.bar'])
        self.assertEqual(config.amqp['password'], 'foo.bar')

        config = parse_arguments(['-amqppass', 'foo.bar'])
        self.assertEqual(config.amqp['password'], 'foo.bar')

    def test_parse_arguments_amqp_vhost(self):
        '''The amqp vhost command line argument can be specified by
        "--amqp-vhost" or "-amqpv" and has a default value of "/"'''
        config = parse_arguments([])
        self.assertEqual(config.amqp['vhost'], '/')

        config = parse_arguments(['--amqp-vhost', 'foo.bar'])
        self.assertEqual(config.amqp['vhost'], 'foo.bar')

        config = parse_arguments(['-amqpv', 'foo.bar'])
        self.assertEqual(config.amqp['vhost'], 'foo.bar')

    def test_parse_arguments_inbound_ttl(self):
        '''The inbound ttl command line argument can be specified by
        "--inbound-message-ttl" or "-ittl" and has a default value of
        10 minutes'''
        config = parse_arguments([])
        self.assertEqual(config.inbound_message_ttl, 60 * 10)

        config = parse_arguments(['--inbound-message-ttl', '80'])
        self.assertEqual(config.inbound_message_ttl, 80)

        config = parse_arguments(['-ittl', '80'])
        self.assertEqual(config.inbound_message_ttl, 80)

    def test_parse_arguments_outbound_ttl(self):
        '''The outbound ttl command line argument can be specified by
        "--outbound-message-ttl" or "-ottl" and has a default value of 2 days
        '''
        config = parse_arguments([])
        self.assertEqual(config.outbound_message_ttl, 60*60*24*2)

        config = parse_arguments(['--outbound-message-ttl', '90'])
        self.assertEqual(config.outbound_message_ttl, 90)

        config = parse_arguments(['-ottl', '90'])
        self.assertEqual(config.outbound_message_ttl, 90)

    def test_parse_arguments_channels(self):
        '''Each channel mapping be specified by "--channels" or "-ch"'''
        config = parse_arguments([])
        self.assertEqual(config.channels, {})

        config = parse_arguments(['--channels', 'foo:bar'])
        self.assertEqual(config.channels, {'foo': 'bar'})

        config = parse_arguments([
            '--channels', 'foo:bar', '--channels', 'bar:foo'])
        self.assertEqual(config.channels, {'foo': 'bar', 'bar': 'foo'})

        config = parse_arguments(['-ch', 'foo:bar'])
        self.assertEqual(config.channels, {'foo': 'bar'})

        config = parse_arguments(['-ch', 'foo:bar', '-ch', 'bar:foo'])
        self.assertEqual(config.channels, {'foo': 'bar', 'bar': 'foo'})

    def test_parse_arguments_replace_channels(self):
        '''The replace channels command line argument can be specified by
        "--replace-channels" or "-rch" and has a default value of False
        '''
        config = parse_arguments([])
        self.assertEqual(config.replace_channels, False)

        config = parse_arguments(['--replace-channels', 'true'])
        self.assertEqual(config.replace_channels, True)

        config = parse_arguments(['-rch', 'true'])
        self.assertEqual(config.replace_channels, True)

    def test_parse_arguments_plugins(self):
        '''Each plugin config is specified by "--plugin" or "-pl"'''
        config = parse_arguments([])
        self.assertEqual(config.plugins, [])

        config = parse_arguments(['--plugin', json.dumps({'type': 'foo.bar'})])
        self.assertEqual(config.plugins, [{'type': 'foo.bar'}])

        config = parse_arguments([
            '--plugin', json.dumps({'type': 'foo.bar'}),
            '--plugin', json.dumps({'type': 'bar.foo'})])
        self.assertEqual(sorted(config.plugins), [
            {'type': 'bar.foo'}, {'type': 'foo.bar'}])

        config = parse_arguments(['-pl', json.dumps({'type': 'foo.bar'})])
        self.assertEqual(config.plugins, [{'type': 'foo.bar'}])

        config = parse_arguments([
            '-pl', json.dumps({'type': 'foo.bar'}),
            '-pl', json.dumps({'type': 'bar.foo'})])
        self.assertEqual(sorted(config.plugins), [
            {'type': 'bar.foo'}, {'type': 'foo.bar'}])

    def test_parse_arguments_metric_window(self):
        '''The metric window can be specified by "--metric-window" or "-mw"'''
        config = parse_arguments([])
        self.assertEqual(config.metric_window, 10.0)

        config = parse_arguments(['--metric-window', '2.0'])
        self.assertEqual(config.metric_window, 2.0)

        config = parse_arguments(['-mw', '2.0'])
        self.assertEqual(config.metric_window, 2.0)

    def test_parse_arguments_logging_path(self):
        '''The logging path can be specified by "--logging-path" or "-lp"'''
        config = parse_arguments([])
        self.assertEqual(config.logging_path, 'logs/')

        config = parse_arguments(['--logging-path', 'other-logs/'])
        self.assertEqual(config.logging_path, 'other-logs/')

        config = parse_arguments(['-lp', 'other-logs/'])
        self.assertEqual(config.logging_path, 'other-logs/')

    def testparse_arguments_sentry_dsn(self):
        '''The sentry DSN can be specified by "--sentry-dsn" or "-sd"'''
        config = parse_arguments([])
        self.assertEqual(config.sentry_dsn, None)

        config = parse_arguments(["--sentry-dsn", "http://sentry-dsn.com"])
        self.assertEqual(config.sentry_dsn, "http://sentry-dsn.com")

        config = parse_arguments(["-sd", "http://sentry-dsn.com"])
        self.assertEqual(config.sentry_dsn, "http://sentry-dsn.com")

    def test_parse_arguments_log_rotate_size(self):
        '''The log rotate size can be specified by "--log-rotate-size" or
        "-lrs"'''
        config = parse_arguments([])
        self.assertEqual(config.log_rotate_size, 1000000)

        config = parse_arguments(['--log-rotate-size', '7'])
        self.assertEqual(config.log_rotate_size, 7)

        config = parse_arguments(['-lrs', '7'])
        self.assertEqual(config.log_rotate_size, 7)

    def test_parse_arguments_max_log_files(self):
        '''The max log files can be specified by "--max-log-files" or "-mlf"'''
        config = parse_arguments([])
        self.assertEqual(config.max_log_files, None)

        config = parse_arguments(['--max-log-files', '2'])
        self.assertEqual(config.max_log_files, 2)

        config = parse_arguments(['-mlf', '2'])
        self.assertEqual(config.max_log_files, 2)

        config = parse_arguments(['--max-log-files', '0'])
        self.assertEqual(config.max_log_files, None)

        config = parse_arguments(['-mlf', '0'])
        self.assertEqual(config.max_log_files, None)

    def test_parse_arguments_max_logs(self):
        '''The max logs can be specified by "--max-logs" or "-ml" and defaults
        to 100.'''
        config = parse_arguments([])
        self.assertEqual(config.max_logs, 100)

        config = parse_arguments(['--max-logs', '2'])
        self.assertEqual(config.max_logs, 2)

        config = parse_arguments(['-ml', '2'])
        self.assertEqual(config.max_logs, 2)

    def test_config_file(self):
        '''The config file command line argument can be specified by
        "--config" or "-c"'''
        self.patch_yaml_load({
            '/foo/bar.yaml': {
                'interface': 'lolcathost',
                'port': 1337,
                'logfile': 'stuff.log',
                'redis': {
                    'host': 'rawrcathost',
                    'port': 3223,
                    'db': 9000,
                    'password': 't00r'
                },
                'amqp': {
                    'hostname': 'xorcathost',
                    'port': 2332,
                    'vhost': '/root',
                    'username': 'admin',
                    'password': 'nimda',
                },
                'inbound_message_ttl': 80,
                'outbound_message_ttl': 90,
                'channels': {'foo': 'bar'},
                'plugins': [{'type': 'foo.bar'}],
                'metric_window': 2.0,
                'logging_path': 'other-logs/',
                'sentry_dsn': 'http://sentry-dsn.com',
                'log_rotate_size': 2,
                'max_log_files': 3,
                'max_logs': 4,
            }
        })

        config = parse_arguments(['--config', '/foo/bar.yaml'])
        self.assertEqual(config.interface, 'lolcathost')
        self.assertEqual(config.port, 1337)
        self.assertEqual(config.logfile, 'stuff.log')
        self.assertEqual(config.redis['host'], 'rawrcathost')
        self.assertEqual(config.redis['port'], 3223)
        self.assertEqual(config.redis['db'], 9000)
        self.assertEqual(config.redis['password'], 't00r')
        self.assertEqual(config.amqp['hostname'], 'xorcathost')
        self.assertEqual(config.amqp['vhost'], '/root')
        self.assertEqual(config.amqp['port'], 2332)
        self.assertEqual(config.amqp['username'], 'admin')
        self.assertEqual(config.amqp['password'], 'nimda')
        self.assertEqual(config.inbound_message_ttl, 80)
        self.assertEqual(config.outbound_message_ttl, 90)
        self.assertEqual(config.channels, {'foo': 'bar'})
        self.assertEqual(config.plugins, [{'type': 'foo.bar'}])
        self.assertEqual(config.metric_window, 2.0)
        self.assertEqual(config.logging_path, 'other-logs/')
        self.assertEqual(config.sentry_dsn, 'http://sentry-dsn.com')
        self.assertEqual(config.log_rotate_size, 2)
        self.assertEqual(config.max_log_files, 3)
        self.assertEqual(config.max_logs, 4)

        config = parse_arguments(['-c', '/foo/bar.yaml'])
        self.assertEqual(config.interface, 'lolcathost')
        self.assertEqual(config.port, 1337)
        self.assertEqual(config.logfile, 'stuff.log')
        self.assertEqual(config.redis['host'], 'rawrcathost')
        self.assertEqual(config.redis['port'], 3223)
        self.assertEqual(config.redis['db'], 9000)
        self.assertEqual(config.redis['password'], 't00r')
        self.assertEqual(config.amqp['hostname'], 'xorcathost')
        self.assertEqual(config.amqp['vhost'], '/root')
        self.assertEqual(config.amqp['port'], 2332)
        self.assertEqual(config.amqp['username'], 'admin')
        self.assertEqual(config.amqp['password'], 'nimda')
        self.assertEqual(config.inbound_message_ttl, 80)
        self.assertEqual(config.outbound_message_ttl, 90)
        self.assertEqual(config.channels, {'foo': 'bar'})
        self.assertEqual(config.plugins, [{'type': 'foo.bar'}])
        self.assertEqual(config.metric_window, 2.0)
        self.assertEqual(config.logging_path, 'other-logs/')
        self.assertEqual(config.sentry_dsn, 'http://sentry-dsn.com')
        self.assertEqual(config.log_rotate_size, 2)
        self.assertEqual(config.max_log_files, 3)
        self.assertEqual(config.max_logs, 4)

    def test_config_file_overriding(self):
        '''Config file options are overriden by their corresponding command
        line arguments'''
        self.patch_yaml_load({
            '/foo/bar.yaml': {
                'interface': 'lolcathost',
                'port': 1337,
                'logfile': 'stuff.log',
                'redis': {
                    'host': 'rawrcathost',
                    'port': 3223,
                    'db': 9000,
                    'password': 't00r'
                },
                'amqp': {
                    'hostname': 'xorcathost',
                    'port': 2332,
                    'vhost': '/root',
                    'username': 'admin',
                    'password': 'nimda',
                },
                'plugins': [{'type': 'foo.bar'}],
                'metric_window': 2.0,
                'logging_path': 'other-logs/',
                'log_rotate_size': 2,
                'max_log_files': 3,
                'max_logs': 4,
            }
        })

        config = parse_arguments([
            '-c', '/foo/bar.yaml',
            '-i', 'zuulcathost',
            '-p', '1620',
            '-l', 'logs.log',
            '-redish', 'bluish',
            '-redisp', '2112',
            '-redisdb', '23',
            '-redispass', 'cat',
            '-amqph', 'soup',
            '-amqpp', '2112',
            '-amqpvh', '/soho',
            '-amqpu', 'koenji',
            '-amqppass', 'kodama',
            '-pl', json.dumps({'type': 'bar.foo'}),
            '-mw', '3.0',
            '-lp', 'my-logs/',
            '-lrs', '100',
            '-mlf', '10',
            '-ml', '5',
        ])

        self.assertEqual(config.interface, 'zuulcathost')
        self.assertEqual(config.port, 1620)
        self.assertEqual(config.logfile, 'logs.log')
        self.assertEqual(config.redis['host'], 'bluish')
        self.assertEqual(config.redis['port'], 2112)
        self.assertEqual(config.redis['db'], 23)
        self.assertEqual(config.redis['password'], 'cat')
        self.assertEqual(config.amqp['hostname'], 'soup')
        self.assertEqual(config.amqp['vhost'], '/soho')
        self.assertEqual(config.amqp['port'], 2112)
        self.assertEqual(config.amqp['username'], 'koenji')
        self.assertEqual(config.amqp['password'], 'kodama')
        self.assertEqual(sorted(config.plugins), [
            {'type': 'bar.foo'},
            {'type': 'foo.bar'}
        ])
        self.assertEqual(config.metric_window, 3.0)
        self.assertEqual(config.logging_path, 'my-logs/')
        self.assertEqual(config.log_rotate_size, 100)
        self.assertEqual(config.max_log_files, 10)
        self.assertEqual(config.max_logs, 5)

    def test_logging_setup(self):
        '''If filename is None, just a stdout logger is created, if filename
        is not None, both the stdout logger and a file logger is created'''
        logging_setup(None, None)
        [handler] = logging.getLogger().handlers
        self.assertEqual(handler.stream.name, '<stdout>')
        logging.getLogger().removeHandler(handler)

        filename = self.mktemp()
        logging_setup(filename, None)
        [handler1, handler2] = sorted(
            logging.getLogger().handlers,
            key=lambda h: hasattr(h, 'baseFilename'))

        self.assertEqual(
            os.path.abspath(handler2.baseFilename),
            os.path.abspath(filename))
        self.assertEqual(handler1.stream.name, '<stdout>')

        logging.getLogger().removeHandler(handler1)
        logging.getLogger().removeHandler(handler2)

    def test_sentry_setup(self):
        count = len(log.theLogPublisher._legacyObservers)

        sentry_setup(None)
        self.assertEqual(len(log.theLogPublisher._legacyObservers), count)

        e = ValueError("Test Error")
        with patch.object(Client, 'captureException') as mock_method:
            log.err(e)
            mock_method.assert_not_called()

        sentry_setup("http://username:password@sentry.test.com/16")
        function = log.theLogPublisher._legacyObservers[count].legacyObserver
        self.assertEqual(len(log.theLogPublisher._legacyObservers), count+1)
        self.assertEqual(function.func_name, "logToSentry")

        with patch.object(Client, 'captureException') as mock_method:
            try:
                raise e
            except:
                tb = sys.exc_info()
                log.err()
            mock_method.assert_called_once_with(tb)

        errors = self.flushLoggedErrors(ValueError)
        self.assertEqual(len(errors), 2)

    @inlineCallbacks
    def test_start_server(self):
        '''Starting the server should listen on the specified interface and
        port'''
        redis = yield self.get_redis()

        config = JunebugConfig({
            'port': 0,
            'interface': 'localhost',
            'redis': redis._config,
        })

        service = yield start_server(config)
        port = service._port
        host = port.getHost()
        self.assertEqual(host.host, '127.0.0.1')
        self.assertEqual(host.type, 'TCP')
        self.assertTrue(host.port > 0)
        yield service.stopService()
