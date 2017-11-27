.. _routers:


Routers
=======
.. note::

   Not yet implemented

Introduction
------------
Routers in Junebug allow you to use a single channel with multiple
applications.

This can be useful in cases where, for example with an SMPP transport, you
have a single bind with a provider, but multiple SMS lines.

Or if you have a USSD line, and you want the subcodes to go to different
applications.

The routers are desgined in such a way that you can do both one to many, and
many to one routing, for example where you have multiple MNOs that you have a
separate channel for each, but you want all messages to go to a single
application.

.. seealso::
   :ref:`routers-http-api`
        How to use routers with the http API

   :doc:`config-reference`
        How to add new router types via a config file

   :doc:`cli-reference`
        How to add new router types via command line arguments

Built in router types
---------------------
The following routers are available with any default setup and installation of
Junebug.

From address router
^^^^^^^^^^^^^^^^^^^
The ``from_address`` router type routes inbound messages based on regex rules
on the from address.

The config for the router takes the following parameters:

:channel *(str)*:
    The channel ID of the channel whose messages you want to route.
    This channel may not have an ``amqp_queue`` parameter specified. Required.

The config for each of the router destinations takes the following parameters:

:regular_expression *(str)*:
    The regular expression to match the from address on. Any inbound messages
    with a from address that matches this regular expression will be sent to
    this destination.
:default *(bool)*:
    Whether or not this destination is the default destination. Only one
    destination may be the default destination. Any messages that don't match
    any of the configured destinations will be sent to the default destination.
    If no default destination is configured, then non-matching messages will be
    dropped. Optional, defaults to false.
