# WeePost - WeeWX extension that posts data to an endpoint script

Author: Andrew Billits

Derived from WeeRT WeeWX extension by Tom Keffer:

https://github.com/tkeffer/weert-js

# Notes:
========================================================
1. This extension simply posts live data to an endpoint. An example script (live.php) is provided but it is not required to use this script.
2. If using the included example script, PHP 7 or newer must be installed.
3. live.php accepts data posted to it, stores it as JSON in server memory, and outputs the stored JSON for GET requests. It's a very simple script.
4. You are responsible for either creating your own endpoint script or modifying your theme to read the JSON data from example script via javascript and display it.
5. An example of this extension in use can be found at griffinparkweather.com

# Installation:
========================================================
1. Add live.php to your skin directory, your local www directory, or to a remote www directory.
2. Place weepost.py into weewx user directory (ex: /usr/share/weewx/user)
3. Modify your weewx.conf by adding the following to the [StdRestful] section but change the key to something unique and change the endpoint to the location of live.php (or whatever script you wish)
```
[WeePOST]
    # The WeePOST server
    endpoint = http://127.0.0.1/weewx/live.php
    key = f38cxZ92m8EgX203Grnv-2
```
4. Locate the line that begings with "restful_services" in weewx.conf (under [Engine] -> [[Services]]) and add user.weepost.WeePOST. Ex:
```
    restful_services = weewx.restx.StdStationRegistry, ... weewx.restx.StdAWEKAS, user.weepost.WeePOST
```
5. Restart WeeWX
