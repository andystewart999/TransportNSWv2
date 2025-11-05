# TransportNSWv2
Python lib to access Transport NSW stop and journey information.

## How to Use

### Get an API Key
An OpenData account and API key is required to request the data. More information on how to create the free account can be found [here](https://opendata.transport.nsw.gov.au/user-guide).  You need to register an application that needs both the Trip Planner and Realtime Vehicle Positions APIs.

### Get the stop IDs
The only mandatory parameters are the API key and the origin/destination stop IDs - the easiest way to get the stop ID is via https://transportnsw.info/stops#/ - that page provides the option to search for either a location or a specific platform, bus stop or ferry wharf.  Regardless of if you specify a general location for the origin or destination, the return information shows the stop ID for the actual arrival and destination platform, bus stop or ferry wharf.

If it's available, the general occupancy level as wel as the latitude and longitude of the selected journey's vehicle(s) (train, bus, etc) will be returned, unless you specifically set `include_realtime_location` to `False`.

### API Documentation
The source Transport NSW API details can be found [here](https://opendata.transport.nsw.gov.au/sites/default/files/2023-08/Trip%20Planner%20API%20manual-opendataproduction%20v3.2.pdf).

### Exposed functions
Two functions are available:

`get_trip()` returns trip information between two stop IDs

`check_stops()` lets you confirm that the two stop IDs are valid, plus it returns all the stop ID metadata.
Note that ```get_trip()``` calls this function internally (unless you tell it not to, see below) and fails with a `StopError` Exception if either of the stop IDs are invalid, so there's no specific need to call `check_stops()` unless you want the stop ID metadata, or know you'll be calling the same journey multiple times and want to reduce your daily API calls by pre-checking once.

### check_stops() parameters
All parameters are mandatory.  Note that `stop_list` can be a single string or a list of strings:
```python
 .check_stops(api_key, ['200070', '200060'])
```
The return is a JSON-compatible Python object as per the example here:
```
{
  "all_stops_valid": true,
  "stop_list": [
    {
      "stop_id": "200060",
      "valid": true,
      "error_code": 0,
      "stop_detail": {
        "id": "200060",
        "name": "Central Station, Sydney",
        "disassembledName": "Central Station",
        <etc, as per the Transport NSW API>
        }
      }
    },
    {
      "stop_id": "229310",
      "valid": true,
      "error_code": 0,
      "stop_detail": {
        "id": "229310",
        "name": "Newcastle Interchange, Wickham",
        "disassembledName": "Newcastle Interchange",
        <etc, as per the Transport NSW API>
      }
    }
  ]
}
```
Most of the top-level properties are pretty self-explanatory.  If all you want to do is get a general yes/no then `all_stops_valid` is the quickest check, although with the latest version raising a StopError exception if a stop ID check fails that's become a little bit academic.
If the API call was successful then `stop_detail` will contain everything that the API sent back for the closest match it found.

### Sample Code - catching an invalid stop

The following example checks two stops to see if they're valid, and it turns out that one of them isn't.

**Code:**
```python
from TransportNSWv2 import TransportNSWv2, StopError

tnsw = TransportNSWv2()
try:
    _data = tnsw.check_stops(<your API key>, ['20006012345', '229310'])
    print (_data['all_stops_valid'])

except StopError as ex:
    print (f"Stop error - {ex}")

except Exception as ex:
    print (f"Misc error - {ex}")
```

**Result:**
```python
Stop error - Error 'stop invalid' calling stop finder API for stop ID 20006012345
```

### get_trip() parameters
Only the first three parameters are mandatory, the rest are optional.  All parameters and their defaults are as follows:
```python
.get_trip(name_origin = <origin stop ID>, name_destination = <destination stop ID>, api_key = <your API key>, journey_wait_time = 0, origin_transport_type = [0], destination_transport_type = [0], strict_transport_type = False, journeys_to_return = 1, route_filter = '', include_realtime_location = True, include_alerts = 'none', alert_type = ['all'], raw_output = False, check_stop_ids = True)
```

`journey_wait_time` is how many minutes from now the departure should be.

`origin_transport_type` and `destination_transport_type` are integer lists of vehicle transport types - only journeys whose first/last **non-walking** leg fits the criteria will be included, unless `strict_transport_type` is `True` in which case literally the first  and last leg **must** be one of the requested types - it's effectively a 'no walking' filter.  A ```transport_type``` of [0] means that **all** transport types are permitted.

If `route_filter` has a value then only journeys with that value in either the `origin_line_name` or `origin_line_name_short` fields are included - it's a caseless wildcard search so for example `north` would include 'T1 North Shore & Western Line' journeys.

Specifying an alert priority in `include_alerts` means that any alerts of that priority or higher will be included in the output as raw JSON, basically a collation of the alerts that the Trip API sent back.  By default **all** alert types will be included - you can limit the output to specific alert types by setting `alert_type` to something like `['lineInfo', 'stopInfo', 'bannerInfo']`.

`raw_output` means that function returns whatever came back from the API call as-is, ignoring all of the above optional parameters with the exception of `journey_wait_time`.

Setting `check_stop_ids` to `False` does just that - `get_trip()` won't initially check that the provided stop IDs are valid, saving on your daily API quota.

Transport types:
```
1:      Train
2:      Metro
4:      Light rail
5:      Bus
7:      Coach
9:      Ferry
11:     School bus
99:     Walk
100:    Walk
107:    Cycle
```

Alert priorities:
```
veryLow
low
normal
high
veryHigh
```

Alert types:
```
routeInfo:      Alerts relating to a specific route
lineInfo:       Alerts relating to a specific journey
stopInfo:       Alerts relating to specific stops
stopBlocking:   Alerts relating to stop closures
bannerInfo:     Alerts potentially relating to network-wide impacts
all:            All alerts
```

TransportNSW's trip planner can work better if you use the general stop IDs (e.g. `220010` for Bankstown Station) rather than a specific stop ID (e.g. `2200501` for Bankstown Station, Platform 1) for the destination, depending on the transport type, as forcing a specific destination stop ID sometimes results in much more complicated trips.  Also note that the API expects (and returns) the stop IDs as strings, although so far they all appear to be numeric.

### Sample Code - train journey, line and stop-related alerts of normal higher priority included
The following example returns the next train-only journey that starts from Redfern (`201510`) to Milsons Point (`206110`) ten minutes from now.  Two journeys have been requested, we want realtime locations if possible, and we also want lineInfo and stopInfo alerts of priority normal or higher:

**Code:**
```python
from TransportNSWv2 import TransportNSWv2
tnsw = TransportNSWv2()
journey = tnsw.get_trip('201510', '20610', '<your API key>', journey_wait_time = 10 ,origin_transport_type = [1, 2, 4], destination_transport_type = [1, 2, 4], journeys_to_return = 2, include_alerts = 'normal', alert_type = ['lineInfo', 'stopInfo'])

print(journey)
```
**Result:**
```python
{
  "journeys_to_return": 2,
  "journeys_with_data": 2,
  "journeys": [
    {
      "due": 10,
      "delay": 1,
      "origin_stop_id": "2015133",
      "origin_name": "Redfern Station, Platform 3, Eveleigh",
      "departure_time": "2025-08-27T22:13:48Z",
      "destination_stop_id": "206142",
      "destination_name": "Milsons Point Station, Platform 2, Milsons Point",
      "arrival_time": "2025-08-27T22:24:36Z",
      "origin_transport_type": "Train",
      "origin_transport_name": "Sydney Trains Network",
      "origin_line_name": "T1 North Shore & Western Line",
      "origin_line_name_short": "T1",
      "destination_transport_type": "Train",
      "destination_transport_name": "Sydney Trains Network",
      "destination_line_name": "T1 North Shore & Western Line",
      "destination_line_name_short": "T1",
      "changes": 0,
      "origin_occupancy": "n/a",
      "destination_occupancy": "n/a",
      "origin_real_time_trip_id": "159C.938.149.32.A.8.86302165",
      "destination_real_time_trip_id": "159C.938.149.32.A.8.86302165",
      "origin_latitude": -33.875030517578125,
      "origin_longitude": 151.0980682373047,
      "destination_latitude": -33.875030517578125,
      "destination_longitude": 151.0980682373047,
      "alerts": []
    },
    {
      "due": 12,
      "delay": 0,
      "origin_stop_id": "2015133",
      "origin_name": "Redfern Station, Platform 3, Eveleigh",
      "departure_time": "2025-08-27T22:16:00Z",
      "destination_stop_id": "206142",
      "destination_name": "Milsons Point Station, Platform 2, Milsons Point",
      "arrival_time": "2025-08-27T22:27:30Z",
      "origin_transport_type": "Train",
      "origin_transport_name": "Sydney Trains Network",
      "origin_line_name": "T9 Northern Line",
      "origin_line_name_short": "T9",
      "destination_transport_type": "Train",
      "destination_transport_name": "Sydney Trains Network",
      "destination_line_name": "T9 Northern Line",
      "destination_line_name_short": "T9",
      "changes": 0,
      "origin_occupancy": "n/a",
      "destination_occupancy": "n/a",
      "origin_real_time_trip_id": "140C.938.149.48.A.8.86304102",
      "destination_real_time_trip_id": "140C.938.149.48.A.8.86304102",
      "origin_latitude": -33.871639251708984,
      "origin_longitude": 151.0941925048828,
      "destination_latitude": -33.871639251708984,
      "destination_longitude": 151.0941925048828,
      "alerts": []
    }
  ]
}
```
In this example you can see that no actual alerts of that type were provided by the API.  Below is an example of the alerts output:
```
      "alerts": [
        {
          "priority": "normal",
          "id": "ems-53698",
          "version": 17859,
          "type": "lineInfo",
          "properties": {
            "publisher": "ems.comm.addinfo",
            "infoType": "lineInfo",
            "smsText": "Minor timetable adjustments to some train services from Sunday 29 June",
            "speechText": "From Sunday 29 June, minor timetable adjustments will be made to some train services. These adjustments are being introduced as part of a regular review of train services to improve reliability for passengers.\n \nSee the news story for more information at transportnsw.info."
          },
          "infoLinks": [
            {
              "urlText": "Minor timetable adjustments to some train services from Sunday 29 June",
              "url": "https://transportnsw.info/alerts/details#/ems-53698",
              "content": "<div>From<strong>&nbsp;Sunday 29 June</strong>, minor timetable adjustments will be made to some train services. These adjustments are being introduced as part of a regular review of train services to improve reliability for passengers.</div>\n<div>&nbsp;</div>\n<div>See the <a href=\"https://transportnsw.info/news/2025/train-timetable-changes-in-june\">news story</a> for more information.</div>",
              "subtitle": "Minor timetable adjustments to some train services from Sunday 29 June",
              "smsText": "Minor timetable adjustments to some train services from Sunday 29 June",
              "speechText": "From Sunday 29 June, minor timetable adjustments will be made to some train services. These adjustments are being introduced as part of a regular review of train services to improve reliability for passengers.\n \nSee the news story for more information at transportnsw.info."
            }
          ],
          "urlText": "Minor timetable adjustments to some train services from Sunday 29 June",
          "url": "https://transportnsw.info/alerts/details#/ems-53698",
          "content": "<div>From<strong>&nbsp;Sunday 29 June</strong>, minor timetable adjustments will be made to some train services. These adjustments are being introduced as part of a regular review of train services to improve reliability for passengers.</div>\n<div>&nbsp;</div>\n<div>See the <a href=\"https://transportnsw.info/news/2025/train-timetable-changes-in-june\">news story</a> for more information.</div>",
          "subtitle": "Minor timetable adjustments to some train services from Sunday 29 June"
        }
      ]
    }
```
### Output explanations

* `due`: the time (in minutes) before the journey starts
* `delay`: how delayed (in minutes) the next service is.  Note that ```due``` already factors in delays
* `origin_stop_id`: the specific departure stop id of the journey
* `origin_name`:` the name of the departure location
* `departure_time`: the departure time, in UTC
* `destination_stop_id`: the specific destination stop id of the journey
* `destination_name`: the name of the destination location
* `arrival_time`: the planned arrival time at the origin, in UTC
* `origin_transport_type`: the type of transport, eg train, bus, ferry etc of the first leg of the journey
* `origin_transport_name`: the full name of the first-leg transport provider
* `origin_line_name` & `origin_line_name_short`: the full and short names of the first-leg line or service
* `destination_transport_type`: the type of transport, eg train, bus, ferry etc of the final leg of the journey
* `destination_transport_name`: the full name of the last-leg transport provider
* `destination_line_name` and `destination_line_name_short`: the full and short names of the last-leg line or service
* `changes`: how many transport changes are needed on the journey, excluding walking
* `origin_occupancy`: how full the first-leg vehicle is, if available
* `destination_occupancy`: how full the last-leg vehicle is, if available
* `origin_real_time_trip_id`: the unique TransportNSW id for the first-leg vehicle, if available
* `destination_real_time_trip_id`: the unique TransportNSW id for the last-leg vehicle, if available
* `origin_latitude/longitude` and `destination_latitude/longitude`: The current location of the first-leg and last-leg vehicles, if available
* `alerts`: An array of alerts pertinent to that journey

For single-leg journeys the `origin_*` and `destination_*` outputs will be identical.


### Notes ###
Requesting multiple journeys to be returned doesn't always return that exact number of journeys.  The API call only ever returns five or six and if you have any filters applied then that might further reduce the number of 'valid' journeys.

Note that the origin and destination details are just that - information about the first and last stops on the journey at the time the request was made.  The output doesn't include any intermediate steps, transport change types etc. other than the total number of changes - the assumption is that you'll know the details of your specified trip, you just want to know when the next departure is.  If you need much more detailed information then I recommend that you use the full [Transport NSW trip planner](https://transportnsw.info/trip#/trip)  or app, or parse the raw output by adding `raw_output = True` to your call.

## Exceptions ##
The latest release of TransportNSWv2 now uses custom Exceptions when things go wrong, instead of returning None - it's more 'Pythonic'.  The Exceptions that can be imported are as follows:
* InvalidAPIKey - API key-related issues
* APIRateLimitExceeded - API rate-limit issues
* StopError - stop ID issues, usually when checking that a stop ID is valid
* TripError - trip-related issues, including no journeys being returned when calling ```.get_trip()```

## Rate limits ##
By default the TransportNSW API allows each API key to make 60,000 calls in a day and up to 5 calls per second.  When requesting real-time location information some services required me to brute-force up to 12 (!) URIs until I found the right one which sometimes resulted in an API rate-limit breach.  From version 0.8.7 I found a TransportNSW-maintained CSV that contains mappings of bus agency IDs to URIs so I'm using that, plus adding in a 0.75 second delay between API calls.  Plus, if you're confident that the origin and destination IDs are correct you can reduce your totail daily API calls by adding `check_trip_ids = False` in the parameters.

## Thank you
Thank you [Dav0815](https://github.com/Dav0815/TransportNSW) for your TransportNSW library that the vast majority of this fork is based on.  I couldn't have done it without you!

