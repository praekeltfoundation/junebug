Junebug
=======

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
    (ve)$ pip install -e .-r requirements-docs.txt
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

Running tests
-------------

To run the tests locally::

    $ virtualenv ve
    $ source ve/bin/activate
    (ve) pip install -e . -r requirements-dev.txt
    (ve)$ trial junebug

Making releases
---------------
Releases are done according to git flow, and sticks to semantic versioning for
selecting a new version number. You should ensure that the release notes in
docs/release-notes.rst are up to date before doing a new release.

To create a new release, make sure you're on the develop branch, and then use
the utils script to change the package version::

    $ git checkout develop
    $ ./utils/bump-version.sh 0.1.0

Then, commit the changed files and tag that commit::

    $ git commit -m "Release 0.1.0"
    $ git tag junebug-0.1.0

Then, push the changes to develop, and push the new tag. This will start a
travis build, which when it passes, will create a new release to PyPI::

    $ git push origin develop
    $ git push origin junebug-0.1.0

Then, you can merge and push this code to the master and relevant release
branches::

    $ git checkout master
    $ git merge junebug-0.1.0
    $ git push origin master
    $ git checkout release/0.1.x
    $ git merge junebug-0.1.0
    $ git push origin release/0.1.x

Developing on Junebug
---------------------

For every python file in the junebug directory, there is a corresponding file
in the junebug/tests directory, that contains the unit tests for that file.

Any added fixes should have a relevant test added to ensure that any future
changes cannot reintroduce the bug.

Any added features should have relevant tests to ensure that the features work
as intended.

Each pull request should include any relevant changes to the documentation,
including updating the release notes to include the changes made in the pull
request.

junebug.amqp
~~~~~~~~~~~~
This module is responsible for maintaining an AMQP connection, and sending an
receiving messages over that connection.

junebug.api
~~~~~~~~~~~
This module is responsible for housing the logic of each of the HTTP API
endpoints. It uses `Klein`_, which is a web framework similar to `Flask`_, but
runs on top of `Twisted`_ and supports returning deferreds, which allows us to
perform async actions in our response generation, without blocking.

.. _Klein: https://klein.readthedocs.io/en/latest/
.. _Flask: http://flask.pocoo.org/
.. _Twisted: https://twistedmatrix.com/trac/

junebug.channel
~~~~~~~~~~~~~~~
This module contains our currently only implementation of a Junebug channel.
This implementation is an in-memory implementation, where new channels are
started as `Twisted`_ services.

Other possible future implementations might include a process based
implementation, where each channel is started as a new process, or a Mesos
based implementation, where each channel is started as a new container within a
cluster.

Any new channel implementations would need to implement all public methods on
the Channel class.

junebug.command_line
~~~~~~~~~~~~~~~~~~~~
This module contains all configuration, processing, and running of services
related to starting Junebug using the command line interface.

Any changes to the configuration options should also be made to the file-based
yaml configuration options, found in junebug/config.py

junebug.config
~~~~~~~~~~~~~~
This module contains a `confmodel`_ class, which is used to validate the yaml
file that can be used to specify configuration options for Junebug.

Any changes to the configuration options should also be made in the command
line arguments, found in junebug/command_line.py

.. _confmodel: https://confmodel.readthedocs.io/en/latest/

junebug.error
~~~~~~~~~~~~~
This module contains error classes that are shared between all Junebug modules.

junebug.logging_service
~~~~~~~~~~~~~~~~~~~~~~~
This module contains the logging observer, which is used to observe logs from
specific channels, and to write these logs to separate files, so that each
channel can have its logs displayed separately.

It also contains some utility methods to read these log files into a list of
objects.

junebug.plugin
~~~~~~~~~~~~~~
This module contains the base class for all Junebug plugins. It shows what
functions plugin implementors would need to implement.

junebug.plugins.*
~~~~~~~~~~~~~~~~~
Each module in this package contains a junebug plugin that is built into the
core Junebug code base.

junebug.service
~~~~~~~~~~~~~~~
This module houses the main Junebug twisted services, which runs the http API,
and has all the transports as its children.

junebug.stores
~~~~~~~~~~~~~~
This module houses all the different stores that we have. Currently they're all
backed by Redis, and store channel, message, and event related information.

junebug.utils
~~~~~~~~~~~~~
This module houses utility functions that are used all over Junebug.

junebug.validate
~~~~~~~~~~~~~~~~
This module contains some helper functions for defining validators that are use
to validate requests coming into the HTTP API.

junebug.workers
~~~~~~~~~~~~~~~
This module contains the Vumi workers that Junebug runs for each channel. This
includes things like the message forwarding worker, which forwards inbound
messages over AMQP and HTTP, and stores the messages and events in the various
stores, and the channel status worker, which stores and forwards channel status
updates.
