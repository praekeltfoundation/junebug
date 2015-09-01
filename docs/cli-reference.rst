.. Junebug command line

Command-line Reference
======================

Running junebug is done through the ``jb`` command.

Usage
-----

``jb [-h] [--interface INTERFACE] [--port PORT] [--log-file LOGFILE]``

Optional Arguments:
-------------------

-h, --help                              Show the help message.
--interface INTERFACE, -i INTERFACE     The interface to expose the API on.
    Defaults to ``localhost``. Set to ``0.0.0.0`` to expose the API to the
    outside world.
--port PORT, -p PORT                    The port to expose the API on,
    defaults to ``8080``.
--log-file LOGFILE, -l LOGFILE          The file to log to. Defaults to not
    logging to any file.
