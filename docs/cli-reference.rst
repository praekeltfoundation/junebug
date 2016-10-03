.. _cli-reference:

Command-line Reference
======================

.. argparse::
   :module: junebug.command_line
   :func: create_parser
   :prog: jb

We also have the following environment variables:
:JUNEBUG_REACTOR:
    Choose which twisted reactor to use for Junebug. Can be one of SELECT,
    POLL, KQUEUE, WFMO, IOCP or EPOLL.
:JUNEBUG_DISABLE_LOGGING:
    Set to true to disable logging to the command line for Junebug.
