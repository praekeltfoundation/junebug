from os import path

from confmodel import Config
from confmodel.fields import ConfigText

from junebug.plugin import JunebugPlugin


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
        "Path to the template file to use for the vhost file",
        default='%s/vhost.template' % (path.dirname(__file__,)), static=True)


class NginxPlugin(JunebugPlugin):
    '''
    Manages an nginx virtual host that proxies to the Junebug instance's
    http-based channels.
    '''

    def start_plugin(self, config, junebug_config):
        self.config = NginxPluginConfig(config)
        self.vhost_template = read(self.config.vhost_template)
        write(self.config.vhost_file, self.get_vhost_config())

    def get_vhost_config(self):
        return self.vhost_template % self.get_vhost_context()

    def get_vhost_context(self):
        return {
            'server_name': self.config.server_name,
            'includes': path.join(self.config.locations_dir, '*.conf'),
        }


def read(filename):
    with open(filename, 'r') as file:
        return file.read()


def write(filename, content):
    with open(filename, 'w') as file:
        file.write(content)
