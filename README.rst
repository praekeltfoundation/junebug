Junebug
=======

|junebug-docs|

.. |junebug-docs| image:: https://readthedocs.org/projects/junebug/badge/?version=latest
    :alt: Documentation
    :scale: 100%
    :target: http://junebug.readthedocs.org/

Junebug is an open-source server application providing SMS and USSD
gateway connectivity for integrators, operators and application
developers.

Junebug enables integrators to automate the setup, monitoring,
logging, and health checking of population scale messaging
integrations.

Junebug is a system for managing text messaging transports via a
RESTful HTTP interface that supports:

* Creating, introspecting, updating and deleting transports
* Sending and receiving text messages
* Receiving status updates on text messages sent
* Monitoring transport health and performance
* Retrieving recent transport logs for debugging transport issues.


Design Principles
-----------------

Junebug aims to satisfy the following broad criteria:

* Easy to install
* Minimal useful feature set
* Sane set of dependencies


Documentation
-------------

Documentation is available online at http://junebug.readthedocs.org/
and in the `docs` directory of the repository.

.. |junebug-docs| image:: https://readthedocs.org/projects/junebug/badge/?version=latest
    :alt: Documentation
    :scale: 100%
    :target: http://junebug.readthedocs.org/

To build the docs locally::

    $ virtualenv ve
    $ source ve/bin/activate
    (ve)$ pip install -r requirements-docs.txt
    (ve)$ cd docs
    (ve)$ make html

You'll find the docs in `docs/_build/index.html`

You can contact the Junebug development team in the following ways:

* via *email* by joining the the `junebug@googlegroups.com`_ mailing list
* on *irc* in *#junebug* on the `Freenode IRC network`_

.. _junebug@googlegroups.com: https://groups.google.com/forum/?fromgroups#!forum/junebug
.. _Freenode IRC network: https://webchat.freenode.net/?channels=#junebug

Issues can be filed in the GitHub issue tracker. Please don't use the issue
tracker for general support queries.
