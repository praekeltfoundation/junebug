import logging
import subprocess
from os import path, remove
from distutils.dir_util import mkpath
from urlparse import urljoin
from pkg_resources import resource_filename

from confmodel import Config
from confmodel.fields import ConfigText

from junebug.plugin import JunebugPlugin
from junebug.utils import channel_public_http_properties


log = logging.getLogger(__name__)


def resource_path(filename):
    return resource_filename('junebug.plugins.nginx', filename)


class NginxPluginConfig(Config):
    '''Config for :class:`NginxJunebugPlugin`'''

    vhost_file = ConfigText(
        "The file to write the junebug nginx vhost file to",
        default='/etc/nginx/sites-enabled/junebug.conf', static=True)

    locations_dir = ConfigText(
        "The directory to write location block config files to",
        default='/etc/nginx/includes/junebug/', static=True)

    server_name = ConfigText(
        "Server name to use for nginx vhost",
        required=True, static=True)

    vhost_template = ConfigText(
        "Path to the template file to use for the vhost config",
        default=resource_path('vhost.template'), static=True)

    location_template = ConfigText(
        "Path to the template file to use for each channel's location config",
        default=resource_path('location.template'), static=True)


class NginxPlugin(JunebugPlugin):
    '''
    Manages an nginx virtual host that proxies to the Junebug instance's
    http-based channels.
    '''

    def start_plugin(self, config, junebug_config):
        self.configured_channels = set()
        self.config = NginxPluginConfig(config)
        self.vhost_template = read(self.config.vhost_template)
        self.location_template = read(self.config.location_template)
        write(self.config.vhost_file, self.get_vhost_config())
        reload_nginx()

    def stop_plugin(self):
        ensure_removed(self.config.vhost_file)

        for channel_id in self.configured_channels:
            ensure_removed(self.get_location_path(channel_id))

        self.configured_channels = set()
        reload_nginx()

    def channel_started(self, channel):
        properties = channel_public_http_properties(channel._properties)

        if properties is not None and properties['enabled']:
            mkpath(self.config.locations_dir)

            write(
                self.get_location_path(channel.id),
                self.get_location_config(properties))

            reload_nginx()

            self.configured_channels.add(channel.id)

    def channel_stopped(self, channel):
        if channel.id in self.configured_channels:
            ensure_removed(self.get_location_path(channel.id))
            self.configured_channels.remove(channel.id)
            reload_nginx()

    def get_vhost_config(self):
        return self.vhost_template % self.get_vhost_context()

    def get_vhost_context(self):
        return {
            'server_name': self.config.server_name,
            'includes': path.join(self.config.locations_dir, '*.conf')
        }

    def get_location_config(self, properties):
        return self.location_template % self.get_location_context(properties)

    def get_location_context(self, properties):
        web_path = properties['web_path']
        web_path = '/%s' % web_path.lstrip('/')
        base_url = 'http://localhost:%s' % (properties['web_port'],)

        return {
            'external_path': web_path,
            'internal_url': urljoin(base_url, web_path)
        }

    def get_location_path(self, id):
        return path.join(self.config.locations_dir, "%s.conf" % (id,))


def reload_nginx():
    if in_path('nginx'):
        subprocess.check_call(['nginx', '-s', 'reload'])
    else:
        log.error('Cannot reload nginx, nginx not found in path')


def in_path(name):
    return True if subprocess.call(['which', name]) == 0 else False


def read(filename):
    with open(filename, 'r') as file:
        return file.read()


def write(filename, content):
    with open(filename, 'w') as file:
        file.write(content)


def ensure_removed(filename):
    if path.exists(filename):
        remove(filename)
