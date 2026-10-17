# Make sure all necessary DroneKit classes are imported
import time

from dronekit import connect, VehicleMode, APIException, LocationGlobalRelative, Command
from pymavlink import mavutil
import logging
import math

#Live map on the projector (optional)
#Your name on the map, keep it short and different from everyone else's
PILOT_NAME = ""
#Address of the live map laptop, we will write it on the board (e.g. "http://192.168.1.50:8080")
#Leave it empty to turn the live map off
LIVE_MAP_URL = ""

def get_distance_meters(a_location1, a_location2):
    """
    Returns the ground distance in metres between two LocationGlobal objects.
    This method is an approximation, and will not be accurate over large distances and close to the
    earth's poles. It comes from the ArduPilot test code:
    https://github.com/diydrones/ardupilot/blob/master/Tools/autotest/common.py
    """
    # Check if locations are valid location objects with lat/lon
    # (works with LocationGlobal and LocationGlobalRelative alike)
    if a_location1 is None or a_location2 is None or \
       a_location1.lat is None or a_location1.lon is None or \
       a_location2.lat is None or a_location2.lon is None:
        logging.warning("Attempted to calculate distance with invalid location(s).")
        return float('inf') # Return infinite distance for invalid input

    dlat = a_location2.lat - a_location1.lat
    dlon = a_location2.lon - a_location1.lon
    return math.sqrt((dlat*dlat) + (dlon*dlon)) * 1.113195e5
    
def generate_circle_waypoints(center_lat, center_lon, altitude, radius=50, num_points=12):
    """Generates a list of LocationGlobalRelative waypoints for a circle."""
    waypoints = []
    if center_lat is None or center_lon is None:
        logging.error("Cannot generate waypoints: Center location is invalid.")
        return waypoints

    for i in range(num_points):
        angle = (2 * math.pi * i) / num_points
        # Approximate conversion from radius in meters to degrees lat/lon
        # meters per degree latitude is approx constant
        dlat_deg = (radius * math.cos(angle)) / 111319.5
        # meters per degree longitude varies with latitude
        dlon_deg = (radius * math.sin(angle)) / (111319.5 * math.cos(math.radians(center_lat)))
        waypoints.append(LocationGlobalRelative(
            center_lat + dlat_deg,
            center_lon + dlon_deg,
            altitude
        ))

    waypoints.append(waypoints[0])

    return waypoints

def land_at(my_vehicle, lat, lon):
    """
    Lands the plane at (lat, lon). It glides there in a straight line from wherever it is
    and touches down near the point, so arrive low and already pointing at it for a short landing.
    Returns straight away; the landing runs in AUTO mode.
    """
    # A one-item mission with just the landing point
    cmds = my_vehicle.commands
    cmds.download()
    cmds.wait_ready()
    cmds.clear()
    cmds.add(Command(0, 0, 0, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                     mavutil.mavlink.MAV_CMD_NAV_LAND, 0, 0, 0, 0, 0, 0, lat, lon, 0))
    cmds.upload()
    cmds.next = 1 # Start from the landing point, not from where an older mission stopped
    my_vehicle.mode = VehicleMode("AUTO")

#We will change the functions below this point

def workshop_takeoff(my_vehicle, target_altitude):

    #A plane takes off in TAKEOFF mode: once armed it speeds up, lifts off
    #and climbs straight ahead to the altitude in the TKOFF_ALT parameter

    #set the takeoff altitude here (the parameter is my_vehicle.parameters['TKOFF_ALT'])

    #set vehicle mode to TAKEOFF here

    time.sleep(1)

    #arm vehicle motors here

    #fill this so we wait for the vehicle to arm
    #while ...
    #    print(" Waiting for arming...")
    #    time.sleep(1)

    #There is no takeoff command: armed in TAKEOFF mode, the plane goes by itself.
    #The code below waits until it has climbed, because on the runway it can't do anything else
    #(we assume something is wrong if it hasn't climbed after a minute)
    start_time = time.time()
    while my_vehicle.location.global_relative_frame.alt < target_altitude * 0.9:
        if time.time() - start_time > 60:
            raise TimeoutError("The plane didn't climb. Is it armed and in TAKEOFF mode?")
        print(f" Climbing, altitude {my_vehicle.location.global_relative_frame.alt:.1f} m")
        time.sleep(1)

def workshop_simple_mission(my_vehicle):

    if my_vehicle.mode.name != "GUIDED":

        #Set mode to guided here

        #Code below waits for mode change
        #(we assume it failed after a certain time)
        start_time = time.time()
        while my_vehicle.mode.name != "GUIDED":
            if time.time() - start_time > 10:
                raise TimeoutError("Timeout setting mode to GUIDED")
            time.sleep(0.5)

    #Fill so we check is vehicle is armed
    #if ...
        #raise Exception("Vehicle is not armed")

    wp1 = LocationGlobalRelative(39.359523, 22.930260, 30)
    wp2 = LocationGlobalRelative(39.361381, 22.933684, 30)

    waypoints = [wp1, wp2]

    #A plane can't stop or turn on the spot: it passes a waypoint 25 m away or more,
    #and if it misses it circles about 50 m around it, so "reached" has to mean "within 60 m"
    target_threshold = 60.0

    #We have access to both the index (i) and the waypoint (w)
    for i, w in enumerate(waypoints):
        print(f"Going to waypoint {i+1}")

        #go to waypoint w here

        while True:
            #Check if vehicle disconnected during the mission
            if not my_vehicle:
                logging.error("Vehicle disconnected during mission.")
                raise Exception("Vehicle disconnected during mission")

            #Get Current location here

            #Get the distance from the waypoint using get_distance_meters()

            #fill the code so we leave while True if we are within a threshold
            #of the waypoint (target_threshold)
            #if ...
            #    print(f"Reached waypoint {i+1}")
            #    break

            #We will get the distance every second
            time.sleep(1)

    print("All waypoints travelled!")

def workshop_create_circle(my_vehicle, lat, lon, altitude, radius = 50):

    #Set vehicle mode to guided if it isn't here (look at the code above)

    #Check if the vehicle is armed (look at the code above)

    #Feel free to change parameters below, or the function itself!
    center_lat = lat
    center_lon = lon
    circle_altitude = altitude
    circle_radius = radius
    circle_waypoint_num = 8
    waypoints = generate_circle_waypoints(center_lat, center_lon, circle_altitude, circle_radius, circle_waypoint_num)

    #Target threshold (feel free to tweak, but a plane circles about 50 m around a point it missed)
    target_threshold = 60.0

    #iterate over every waypoint here, similar to above
    #for ... in ...:

        #go to next waypoint here

    #    while True:

            #Check if vehicle is still connected

            #Break if we are within a target threshold of the waypoint

            #sleep for a while

    print("Circle completed!")


