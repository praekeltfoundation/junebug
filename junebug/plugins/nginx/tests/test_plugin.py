import subprocess
from os import path
from shutil import rmtree
from tempfile import mkdtemp, mkstemp

from twisted.internet.defer import inlineCallbacks

from junebug.config import JunebugConfig
from junebug.tests.helpers import JunebugTestBase
from junebug.plugins.nginx.plugin import (
    NginxPlugin, read, write, ensure_removed)


class TestNginxPlugin(JunebugTestBase):
    @inlineCallbacks
    def setUp(self):
        yield self.start_server()
        self.nginx_reloads = self.patch_nginx_reloads()

    def patch_subprocess_call(self, fixtures):
        calls = []

        def call(call_args):
            calls.append(call_args)
            matches = [res for args, res in fixtures if args == call_args]
            return matches[0] if matches else None

        self.patch(subprocess, 'call', call)
        return calls

    def patch_nginx_reloads(self):
        calls = self.patch_subprocess_call((
            (['which', 'nginx'], 0),
            (['nginx', '-s', 'reload'], 0),
        ))

        def nginx_reloads():
            reloads = calls.count(['nginx', '-s', 'reload'])
            del calls[:]
            return reloads

        return nginx_reloads

    def make_temp_dir(self):
        dirname = mkdtemp()
        self.addCleanup(lambda: rmtree(dirname))
        return dirname

    def make_temp_file(self):
        _, filename = mkstemp()
        self.addCleanup(lambda: ensure_removed(filename))
        return filename

    def test_start_plugin_create_vhost_config(self):
        plugin = NginxPlugin()

        locations_dirname = self.make_temp_dir()
        vhost_filename = self.make_temp_file()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': vhost_filename,
            'locations_dir': locations_dirname
        }, JunebugConfig({}))

        self.assertEqual(
            read(vhost_filename),
            read(plugin.config.vhost_template) % {
                'server_name': 'http//www.example.org',
                'includes': path.join(locations_dirname, '*.conf')
            })

    def test_start_plugin_create_vhost_config_custom_template(self):
        plugin = NginxPlugin()

        vhost_filename = self.make_temp_file()
        vhost_template_filename = self.make_temp_file()
        write(vhost_template_filename, '%(server_name)s')

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': vhost_filename,
            'locations_dir': self.make_temp_dir(),
            'vhost_template': vhost_template_filename,
        }, JunebugConfig({}))

        self.assertEqual(read(vhost_filename), 'http//www.example.org')

    def test_start_plugin_nginx_reload(self):
        plugin = NginxPlugin()

        self.assertEqual(self.nginx_reloads(), 0)

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': self.make_temp_dir()
        }, JunebugConfig({}))

        self.assertEqual(self.nginx_reloads(), 1)

    def test_stop_plugin_remove_vhost_config(self):
        plugin = NginxPlugin()
        vhost_filename = self.make_temp_file()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': vhost_filename,
            'locations_dir': self.make_temp_dir()
        }, JunebugConfig({}))

        self.assertTrue(path.exists(vhost_filename))
        plugin.stop_plugin()
        self.assertFalse(path.exists(vhost_filename))

    @inlineCallbacks
    def test_stop_plugin_remove_location_configs(self):
        plugin = NginxPlugin()
        locations_dirname = self.make_temp_dir()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': locations_dirname
        }, JunebugConfig({}))

        properties = self.create_channel_properties(config={
            'web_path': '/foo/bar',
            'web_port': 2323,
        })

        chan4 = yield self.create_channel(
            self.service, self.redis, id='chan4', properties=properties)

        chan5 = yield self.create_channel(
            self.service, self.redis, id='chan5', properties=properties)

        plugin.channel_started(chan4)
        plugin.channel_started(chan5)

        self.assertTrue(
            path.exists(path.join(locations_dirname, 'chan4.conf')))

        self.assertTrue(
            path.exists(path.join(locations_dirname, 'chan5.conf')))

        plugin.stop_plugin()

        self.assertFalse(
            path.exists(path.join(locations_dirname, 'chan4.conf')))

        self.assertFalse(
            path.exists(path.join(locations_dirname, 'chan5.conf')))

    @inlineCallbacks
    def test_stop_plugin_nginx_reload(self):
        plugin = NginxPlugin()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': self.make_temp_dir()
        }, JunebugConfig({}))

        properties = self.create_channel_properties(config={
            'web_path': '/foo/bar',
            'web_port': 2323,
        })

        chan4 = yield self.create_channel(
            self.service, self.redis, id='chan4', properties=properties)

        chan5 = yield self.create_channel(
            self.service, self.redis, id='chan5', properties=properties)

        plugin.channel_started(chan4)
        plugin.channel_started(chan5)

        self.nginx_reloads()  # flush reloads
        plugin.stop_plugin()
        self.assertEqual(self.nginx_reloads(), 1)

    @inlineCallbacks
    def test_channel_started(self):
        plugin = NginxPlugin()
        locations_dirname = self.make_temp_dir()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': locations_dirname
        }, JunebugConfig({}))

        properties = self.create_channel_properties(config={
            'web_path': '/foo/bar',
            'web_port': 2323,
        })

        channel = yield self.create_channel(
            self.service, self.redis, id='chan4', properties=properties)

        plugin.channel_started(channel)

        self.assertEqual(
            read(path.join(locations_dirname, 'chan4.conf')),
            read(plugin.config.location_template) % {
                'external_path': '/foo/bar',
                'internal_url': 'http://localhost:2323/foo/bar'
            })

    @inlineCallbacks
    def test_channel_started_custom_template(self):
        plugin = NginxPlugin()
        locations_dirname = self.make_temp_dir()
        location_template_filename = self.make_temp_file()
        write(location_template_filename, '%(external_path)s')

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': locations_dirname,
            'location_template': location_template_filename
        }, JunebugConfig({}))

        properties = self.create_channel_properties(config={
            'web_path': '/foo/bar',
            'web_port': 2323,
        })

        channel = yield self.create_channel(
            self.service, self.redis, id='chan4', properties=properties)

        plugin.channel_started(channel)

        self.assertEqual(
            read(path.join(locations_dirname, 'chan4.conf')),
            '/foo/bar')

    @inlineCallbacks
    def test_channel_started_ensure_dir(self):
        plugin = NginxPlugin()
        locations_dirname = path.join(self.make_temp_dir(), 'a/b/c')

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': locations_dirname
        }, JunebugConfig({}))

        properties = self.create_channel_properties(config={
            'web_path': '/foo/bar',
            'web_port': 2323,
        })

        channel = yield self.create_channel(
            self.service, self.redis, id='chan4', properties=properties)

        plugin.channel_started(channel)

        self.assertTrue(path.exists(locations_dirname))

    @inlineCallbacks
    def test_channel_started_non_http(self):
        plugin = NginxPlugin()
        locations_dirname = self.make_temp_dir()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': locations_dirname
        }, JunebugConfig({}))

        channel = yield self.create_channel(
            self.service, self.redis, id='chan4')

        plugin.channel_started(channel)

        self.assertFalse(
            path.exists(path.join(locations_dirname, 'chan4.conf')))

    @inlineCallbacks
    def test_channel_started_public_http_disabled(self):
        plugin = NginxPlugin()
        locations_dirname = self.make_temp_dir()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': locations_dirname
        }, JunebugConfig({}))

        properties = self.create_channel_properties(public_http={
            'enabled': False,
            'web_path': '/foo/bar',
            'web_port': 2323
        })

        channel = yield self.create_channel(
            self.service, self.redis, id='chan4', properties=properties)

        plugin.channel_started(channel)

        self.assertFalse(
            path.exists(path.join(locations_dirname, 'chan4.conf')))

    @inlineCallbacks
    def test_channel_started_exec_nginx_reload(self):
        plugin = NginxPlugin()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': self.make_temp_dir()
        }, JunebugConfig({}))

        properties = self.create_channel_properties(config={
            'web_path': '/foo/bar',
            'web_port': 2323,
        })

        channel = yield self.create_channel(
            self.service, self.redis, properties=properties)

        self.nginx_reloads()  # flush reloads
        plugin.channel_started(channel)
        self.assertEqual(self.nginx_reloads(), 1)

    @inlineCallbacks
    def test_channel_started_no_nginx_found(self):
        self.patch_logger()

        calls = self.patch_subprocess_call((
            (['which', 'nginx'], 1),
        ))

        plugin = NginxPlugin()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': self.make_temp_dir()
        }, JunebugConfig({}))

        properties = self.create_channel_properties(
            web_path='/foo/bar',
            web_port=2323)

        channel = yield self.create_channel(
            self.service, self.redis, properties=properties)

        self.assertEqual(calls.count(['nginx', '-s', 'reload']), 0)
        plugin.channel_started(channel)
        self.assertEqual(calls.count(['nginx', '-s', 'reload']), 0)

        self.assert_was_logged('Cannot reload nginx, nginx not found in path')

    @inlineCallbacks
    def test_channel_stopped(self):
        plugin = NginxPlugin()
        locations_dirname = self.make_temp_dir()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': locations_dirname
        }, JunebugConfig({}))

        properties = self.create_channel_properties(config={
            'web_path': '/foo/bar',
            'web_port': 2323,
        })

        channel = yield self.create_channel(
            self.service, self.redis, id='chan4', properties=properties)

        plugin.channel_started(channel)

        self.assertTrue(
            path.exists(path.join(locations_dirname, 'chan4.conf')))

        plugin.channel_stopped(channel)

        self.assertFalse(
            path.exists(path.join(locations_dirname, 'chan4.conf')))

    @inlineCallbacks
    def test_channel_stopped_irrelevant_channels(self):
        plugin = NginxPlugin()
        locations_dirname = self.make_temp_dir()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': locations_dirname
        }, JunebugConfig({}))

        properties = self.create_channel_properties(config={
            'web_path': '/foo/bar',
            'web_port': 2323,
        })

        chan4 = yield self.create_channel(
            self.service, self.redis, id='chan4', properties=properties)

        chan5 = yield self.create_channel(
            self.service, self.redis, id='chan5', properties=properties)

        write(path.join(locations_dirname, 'chan5.conf'), 'foo')
        plugin.channel_started(chan4)

        self.assertTrue(
            path.exists(path.join(locations_dirname, 'chan4.conf')))

        self.assertTrue(
            path.exists(path.join(locations_dirname, 'chan5.conf')))

        plugin.channel_stopped(chan4)
        plugin.channel_stopped(chan5)

        self.assertFalse(
            path.exists(path.join(locations_dirname, 'chan4.conf')))

        self.assertTrue(
            path.exists(path.join(locations_dirname, 'chan5.conf')))

    @inlineCallbacks
    def test_channel_stopped_nginx_reload(self):
        plugin = NginxPlugin()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': self.make_temp_dir()
        }, JunebugConfig({}))

        properties = self.create_channel_properties(config={
            'web_path': '/foo/bar',
            'web_port': 2323,
        })

        channel = yield self.create_channel(
            self.service, self.redis, properties=properties)

        plugin.channel_started(channel)

        self.nginx_reloads()  # flush reloads
        plugin.channel_stopped(channel)
        self.assertEqual(self.nginx_reloads(), 1)

    @inlineCallbacks
    def test_channel_stopped_irrelevant_channel_nginx_reload(self):
        plugin = NginxPlugin()

        plugin.start_plugin({
            'server_name': 'http//www.example.org',
            'vhost_file': self.make_temp_file(),
            'locations_dir': self.make_temp_dir()
        }, JunebugConfig({}))

        properties = self.create_channel_properties(config={
            'web_path': '/foo/bar',
            'web_port': 2323,
        })

        chan4 = yield self.create_channel(
            self.service, self.redis, id='chan4', properties=properties)

        chan5 = yield self.create_channel(
            self.service, self.redis, id='chan5', properties=properties)

        plugin.channel_started(chan4)

        self.nginx_reloads()  # flush reloads
        plugin.channel_stopped(chan4)
        plugin.channel_stopped(chan5)
        self.assertEqual(self.nginx_reloads(), 1)

    def test_get_location_context(self):
        plugin = NginxPlugin()
        properties = self.create_channel_properties(config={
            'web_path': '/foo/bar',
            'web_port': 2323,
        })
        context = plugin.get_location_context(properties['config'])
        self.assertEqual(context, {
            'external_path': '/foo/bar',
            'internal_url': 'http://localhost:2323/foo/bar',
        })

    def test_get_location_context_prepends_slash(self):
        plugin = NginxPlugin()
        properties = self.create_channel_properties(config={
            'web_path': 'foo/bar',
            'web_port': 2323,
        })
        context = plugin.get_location_context(properties['config'])
        self.assertEqual(context, {
            'external_path': '/foo/bar',
            'internal_url': 'http://localhost:2323/foo/bar',
        })
