.. Junebug installation

Installation via pip
====================


Prerequisites
-------------
Junebug requires `Python`_ (version 2.6 or 2.7) to be installed. This installation
method also requires `pip`_. Both of these must be installed before following the
installation steps below.

.. _Python: https://www.python.org/
.. _pip: https://pip.pypa.io/en/latest/index.html

pip will install the following requirements automatically:

* `klein`_
* `jsonschema`_
* `treq`_

.. _klein: https://pypi.python.org/pypi/klein/15.0.0
.. _jsonschema: https://pypi.python.org/pypi/jsonschema
.. _treq: https://pypi.python.org/pypi/treq/15.0.0

Installation
------------
Installation is performed by the following command:

``pip install junebug``

.. warning::

    The PyPI package for Junebug does not yet exist. Use
    ``git+git://github.com/praekelt/junebug.git@develop`` to install the
    latest code, instead of ``junebug``.
