import json
import logging
import sys
import os
import shutil

from twisted.internet.defer import inlineCallbacks
from twisted.python.failure import Failure
from twisted.python.log import LogPublisher
from twisted.python.logfile import LogFile

import junebug
from junebug.tests.helpers import JunebugTestBase, DummyLogFile
from junebug.logging_service import (
    JunebugLogObserver, JunebugLoggerService, read_logs)


class TestSentryLogObserver(JunebugTestBase):
    def setUp(self):
        self.logpath = self.mktemp()
        os.mkdir(self.logpath)
        self.logfile = DummyLogFile('worker-1', self.logpath, None, None)
        self.obs = JunebugLogObserver(self.logfile, 'worker-1')

    def assert_log(self, log, expected):
        '''Assert that a log matches what is expected.'''
        log = json.loads(log)
        timestamp = log.pop('timestamp')
        self.assertTrue(isinstance(timestamp, float))
        self.assertEqual(log, expected)

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
        self.assertEqual(self.obs.logger_for_event(
            {'system': 'foo,bar'}), 'foo.bar')

    def test_log_failure(self):
        '''A failure should be logged with the correct format.'''
        e = ValueError("foo error")
        f = Failure(e)
        self.obs({
            'failure': f, 'system': 'worker-1', 'isError': 1,
            'message': [e.message]})

        [log] = self.logfile.logs
        self.assert_log(log, {
            'level': JunebugLogObserver.DEFAULT_ERROR_LEVEL,
            'message': 'foo error',
            'logger': 'worker-1',
            'exception': {
                'class': repr(ValueError),
                'instance': repr(e),
                'stack': [],
            },
        })

    def test_log_traceback(self):
        '''Logging a log with a traceback should place the traceback in the
        logfile.'''
        try:
            raise ValueError("foo")
        except ValueError:
            f = Failure(*sys.exc_info())
        self.obs({
            'failure': f, 'isError': 1, 'message': ['foo'],
            'system': 'worker-1'})
        [log] = self.logfile.logs
        self.assert_log(log, {
            'message': 'foo',
            'logger': 'worker-1',
            'level': logging.ERROR,
            'exception': {
                'class': repr(f.type),
                'instance': repr(ValueError),
                # json encoding changes all tuples to lists
                'stack': json.loads(json.dumps(f.stack)),
            },
        })

    def test_log_warning(self):
        '''Logging an warning level log should generate the correct level log
        message'''
        self.obs({
            'message': ["a"], 'system': 'worker-1', 'logLevel': logging.WARN})
        [log] = self.logfile.logs
        self.assert_log(log, {
            'level': logging.WARN,
            'logger': 'worker-1',
            'message': 'a',
        })

    def test_log_info(self):
        '''Logging an info level log should generate the correct level log
        message'''
        self.obs({'message': ["a"], 'system': 'worker-1'})
        [log] = self.logfile.logs
        self.assert_log(log, {
            'logger': 'worker-1',
            'message': 'a',
            'level': logging.INFO
        })

    def test_log_debug(self):
        '''Logging a debug level log should not generate a log, since it is
        below the minimum log level.'''
        self.obs({'message': ["a"], 'system': 'worker-1',
                  'logLevel': logging.DEBUG})
        self.assertEqual(len(self.logfile.logs), 0)

    def test_log_with_context_sentinel(self):
        '''If the context sentinel has been set for a log, it should not be
        logged again.'''
        event = {'message': ["a"], 'system': 'worker-1'}
        event.update(self.obs.log_context)
        self.obs(event)
        self.assertEqual(len(self.logfile.logs), 0)

    def test_log_only_worker_id(self):
        '''A log should only be created when the worker id is in the system
        id of the log.'''
        self.obs({'message': ["a"], 'system': 'worker-1,bar'})
        self.assertEqual(len(self.logfile.logs), 1)

        self.obs({'message': ["a"], 'system': 'worker-2,foo'})
        self.assertEqual(len(self.logfile.logs), 1)

        self.obs({'message': ["a"], 'system': 'worker-1foo,bar'})
        self.assertEqual(len(self.logfile.logs), 1)

        self.obs({'message': ["a"], 'system': None})
        self.assertEqual(len(self.logfile.logs), 1)


class TestJunebugLoggerService(JunebugTestBase):

    def setUp(self):
        self.patch(junebug.logging_service, 'LogFile', DummyLogFile)
        self.logger = LogPublisher()
        self.logpath = self.mktemp()
        self.service = JunebugLoggerService(
            'worker-id', self.logpath, 1000000, 7, logger=self.logger)

    def assert_log(self, log, expected):
        '''Assert that a log matches what is expected.'''
        log = json.loads(log)
        timestamp = log.pop('timestamp')
        self.assertTrue(isinstance(timestamp, float))
        self.assertEqual(log, expected)

    @inlineCallbacks
    def test_logfile_parameters(self):
        '''When the logfile is created, it should be created with the correct
        parameters.'''
        yield self.service.startService()
        logfile = self.service.logfile
        self.assertEqual(logfile.worker_id, 'worker-id')
        self.assertEqual(logfile.directory, self.logpath)
        self.assertEqual(logfile.rotateLength, 1000000)
        self.assertEqual(logfile.maxRotatedFiles, 7)

    @inlineCallbacks
    def test_logging(self):
        '''The logging service should write logs to the logfile when the
        service is running.'''
        self.logger.msg("Hello")
        self.assertFalse(hasattr(self.service, 'logfile'))

        yield self.service.startService()
        logfile = self.service.logfile
        self.logger.msg("Hello", logLevel=logging.WARN, system='worker-id')
        [log] = logfile.logs

        self.assert_log(log, {
            'level': logging.WARN,
            'logger': 'worker-id',
            'message': 'Hello',
        })

        yield self.service.stopService()
        self.assertEqual(len(logfile.logs), 1)
        self.logger.msg("Foo", logLevel=logging.WARN)
        self.assertEqual(len(logfile.logs), 1)

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

    @inlineCallbacks
    def test_dir_create(self):
        '''If log directory already exists, make sure it is not recreated.'''
        if not os.path.exists(self.service.path):
            os.makedirs(self.service.path, 0777)
        stat1 = os.stat(self.service.path)
        yield self.service.startService()
        stat2 = os.stat(self.service.path)
        self.assertTrue(os.path.samestat(stat1, stat2))
        yield self.service.stopService()
        shutil.rmtree(self.service.path)
        self.assertFalse(os.path.exists(self.service.path))
        yield self.service.startService()
        self.assertTrue(os.path.exists(self.service.path))
        yield self.service.stopService()


class TestReadingLogs(JunebugTestBase):
    def create_logfile(self):
        '''Creates and returns a temporary LogFile.'''
        return LogFile.fromFullPath(self.mktemp())

    def test_read_empty_log(self):
        '''Reading an empty log should return an empty list.'''
        logfile = self.create_logfile()
        logs = read_logs(logfile, 10)
        self.assertEqual(logs, [])

    def test_read_single_less_than_total(self):
        '''Reading a single log from a file with multiple logs should only
        return the last written log.'''
        logfile = self.create_logfile()
        logfile.write(json.dumps({'log_entry': 1}) + '\n')
        logfile.write(json.dumps({'log_entry': 2}) + '\n')
        logfile.flush()
        [log] = read_logs(logfile, 1)
        self.assertEqual(log, {'log_entry': 2})

    def test_read_single_equal_to_total(self):
        '''Reading a single log from a file with a single log should just
        return that log.'''
        logfile = self.create_logfile()
        logfile.write(json.dumps({'log_entry': 1}) + '\n')
        logfile.flush()
        [log] = read_logs(logfile, 1)
        self.assertEqual(log, {'log_entry': 1})

    def test_read_multiple_less_than_total(self):
        '''Reading multiple logs from a file with more logs than required
        should just return the required number of logs.'''
        logfile = self.create_logfile()
        logfile.write(json.dumps({'log_entry': 1}) + '\n')
        logfile.write(json.dumps({'log_entry': 2}) + '\n')
        logfile.write(json.dumps({'log_entry': 3}) + '\n')
        logfile.flush()
        [log1, log2] = read_logs(logfile, 2)
        self.assertEqual(log1, {'log_entry': 3})
        self.assertEqual(log2, {'log_entry': 2})

    def test_read_multiple_more_than_total(self):
        '''Reading multiple logs from a file with less logs than required
        should just return the number of logs available.'''
        logfile = self.create_logfile()
        logfile.write(json.dumps({'log_entry': 1}) + '\n')
        logfile.flush()
        [log] = read_logs(logfile, 2)
        self.assertEqual(log, {'log_entry': 1})

    def test_read_multiple_equal_than_total(self):
        '''Reading multiple logs from a file with the required amount of logs
        should just return the all of logs available.'''
        logfile = self.create_logfile()
        logfile.write(json.dumps({'log_entry': 1}) + '\n')
        logfile.write(json.dumps({'log_entry': 2}) + '\n')
        logfile.flush()
        [log1, log2] = read_logs(logfile, 2)
        self.assertEqual(log1, {'log_entry': 2})
        self.assertEqual(log2, {'log_entry': 1})

    def test_read_logs_from_multiple_files_more_than_available(self):
        '''If there are not enough logs in the current log, it should check
        the rotated log files for more logs. Total logs more than required
        logs.'''
        logfile = self.create_logfile()
        logfile.write(json.dumps({'log_entry': 1}) + '\n')
        logfile.write(json.dumps({'log_entry': 2}) + '\n')
        logfile.rotate()
        logfile.write(json.dumps({'log_entry': 3}) + '\n')
        logfile.write(json.dumps({'log_entry': 4}) + '\n')
        logfile.flush()

        [log1, log2, log3] = read_logs(logfile, 3)
        self.assertEqual(log1, {'log_entry': 4})
        self.assertEqual(log2, {'log_entry': 3})
        self.assertEqual(log3, {'log_entry': 2})

    def test_read_logs_from_multiple_files_equal_available(self):
        '''If there are not enough logs in the current log, it should check
        the rotated log files for more logs. Total logs equal to required
        logs.'''
        logfile = self.create_logfile()
        logfile.write(json.dumps({'log_entry': 1}) + '\n')
        logfile.write(json.dumps({'log_entry': 2}) + '\n')
        logfile.rotate()
        logfile.write(json.dumps({'log_entry': 3}) + '\n')
        logfile.flush()

        [log1, log2, log3] = read_logs(logfile, 3)
        self.assertEqual(log1, {'log_entry': 3})
        self.assertEqual(log2, {'log_entry': 2})
        self.assertEqual(log3, {'log_entry': 1})

    def test_read_logs_from_multiple_files_less_than_available(self):
        '''If there are not enough logs in the current log, it should check
        the rotated log files for more logs. Total logs less than to required
        logs.'''
        logfile = self.create_logfile()
        logfile.write(json.dumps({'log_entry': 1}) + '\n')
        logfile.rotate()
        logfile.write(json.dumps({'log_entry': 2}) + '\n')
        logfile.flush()

        [log1, log2] = read_logs(logfile, 3)
        self.assertEqual(log1, {'log_entry': 2})
        self.assertEqual(log2, {'log_entry': 1})

    def test_read_single_log_bigger_than_buffer(self):
        '''If a single log entry is greater than the buffer size, it should
        still read the log entry correctly.'''
        logfile = self.create_logfile()
        logfile.write(json.dumps({'log_entry': 1}) + '\n')
        logfile.flush()

        [log] = read_logs(logfile, 2, buf=1)
        self.assertEqual(log, {'log_entry': 1})

    def test_read_log_incomplete_last_entry(self):
        '''If the last log entry does not end in a new line, then discard
        it.'''
        logfile = self.create_logfile()
        logfile.write(json.dumps({'log_entry': 1}) + '\n')
        logfile.write(json.dumps({'log_entry': 2}))
        logfile.flush()

        [log] = read_logs(logfile, 2, buf=1)
        self.assertEqual(log, {'log_entry': 1})
