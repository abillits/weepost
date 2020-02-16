#!/usr/bin/env python
"""
WeePost - WeeWX extension that posts data to an endpoint script
Author: Andrew Billits

Derived from WeeRT WeeWX extension by Tom Keffer:
https://github.com/tkeffer/weert-js

Notes:
========================================================
1) This extension simply posts live data to an endpoint. An example script (live.php) is provided but it is not required to use this script.
2) If using the included example script, PHP 7 or newer must be installed.
3) live.php accepts data posted to it, stores it as JSON in server memory, and outputs the stored JSON for GET requests. It's a very simple script.
4) You are responsible for either creating your own endpoint script or modifying your theme to read the JSON data from example script via javascript and display it.
5) An example of this extension in use can be found at griffinparkweather.com

Installation:
========================================================
1) Add live.php to your skin directory, your local www directory, or to a remote www directory.
2) Place weepost.py into weewx user directory (ex: /usr/share/weewx/user)
3) Modify your weewx.conf by adding the following to the [StdRestful] section but change the key to something unique and change the endpoint to the location of live.php (or whatever script you wish)

[WeePOST]
    # The WeePOST server
    endpoint = http://127.0.0.1/weewx/live.php
    key = f38cxZ92m8EgX203Grnv-2

4) Locate the line that begings with "restful_services" in weewx.conf (under [Engine] -> [[Services]]) and add user.weepost.WeePOST. Ex:

    restful_services = weewx.restx.StdStationRegistry, ... weewx.restx.StdAWEKAS, user.weepost.WeePOST

5) Restart WeeWX

Useful Commands:
========================================================
/etc/init.d/weewx stop
/etc/init.d/weewx start
"""

import base64
import json
import math
import threading
import sys

# Python 2 / 3 compatibility imports

try:
    # Python 2
    from Queue import Queue
except ImportError:
    # Python 3
    from queue import Queue

try:
    # Python 2
    from StringIO import StringIO
except ImportError:
    # Python 3
    from io import StringIO

import configobj

from weeutil.weeutil import to_int
import weewx.restx

try:
    # Test for new-style weewx logging by trying to import weeutil.logger
    import weeutil.logger
    import logging
    log = logging.getLogger(__name__)

    def logdbg(msg):
        log.debug(msg)

    def loginf(msg):
        log.info(msg)

    def logerr(msg):
        log.error(msg)

except ImportError:
    # Old-style weewx logging
    import syslog

    def logmsg(level, msg):
        syslog.syslog(level, 'weepost: %s:' % msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)


DEFAULTS_INI = """
[WeePOST]
    # The WeePOST server
    endpoint = http://127.0.0.1/weewx/live.php
    key = f38cxZ92m8EgX203Grnv-2

    [[loop_filters]]
        last-updated = dateTime
        current.barometer = barometer
        current.altimeter = altimeter
        current.pressure = pressure
        current.outTemp = outTemp
        current.dewpoint = dewpoint
        current.windchill = windchill
        current.heatindex = heatindex
        current.appTemp = appTemp
        current.outHumidity = outHumidity
        current.humidex = humidex
        current.radiation = radiation
        current.UV = UV
        current.windDir = windDir
        current.windSpeed = windSpeed
        current.rain = rain
        current.rainRate = rainRate
        current.cloudbase = cloudbase
        current.soilMoist1 = soilMoist1
        current.soilTemp1 = soilTemp1
"""

weepost_defaults = configobj.ConfigObj(StringIO(DEFAULTS_INI), encoding='utf-8')


class WeePOST(weewx.restx.StdRESTful):
    """WeeWX service for uploading to the WeePOST server."""

    def __init__(self, engine, config_dict):
        super(WeePOST, self).__init__(engine, config_dict)

        # This utility will check the config_dict for any missing options. It returns None if
        # something is missing.
        weepost_dict = weewx.restx.get_site_dict(config_dict, 'WeePOST', 'endpoint', 'key')
        if weepost_dict is None:
            return

        # Check to make sure this version of weewx supports JSON posts.
        # To do this, look for function weewx.restx.RESTThread.get_post_body
        try:
            getattr(weewx.restx.RESTThread, 'get_post_body')
        except AttributeError:
            loginf('WeeWX needs to be upgraded to V3.8 in order to run WeePOST')
            loginf('****   WeePOST upload skipped')
            return

        # Start with the defaults. Make a copy --- we will be modifying it
        weepost_config = configobj.ConfigObj(weepost_defaults)['WeePOST']
        # Now merge in the overrides from the config file
        weepost_config.merge(weepost_dict)

        # Create and start a separate thread to do the actual posting.
        self.loop_queue = Queue()
        self.archive_thread = WeePOSTThread(self.loop_queue, **weepost_config)
        self.archive_thread.start()

        # Bind to the NEW_LOOP_PACKET event.
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        loginf("LOOP packets will be posted to %s"
               % (weepost_config['endpoint']))

    def new_loop_packet(self, event):
        "Called when a new loop packet arrives"
        # Stuff the packet into the queue
        self.loop_queue.put(event.packet)


class WeePOSTThread(weewx.restx.RESTThread):
    """Thread that posts to a WeePOST endpoint"""

    def __init__(self, queue,
                 endpoint, key,
                 loop_filters,
                 protocol_name="WeePOST",
                 post_interval=2, max_backlog=sys.maxsize, stale=None,
                 log_success=False, log_failure=True,
                 timeout=10, max_tries=3, retry_wait=5, retry_login=3600,
                 softwaretype="weewx-%s" % weewx.__version__,
                 skip_upload=False):

        """
        Initializer for the WeePOSThread class.

        Parameters specific to this class:

          endpoint: The full address of the endoint script

          key: The endpoint access key

          loop_filters: A data structure holding what values are to be emitted.
        """
        super(WeePOSTThread, self).__init__(queue,
                                          protocol_name=protocol_name,
                                          post_interval=post_interval,
                                          max_backlog=max_backlog,
                                          stale=stale,
                                          log_success=log_success,
                                          log_failure=log_failure,
                                          timeout=timeout,
                                          max_tries=max_tries,
                                          retry_wait=retry_wait,
                                          retry_login=retry_login,
                                          softwaretype=softwaretype,
                                          skip_upload=skip_upload)

        self.endpoint = endpoint
        self.key = key

        # Compile the filter functions for the loop packets:
        self.filter_funcs = _compile_filters(loop_filters)

    def format_url(self, _):
        """Override and return the URL used to post to the WeePOST server"""

        url = "%s" % (self.endpoint)
        return url

    def get_request(self, url):
        # Get the basic Request from my superclass
        request = super(WeePOSTThread, self).get_request(url)

        # Create a base64 byte string with the authorization info
        base64string = base64.b64encode(('%s' % (self.key)).encode())
        # Add the authentication header to the request:
        request.add_header("key", b"%s" % base64string)
        return request

    def get_post_body(self, packet):
        """Override, then supply the body and MIME type of the POST"""

        out_packet = {}
        # Subject all the types to be sent to a filter function.
        for k in self.filter_funcs:
            # This will include only types included in the filter functions.
            # If there is not enough information in the packet to support the filter
            # function, then an exception of type NameError will be raised,
            # and the type will be skipped.
            try:
                out_packet[k] = eval(self.filter_funcs[k], {"math": math}, packet)
            except NameError:
                pass

        body = out_packet
        json_body = json.dumps(body)
        return json_body, 'application/json'


def _compile_filters(loop_filters):
    """Compile the filter statements"""
    filter_funcs = {}
    for obs_type in loop_filters:
        filter_funcs[obs_type] = compile(loop_filters[obs_type], "WeePOST", 'eval')
    return filter_funcs
