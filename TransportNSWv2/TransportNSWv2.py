"""  A module to query Transport NSW (Australia) departure times.         """
"""  First created by Dav0815 ( https://pypi.org/user/Dav0815/)           """
"""  Extended by AndyStewart999 ( https://pypi.org/user/andystewart999/ ) """
from datetime import datetime, timedelta
import requests
import logging
import re
import json
import time
import copy
import sys
from .gtfs_extensions import tfnsw_gtfs_extensions

# Global variables
api_calls = 0

def reset_api_counter():
    global api_calls
    api_calls = 0


def increment_api_counter(source):
    global api_calls
    api_calls += 1


# Constants
CONF_FIRST_LEG_DEVICE_TRACKER = 'first_leg_device_tracker'
CONF_LAST_LEG_DEVICE_TRACKER = 'last_leg_device_tracker'
CONF_ORIGIN_DEVICE_TRACKER = 'origin_device_tracker'
CONF_DESTINATION_DEVICE_TRACKER = 'destination_device_tracker'
CONF_CHANGES_DEVICE_TRACKER = 'changes_device_tracker'
ATTR_DUE_IN = 'due'
ATTR_FIRST_LEG_WALKING = 'first_leg_walking'
ATTR_DELAY = 'delay'
ATTR_DURATION = 'duration'
ATTR_ORIGIN_DETAIL = 'origin_detail'
ATTR_DESTINATION_DETAIL = 'destination_detail'
ATTR_ORIGIN_TRANSPORT_DETAIL = 'origin_transport_detail'
ATTR_DESTINATION_TRANSPORT_DETAIL = 'destination_transport_detail'
ATTR_CHANGES = 'changes'
ATTR_CHANGES_SIMPLE = 'changes_simple'
ATTR_LOCATIONS_LIST = 'locations_list'
ATTR_ORIGIN_OCCUPANCY = 'origin_occupancy'
ATTR_DESTINATION_OCCUPANCY = 'destination_occupancy'
ATTR_ORIGIN_REAL_TIME_TRIP_ID = 'origin_real_time_trip_id'
ATTR_ORIGIN_GTFS_TRIP_ID = 'origin_gtfs_trip_id'
ATTR_DESTINATION_REAL_TIME_TRIP_ID = 'destination_real_time_trip_id'
ATTR_DESTINATION_GTFS_TRIP_ID = 'destination_gtfs_trip_id'
ATTR_ORIGIN_NEXT_MAJOR_HUB = 'origin_next_major_hub'            # TBD: work out the next major hub from journey text and time
ATTR_ORIGIN_END_OF_LINE = 'origin_end_of_line'
ATTR_DESTINATION_NEXT_MAJOR_HUB ='destination_next_major_hub'
ATTR_DESTINATION_END_OF_LINE = 'destination_end_of_line'
ATTR_ORIGIN_RUN_NAME = 'origin_run_name'
ATTR_DESTINATION_RUN_NAME = 'destination_run_name'
ATTR_ALERTS = 'alerts'

_LOGGER = logging.getLogger(__name__)

class TransportNSWv2(object):
    """The Class for handling the data retrieval."""

    # The application requires an API key. You can register for
    # free on the service NSW website for it.
    # You need to register for both the Trip Planner and Realtime Vehicle Position APIs

    def __init__(self):
        """Initialize the data object with default values."""
        self._info = {}
        self._gtfs_cache = {}

    def check_stops(self, api_key, stops, sleep_time = 0.2):
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
                            raise APIRateLimitExceeded("API rate limit exceeded calling /stop_finder API")

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
                        time.sleep(sleep_time)

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

                # Put in a quick pause here to make sure we stay under the API calls/second threshold
                # This number is a bit arbitrary, unforunately
                time.sleep(sleep_time)


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
                 include_realtime_location = True, include_alerts = 'none', alert_type = ['all'], check_stop_ids = True, max_changes = 9, sleep_time = 0.2):

        """Get the latest data from Transport NSW."""
        fmt = '%Y-%m-%dT%H:%M:%SZ'
        reset_api_counter()
        self._gtfs_cache = {}

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
            # It's a lat/lon origin
            type_origin = "coord"
            exclusion = self._get_excluded_means(list(set(origin_transport_type_copy + destination_transport_type_copy)))

            # Make sure walking and footpaths are in the origin transport types list
            for tt in [99, 100]:
                if tt not in origin_transport_type_copy:
                    origin_transport_type_copy.append(tt)

        else:
            # It's a stop ID
            type_origin = "any"
            exclusion = self._get_excluded_means(list(set(origin_transport_type_copy + destination_transport_type_copy)))

            # If 99 is in the transport types lists, add 100 as well.  Some walking sections are classed as 100, not 99, I don't know why
            for tt in [origin_transport_type_copy, destination_transport_type_copy]:
                if 99 in tt:
                    tt.append(100)
                    break  # Haha, suck it up, purists!

        # First, check if the source and dest stops are valid unless we've been told not to
        if check_stop_ids:
            # name_destination is already a list, so just append name_origin to it for the stop check
            stop_list = name_destination
            stop_list.append(name_origin)
            data = self.check_stops(api_key, stop_list, sleep_time)

            if not data['all_stops_valid']:
                # One or both of those stops was invalid - log an error and exit
                stop_error = ""

                for stop in data['stop_list']:
                    if not stop['valid']:
                        stop_error += stop['stop_id']+ ", "

                raise StopError (f"Stop ID(s) {stop_error[:-2]} invalid", stop_error)


        # We don't control how many journeys are returned although we CAN request a specific number of journeys, so need to be careful of running out of valid journeys if there is a filter in place, particularly a strict filter
        # It would be more efficient to return one journey, check if the filter is met and then retrieve the next one via a new query if not, but for now we'll only be making use of the journeys we've been given

        json_output = {}
        valid_journeys = []
        api_rate_warning = False

        for destination in name_destination:
            # Build the entire URL
            url = \
                'https://api.transport.nsw.gov.au/v1/tp/trip?' \
                'outputFormat=rapidJSON&coordOutputFormat=EPSG%3A4326' \
                '&depArrMacro=dep&itdDate=' + itdDate + '&itdTime=' + itdTime + \
                '&type_origin=' + type_origin + '&name_origin=' + name_origin + \
                '&type_destination=any&name_destination=' + destination + \
                exclusion + '&TfNSWTR=true&calcNumberOfTrips=' + str(journeys_to_return * 2)

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

            # Put in a pause here to try and make sure we stay under the 5 API calls/second limit
            # Not usually an issue but if multiple processes are running multiple calls we might hit it
            time.sleep(sleep_time)

            result = response.json()
            # The API will always return a valid trip, so it's just a case of grabbing the metadata that we need... We're only reporting on the origin and destination, it's out of
            # scope to discuss the specifics of the ENTIRE journey This isn't a route planner, just a 'how long until the next journey I've specified' tool The assumption is that the
            # travelee will know HOW to make the defined journey, they're just asking WHEN it's happening next.  All we potentially have to do is find the first trip that matches the
            # transport_type filter

            if raw_output == True:
                # Just return the raw output
                return json.dumps(result)

            # Make sure we've got at least one journey
            try:
                if 'journeys' in result:
                    retrieved_journeys = len(result['journeys'])
                else:
                    retrieved_journeys = 0
            except:
                retrieved_journeys = 0
#                raise TripError(f"Error 'no journeys returned' calling trip API for journey {name_origin} to {destination}")

            # Loop through the results applying filters where required, and generate the appropriate JSON output including an array of in-scope trips
            found_journeys = 0

            for current_journey_index in range (0, retrieved_journeys, 1):
                # Look for a trip with a matching transport type filter in at least one of its legs.  Either ANY, or the first leg, depending on how strict we're being
                # Note that if the journey starts with a device tracker, then the first leg will actually be the second leg, if the first leg is walking
                journey, next_journey_index, first_leg, last_leg, changes, changes_simple, locations_list, first_leg_walking = self._find_next_journey(result['journeys'], current_journey_index, origin_transport_type_copy, destination_transport_type, strict_transport_type, route_filter, type_origin)
                if journey is None:
                    # An empty journey that didn't meet the criteria - which means all the valid journeys have been found already
                    pass

                elif changes > max_changes:
                    # Too many changes so ignore this otherwise valid journey
                    pass

                else:
                    legs = journey['legs']
                    origin_leg = first_leg['origin']
                    origin_stop = first_leg['destination']
                    destination_stop = last_leg['destination']

                    origin_transportation = first_leg['transportation']
                    origin_end_of_line = origin_transportation['destination']['name'].split('via')[0].strip()
                    origin_run_name = origin_transportation['description']

                    destination_transportation = last_leg['transportation']
                    destination_end_of_line = destination_transportation['destination']['name'].split('via')[0].strip()
                    destination_run_name = destination_transportation['description']

                    # Origin type info - train, bus, etc
                    origin_mode, origin_mode_default = self._get_mode(origin_transportation['product']['class'])
                    origin_mode_name = origin_transportation['product']['name']

                    # Destination type info - train, bus, etc
                    destination_mode, destination_mode_default = self._get_mode(destination_transportation['product']['class'])
                    destination_mode_name = destination_transportation['product']['name']

                    # Origin info
                    origin_stop_id = origin_leg['id']
                    origin_name = origin_leg['name']
                    origin_departure_time = origin_leg['departureTimeEstimated']
                    origin_departure_time_planned = origin_leg['departureTimePlanned']

                    # Get the type-specific detail from the name, ie just the platform for a train station
                    origin_name_extract = self._get_specific_detail(origin_name, origin_mode)

                    origin_detail = {
                        'stop_id': origin_stop_id,
                        'name': origin_name,
                        'detail': origin_name_extract,
                        'departure_time': origin_departure_time,
                        'departure_time_planned': origin_departure_time_planned
                    }

                    t1 = datetime.strptime(origin_departure_time, fmt).timestamp()
                    t2 = datetime.strptime(origin_departure_time_planned, fmt).timestamp()
                    delay = int((t1-t2) / 60)

                    # How long until it leaves?
                    due = self._get_due(datetime.strptime(origin_departure_time, fmt))

                    # Destination info
                    destination_stop_id = destination_stop['id']
                    destination_name = destination_stop['name']
                    destination_arrival_time = destination_stop['arrivalTimeEstimated']
                    destination_arrival_time_planned = destination_stop['arrivalTimePlanned']

                    # Get the type-specific detail from the name, ie just the platform for a train station
                    destination_name_extract = self._get_specific_detail(destination_name, destination_mode)

                    destination_detail = {
                        'stop_id': destination_stop_id,
                        'name': destination_name,
                        'detail': destination_name_extract,
                        'arrival_time': destination_arrival_time,
                        'arrival_time_planned': destination_arrival_time_planned
                    }

                    # What's the expected duration
                    t3 = datetime.strptime(destination_arrival_time, fmt).timestamp()
                    duration = int ((t3 - t1) / 60)

                    # RealTimeTripID info so we can try and get the current location later
                    origin_realtimetripid = 'Unknown'
                    origin_gtfs_tripid = 'Unknown'
                    origin_agencyid = 'Unknown'
                    destination_realtimetripid = 'Unknown'
                    destination_gtfs_tripid = 'Unknown'
                    destination_agencyid = 'Unknown'

                    if origin_mode != 'Walk':
                        if 'properties' in origin_transportation:
                            # We prefer RealtimeTripID, but we fail back to AVMSTripID if required
                            for tripidsource in ['RealtimeTripId', 'AVMSTripID']:
                                if tripidsource in origin_transportation['properties']:
                                    origin_realtimetripid = origin_transportation['properties'][tripidsource]
                                    origin_agencyid = origin_transportation['operator']['id']
                                    break

                            # Also get gtfsTripId if possible - don't know if we need it yet though
                            if 'gtfsTripId' in origin_transportation['properties']:
                                origin_gtfs_tripid = origin_transportation['properties']['gtfsTripId']

                    if destination_mode != 'Walk':
                        if 'properties' in destination_transportation:
                            # We prefer RealtimeTripID, but we fail back to AVMSTripID if required
                            for tripidsource in ['RealtimeTripId', 'AVMSTripID']:
                                if tripidsource in destination_transportation['properties']:
                                    destination_realtimetripid = destination_transportation['properties'][tripidsource]
                                    destination_agencyid = destination_transportation['operator']['id']
                                    break

                            if 'gtfsTripId' in destination_transportation['properties']:
                                destination_gtfs_tripid = destination_transportation['properties']['gtfsTripId']

                    # Line info
                    origin_line_name_short = 'Unknown'
                    if 'disassembledName' in origin_transportation:
                        origin_line_name_short = origin_transportation['disassembledName']

                    origin_line_name = 'Unknown'
                    if 'number' in origin_transportation:
                        origin_line_name = origin_transportation['number']

                    destination_line_name_short = 'Unknown'
                    if 'disassembledName' in destination_transportation:
                        destination_line_name_short = destination_transportation['disassembledName']

                    destination_line_name = 'Unknown'
                    if 'number' in destination_transportation:
                        destination_line_name = destination_transportation['number']

                    # General occupancy info, if it's there
                    origin_occupancy = 'Unknown'
                    destination_occupancy = 'Unknown'

                    if origin_mode != 'Walk':
                        if 'properties' in origin_stop and 'occupancy' in origin_stop['properties']:
                            origin_occupancy = origin_stop['properties']['occupancy']

                    if destination_mode != 'Walk':
                        if 'properties' in destination_stop and 'occupancy' in destination_stop['properties']:
                            destination_occupancy = destination_stop['properties']['occupancy']

                    alerts = '[]'
                    if include_alerts != 'none':
                        # We'll be adding these to the returned JSON string as an array
                        # Only include alerts of the specified priority or greater, and of the specified type
                        alerts = self._find_alerts(legs, include_alerts, alert_type)

                    # Try and get the location, detailed occupancy and other details of the origin vehicle if possible
                    origin_transport_detail, origin_occupancy, temp_rate_warning = self._find_gtfs_info(include_realtime_location, api_key, origin_mode, origin_mode_default, origin_realtimetripid, origin_agencyid, origin_occupancy, sleep_time)
                    if temp_rate_warning:
                        api_rate_warning = True

                    if origin_transport_detail['location']['latitude'] != 'Unknown':
                        # Add the origin vehicle's current location to the list of journey-relevant locations
                        locations_list['vehicles'].append(self._get_location_info(origin_transport_detail['location'], CONF_FIRST_LEG_DEVICE_TRACKER))

                    # See if we can save time and up to three API invocations if the origin and destination vehicle details are the same, i.e. it's a journey without changes
                    if (origin_realtimetripid == destination_realtimetripid) and (origin_agencyid == destination_agencyid):
                        # We can just re-use what we got from the origin
                        destination_transport_detail = origin_transport_detail
                        destination_occupancy = origin_occupancy
                    else:
                        # Try and get the location, detailed occupancy and other details of the destination vehicle
                        destination_transport_detail, destination_occupancy, temp_rate_warning = self._find_gtfs_info(include_realtime_location, api_key, destination_mode, destination_mode_default, destination_realtimetripid, destination_agencyid, destination_occupancy, sleep_time)
                        if temp_rate_warning:
                            api_rate_warning = True

                    if destination_transport_detail['location']['latitude'] != 'Unknown':
                        # Add the destination vehicle's current location to the list of journey-relevant locations
                        locations_list['vehicles'].append(self._get_location_info(destination_transport_detail['location'], CONF_LAST_LEG_DEVICE_TRACKER))

                    # Add *_occupancy, *_mode_name, *_line_name and *_line_name_short to the appropriate *_transport_detail dict
                    origin_transport_detail['occupancy'] = origin_occupancy
                    origin_transport_detail['provider_name'] = origin_mode_name
                    origin_transport_detail['line_name'] = origin_line_name
                    origin_transport_detail['line_name_short'] = origin_line_name_short
                    origin_transport_detail['run_name'] = origin_run_name
                    origin_transport_detail['end_of_line'] = origin_end_of_line

                    destination_transport_detail['occupancy'] = destination_occupancy
                    destination_transport_detail['provider_name'] = destination_mode_name
                    destination_transport_detail['line_name'] = destination_line_name
                    destination_transport_detail['line_name_short'] = destination_line_name_short
                    destination_transport_detail['run_name'] = destination_run_name
                    destination_transport_detail['end_of_line'] = destination_end_of_line

                    self._info = {
                        ATTR_DUE_IN: due,
                        ATTR_DELAY: delay,
                        ATTR_DURATION: duration,
                        ATTR_FIRST_LEG_WALKING: first_leg_walking,
                        ATTR_ORIGIN_DETAIL: origin_detail,
                        ATTR_DESTINATION_DETAIL: destination_detail,
                        ATTR_ORIGIN_TRANSPORT_DETAIL: origin_transport_detail,
                        ATTR_DESTINATION_TRANSPORT_DETAIL: destination_transport_detail,
                        ATTR_CHANGES: changes,
                        ATTR_CHANGES_SIMPLE: changes_simple,
                        ATTR_LOCATIONS_LIST: locations_list,
                        ATTR_ORIGIN_REAL_TIME_TRIP_ID: origin_realtimetripid,
                        ATTR_ORIGIN_GTFS_TRIP_ID: origin_gtfs_tripid,
                        ATTR_DESTINATION_REAL_TIME_TRIP_ID: destination_realtimetripid,
                        ATTR_DESTINATION_GTFS_TRIP_ID: destination_gtfs_tripid,
                        ATTR_ALERTS: json.loads(alerts)
                        }

                    found_journeys = found_journeys + 1

                    # This is a valid journey, add it to the list.  It will be sorted later
                    valid_journeys.append(self._info)

                    if (found_journeys == journeys_to_return):
                        # We have enough valid journeys so break out
                        # Although if there were multiple destinations we may still need to truncate the return
                        break

                    current_journey_index = next_journey_index

        # Order valid_journeys by 'due'
        sorted_valid_journeys = sorted(valid_journeys, key = lambda d: datetime.fromisoformat(d['destination_detail']['arrival_time'].replace("Z", "+00:00")))

        # Now truncate it, if necessary - should only be necessary if multiple destinations were provided
        if len(sorted_valid_journeys) > journeys_to_return:
            sorted_valid_journeys = sorted_valid_journeys[:journeys_to_return]

        json_output = {
            'journeys_to_return': journeys_to_return,
            'journeys_with_data': len(sorted_valid_journeys),
            'api_calls': api_calls,
            'api_rate_warning': api_rate_warning,
            'journeys': sorted_valid_journeys
            }

        return json.dumps(json_output)


    def _find_next_journey(self, journeys, start_journey_index, origin_transport_type_copy, destination_transport_type, strict, route_filter, type_origin):
        # Find the next journey that has a leg of the requested type, and/or that satisfies the route filter
        try:
            journey_count = len(journeys)

            # Some basic error checking
            if start_journey_index > journey_count:
                return None, None, None, None, 9, None, None, None

            for journey_index in range (start_journey_index, journey_count, 1):
                journey = journeys[journey_index]

                origin_leg, first_leg_walking = self._find_first_leg(journey['legs'], origin_transport_type_copy, strict, route_filter, type_origin)
                if origin_leg is not None:
                    destination_leg = self._find_last_leg(journey['legs'], destination_transport_type, strict)


                if origin_leg is not None and destination_leg is not None:
                    # Get change information
                    changes, changes_simple, locations_list = self._find_changes(journey['legs'], origin_leg, destination_leg, first_leg_walking)
                    return journey, journey_index + 1, origin_leg, destination_leg, changes, changes_simple, locations_list, first_leg_walking
                else:
                    return None, None, None, None, 9, None, None, None

            # Hmm, we didn't find one
            return None, None, None, None, 9, None, None, None

        except:
            return None, None, None, None, 9, None, None, None

    def _find_first_leg(self, legs, transport_type, strict, route_filter, type_origin):
        # Find the first leg of the requested type
        walking_flag = False

        for index, leg in enumerate(legs):
            if type_origin == "coord":
                if index == 0 and leg['transportation']['product']['class'] >= 99:
                    #Skip the walking leg of a journey that starts with a device tracker, but mark that we are in fact walking
                    walking_flag = True
                    continue

            #First, check against the route filter if possible
            origin_line_name_short = 'Unknown'
            origin_line_name = 'Unknown'

            leg_class = leg['transportation']['product']['class']
            if transport_type == [0] or leg_class in transport_type:
                # This leg meets the transport type criteria
                if leg_class < 99:
                    origin_line_name_short = leg['transportation']['disassembledName'].lower()
                    origin_line_name = leg['transportation']['number'].lower()

                    if (route_filter in origin_line_name_short or route_filter in origin_line_name):
                        # This leg passes the route filter
                        return leg, walking_flag

                    if 0 in transport_type and leg_class < 99:
                        # We don't have a filter, and this is the first non-walk/cycle leg so return that leg
                        return leg, walking_flag

                else:
                    # It's a walking leg - we need to return the next leg, but still show that there's also a walking leg
                    # Honestly we should never get here unless there are TWO walking legs in succession, which is unlikely
                    return legs[index+1], True

            # Exit if we're doing strict filtering and we haven't found that type in the first leg, which we haven't if we've got this far
            if strict == True:
                leg_class_friendly = self._get_mode(leg_class)[0]
                _LOGGER.warning (f"Rejecting returned journey [{index}] - first leg transport_type {leg_class} ({leg_class_friendly}) doesn't match strict filter {transport_type}")
                return None, False

        # Hmm, we didn't find one
        return None, False

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
                leg_class_friendly = self._get_mode(leg_class)[0]
                _LOGGER.warning (f"Rejecting returned journey [{index}] - last leg transport_type {leg_class} ({leg_class_friendly}) doesn't match strict filter")
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

    def _get_stop_info(self, leg, section, key):
        section_name = leg[section]["name"]
        section_id = leg[section]["id"]
        section_disassembled_name = leg[section]["disassembledName"]
        section_coords = leg[section]["coord"]

        return {
            "key": key,
            "name": section_name,
            "id": section_id,
            "disassembled_name": section_disassembled_name,
            "coords": section_coords
        }

    def _get_location_info(self, location_detail, key):

        return {
            "key": key,
            "name": key,
            "disassembled_name": key,
            "coords": location_detail
        }

    def _find_changes(self, legs, origin_leg, destination_leg, first_leg_walking):
        # Find out how often we have to change, and populate the 'locations' list:
        #     The origin location
        #     The destination location
        #     Any intervening changes
        #
        # Also create a high-level string that just shows the intervening locations

        locations_list = []
        simple_list = []
        changes = 0
        midpoint_index = 0

        # Count the changes, each time we hit s new non-walking leg is considered to be a change
        bInJourney = False

        # Add the origin
        locations_list.append(self._get_stop_info(origin_leg, 'origin', 'origin_device_tracker'))
        simple_list.append(origin_leg['origin']['name'].split(',')[0])

        # Now the middle changes, if any
        # Ignore the first leg if it's a walking leg
        if first_leg_walking:
            start_index = 2
        else:
            start_index = 1

        tracker_num = 0

        for index, (previous_leg, next_leg) in enumerate(zip(legs, legs[start_index:])):
            arrival = previous_leg['destination']
            departure = next_leg['origin']

            locations_list.append(self._get_stop_info(previous_leg, 'destination', f'changes_device_tracker_{tracker_num}'))
            locations_list.append(self._get_stop_info(next_leg, 'origin', f'changes_device_tracker_{tracker_num+1}'))
            tracker_num += 2

            simple_list.append(previous_leg['destination']['name'].split(',')[0])
            simple_list.append(next_leg['origin']['name'].split(',')[0])

            #changes = index+1
            changes += 1

        # Finally the destination
        locations_list.append(self._get_stop_info(destination_leg, 'destination', 'destination_device_tracker'))
        simple_list.append(destination_leg['destination']['name'].split(',')[0])

        # For the simple changes list we just need a comma-separated string
        if changes == 0:
            changes_simple = 'None'
        else:
            prev_name = ''
            for location in simple_list[:]:
                if location == prev_name:
                    simple_list.remove (location)

                prev_name = location

            changes_simple =  ", ".join(simple_list)

        return changes, changes_simple, {"locations": locations_list, "vehicles":[]}


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


    def _find_gtfs_info(self, include_realtime_location, api_key, mode, mode_default_carriages, realtimetripid, agencyid, general_occupancy, sleep_time):
        # See if we can get the real-time GTFS record for this journey
        # It contains latitude, longitude and a few other useful fields

        # Sometimes the overall 'occupancy' value isn't provided, but per-carriage occupancy IS available, so handle that edge case as well

        # Populate with defaults in case of issues, and update what we can
        latitude = 'Unknown'
        longitude = 'Unknown'
        location_detail = {
            'latitude': latitude,
            'longitude': longitude
            }

        vehicle_id = 'Unknown'
        vehicle_model = 'Unknown'
        vehicle_set = 'Unknown'

        carriage_num = mode_default_carriages
        carriage_detail = []
        calculated_occupancy = general_occupancy

        api_rate_warning = False
        gtfs_data = None

        # Don't bother to check if we haven't been asked to
        # Doing it this way means we can reuse the defaults code rather than doubling up elsewhere
        if include_realtime_location:
            realtime_url, temp_rate_warning = self._get_realtime_url(agencyid, sleep_time)
            if temp_rate_warning:
                api_rate_warning = True

            # See if the realtime_url is in the GTFS cache
            if realtime_url in self._gtfs_cache:
                gtfs_data = self._gtfs_cache[realtime_url]
            else:
                auth = 'apikey ' + api_key
                header = {'Accept': 'application/x-google-protobuf', 'Authorization': auth}

                response = requests.get(realtime_url, headers=header, timeout=10)
                increment_api_counter(realtime_url)

            # Only try and process the results if we got a good return code, or if we got a cache hit
            # A bit clunky but saves me having to re-write and re-indent the whole function
            if gtfs_data is not None or response.status_code == 200:
                if gtfs_data is None:
                    # We got the data from the API, not the cache - so update the cache
                    gtfs_data = response.content
                    self._gtfs_cache[realtime_url] = gtfs_data

                # Put in a pause here to try and make sure we stay under the 5 API calls/second limit
                # Not usually an issue but if multiple processes are running multiple calls we might hit it
                time.sleep(sleep_time)

                # Search the feed and see if we can match realtimetripid to trip_id
                # If we do, capture the latitude and longitude
                feed = tfnsw_gtfs_extensions.FeedMessage()
                feed.ParseFromString(gtfs_data)
                reg = re.compile(realtimetripid)

                for entity in feed.entity:
                    if bool(re.match(reg, entity.vehicle.trip.trip_id)):
                        latitude = entity.vehicle.position.latitude
                        longitude = entity.vehicle.position.longitude
                        location_detail = {
                            'latitude': latitude,
                            'longitude': longitude
                            }

                        vehicle_id = entity.vehicle.vehicle.id

                        # Try and get the extended vehicle info
                        try:
                            vehicle_descriptor = entity.vehicle.vehicle.Extensions[tfnsw_gtfs_extensions.tfnsw_vehicle_descriptor]
                            if vehicle_descriptor is not None:
                                vehicle_model = vehicle_descriptor.vehicle_model

                        except:
                            pass

                                # Try and get detailed carriage and occupancy info, if available
                        # Also get an overall sense of general occupancy
                        try:
                            carriages = entity.vehicle.Extensions[tfnsw_gtfs_extensions.consist]
                            if carriages is not None:
                                carriage_num = len(carriages)
                                for carriage in carriages:
                                    name = carriage.name if carriage.HasField("name") else None
                                    position = carriage.position_in_consist

                                    if carriage.HasField("occupancy_status"):
                                        occupancy_num = carriage.occupancy_status
                                        occupancy_name = tfnsw_gtfs_extensions.CarriageDescriptor.OccupancyStatus.Name(occupancy_num)

                                        carriage_detail.append({
                                            "position": position,
                                            "name": name,
                                            "occupancy": occupancy_num,
                                            "occupancy_friendly": occupancy_name
                                            })

                                # Work out the general vehicle-level occupancy in case we need it
                                occupancy_average = round(sum(carriage["occupancy"] for carriage in carriage_detail) / len(carriage_detail))
                                calculated_occupancy = tfnsw_gtfs_extensions.CarriageDescriptor.OccupancyStatus.Name(occupancy_average)

                        except:
                             pass

                        # We found it, so break out
                        break
            else:
                # Warn that we didn't get a good return, but don't raise a fatal error as this is optional data
                # Log API rate limit warnings though
                if response.status_code == 401:
                    # Honestly this should never happen, the API key has already been checked
                    logger.warning(f"Error 'Invalid API key' calling {realtime_url} API")
                elif response.status_code == 403 or response.status_code == 429:
                    logger.warning(f"Error 'API rate limit exceeded' calling {realtime_url} API")
                    api_rate_warning = True
                else:
                    logger.warning(f"Error '{str(response.status_code)}' calling {realtime_url} API")

        # Put together the transport_type dictionary
        vehicle_set = self._get_vehicle_set(mode, realtimetripid, vehicle_id, vehicle_model, carriage_num)

        # If necessary create a carriage list based on the general occupancy if we weren't able to get the actual detail.  This will make my life easier in the HA integration!
        if not carriage_detail:
            for position in range(1, mode_default_carriages + 1):
                carriage_detail.append({
                    "position": position,
                    "name": None,
                    "occupancy": self._get_occupancy_number(general_occupancy.upper()),
                    "occupancy_friendly": general_occupancy.upper()
                    })

        # Put it all together
        transport_detail = {
            'type': mode,
            'location': location_detail,
            'carriages': carriage_num,
            'carriage_detail': carriage_detail,
            'vehicle_set': vehicle_set
        }

        if general_occupancy != 'Unknown':
            return transport_detail, general_occupancy, api_rate_warning
        else:
            return transport_detail, calculated_occupancy, api_rate_warning


    def _get_vehicle_set(self, mode, realtimetripid, vehicle_id, vehicle_model, carriage_num) -> str:
        # Return the appropriate vehicle set description depending on what type of vehicle it is
        match mode.lower():
            case 'train':
                # Everything we need is in the realtimetripid
                trip_id = realtimetripid.split('.')
                if len(trip_id) < 7:
                    vehicle_set = 'Unknown'
                else:
                    vehicle_set_code = trip_id[4]
                    vehicle_set_friendly = self._get_train_set(vehicle_set_code)

                    vehicle_set = f'{carriage_num}-car {self._get_train_set(trip_id[4])}'

            case 'metro' | 'light rail':
                vehicle_set = vehicle_model

            case 'bus' | 'coach' | 'school bus':
                vehicle_set = vehicle_model.replace('~', ' ')

            case 'ferry':
                if vehicle_model != 'Unknown':
                    vehicle_set = f'{vehicle_id}, {vehicle_model}-class ferry'
                else:
                    vehicle_set = 'Unknown'

            case '_':
                vehicle_set = 'Unknown'

        return vehicle_set


    def _get_mode(self, transport_class):
        """Map transport_class to a list containing the friendly name and the default number of 'carriages'"""
        modes = {
            1   : ["Train", 8],
            2   : ["Metro", 6],
            4   : ["Light rail", 2],
            5   : ["Bus", 1],
            7   : ["Coach", 1],
            9   : ["Ferry", 1],
            11  : ["School bus", 1],
            99  : ["Walk", 0],
            100 : ["Walk", 0],
            107 : ["Cycle", 0]
        }

        return modes.get(transport_class, [None, 0])


    def _get_specific_detail(self, location_name, transport_type) -> str:
        # Extract the specific platform, wharf etc for this journey
        try:
            if (transport_type == "Train" or transport_type == "Metro"):
                return location_name.split(", ")[1]

            elif transport_type == "Ferry":
                tmpLen = len(location_name.split(", "))

                if tmpLen == 4:
                    return location_name.split(", ")[1] + ", " + origin_name.split(", ")[2]

                elif tmpLen == 3:
                    return location_name.split(", ")[1]

                elif tmpLen == 2:
                    return location_name.split(", ")[1]

                else:
                    return location_name.split(", ")[0]

            elif transport_type == "Bus":
                return location_name.split(", ")[0]

            elif transport_type == "Light rail":
                tmpFind = location_name.find(" Light Rail")
                if tmpFind == -1:
                    return location_name
                else:
                    return location_name[: tmpFind]
            else:
                return location_name

        except:
            return location_name


    def _get_train_set(self, setcode) -> str:
        """Map the setcode to a specific train set"""

        train_sets = {
            "A": "Waratah",
            "B": "Waratah Series 2",
            "C": "C-set",
            "D": "Mariyung",
            "H": "Oscar",
            "J": "Hunter",
            "K": "K-set",
            "M": "Millennium",
            "N": "Endeavour",
            "P": "Xplorer",
            "T": "Tangara",
            "V": "V-set",
            "X": "XPT"
        }

        return train_sets.get(setcode, "Unknown")


    def _get_occupancy_number(self, friendly_occupancy) -> int:
        """ Return the numeric version of the occupancy string"""

        occupancy_map = {
            "MANY_SEATS":                   1,
            "MANY_SEATS_AVAILABLE":         1,
            "FEW_SEATS":                    2,
            "FEW_SEATS_AVAILABLE":          2,
            "STANDING_ONL":                 3,
            "STANDING_ROOM_ONLY":           3,
            "CRUSHED_STANDING_ROOM_ONLY":   3,
            "FULL":                         3,
            "UNKNOWN":                      0,
            "UNAVAILABLE":                  0
        }

        return occupancy_map.get(friendly_occupancy, 0)


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


    def _get_realtime_url(self, agencyid, sleep_time):
        """
        Map the journey mode to the proper realtime-location URL
        """

        # Use this CSV resource to determine the appropriate real-time location URL
        # I'm hoping that this CSV resource URL is static when updated by TransportNSW!  So far so good.
        url = "https://opendata.transport.nsw.gov.au/data/api/action/datastore_search?resource_id=30b850b7-f439-4e30-8072-e07ef62a2a36&filters={%22Complete%20GTFS%20agency_id%22:%22" + agencyid + "%22}&limit=1"
        api_rate_warning = False

        # Send the query and return an error if something goes wrong
        try:
            response = requests.get(url, timeout=5)
        except Exception as ex:
            logger.error(f"Error '{str(ex)}' querying GTFS URL datastore")
            return None, api_rate_warning

        # If we get bad status code, log error and return with None as this is optional data
        # But be aware of an API rate warning if appropriate
        if response.status_code != 200:
            if response.status_code == 401:
                # This should never happen, the API key has already been tested
                logger.warning (f"Error 'Invalid API key' calling GTFS API url {url}")
            elif response.status_code == 403 or response.status_code == 429:
                api_rate_warning = True
                logger.warning(f"Error 'API rate limit exceeded' calling GTFS API url {url}")
            else:
                logger.warning(f"Error '{str(response.status_code)}' calling GTFS API url {url}")

            return None, api_rate_warning

        # Put in a pause here to try and make sure we stay under the 5 API calls/second limit
        # Not usually an issue but if multiple processes are running multiple calls we might hit it
        time.sleep(sleep_time)

        # Parse the result as JSON
        result = response.json()
        if 'records' in result['result'] and len(result['result']['records']) > 0:
            return result['result']['records'][0]['Vehicle Position Feed'], api_rate_warning
        else:
            return None, api_rate_warning


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
    """ Trip-finder related error """
