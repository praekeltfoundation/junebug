.. _plugins-reference:

Plugin Reference
================

A Junebug plugin is a class that has specific methods that get called during
specific events that happen within Junebug. Plugins provide a way to hook into
Junebug and add extra functionality.

.. _installing-plugins:

Installing plugins
------------------
The :ref:`CLI <cli-reference>` and :ref:`config <config-reference>` references
describe how you can add plugins to Junebug.

Methods
-------
The following methods are available to plugins to perform actions according to
events that happen within Junebug:

.. autoclass:: junebug.plugin.JunebugPlugin
   :members:

Creating Plugins
----------------
In order to create a plugin, create a python class that inherits from
`junebug.plugin.JunebugPlugin`, and implements any of the methods. Then add
the plugin to Junebug through either the CLI or a config file, as described in
:ref:`Installing plugins <installing-plugins>`.

Bundled plugins
---------------

.. _nginx-plugin:

Nginx
~~~~~

Maintains configuration for an `nginx`_ virtual host for Junebug to expose http-based channels, reloading nginx whenever a new http-based channel is added.

.. _nginx: http://nginx.org/

The plugin looks for ``web_path`` and ``web_port`` config fields in each added
channel's config. ``web_port`` determines the internal tcp port for the server that nginx should proxy requests to. ``web_path`` determines the path to expose the http-channel on (e.g. ``'/foo/bar'``) for the vhost.

Config options:

.. confmodel::
   :module: junebug.plugins.nginx.plugin
   :class: NginxPluginConfig

.. note::

   The plugin needs permissions to write the vhost and location config files it
   maintains. See the config options for the default paths that the plugin will
   write these files to.
