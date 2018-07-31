.. _release-notes:

Release Notes
=============

v0.1.41
-------
.. Pull requests 173

-- Fixes
    - Included destination queues in health checks.

-- New Minimum Requirements
    - Twisted==17.9.0

v0.1.40
-------
.. Pull requests 169

-- Fixes
    - Destination reply to messages fetches from correct place and saves
      outbound.

v0.1.39
-------
.. Pull requests 165, 166, 167

-- Fixes
    - View messages on destination now fetches from the correct place.
    - Disabled channel messages endpoint if there is no destination configured.

v0.1.38
-------
.. Pull request 164

-- Features
    - Endpoint to create and view messages directly on a routers destination.

v0.1.37
-------
.. Pull request 163

-- Features
    - Added a log endpoint for routers

v0.1.36
-------
.. Pull request 162

- Fixes
    - Validation on router PATCH api endpoint.

v0.1.35
-------
.. Pull request 161

- Fixes
    - Store outbound messages that the from address router is forwarding, so
      that we can forward the events to the correct place.

v0.1.34
-------
.. Pull request 160

*8 January 2018*

- Fixes
    - Add handling for outbound messages from destinations on the from address
      router

v0.1.33
-------
.. Pull requests 158, 159

*4 January 2018*

-- Features
    - Added a base router class and a new from address router.

v0.1.32
-------
.. Pull requests 156, 157

*13 December 2017*

- Documentation
    - Fixed the mo_url_auth_token field description for channels

- Fixes
    - Fixed character limit validation for router destinations

v0.1.31
-------
.. Pull requests 147, 148, 149, 150

*12 December 2017*

- Features
    - Added endpoints for creating, modifying, deleting and listing router
      destinations.

- Documentation
    - Remove not yet implemented note for router destinations.

v0.1.30
-------
.. Pull requests 153, 154

*12 December 2017*

- Documentation
    - Add format for inbound messages send from Junebug.

- Fixes
    - Add handling for invalid JSON in the request body

v0.1.29
-------

.. Pull request 152

*6 December 2017*

- Fixes
    - Fix the name clash of validate_config for creating routers
    - Fix the TestRouter so that it can be used as an actual router for testing

v0.1.28
-------

.. Pull requests 142, 143, 144, 145, 146, 151

*5 December 2017*

- Features
    - Added the endpoints for creating, modifying, and deleting routers.

- Documentation
    - Removed not yet implemented from Router endpoints.

v0.1.27
-------

.. Pull requests 138, 141

*27 November 2017*

- Features
    - Added a config option for RabbitMQ Management Interface to see status of
      each queue with the health check.

- Fixes
    - Change created API endpoint statuses to 201 to match documentation

- Documentation
    - Use older version of docutils in documentation build, since txJSON-RPC
      does not work with the newer version.
    - Create minimal sphinx argparse implementation to use until official
      sphinx-argparse is made to work with readthedocs again
    - Bring release notes up to date
    - Update design notes to mark what has been implemented and what is yet to
      be implemented
    - Bring getting started section up to date with what the current API
      actually returns
    - Adding section in getting started to show getting the related events for
      a message
    - Update HTTP API documentation to what the API actually looks like
    - Update Readme to give more information to someone who wants to work on
      the project.

v0.1.26
-------

.. Pull requests 137

*07 September 2017*

- Fixes
    - Also catch RequestTransmissionFailed for HTTP requests. This should fix
      the issue where messages or events would stop being processed in the case
      of an HTTP error

v0.1.25
-------

.. Pull requests 136

*28 August 2017*

- Features
    - Update to vumi 0.6.18

v0.1.24
-------

.. Pull requests 134

*31 July 2017*

- Features
    - Allow event auth token to be specified when sending a message

- Documentation
    - Add documentation mentioning specifying an auth token for the mo_url and
      for the event URL


v0.1.23
-------

.. Pull requests 135

*28 July 2017*

- Features
    - Allow specifying all of to, from, and reply to when sending a message,
      defaulting to using reply_to if specified.
    - If allow_expired_replies is specified in the configuration, then if to,
      from, and reply_to is specified, and reply_to does not resolve to a valid
      message in the message store, then we will fall back to to and from for
      creating the message.

v0.1.22
-------

.. Pull requests 132

*24 July 2017*

- Features
    - Allow token and basic auth for sending of event messages


v0.1.21
-------

.. Pull requests: None

*21 July 2017*

- Features
    - Upgrade to vumi 0.6.17


v0.1.20
-------

.. Pull requests 133

*18 July 2017*

- Fixes
    - Allow any 6.x.x version for Raven (Sentry)


v0.1.19
-------

.. Pull requests 119, 130, 131

*17 July 2017*

- Features
    - Expose 'group' attribute from vumi message in message payload

- Documentation
    - Add newline in cli reference so that documentation renders correctly
    - Fix example response for message creation
    - Update documentation for reply_to change


v0.1.18
-------

.. Pull requests 127

*12 July 2017*

- Fixes
    - Change to setup.py to allow Junebug to be installable on python 3

v0.1.17
-------

.. Pull requests 128, 129

*10 July 2017*

- Features
    - Display more information on HTTP failure when logging failure
    - Allow an auth token to be specified for inbound (mobile originated)
      messages being sent over HTTP
- Fixes
    - Also catch CancelledError for HTTP timeouts


v0.1.16
-------

.. Pull requests 126

*7 June 2017*

- Features
    - Upgrade to pypy 5.7.1
    - Add ability to log exceptions to Sentry


v0.1.15
-------

.. Pull requests: None

*29 May 2017*

- Features
    - Upgrade vumi to 0.6.16

v0.1.14
-------

.. Pull requests: None

*31 March 2017*

- Fixes
    - Fix tests for new Twisted error output

v0.1.13
-------

Skipped


v0.1.12
-------

.. Pull requests 119

*31 March 2017*

- Features
    - Upgrade vumi to 0.6.14

v0.1.11
-------

.. Pull requests 118

*10 February 2017*

- Fixes
    - Trap ConnectionRefusedError that can happen when trying to relay
      a message to an event_url of mo_url.

v0.1.10
-------
.. Pull requests 114

*06 February 2017*

- Fixes
    - Make Junebug gracefully handle timeouts and connection failure for
      events and messages posted to URL endpoints.

v0.1.9
------
.. Pull requests 91

*02 February 2017*

- Fixes
    - Allow one to set the ``status_url`` and the ``mo_url`` for a channel to
      ``None`` to disable pushing of status events and messages to these URLs.

v0.1.8
------
.. Pull requests 112

*18 January 2017*

- Fixes
    - Change the default smpp channel type from the depricated SmppTransport
      (SmppTransceiverTransportWithOldConfig), to the new
      SmppTransceiverTransport.

v0.1.7
------
.. Pull requests 110

*10 January 2017*

- Features
   - Update the minimum version of vumi to get the latest version of the SMPP
     transport, which allows us to set the keys of the data coding mapping to
     strings. This allows us to use the data coding mapping setting in Junebug,
     since in JSON we cannot have integers as keys in an object.

v0.1.6
------
.. Pull requests 90, 92, 93, 100, 103, 105, 107, 108

*3 October 2016*

- Fixes
    - Fix the teardown of the MessageForwardingWorker so that if it didn't
      start up properly, it would still teardown properly.
    - Handling for 301 redirect responses improved by providing the URL to be
      redirected to in the body as well as the Location header.
    - We no longer crash if we get an event without the user_message_id field.
      Instead, we just don't store that event.

- Features
    - Update channel config error responses with the field that is causing the
      issue.
    - Set a minimum twisted version that we support (15.3.0), and ensure that
      we're testing against it in our travis tests.
    - The logging service now creates the logging directory if it doesn't exist
      and if we have permissions. Previously we would give an error if the
      directory didn't exist.

- Documentation
    - Added instructions to install libssl-dev and libffi-dev to the
      installation instructions.
    - Added documentation and diagrams for the internal architecture of
      Junebug.

v0.1.5
------
.. Pull requests 89

*19 April 2016*

- Fixes
    - Have nginx plugin add a leading slash to location paths if necessary.

v0.1.4
------
.. Pull requests 87, 88, 81

*12 April 2016*

- Fixes
    - Fix nginx plugin to properly support reading of web_path and web_port
      configuration.
    - Add endpoint for restarting channels.
    - Automate deploys.

v0.1.3
------
.. Pull requests 86

*5 April 2016*

- Fixes
    - Reload nginx when nginx plugin starts so that the vhost file is
      loaded straight away if the nginx plugin is active.

v0.1.2
------
.. Pull requests 83, 84, 85

*5 April 2016*

- Fixes
    - Added manifest file to fix nginx plugin template files that were
      missing from the built Junebug packages.

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
