import json
import logging
import sys

from twisted.internet.defer import inlineCallbacks
from twisted.python.failure import Failure
from twisted.python.log import LogPublisher
from vumi.tests.helpers import VumiTestCase

import junebug
from junebug.logging_service import JunebugLogObserver, JunebugLoggerService


class DummyLogFile(object):
    '''LogFile that just stores logs in memory in `logs`.'''
    def __init__(
            self, worker_id, path, rotateLength, maxRotatedFiles):
        self.worker_id = worker_id
        self.path = path
        self.rotateLength = rotateLength
        self.maxRotatedFiles = maxRotatedFiles
        self.logs = []
        self.closed_count = 0

    def write(self, data):
        self.logs.append(data)

    def close(self):
        self.closed_count += 1


class TestSentryLogObserver(VumiTestCase):
    def setUp(self):
        self.logfile = DummyLogFile(None, None, None, None)
        self.obs = JunebugLogObserver(self.logfile, 'worker-1')

    def test_level_for_event(self):
        '''The correct logging level is returned by `level_for_event`.'''
        for expected_level, event in [
            (logging.WARN, {'logLevel': logging.WARN}),
            (logging.ERROR, {'isError': 1}),
            (logging.INFO, {}),
        ]:
            self.assertEqual(self.obs.level_for_event(event), expected_level)

    def test_logger_for_event(self):
        '''The correct logger name is returned by `logger_for_event`.'''
        self.assertEqual(self.obs.logger_for_event({'system': 'foo,bar'}),
                         'worker-1.foo.bar')
        self.assertEqual(self.obs.logger_for_event({}), 'worker-1')

    def test_log_failure(self):
        '''A failure should be logged with the correct format.'''
        e = ValueError("foo error")
        f = Failure(e)
        self.obs({
            'failure': f, 'system': 'foo', 'isError': 1,
            'message': [e.message]})

        [log] = self.logfile.logs
        log = json.loads(log)
        log.pop('timestamp')

        self.assertEqual(log, {
            'level': JunebugLogObserver.DEFAULT_ERROR_LEVEL,
            'message': 'foo error',
            'logger': 'worker-1.foo',
            'class': repr(ValueError),
            'instance': repr(e),
            'stack': [],
        })

    def test_log_traceback(self):
        '''Logging a log with a traceback should place the traceback in the
        logfile.'''
        try:
            raise ValueError("foo")
        except ValueError:
            f = Failure(*sys.exc_info())
        self.obs({'failure': f, 'isError': 1, 'message': ['foo']})
        [log] = self.logfile.logs
        log = json.loads(log)
        log.pop('timestamp')
        self.assertEqual(log, {
            'message': 'foo',
            'logger': 'worker-1',
            'level': logging.ERROR,
            'class': repr(f.type),
            'instance': repr(ValueError),
            # json encoding changes all tuples to lists
            'stack': json.loads(json.dumps(f.stack)),
        })

    def test_log_warning(self):
        '''Logging an warning level log should generate the correct level log
        message'''
        self.obs({'message': ["a"], 'system': 'foo',
                  'logLevel': logging.WARN})
        [log] = self.logfile.logs
        log = json.loads(log)
        log.pop('timestamp')

        self.assertEqual(log, {
            'level': logging.WARN,
            'logger': 'worker-1.foo',
            'message': 'a',
        })

    def test_log_info(self):
        '''Logging an info level log should generate the correct level log
        message'''
        self.obs({'message': ["a"], 'system': 'test.log'})
        [log] = self.logfile.logs
        log = json.loads(log)
        log.pop('timestamp')

        self.assertEqual(log, {
            'logger': 'worker-1.test.log',
            'message': 'a',
            'level': logging.INFO
        })

    def test_log_debug(self):
        '''Logging a debug level log should not generate a log, since it is
        below the minimum log level.'''
        self.obs({'message': ["a"], 'system': 'foo',
                  'logLevel': logging.DEBUG})
        self.assertEqual(len(self.logfile.logs), 0)

    def test_log_with_context_sentinel(self):
        '''If the context sentinel has been set for a log, it should not be
        logged again.'''
        event = {'message': ["a"], 'system': 'foo'}
        event.update(self.obs.log_context)
        self.obs(event)
        self.assertEqual(len(self.logfile.logs), 0)


class TestJunebugLoggerSerivce(VumiTestCase):

    def setUp(self):
        self.patch(junebug.logging_service, 'LogFile', DummyLogFile)
        self.logger = LogPublisher()
        self.service = JunebugLoggerService(
            'worker-id', '/testpath/', 1000000, 7, logger=self.logger)

    @inlineCallbacks
    def test_logfile_parameters(self):
        '''When the logfile is created, it should be created with the correct
        parameters.'''
        yield self.service.startService()
        logfile = self.service.logfile
        self.assertEqual(logfile.worker_id, 'worker-id')
        self.assertEqual(logfile.path, '/testpath/')
        self.assertEqual(logfile.rotateLength, 1000000)
        self.assertEqual(logfile.maxRotatedFiles, 7)

    @inlineCallbacks
    def test_logging(self):
        '''The logging service should write logs to the logfile when the
        service is running.'''
        yield self.service.startService()
        logfile = self.service.logfile
        self.logger.msg("Hello", logLevel=logging.WARN)
        [log] = logfile.logs
        log = json.loads(log)
        log.pop('timestamp')

        self.assertEqual(log, {
            'level': logging.WARN,
            'logger': 'worker-id',
            'message': 'Hello',
        })

        del logfile.logs[:]
        yield self.service.stopService()
        self.logger.msg("Foo", logLevel=logging.WARN)
        self.assertEqual(logfile.logs, [])

    @inlineCallbacks
    def test_stop_not_running(self):
        '''If stopService is called when the service is not running, there
        should be no exceptions raised.'''
        yield self.service.stopService()
        self.assertFalse(self.service.running)

    @inlineCallbacks
    def test_start_stop(self):
        '''Stopping the service after it has been started should result in
        properly closing the logfile.'''
        self.assertFalse(self.service.registered())
        yield self.service.startService()
        self.assertEqual(self.service.logfile.closed_count, 0)
        self.assertTrue(self.service.registered())
        yield self.service.stopService()
        self.assertFalse(self.service.registered())
        self.assertEqual(self.service.logfile.closed_count, 1)
