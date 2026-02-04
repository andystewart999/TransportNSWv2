"""  A module to query Transport NSW (Australia) departure times.         """
"""  First created by Dav0815 ( https://pypi.org/user/Dav0815/)           """
"""  Extended by AndyStewart999 ( https://pypi.org/user/andystewart999/ ) """

from datetime import datetime, timedelta
from google.transit import gtfs_realtime_pb2

import requests
import logging
import re
import json
import time
import copy
import sys

from zoneinfo import ZoneInfo

# Global API variable
api_calls = 0

# Constants
CONF_FIRST_LEG_DEVICE_TRACKER = 'first_leg_device_tracker'
CONF_LAST_LEG_DEVICE_TRACKER = 'last_leg_device_tracker'
CONF_ORIGIN_DEVICE_TRACKER = 'origin_device_tracker'
CONF_DESTINATION_DEVICE_TRACKER = 'destination_device_tracker'
CONF_CHANGES_DEVICE_TRACKER = 'changes_device_tracker'

def reset_api_counter():
    global api_calls
    api_calls = 0

def increment_api_counter(source):
    global api_calls
    api_calls += 1
    #print(str(api_calls) + " " + source)

# Constants
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
ATTR_DESTINATION_TRANSPORT_TYPE = 'destination_transport_type'
ATTR_DESTINATION_TRANSPORT_NAME = 'destination_transport_name'
ATTR_DESTINATION_LINE_NAME = 'destination_line_name'
ATTR_DESTINATION_LINE_NAME_SHORT = 'destination_line_name_short'

ATTR_CHANGES = 'changes'
ATTR_LOCATIONS_LIST = 'locations_list'

ATTR_ORIGIN_OCCUPANCY = 'origin_occupancy'
ATTR_DESTINATION_OCCUPANCY = 'destination_occupancy'

ATTR_ORIGIN_REAL_TIME_TRIP_ID = 'origin_real_time_trip_id'
ATTR_DESTINATION_REAL_TIME_TRIP_ID = 'destination_real_time_trip_id'
ATTR_ORIGIN_LATITUDE = 'origin_latitude'
ATTR_ORIGIN_LONGITUDE = 'origin_longitude'
ATTR_DESTINATION_LATITUDE = 'destination_latitude'
ATTR_DESTINATION_LONGITUDE = 'destination_longitude'

ATTR_ALERTS = 'alerts'

logger = logging.getLogger(__name__)

class TransportNSWv2(object):
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
            ATTR_DESTINATION_TRANSPORT_TYPE : 'n/a',
            ATTR_DESTINATION_TRANSPORT_NAME : 'n/a',
            ATTR_DESTINATION_LINE_NAME : 'n/a',
            ATTR_DESTINATION_LINE_NAME_SHORT : 'n/a',
            ATTR_CHANGES : 'n/a',
            ATTR_LOCATIONS_LIST: [],
            ATTR_ORIGIN_OCCUPANCY: 'n/a',
            ATTR_DESTINATION_OCCUPANCY: 'n/a',
            ATTR_ORIGIN_REAL_TIME_TRIP_ID : 'n/a',
            ATTR_ORIGIN_LATITUDE : 'n/a',
            ATTR_ORIGIN_LONGITUDE : 'n/a',
            ATTR_DESTINATION_REAL_TIME_TRIP_ID : 'n/a',
            ATTR_DESTINATION_LATITUDE : 'n/a',
            ATTR_DESTINATION_LONGITUDE : 'n/a',
            ATTR_ALERTS: '[]'
            }


    def check_stops(self, api_key, stops):
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


        try:
            for stop in stops:
                # Don't check it if it's coords
                if not self._origin_is_coords(stop):
                    # Make an educated guess about what the data is that we've been sent - assume the worst
                    type_sf = 'any'

                    # If the data is numeric then it's a stop ID.  Some bus stops have a 'G' at the beginning so cater for that also
                    if stop[1:].isnumeric():
                        type_sf = 'stop'

                    # Send the query
                    url = 'https://api.transport.nsw.gov.au/v1/tp/stop_finder?outputFormat=rapidJSON&coordOutputFormat=EPSG%3A4326&type_sf=' + type_sf + '&name_sf=' + str(stop) + '&TfNSWSF=true'
                    error_code = 0

                    if not skip_api_calls:
                        # Make the call and increment the API counter
                        response = requests.get(url, headers=header, timeout=5)
                        increment_api_counter('stop_finder')

                    else:
                        # An earlier call resulted in an API key error so no point trying again
                        response.status_code = 401

                    # If we get bad status code, handle it depending on the error type
                    if response.status_code != 200:
                        # We can't be sure that all the stops are valid
                        error_code = response.status_code
                        stop_response = []

                        if response.status_code == 401:
                            raise InvalidAPIKey("Invalid API key")

                        elif response.status_code == 403 or response.status_code == 429:
                            raise APIRateLimitExceeded("API rate limit exceeded")

                    else:
                        # Parse the result as a JSON object
                        stop_response = response.json()
                        stop_warning = False

                        # Just a quick check - the presence of systemMessages signifies an error, otherwise we assume it's ok
                        if 'systemMessages' in stop_response:
                            stop_warning = True
                            error_code = stop_response['systemMessages'][0]['code']

                        # Put in a pause here to try and make sure we stay under the 5 API calls/second limit
                        # Not usually an issue but if multiple processes are running multiple calls we might hit it
                        time.sleep(1.0)

                    # Append the results to the JSON output - only return the 'isBest' location entry if there's more than one
                    if stop_response != []:
                        # We want a positive indicator that this is a valid stop
                        stop_valid = False
                        stop_detail = []

                        for location in stop_response['locations']:
                            if location['isBest']:
                                # Make sure it's a stop ID we can use
                                actual_stop_id = location['id']
                                if actual_stop_id[1:].isnumeric():
                                    # We can use this
                                    stop_detail = location
                                    stop_valid = True
                                    stop = actual_stop_id
                                    break

                        if not stop_valid:
                            all_stops_valid = False

                    else:
                        stop_valid = False
                        all_stops_valid = False
                        stop_detail = []

                    #Add it to the list
                    data = {"stop_id": stop, "valid": stop_valid, "warning": stop_warning, "error_code": error_code, "stop_detail": stop_detail}

                else:
                    data = {"stop_id": stop, "valid": True, "warning": False, "error_code": "", "stop_detail": {}}

                stop_list.append (data)

                #Put in a quick pause here to make sure we stay under the API calls/second threshold
                time.sleep(0.75)


            # Complete the JSON output and return it
            data = {"all_stops_valid": all_stops_valid, "stop_list": stop_list}

            return json.dumps(data)

        except InvalidAPIKey as ex:
            raise InvalidAPIKey (f"Invalid API key {api_key}")

        except StopError as ex:
            raise StopError (f"Error '{ex}' calling stop finder API for stop ID {stop}")

        except Exception as ex:
            raise StopError(f"Error '{ex}' calling stop finder API for stop ID {stop}", stop)


    def get_trip(self, name_origin, name_destination , api_key, journey_wait_time = 0, origin_transport_type = [0], destination_transport_type = [0], \
                 strict_transport_type = False, raw_output = False, journeys_to_return = 1, route_filter = '', \
                 include_realtime_location = True, include_alerts = 'none', alert_type = ['all'], check_stop_ids = True, max_changes = 9):

        """Get the latest data from Transport NSW."""
        fmt = '%Y-%m-%dT%H:%M:%SZ'
        reset_api_counter()

        route_filter = route_filter.lower()
        include_alerts = include_alerts.lower()

        # Sanity checking - convert any single-instance variables to lists
        if isinstance(origin_transport_type, int):
            origin_transport_type = [origin_transport_type]

        if isinstance(destination_transport_type, int):
            destination_transport_type = [destination_transport_type]

        if isinstance(alert_type, str):
            alert_type = alert_type.split('|')

        if isinstance(name_destination, str):
            name_destination = [name_destination]


        alert_type = [alert.lower() for alert in alert_type]

        # This query always uses the current date and time - but add in any 'journey_wait_time' minutes
        now_plus_wait = datetime.now() + timedelta(minutes = journey_wait_time)
        itdDate = now_plus_wait.strftime('%Y%m%d')
        itdTime = now_plus_wait.strftime('%H%M')

        auth = 'apikey ' + api_key
        header = {'Accept': 'application/json', 'Authorization': auth}

        origin_transport_type_copy = copy.deepcopy(origin_transport_type)
        destination_transport_type_copy = copy.deepcopy(destination_transport_type)

        # Check to see if the origin is a lat/lon or a stop ID
        if self._origin_is_coords(name_origin):
            type_origin = "coord"
            exclusion = self._get_excluded_means(list(set(origin_transport_type_copy + destination_transport_type_copy)))

            # Make sure walking and footpaths are in the origin transport types list
            for tt in [99, 100]:
                if tt not in origin_transport_type_copy:
                    origin_transport_type_copy.append(tt)

        else:
            type_origin = "any"
            exclusion = self._get_excluded_means(list(set(origin_transport_type_copy + destination_transport_type_copy)))

        # First, check if the source and dest stops are valid unless we've been told not to
        if check_stop_ids:
            # name_destination is already a list, so just append name_origin to it for the stop check
            stop_list = name_destination
            stop_list.append(name_origin)
            data = self.check_stops(api_key, stop_list)

            if not data['all_stops_valid']:
                # One or both of those stops was invalid - log an error and exit
                stop_error = ""

                for stop in data['stop_list']:
                    if not stop['valid']:
                        stop_error += stop['stop_id']+ ", "

                raise StopError (f"Stop ID(s) {stop_error[:-2]} invalid", stop_error)


        # We don't control how many journeys are returned any more, so need to be careful of running out of valid journeys if there is a filter in place, particularly a strict filter
        # It would be more efficient to return one journey, check if the filter is met and then retrieve the next one via a new query if not, but for now we'll only be making use of the journeys we've been given

        json_output = {}
        valid_journeys = []

        for destination in name_destination:
            # Build the entire URL
            url = \
                'https://api.transport.nsw.gov.au/v1/tp/trip?' \
                'outputFormat=rapidJSON&coordOutputFormat=EPSG%3A4326' \
                '&depArrMacro=dep&itdDate=' + itdDate + '&itdTime=' + itdTime + \
                '&type_origin=' + type_origin + '&name_origin=' + name_origin + \
                '&type_destination=any&name_destination=' + destination + \
                exclusion + '&TfNSWTR=true'

            # Send the query and return an error if something goes wrong
            # Otherwise store the response for the next steps
            try:
                response = requests.get(url, headers=header, timeout=10)
                increment_api_counter('trip')

            except Exception as ex:
                raise TripError (f"Error '{str(ex)}' calling trip API for journey {name_origin} to {destination}")

            # If we get bad status code, log error and return with n/a or an empty string
            if response.status_code != 200:
                if response.status_code == 401:
                    # API key issue
                    raise InvalidAPIKey("Error 'Invalid API key' calling trip API for journey {name_origin} to {destination}")

                elif response.status_code == 403 or response.status_code == 429:
                    raise APIRateLimitExceeded("Error 'API rate limit exceeded' calling trip API for journey {name_origin} to {destination}")

                else:
                    raise TripError(f"Error '{str(response.status_code)}' calling trip API for journey {name_origin} to {destination}")

            result = response.json()

            # The API will always return a valid trip, so it's just a case of grabbing the metadata that we need... We're only reporting on the origin and destination, it's out of
            # scope to discuss the specifics of the ENTIRE journey This isn't a route planner, just a 'how long until the next journey I've specified' tool The assumption is that the
            # travelee will know HOW to make the defined journey, they're just asking WHEN it's happening next All we potentially have to do is find the first trip that matches the
            # transport_type filter

            if raw_output == True:
                # Just return the raw output
                return json.dumps(result)

            # Make sure we've got at least one journey
            try:
                retrieved_journeys = len(result['journeys'])

            except:
                raise TripError(f"Error 'no journeys returned' calling trip API for journey {name_origin} to {destination}")

            # Loop through the results applying filters where required, and generate the appropriate JSON output including an array of in-scope trips
            found_journeys = 0
            no_valid_journeys = False

            for current_journey_index in range (0, retrieved_journeys, 1):
                # Look for a trip with a matching transport type filter in at least one of its legs.  Either ANY, or the first leg, depending on how strict we're being
                # Note that if the journey starts with a device tracker, then the first leg will actually be the second leg, if the first leg is walking
                legs, next_journey_index, first_leg, last_leg, changes, locations_list = self._find_next_journey(result['journeys'], current_journey_index, origin_transport_type_copy, destination_transport_type, strict_transport_type, route_filter, type_origin)

                if legs is None:
                    # An empty journey that didn't meet the criteria - which means all the valid journeys have been found already
                    # To many changes so ignore this otherwise valid journey
                    pass
                elif changes > max_changes:
                    # Too many changes so ignore this otherwise valid journey
                    pass
                else:
                    origin_leg = first_leg['origin']
                    origin_stop = first_leg['destination']
                    destination_stop = last_leg['destination']
                    origin_transportation = first_leg['transportation']
                    destination_transportation = last_leg['transportation']

                    # Origin info
                    origin_stop_id = origin_leg['id']
                    origin_name = origin_leg['name']
                    origin_departure_time = origin_leg['departureTimeEstimated']
                    origin_departure_time_planned = origin_leg['departureTimePlanned']

                    t1 = datetime.strptime(origin_departure_time, fmt).timestamp()
                    t2 = datetime.strptime(origin_departure_time_planned, fmt).timestamp()
                    delay = int((t1-t2) / 60)
                    utc_dt = datetime.fromisoformat(origin_departure_time.replace('Z', '+00:00'))
                    local_dt = utc_dt.astimezone(ZoneInfo("localtime"))

                    # How long until it leaves?
                    due = self._get_due(datetime.strptime(origin_departure_time, fmt))

                    # Destination info
                    destination_stop_id = destination_stop['id']
                    destination_name = destination_stop['name']
                    destination_arrival_time = destination_stop['arrivalTimeEstimated']

                    # Origin type info - train, bus, etc
                    origin_mode = self._get_mode(origin_transportation['product']['class'])
                    origin_mode_name = origin_transportation['product']['name']

                    # Destination type info - train, bus, etc
                    destination_mode = self._get_mode(destination_transportation['product']['class'])
                    destination_mode_name = destination_transportation['product']['name']

                    # RealTimeTripID info so we can try and get the current location later
                    origin_realtimetripid = 'n/a'
                    origin_agencyid = ''
                    destination_realtimetripid = 'n/a'
                    destination_agencyid = ''

                    if origin_mode != 'Walk':
                        if 'properties' in origin_transportation:
                            for tripidsource in ['RealtimeTripId', 'AVMSTripID']:
                              if tripidsource in origin_transportation['properties']:
                                origin_realtimetripid = origin_transportation['properties'][tripidsource]
                                origin_agencyid = origin_transportation['operator']['id']
                                break

                    if destination_mode != 'Walk':
                        if 'properties' in destination_transportation:
                          for tripidsource in ['RealtimeTripId', 'AVMSTripID']:
                            if tripidsource in destination_transportation['properties']:
                              destination_realtimetripid = destination_transportation['properties'][tripidsource]
                              destination_agencyid = destination_transportation['operator']['id']
                              break

                    # Line info
                    origin_line_name_short = 'n/a'
                    if 'disassembledName' in origin_transportation:
                        origin_line_name_short = origin_transportation['disassembledName']

                    origin_line_name = 'n/a'
                    if 'number' in origin_transportation:
                        origin_line_name = origin_transportation['number']

                    destination_line_name_short = 'n/a'
                    if 'disassembledName' in destination_transportation:
                        destination_line_name_short = destination_transportation['disassembledName']

                    destination_line_name = 'n/a'
                    if 'number' in destination_transportation:
                        destination_line_name = destination_transportation['number']

                    # Occupancy info, if it's there
                    origin_occupancy = 'n/a'
                    destination_occupancy = 'n/a'

                    if origin_mode != 'Walk':
                        if 'properties' in origin_stop and 'occupancy' in origin_stop['properties']:
                            origin_occupancy = origin_stop['properties']['occupancy']

                    if destination_mode != 'Walk':
                        if 'properties' in destination_stop and 'occupancy' in destination_stop['properties']:
                            destination_occupancy = destination_stop['properties']['occupancy']

                    alerts = "[]"
                    if include_alerts != 'none':
                        # We'll be adding these to the returned JSON string as an array
                        # Only include alerts of the specified priority or greater, and of the specified type
                        alerts = self._find_alerts(legs, include_alerts, alert_type)

                    #origin_latitude = 'n/a'
                    #origin_longitude = 'n/a'
                    #destination_latitude = 'n/a'
                    #destination_longitude = 'n/a'

                    if include_realtime_location and origin_realtimetripid != 'n/a':
                        origin_latitude, origin_longitude = self._find_location(api_key, origin_mode, origin_realtimetripid, origin_agencyid)
                        if origin_latitude != 'n/a':
                            locations_list['vehicles'].append(self._add_location_info(origin_latitude, origin_longitude, CONF_FIRST_LEG_DEVICE_TRACKER))

                    if include_realtime_location and destination_realtimetripid != 'n/a':
                        destination_latitude, destination_longitude = self._find_location(api_key, destination_mode, destination_realtimetripid, destination_agencyid)
                        if destination_latitude != 'n/a':
                            locations_list['vehicles'].append(self._add_location_info(destination_latitude, destination_longitude, CONF_LAST_LEG_DEVICE_TRACKER))

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
                        ATTR_DESTINATION_TRANSPORT_TYPE : destination_mode,
                        ATTR_DESTINATION_TRANSPORT_NAME: destination_mode_name,
                        ATTR_DESTINATION_LINE_NAME : destination_line_name,
                        ATTR_DESTINATION_LINE_NAME_SHORT : destination_line_name_short,
                        ATTR_CHANGES: changes,
                        ATTR_LOCATIONS_LIST: locations_list,
                        ATTR_ORIGIN_OCCUPANCY: origin_occupancy,
                        ATTR_DESTINATION_OCCUPANCY: destination_occupancy,
                        ATTR_ORIGIN_REAL_TIME_TRIP_ID: origin_realtimetripid,
                        ATTR_DESTINATION_REAL_TIME_TRIP_ID: destination_realtimetripid,
                        ATTR_ORIGIN_LATITUDE: origin_latitude,
                        ATTR_ORIGIN_LONGITUDE: origin_longitude,
                        ATTR_DESTINATION_LATITUDE: destination_latitude,
                        ATTR_DESTINATION_LONGITUDE: destination_longitude,
                        ATTR_ALERTS: json.loads(alerts)
                        }

                    found_journeys = found_journeys + 1

                    # Add to the return array
                    if (no_valid_journeys == True):
                        break

                    # This is a valid journey, add it to the list.  It will be sorted later
                    valid_journeys.append(self.info)

                    if (found_journeys == journeys_to_return):
                        break

                    current_journey_index = next_journey_index

        # Order valid_journeys by 'due'
        #sorted_valid_journeys = sorted(valid_journeys, key = lambda d: datetime.fromisoformat(d['arrival_time']))   #This line requires Python >=3.11
        sorted_valid_journeys = sorted(valid_journeys, key = lambda d: datetime.fromisoformat(d['arrival_time'].replace("Z", "+00:00")))

        # Now truncate it, if necessary
        if len(sorted_valid_journeys) > journeys_to_return:
            sorted_valid_journeys = sorted_valid_journeys[:journeys_to_return]

        json_output = {
            'journeys_to_return': journeys_to_return,
            'journeys_with_data': found_journeys,
            'api_calls': api_calls,
            'journeys': sorted_valid_journeys
            }

        return json.dumps(json_output)


    def _find_next_journey(self, journeys, start_journey_index, origin_transport_type_copy, destination_transport_type, strict, route_filter, type_origin):
        # Find the next journey that has a leg of the requested type, and/or that satisfies the route filter
        journey_count = len(journeys)

        # Some basic error checking
        if start_journey_index > journey_count:
            return None, None, None, None, 9, None

        for journey_index in range (start_journey_index, journey_count, 1):
            journey = journeys[journey_index]
            origin_leg = self._find_first_leg(journey['legs'], origin_transport_type_copy, strict, route_filter, type_origin)
            if origin_leg is not None:
                destination_leg = self._find_last_leg(journey['legs'], destination_transport_type, strict)

            if origin_leg is not None and destination_leg is not None:
                changes, locations_list = self._find_changes(journey['legs'], origin_leg, destination_leg)
                return journey['legs'], journey_index + 1, origin_leg, destination_leg, changes, locations_list
            else:
                return None, None, None, None, 9, None

        # Hmm, we didn't find one
        return None, None, None, None, 9, None


    def _find_first_leg(self, legs, transport_type, strict, route_filter, type_origin):
        # Find the first leg of the requested type
        for index, leg in enumerate(legs):
            if type_origin == "coord":
                if index == 0 and leg['transportation']['product']['class'] >= 99:
                    #Skip the walking leg of a journey that starts with a device tracker
                    continue

            #First, check against the route filter
            origin_line_name_short = 'n/a'
            origin_line_name = 'n/a'

            if 'transportation' in leg and 'disassembledName' in leg['transportation']:
                origin_line_name_short = leg['transportation']['disassembledName'].lower()
                origin_line_name = leg['transportation']['number'].lower()

                if (route_filter in origin_line_name_short or route_filter in origin_line_name):
                    # This leg passes the route filter, check it passes any transport type filter as well
                    leg_class = leg['transportation']['product']['class']
                    if leg_class in transport_type:
                        # This leg meets the transport type criteria
                        return leg

                    if 0 in transport_type and leg_class < 99:
                        # We don't have a filter, and this is the first non-walk/cycle leg so return that leg
                        return leg

                # Exit if we're doing strict filtering and we haven't found that type in the first leg, which we haven't if we've got this far
                    if strict == True:
                        return None

        # Hmm, we didn't find one
        return None

    def _find_last_leg(self, legs, transport_type, strict):
        # Find the last leg of the requested type
        for leg in reversed(legs):
            leg_class = leg['transportation']['product']['class']

            if leg_class in transport_type:
            # We've got a filter, and the leg type matches it, so return that leg
                return leg

            if 0 in transport_type and leg_class < 99:
            # We don't have a filter, and this is the first non-walk/cycle leg so return that leg
                return leg

            # Exit if we're doing strict filtering and we haven't found that type in the last leg
            if strict == True:
                return None

        # Hmm, we didn't find one
        return None


    def _find_first_stop(self, legs, origin_leg, destination_leg):
        # Find the first origin that's an actual stop - used to over-ride the origin for coord-based journey starts
        bInJourney = False

        for leg in legs:
            if leg == origin_leg:
                bInJourney = True

            if bInJourney:
                leg_class = leg['transportation']['product']['class']
                if leg_class < 99:
                    new_origin_leg = leg
                    new_origin_id = leg['origin']['id']
                    new_origin_name = leg['origin']['name']

                    return new_origin_leg, new_origin_id, new_origin_name

        return "", ""

    def _get_location_info(self, leg, section, key):
        section_name = leg[section]["name"]
        section_id = leg[section]["id"]
        section_disassembled_name = leg[section]["disassembledName"]
        section_coords = leg[section]["coord"]

        return {
            "name": section_name,
            "id": section_id,
            "disassembled_name": section_disassembled_name,
            "coords": section_coords,
            "key": key
        }

    def _add_location_info(self, latitude, longitude, key):

        return {
            "name": key,
            "disassembled_name": key,
            "coords": [latitude, longitude],
            "key": key
        }

    def _find_changes(self, legs, origin_leg, destination_leg):
        # Find out how often we have to change.  Immediately return 0 if the origin and destination legs are the same
        locations_list = []
        changes = 0

        # Count the changes, each time we hit s new non-walking leg is considered to be a change
        bInJourney = False

        # For each leg, once we're in the journey, just add the origin and destination!  no other mucking about
        for leg in legs:
            if leg == origin_leg:
                # We're in the journey so start capturing changes
                bInJourney = True

            if bInJourney:
                # Add the origin to the full locations list
                if leg == origin_leg:
                    key = CONF_ORIGIN_DEVICE_TRACKER
                else:
                    key = ''

                locations_list.append(self._get_location_info(leg, "origin", key))

                # Add the destination to the full locations list
                if leg == destination_leg:
                    key = CONF_DESTINATION_DEVICE_TRACKER
                else:
                    changes += 1
                    key = f"{CONF_CHANGES_DEVICE_TRACKER}_{changes}"

                locations_list.append(self._get_location_info(leg, "destination", key))

            if leg == destination_leg:
                # We've reached the destination so let's break out
                #return changes, {"changes": changes, "locations": locations_list, "vehicles":[]}
                return changes, {"locations": locations_list, "vehicles":[]}

        # We should never get here!
        return 999, None


    def _find_alerts(self, legs, priority_filter, alert_type):
        # Return an array of all the alerts on this trip that meet the priority level and alert type
        found_alerts = []
        priority_minimum = self._get_alert_priority(priority_filter)

        for leg in legs:
            if 'infos' in leg:
                for alert in leg['infos']:
                    if (self._get_alert_priority(alert['priority'])) >= priority_minimum:
                        if ('all' in alert_type) or (alert['type'].lower() in alert_type):
                            found_alerts.append (alert)

        return json.dumps(found_alerts)


    def _find_location(self, api_key, mode, realtimetripid, agencyid):
        # See if we can get the latitude and longitude via the Realtime Vehicle Positions API

        latitude = 'n/a'
        longitude = 'n/a'

        auth = 'apikey ' + api_key
        header = {'Accept': 'application/x-google-protobuf', 'Authorization': auth}

        realtime_url = self._get_realtime_url(agencyid)

        if not realtime_url is None:
            response = requests.get(realtime_url, headers=header, timeout=10)
            increment_api_counter(realtime_url)

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

                        # We found it, so break out
                        return latitude, longitude
            else:
                # Warn that we didn't get a good return
                if response.status_code == 401:
                    logger.error(f"Error 'Invalid API key' calling {realtime_url} API")
                elif response.status_code == 403 or response.status_code == 429:
                    logger.error(f"Error 'API rate limit exceeded' calling {realtime_url} API")
                else:
                    logger.error(f"Error '{str(response.status_code)}' calling {realtime_url} API")

        return latitude, longitude


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
            107 : "Cycle",
        }

        return modes.get(iconId, None)


#    def _get_base_url(self, mode):
#        # Map the journey mode to the proper base real time location URL
#        v1_url = "https://api.transport.nsw.gov.au/v1/gtfs/vehiclepos"
#        v2_url = "https://api.transport.nsw.gov.au/v2/gtfs/vehiclepos"

#        url_options = {
#            "Train"      : v2_url,
#            "Metro"      : v2_url,
#            "Light rail" : v2_url, # Changed on 14th Oct
#            "Bus"        : v1_url,
#            "Coach"      : v1_url,
#            "Ferry"      : v1_url,
#            "School bus" : v1_url
#        }
#
#        return url_options.get(mode, None)


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


    def _get_realtime_url(self, agencyid):
        """
        Map the journey mode to the proper realtime-location URL
        """

        # Use this CSV resource to determine the appropriate real-time location URL
        # I'm hoping that this CSV resource URL is static when updated by TransportNSW!  So far so good.
        url = "https://opendata.transport.nsw.gov.au/data/api/action/datastore_search?resource_id=30b850b7-f439-4e30-8072-e07ef62a2a36&filters={%22Complete%20GTFS%20agency_id%22:%22" + agencyid + "%22}&limit=1"

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
            return result['result']['records'][0]['Vehicle Position Feed']
        else:
            return None


    def _get_due(self, estimated):
        # Minutes until departure
        due = 0
        if estimated > datetime.utcnow():
            due = round((estimated - datetime.utcnow()).seconds / 60)
        return due

    def _origin_is_coords(self, origin):
        # Check to see if the origin is coordinates, not a stop ID
        if "EPSG" in origin:
            return True
        else:
            return False


    def _get_excluded_means(self, transport_type):
        # Create an 'excluded transport type' string based on what's INCLUDED in the transport_type list
        if transport_type == [0]:
            return ""

        exclMOT = {
            "exclMOT_1":  1,
            "exclMOT_2":  1,
            "exclMOT_4":  1,
            "exclMOT_5":  1,
            "exclMOT_7":  1,
            "exclMOT_9":  1,
            "exclMOT_11": 1
        }

        try:
            for tt in transport_type:
                exclMOT[f"exclMOT_{tt}"] = 0

        finally:
            exclMOTstring = "&".join(f"{key}={value}" for key, value in exclMOT.items() if value == 1)

        return f"&excludedMeans=checkbox&{exclMOTstring}"



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

class TripError(Exception):
    """" Trip-finder related error """
