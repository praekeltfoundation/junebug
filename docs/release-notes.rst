.. _release-notes

Release Notes
=============

v0.1.2
------
.. Pull requests 83

- Fixes

- Features
    - Added environment variable for selecting reactor

- Documentation
    - Extended AMQP documentation

v0.1.1
------
.. Pull requests 80

*1 March 2016*

- Fixes
    - Junebug now works with PyPy again
    - Fixed sending messages over AMQP


v0.1.0
------
.. Pull requests 60,62-79

*18 December 2015*

- Fixes
    - Fixed config file loading

- Features
    - We can now get message and event rates on a GET request to the channel
      endpoint
    - Can now get the last N logs for each channel
    - Can send and receive messages to and from AMQP queues as well as HTTP
    - Dockerfile for creating docker containers

- Documentation
    - Add documentation for message and event rates
    - Add documentation for getting a list of logs for a channel
    - Add a changelog to the documentation
    - Update documentation to be ready for v0.1.0 release
    - Remove Alpha version warning


v0.0.5
------
.. Pull requests 10,19,36-42,44-49,51-54,57-59

*9 November 2015*

- Fixes
    - When Junebug is started up, all previously created channels are now
      started

- Features
    - Send errors replies for messages whose length is greater than the
      configured character limit for the channel
    - Ability to add additional channel types through config
    - Get a message status and list of events for that message through an API
      endpoint
    - Have channel statuses POSTed to the configured URL on status change
    - Show the latest channel status event for each component and the overall
      status sumary with a GET request to the specific channel endpoint.
    - Add infrastructure for Junebug Plugins
    - Add Nginx Junebug Plugin that automatically updates the nginx config
      when it is required for HTTP based channels
    - Add SMPP and Dmark USSD channel types to the default list of channel
      types, as we now support those channels fully

- Documentation
    - Add getting started documentation
    - Updates for health events documentation
    - Add documentation for plugins
    - Add documentation for the Nginx plugin

v0.0.4
------
.. Pull request 33,34

*23 September 2015*

- Fixes
    - Ignore events without an associated event forwarding URL, instead of logging
      an error.
    - Fix race condition where an event could come in before the message is
      stored, leading to the event not being forwarded because no URL was found

v0.0.3
------
.. Pull requests 8,18,20-32

*23 September 2015*

- Fixes
    - Remove channel from channel list when it is deleted

- Features
    - Ability to specify the config in a file along with through the command line
      arguments
    - Ability to forward MO messages to a configured URL
    - Ability to reply to MO messages
    - Ability to forward message events to a per-message configured URL

- Documentation
    - Add documentation about configurable TTLs for inbound and outbound messages

v0.0.2
------
.. Pull requests 9,11,12,15,16

*9 September 2015*

- Fixes
    - Collection API endpoints now all end in a ``/``
    - Channels are now only started/stopped once instead of twice

- Features
    - Ability to send a MT message through an API endpoint
    - Ability to get a list of channels through an API endpoint
    - Ability to delete a channel through an API endpoint

v0.0.1
------
.. Pull requests 1-7

*1 September 2015*

- Features:
    - API endpoint structure
    - API endpoint validation
    - Health endpoint
    - ``jb`` command line script
    - Ability to create, get, and modify channels

- Documentation:
    - API endpoint documentation
    - Installation documentation
    - Run command documentation
