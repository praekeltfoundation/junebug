.. _installation:

Installation
============

Junebug requires `Python`_ (version 2.6 or 2.7) to be installed. This
installation method also requires `pip`_. Both of these must be installed before
following the installation steps below.

Junebug also needs `Redis`_ and `RabbitMQ`_. On Debian-based systems, one can
install them using::

   $ apt-get install redis-server rabbitmq-server

The Python cryptography library that Junebug depends on requires that the SSL
and FFI library headers be installed. On Debian-based systems, one can install
these using::

   $ apt-get install libssl-dev libffi-dev

Junebug can be then installed using::

   $ pip install junebug

.. _python: https://www.python.org/
.. _pip: https://pip.pypa.io/en/latest/index.html
.. _redis: http://redis.io/
.. _rabbitmq: https://www.rabbitmq.com/
