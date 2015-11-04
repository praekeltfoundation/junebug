.. _plugins-reference:

Plugin Reference
=====================

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
