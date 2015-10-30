from os import path, remove
from shutil import rmtree
from tempfile import mkdtemp, mkstemp

from junebug.config import JunebugConfig
from junebug.tests.helpers import JunebugTestBase
from junebug.plugins.nginx.plugin import NginxPlugin, read, write


class TestNginxPlugin(JunebugTestBase):
    def make_temp_dir(self):
        dirname = mkdtemp()
        self.addCleanup(lambda: rmtree(dirname))
        return dirname

    def make_temp_file(self):
        _, filename = mkstemp()
        self.addCleanup(lambda: remove(filename))
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
