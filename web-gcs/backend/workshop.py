# Make sure all necessary DroneKit classes are imported
import time

from dronekit import connect, VehicleMode, APIException, LocationGlobalRelative, Command
import logging
import math

def get_distance_meters(a_location1, a_location2):
    """
    Returns the ground distance in metres between two LocationGlobal objects.
    This method is an approximation, and will not be accurate over large distances and close to the
    earth's poles. It comes from the ArduPilot test code:
    https://github.com/diydrones/ardupilot/blob/master/Tools/autotest/common.py
    """
    # Check if locations are valid LocationGlobalRelative objects with lat/lon
    if not isinstance(a_location1, LocationGlobalRelative) or \
       not isinstance(a_location2, LocationGlobalRelative) or \
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
    return waypoints

#We will change the functions below this point

def workshop_takeoff(my_vehicle, target_altitude):

    #set vehicle mode to guided here

    time.sleep(1)

    #arm vehicle motors here

    #fill this so we wait for the vehicle to arm
    #while ...
    #    print(" Waiting for arming...")
    #    time.sleep(1)

    #takeoff here

def workshop_simple_mission(my_vehicle):

    if my_vehicle.mode.name != "GUIDED":

        #Set mode to guided here

        #Code below waits for mode change
        #(we assume it failed after a certain time
        start_time = time.time()
        while my_vehicle.mode.name != "GUIDED":
            if time.time() - start_time > 10:
                raise TimeoutError("Timeout setting mode to GUIDED")
            time.sleep(0.5)

    #Fill so we check is vehicle is armed
    #if ...
        #raise Exception("Vehicle is not armed")

    wp1 = LocationGlobalRelative(39.359523, 22.930260)
    wp2 = LocationGlobalRelative(39.361381, 22.933684)

    waypoints = [wp1, wp2]

    target_threshold = 3.0

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
    circle_waypoint_num = 12
    waypoints = generate_circle_waypoints(center_lat, center_lon, circle_altitude, circle_radius, circle_waypoint_num)

    #Target threshold (feel free to tweak)
    target_threshold = 3.0

    #iterate over every waypoint here, similar to above
    #for ... in ...:

        #go to next waypoint here

    #    while True:

            #Check if vehicle is still connected

            #Break if we are within a target threshold of the waypoint

            #sleep for a while

    print("Circle completed!")


