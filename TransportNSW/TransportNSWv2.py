"""  A module to query Transport NSW (Australia) departure times.         """
"""  First created by Dav0815 ( https://pypi.org/user/Dav0815/)           """
"""  Extended by AndyStewart999 ( https://pypi.org/user/andystewart999/ ) """

from datetime import datetime, timedelta
from google.transit import gtfs_realtime_pb2

import requests

import logging
import re
import json                                     #For the output
import time

ATTR_DUE_IN = 'due'

ATTR_ORIGIN_STOP_ID = 'origin_stop_id'
ATTR_ORIGIN_NAME = 'origin_name'
ATTR_DEPARTURE_TIME = 'departure_time'
ATTR_DELAY = 'delay'

ATTR_DESTINATION_STOP_ID = 'destination_stop_id'
ATTR_DESTINATION_NAME = 'destination_name'
ATTR_ARRIVAL_TIME = 'arrival_time'

ATTR_ORIGIN_TRANSPORT_TYPE = 'origin_transport_type'
ATTR_ORIGIN_TRANSPORT_NAME = 'origin_transport_name'
ATTR_ORIGIN_LINE_NAME = 'origin_line_name'
ATTR_ORIGIN_LINE_NAME_SHORT = 'origin_line_name_short'
ATTR_CHANGES = 'changes'

ATTR_OCCUPANCY = 'occupancy'

ATTR_AVMS_TRIP_ID = 'avms_trip_id'
ATTR_REAL_TIME_TRIP_ID = 'real_time_trip_id'
ATTR_LATITUDE = 'latitude'
ATTR_LONGITUDE = 'longitude'
ATTR_GTFS_URI = 'gtfs_uri'
ATTR_ALERTS = 'alerts'

logger = logging.getLogger(__name__)

class Journeys(object):
    """The Class for handling the data retrieval."""

    # The application requires an API key. You can register for
    # free on the service NSW website for it.
    # You need to register for both the Trip Planner and Realtime Vehicle Position APIs

    def __init__(self):
        """Initialize the data object with default values."""
        self.info = {
            ATTR_DUE_IN : 'n/a',
            ATTR_ORIGIN_STOP_ID : 'n/a',
            ATTR_ORIGIN_NAME : 'n/a',
            ATTR_DEPARTURE_TIME : 'n/a',
            ATTR_DELAY : 'n/a',
            ATTR_DESTINATION_STOP_ID : 'n/a',
            ATTR_DESTINATION_NAME : 'n/a',
            ATTR_ARRIVAL_TIME : 'n/a',
            ATTR_ORIGIN_TRANSPORT_TYPE : 'n/a',
            ATTR_ORIGIN_TRANSPORT_NAME : 'n/a',
            ATTR_ORIGIN_LINE_NAME : 'n/a',
            ATTR_ORIGIN_LINE_NAME_SHORT : 'n/a',
            ATTR_CHANGES : 'n/a',
            ATTR_OCCUPANCY : 'n/a',
            ATTR_REAL_TIME_TRIP_ID : 'n/a',
            ATTR_LATITUDE : 'n/a',
            ATTR_LONGITUDE : 'n/a',
            ATTR_ALERTS: '[]'
            }


    def check_stops(self, api_key, stops, home_assistant = False):
        # Check the list of stops and return a JSON array of the stop details, plus if all the checked stops existed
        # Return a JSON array of the results

        # Sanity checking
        if isinstance(stops, str):
            # If it's a single string, convert it to a list
            stops = [stops]

        auth = 'apikey ' + api_key
        header = {'Accept': 'application/json', 'Authorization': auth}

        #Prepare the output string
        all_stops_valid = True
        stop_list = []
        skip_api_calls = False

        for stop in stops:
            url = \
                'https://api.transport.nsw.gov.au/v1/tp/stop_finder?' \
                'outputFormat=rapidJSON&coordOutputFormat=EPSG%3A4326' \
                '&type_sf=stop&name_sf=' + stop + \
                '&TfNSWSF=true'

            # Send the query
            try:
                url = 'https://api.transport.nsw.gov.au/v1/tp/stop_finder?outputFormat=rapidJSON&coordOutputFormat=EPSG%3A4326&type_sf=stop&name_sf=' + stop + '&TfNSWSF=true'
                error_code = 0

                if not skip_api_calls:
                    response = requests.get(url, headers=header, timeout=5)
                else:
                    # An earlier call resulted in an API key error so no point trying again
                    response.status_code = 401

                # If we get bad status code, handle it depending on the error type
                if response.status_code != 200:
                    # We can't be sure that all the stops are valid
                    error_code = response.status_code
                    stop_detail = []

                    if response.status_code == 401:
                        raise InvalidAPIKey("Invalid API key")

                    elif response.status_code == 403 or response.status_code == 429:
                        raise APIRateLimitExceeded("API rate limit exceeded")

                    else:
                        raise StopError("Unknown")

                else:
                    # Parse the result as a JSON object
                    stop_detail = response.json()

                    # Just a quick check - the presence of systemMessages signifies an error, otherwise we assume it's ok
                    if 'systemMessages' in stop_detail:
                        error_text = stop_detail['systemMessages'][0]['text']
                        raise StopError(f"{error_text}", stop)

                    # Put in a pause here to try and make sure we stay under the 5 API calls/second limit
                    # Not usually an issue but if multiple processes are running multiple calls we might hit it
                    time.sleep(1.0)

            except Exception as ex:
                raise StopError(f"Error '{ex}' calling stop finder API for stop ID {stop}", stop)

            finally:
                # Append the results to the JSON output - only return the 'isBest' location entry if there's more than one
                if stop_detail != []:
                    stop_valid = True
                    for location in stop_detail['locations']:
                        if location['isBest']:
                            stop_detail = location
                            break

                else:
                    stop_valid = False
                    all_stops_valid = False

                #Add it to the list
                data = {"stop_id": stop, "valid": stop_valid, "error_code": error_code, "stop_detail": stop_detail}
                stop_list.append (data)

        # Complete the JSON output and return it
        data = {"all_stops_valid": all_stops_valid, "stop_list": stop_list}
        #return json.dumps(data)
        return data


    def get_trip(self, name_origin, name_destination , api_key, journey_wait_time = 0, transport_type = 0, \
                 strict_transport_type = False, raw_output = False, journeys_to_return = 1, route_filter = '', \
                 include_realtime_location = True, include_alerts = 'none', alert_type = 'all', check_stop_ids = True, forced_gtfs_uri = [],
                 home_assistant = False):

        """Get the latest data from Transport NSW."""
        fmt = '%Y-%m-%dT%H:%M:%SZ'

        route_filter = route_filter.lower()
        include_alerts = include_alerts.lower()
        alert_type = alert_type.lower()

        # This query always uses the current date and time - but add in any 'journey_wait_time' minutes
        now_plus_wait = datetime.now() + timedelta(minutes = journey_wait_time)
        itdDate = now_plus_wait.strftime('%Y%m%d')
        itdTime = now_plus_wait.strftime('%H%M')

        auth = 'apikey ' + api_key
        header = {'Accept': 'application/json', 'Authorization': auth}

        # First, check if the source and dest stops are valid unless we've been told not to
        if check_stop_ids:
            stop_list = [name_origin, name_destination]
            data = self.check_stops(api_key, stop_list)

            if not data['all_stops_valid']:
                # One or both of those stops was invalid - log an error and exit
                stop_error = ""
                for stop in data['stop_list']:
                    if not stop['valid']:
                        stop_error += stop['stop_id']+ ", "

                #logger.error(f"Stop ID(s) {stop_error[:-2]} do not exist - exiting")
                raise StopError (f"Stop ID(s) {stop_error[:-2]} do not exist", stop_error)
                #return None

        # We don't control how many journeys are returned any more, so need to be careful of running out of valid journeys if there is a filter in place, particularly a strict filter
        # It would be more efficient to return one journey, check if the filter is met and then retrieve the next one via a new query if not, but for now we'll only be making use of the journeys we've been given

        # Build the entire URL
        url = \
            'https://api.transport.nsw.gov.au/v1/tp/trip?' \
            'outputFormat=rapidJSON&coordOutputFormat=EPSG%3A4326' \
            '&depArrMacro=dep&itdDate=' + itdDate + '&itdTime=' + itdTime + \
            '&type_origin=any&name_origin=' + name_origin + \
            '&type_destination=any&name_destination=' + name_destination + \
            '&TfNSWTR=true'

        # Send the query and return an error if something goes wrong
        # Otherwise store the response for the next steps
        try:
            response = requests.get(url, headers=header, timeout=10)

        except Exception as ex:
            raise TripError (f"Error '{str(ex)}' calling trip API for journey {name_origin} to {name_destination}")

        # If we get bad status code, log error and return with n/a or an empty string
        if response.status_code != 200:
            if response.status_code == 401:
                # API key issue
                raise InvalidAPIKey("Error 'Invalid API key' calling trip API for journey {name_origin} to {name_destination}")

            elif response.status_code == 403 or response.status_code == 429:
                raise APIRateLimitExceeded("Error 'API rate limit exceeded' calling trip API for journey {name_origin} to {name_destination}")

            else:
                raise TripError(f"Error '{str(response.status_cude)}' calling trip API for journey {name_origin} to {name_destination}")

            return None

        result = response.json()

        # The API will always return a valid trip, so it's just a case of grabbing the metadata that we need...
        # We're only reporting on the origin and destination, it's out of scope to discuss the specifics of the ENTIRE journey
        # This isn't a route planner, just a 'how long until the next journey I've specified' tool
        # The assumption is that the travelee will know HOW to make the defined journey, they're just asking WHEN it's happening next
        # All we potentially have to do is find the first trip that matches the transport_type filter

        if raw_output == True:
            # Just return the raw output
            return json.dumps(result)

        # Make sure we've got at least one journey
        try:
            retrieved_journeys = len(result['journeys'])

        except:
            raise TripError(f"Error 'no journeys returned' calling trip API for journey {name_origin} to {name_destination}")

        # Loop through the results applying filters where required, and generate the appropriate JSON output including an array of in-scope trips
        json_output=''
        found_journeys = 0
        no_valid_journeys = False

        for current_journey_index in range (0, retrieved_journeys, 1):
            # Look for a trip with a matching transport type filter in at least one of its legs.  Either ANY, or the first leg, depending on how strict we're being
            journey, next_journey_index = self._find_next_journey(result['journeys'], current_journey_index, transport_type, strict_transport_type, route_filter)

            if ((journey is None) or (journey['legs']) is None):
                pass
            else:
                legs = journey['legs']
                first_leg = self._find_first_leg(legs, transport_type, strict_transport_type, route_filter)

                #Executive decision - don't be strict on the last leg, there's often some walking (transport type 100) involved.
                last_leg = self._find_last_leg(legs, transport_type, False)
                changes = self._find_changes(legs, transport_type)

                origin = first_leg['origin']
                first_stop = first_leg['destination']
                destination = last_leg['destination']
                transportation = first_leg['transportation']

                # Origin info
                origin_stop_id = origin['id']
                origin_name = origin['name']
                origin_departure_time = origin['departureTimeEstimated']
                origin_departure_time_planned = origin['departureTimePlanned']

                t1 = datetime.strptime(origin_departure_time, fmt).timestamp()
                t2 = datetime.strptime(origin_departure_time_planned, fmt).timestamp()
                delay = int((t1-t2) / 60)

                # How long until it leaves?
                due = self._get_due(datetime.strptime(origin_departure_time, fmt))

                # Destination info
                destination_stop_id = destination['id']
                destination_name = destination['name']
                destination_arrival_time = destination['arrivalTimeEstimated']

                # Origin type info - train, bus, etc
                origin_mode = self._get_mode(transportation['product']['class'])
                origin_mode_name = transportation['product']['name']

                # RealTimeTripID info so we can try and get the current location later
                realtimetripid = 'n/a'
                if 'properties' in transportation and 'RealtimeTripId' in transportation['properties']:
                    realtimetripid = transportation['properties']['RealtimeTripId']

                    # We're also going to need the agency_id if it's a bus journey
                    agencyid = transportation['operator']['id']

                # AVMSTripID is for Home Assistant, if needed
                avmstripid = 'n/a'
                if 'properties' in transportation and 'AVMSTripID' in transportation['properties']:
                    avmstripid = transportation['properties']['AVMSTripID']

                # Line info
                origin_line_name_short = "unknown"
                if 'disassembledName' in transportation:
                    origin_line_name_short = transportation['disassembledName']

                origin_line_name = "unknown"
                if 'number' in transportation:
                    origin_line_name = transportation['number']

                # Occupancy info, if it's there
                occupancy = 'unknown'
                if 'properties' in first_stop and 'occupancy' in first_stop['properties']:
                    occupancy = first_stop['properties']['occupancy']

                alerts = "[]"
                if include_alerts != 'none':
                    # We'll be adding these to the returned JSON string as an array
                    # Only include alerts of the specified priority or greater, and of the specified type
                    alerts = self._find_alerts(legs, include_alerts, alert_type)

                latitude = 'n/a'
                longitude = 'n/a'
                mode_url = 'n/a'

                if include_realtime_location and realtimetripid != 'n/a':
                    # See if we can get the latitute and longitude via the Realtime Vehicle Positions API
                    # Build the URL(s) - some modes have multiple GTFS sources, unforunately
                    # Some travel modes require brute-forcing the API call a few times, so if we're sure of the URI,
                    # ie it's been determined elsewhere then it can be forced

                    bFoundTripID = False
                    url_base_path = self._get_base_url(origin_mode)

                    # Check for a forced URI
                    if not forced_gtfs_uri:
                        url_mode_list = self._get_mode_list(origin_mode, agencyid)
                    else:
                        # We've been forced to use a specific URI!
                        url_mode_list = forced_gtfs_uri

                    if not url_mode_list is None:
                        for mode_url in url_mode_list:
                            url = url_base_path + mode_url
                            response = requests.get(url, headers=header, timeout=10)

                            # Only try and process the results if we got a good return code
                            if response.status_code == 200:
                                # Search the feed and see if we can match realtimetripid to trip_id
                                # If we do, capture the latitude and longitude
                                feed = gtfs_realtime_pb2.FeedMessage()
                                feed.ParseFromString(response.content)
                                reg = re.compile(realtimetripid)

                                for entity in feed.entity:
                                    if bool(re.match(reg, entity.vehicle.trip.trip_id)):
                                        latitude = entity.vehicle.position.latitude
                                        longitude = entity.vehicle.position.longitude

                                        # We found it, so flag it and break out
                                        bFoundTripID = True
                                        break
                            else:
                                # Warn that we didn't get a good return
                                if response.status_code == 401:
                                    logger.error(f"Error 'Invalid API key' calling {url} API")
                                elif response.status_code == 403 or response.status_code == 429:
                                    logger.error(f"Error 'API rate limit exceded' calling {url} API")
                                else:
                                    logger.error(f"Error '{str(response.status_code)}' calling {url} API")

                            if bFoundTripID == True:
                                # No need to look any further
                                break

                            # Put in a quick pause here to try and make sure we stay under the 5 API calls/second limit
                            # Not usually an issue but if multiple processes are running multiple calls we might hit it
                            time.sleep(0.75)

                self.info = {
                    ATTR_DUE_IN: due,
                    ATTR_DELAY: delay,
                    ATTR_ORIGIN_STOP_ID : origin_stop_id,
                    ATTR_ORIGIN_NAME : origin_name,
                    ATTR_DEPARTURE_TIME : origin_departure_time,
                    ATTR_DESTINATION_STOP_ID : destination_stop_id,
                    ATTR_DESTINATION_NAME : destination_name,
                    ATTR_ARRIVAL_TIME : destination_arrival_time,
                    ATTR_ORIGIN_TRANSPORT_TYPE : origin_mode,
                    ATTR_ORIGIN_TRANSPORT_NAME: origin_mode_name,
                    ATTR_ORIGIN_LINE_NAME : origin_line_name,
                    ATTR_ORIGIN_LINE_NAME_SHORT : origin_line_name_short,
                    ATTR_CHANGES: changes,
                    ATTR_OCCUPANCY : occupancy,
                    ATTR_REAL_TIME_TRIP_ID : realtimetripid,
                    ATTR_GTFS_URI: mode_url,
                    ATTR_LATITUDE : latitude,
                    ATTR_LONGITUDE : longitude,
                    ATTR_ALERTS: json.loads(alerts)
                    }

                if home_assistant:
                    self.info.update (
                        {ATTR_AVMS_TRIP_ID: avmstripid}
                    )

                found_journeys = found_journeys + 1

                # Add to the return array
                if (no_valid_journeys == True):
                    break

                if (found_journeys >= 2):
                    json_output = json_output + ',' + json.dumps(self.info)
                else:
                    json_output = json_output + json.dumps(self.info)

                if (found_journeys == journeys_to_return):
                    break

                current_journey_index = next_journey_index

        json_output='{"journeys_to_return": ' + str(journeys_to_return) + ', "journeys_with_data": ' + str(found_journeys) + ', "journeys": [' + json_output + ']}'
        return json_output


    def _find_next_journey(self, journeys, start_journey_index, journeytype, strict, route_filter):
        # Find the next journey that has a leg of the requested type, and/or that satisfies the route filter
        journey_count = len(journeys)

        # Some basic error checking
        if start_journey_index > journey_count:
            return None, None

        for journey_index in range (start_journey_index, journey_count, 1):
            leg = self._find_first_leg(journeys[journey_index]['legs'], journeytype, strict, route_filter)
            if leg is not None:
                return journeys[journey_index], journey_index + 1
            else:
                return None, None

        # Hmm, we didn't find one
        return None, None


    def _find_first_leg(self, legs, legtype, strict, route_filter):
        # Find the first leg of the requested type
        leg_count = len(legs)
        for leg_index in range (0, leg_count, 1):
            #First, check against the route filter
            origin_line_name_short = 'n/a'
            origin_line_name = 'n/a'

            if 'transportation' in legs[leg_index] and 'disassembledName' in legs[leg_index]['transportation']:
                origin_line_name_short = legs[leg_index]['transportation']['disassembledName'].lower()
                origin_line_name = legs[leg_index]['transportation']['number'].lower()

            if (route_filter in origin_line_name_short or route_filter in origin_line_name):
                leg_class = legs[leg_index]['transportation']['product']['class']
                # We've got a filter, and the leg type matches it, so return that leg
                if legtype != 0 and leg_class == legtype:
                    return legs[leg_index]

                # We don't have a filter, and this is the first non-walk/cycle leg so return that leg
                if  legtype == 0 and leg_class < 99:
                    return legs[leg_index]

                # Exit if we're doing strict filtering and we haven't found that type in the first leg
                if legtype != 0 and strict == True:
                    return None

        # Hmm, we didn't find one
        return None


    def _find_last_leg(self, legs, legtype, strict):
        # Find the last leg of the requested type
        leg_count = len(legs)
        for leg_index in range (leg_count - 1, -1, -1):
            leg_class = legs[leg_index]['transportation']['product']['class']

            # We've got a filter, and the leg type matches it, so return that leg
            if legtype != 0 and leg_class == legtype:
                return legs[leg_index]

            # We don't have a filter, and this is the first non-walk/cycle leg so return that leg
            if  legtype == 0 and leg_class < 99:
                return legs[leg_index]

            # Exit if we're doing strict filtering and we haven't found that type in the first leg
            if legtype != 0 and strict == True:
                return None

        # Hmm, we didn't find one
        return None


    def _find_changes(self, legs, legtype):
        # Find out how often we have to change
        changes = 0
        leg_count = len(legs)

        for leg_index in range (0, leg_count, 1):
            leg_class = legs[leg_index]['transportation']['product']['class']
            if leg_class == legtype or legtype == 0:
                changes = changes + 1

        return changes - 1


    def _find_alerts(self, legs, priority_filter, alert_type):
        # Return an array of all the alerts on this trip that meet the priority level and alert type
        leg_count = len(legs)
        found_alerts = []
        priority_minimum = self._get_alert_priority(priority_filter)
        alert_list = alert_type.split("|")

        for leg_index in range (0, leg_count, 1):
            current_leg = legs[leg_index]
            if 'infos' in current_leg:
                alerts = current_leg['infos']
                for alert in alerts:
                    if (self._get_alert_priority(alert['priority'])) >= priority_minimum:
                        if (alert_type == 'all') or (alert['type'].lower() in alert_list):
                            found_alerts.append (alert)

        return json.dumps(found_alerts)


    def _find_hints(self, legs, legtype, priority):
        # Return an array of all the hints on this trip that meet the priority type
        leg_count = len(legs)

        for leg_index in range (0, leg_count, 1):
            current_leg = legs[leg_index]
            leg_class = current_leg['transportation']['product']['class']
            if 'hints' in current_leg:
                hints = current_leg['hints']


    def _get_mode(self, iconId):
        """Map the iconId to a full text string"""
        modes = {
            1   : "Train",
            2   : "Metro",
            4   : "Light rail",
            5   : "Bus",
            7   : "Coach",
            9   : "Ferry",
            11  : "School bus",
            99  : "Walk",
            100 : "Walk",
            107 : "Cycle"
        }

        return modes.get(iconId, None)

    def _get_base_url(self, mode):
        # Map the journey mode to the proper base real time location URL
        v1_url = "https://api.transport.nsw.gov.au/v1/gtfs/vehiclepos"
        v2_url = "https://api.transport.nsw.gov.au/v2/gtfs/vehiclepos"

        url_options = {
            "Train"      : v2_url,
            "Metro"      : v2_url,
            "Light rail" : v1_url,
            "Bus"        : v1_url,
            "Coach"      : v1_url,
            "Ferry"      : v1_url,
            "School bus" : v1_url
        }

        return url_options.get(mode, None)


    def _get_alert_priority(self, alert_priority):
        # Map the alert priority to a number so we can filter later

        alert_priorities = {
            "all"      : 0,
            "verylow"  : 1,
            "low"      : 2,
            "normal"   : 3,
            "high"     : 4,
            "veryhigh" : 5
        }
        return alert_priorities.get(alert_priority.lower(), 4)


    def _get_mode_list(self, mode, agencyid):
        """
        Map the journey mode to the proper modifier URL.  If the mode is Bus, Coach or School bus then use the agency ID to invoke the GTFS datastore search API
        which will give us the appropriate URL to call later - we still have to do light rail the old-fashioned, brute-force way though
        """

        if mode in ["Bus", "Coach", "School bus"]:
            # Use this CSV to determine the appropriate real-time location URL
            # I'm hoping that this CSV resource URL is static when updated by TransportNSW!
            url = "https://opendata.transport.nsw.gov.au/data/api/action/datastore_search?resource_id=30b850b7-f439-4e30-8072-e07ef62a2a36&filters={%22For%20Realtime%20GTFS%20agency_id%22:%22" + agencyid + "%22}&limit=1"

            # Send the query and return an error if something goes wrong
            try:
                response = requests.get(url, timeout=5)
            except Exception as ex:
                logger.error(f"Error '{str(ex)}' querying GTFS URL datastore")
                return None

            # If we get bad status code, log error and return with None
            if response.status_code != 200:
                if response.status_code == 401:
                    logger.error (f"Error 'Invalid API key' calling GTFS API url {url}")
                elif response.status_code == 403 or response.status_code == 429:
                    logger.error(f"Error 'API rate limit exceeded' calling GTFS API url {url}")
                else:
                    logger.error(f"Error '{str(response.status_code)}' calling GTFS API url {url}")

                return None

            # Parse the result as JSON
            result = response.json()
            if 'records' in result['result'] and len(result['result']['records']) > 0:
                mode_path = result['result']['records'][0]['For Realtime parameter']
            else:
                return None

            # Even though there's only one URL we need to return as a list as Light Rail still has multiple URLs that need to be brute-forced, unfortunately
            bus_list = ["/" + mode_path]
            return bus_list
        else:
            # Handle the other modes
            url_options = {
                "Train"      : ["/sydneytrains"],
                "Metro"      : ["/metro"],
                "Light rail" : ["/lightrail/innerwest", "/lightrail/cbdandsoutheast", "/lightrail/newcastle"],
                "Ferry"      : ["/ferries/sydneyferries"]
            }
            return url_options.get(mode, None)


    def _get_due(self, estimated):
        # Minutes until departure
        due = 0
        if estimated > datetime.utcnow():
            due = round((estimated - datetime.utcnow()).seconds / 60)
        return due

# Exceptions
class InvalidAPIKey(Exception):
    """ API key error """

class APIRateLimitExceeded(Exception):
    """ API rate limit exceeded """

class StopError(Exception):
    """ Stop-finder related error """
    def __init__(self, message = "", stop_detail = ""):
        super().__init__(message)
        self.stop_detail = stop_detail

#    def __str__(self):
#        return f"{self.message}"

class TripError(Exception):
    """" Trip-finder related error """
