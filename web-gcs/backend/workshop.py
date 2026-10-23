#Your code for the workshop. Fill it in part by part; the cheat sheet says what each part needs.
#Everything you get ready-made (measuring, lining up, landmarks, photos, buttons) is in toolkit.py.
import math
import time

from dronekit import VehicleMode, LocationGlobalRelative
from toolkit import *

#The game and the map on the projector
#Your name on the map, keep it short and different from everyone else's
PILOT_NAME = ""
#Address of the organisers' laptop, we will write it on the board (e.g. "http://192.168.1.50:8080")
#Leave it empty to practise on your own
GAME_SERVER_URL = ""
#Leave this empty: the game server gives you a plane (without a server, your own SITL is used).
#Only if we tell you to, put a plane's address here (e.g. "tcp:192.168.1.50:5770")
SITL_ADDRESS = ""


#---------- Part 1: Takeoff (the Takeoff button in the GCS runs this) ----------

def take_off(my_vehicle, target_altitude):

    #A plane takes off in TAKEOFF mode: once armed it speeds up, lifts off
    #and climbs straight ahead to the altitude in the TKOFF_ALT parameter

    #the plane should fly to the target_altitude, that the gcs will pass it
    #my_vehicle.parameters['TKOFF_ALT'] = ###
    
    #set vehicle mode to TAKEOFF here
    ### my_vehicle.mode = ...

    time.sleep(1)

    #arm vehicle motors here
    ### my_vehicle...

    #fill this so we wait for the vehicle to arm
    ### while ...
    #    print(" Waiting for arming...")
    #    time.sleep(1)

    #Armed in TAKEOFF mode, the plane goes by itself. The code below waits until it has climbed,
    #because on the runway, it can't do anything else.
    start_time = time.time()
    while my_vehicle.location.global_relative_frame.alt < target_altitude * 0.9:
        
        #(we assume something is wrong if it hasn't climbed after a minute)
        if time.time() - start_time > 60:
            raise TimeoutError("The plane didn't climb. Is it armed and in TAKEOFF mode?")
        print(f" Climbing, altitude {my_vehicle.location.global_relative_frame.alt:.1f} m")
        
        time.sleep(1)


#---------- Part 2: Flying to a point ----------

def fly_to(my_vehicle, location):

    #The plane only follows your commands in GUIDED mode
    if my_vehicle.mode.name != "GUIDED":

        #Set mode to guided here
        ### my_vehicle...

        #Code below waits for mode change
        start_time = time.time()
        while my_vehicle.mode.name != "GUIDED":

            #we assume it failed after a certain time
            if time.time() - start_time > 10:
                raise TimeoutError("Timeout setting mode to GUIDED")
            
            time.sleep(0.5)

    #Send the plane to location here
    ### my_vehicle...

    #A plane can't stop or turn on the spot: it passes a point 25 m at best,
    #(default behaviour in guided mode) and if it misses it circles about 50 m around it.
    # We count being within 60m of a point as close enough to say the plane reached it
    #(under 50 the plane may circle forever)
    reach_distance = 60.0

    #Wait until we have arrived
    #while True:
        #Get the plane's current location here
        ### current = my_vehicle...

        #Get the distance to location here
        #distance = get_distance_meters(current, location)

        #we should leave the while True loop once we are at reach of the point
        ### if ...
        #    break

        #We will check the distance every second
        #time.sleep(1)


#The @button line puts a button in the GCS that runs the function below it.
#This one takes a location too, so it goes in the right-click menu and gets the point you clicked.
#It does nothing until fly_to is written.

@button("Fly here")
def fly_here(my_vehicle, location):
    fly_to(my_vehicle, location)


#---------- Part 3: A mission from your clicks ----------
#Right-click the map and pick "Add waypoint" a few times, then press "Simple mission" in the GCS.

@button("Simple mission")
def simple_mission(my_vehicle):

    waypoints = get_clicked_waypoints()
    if not waypoints:
        print("No waypoints: right-click the map and pick 'Add waypoint' first")
        return

    #Fly to every waypoint in turn here
    ### for ... in enumerate(...):
    #    print(f"Going to waypoint {i+1}")
    ###    

    print("All waypoints travelled!")


#---------- Part 4: Can we take the photo? ----------

def can_photograph(position, heading, landmark):

    #A photo counts when all three are true:

    #1. The distance from the landmark is between landmark.inner and landmark.outer

    ### distance = ...
    ### if distance < ... or distance > ...
    #    return False

    #2. We are on the right side: the direction from the landmark to us
    #   is at most landmark.view_width / 2 away from landmark.approach_from
    
    ### side = get_direction_degrees(...)
    #if get_angle_between(side, landmark.approach_from) > landmark.view_width / 2:
    #    return False

    #3. We are facing it: the direction from us to the landmark
    #   is at most FIELD_OF_VIEW / 2 away from heading
    
    ### to_landmark = get_direction_degrees(...)
    #if get_angle_between(to_landmark, heading) > FIELD_OF_VIEW / 2:
    #    return False

    return True


#---------- Part 5: Lining up (ready-made) ----------

#A plane can't stop or turn on the spot, so before a photo it has to line up: get onto the landmark's
#photo side, pointing at it, far enough out to be flying straight again by the time it gets there.
#approach(my_vehicle, landmark) in toolkit.py does that for you; nothing to write in this part.
#Try it: right-click near a landmark and pick "Line up for this landmark".

@button("Line up for this landmark")
def line_up_here(my_vehicle, location):
    landmark = min(get_known_landmarks(), key=lambda l: get_distance_meters(location, l.loc))
    approach(my_vehicle, landmark)
    my_vehicle.simple_goto(landmark.loc)


#---------- Part 6: Photographing a landmark ----------

#This button will appear at the ribbon on top of the page; allows you to take a photo manually
@button("Take photo")
def photo(my_vehicle):
    ### if ...
    take_photo()


#Rename it if you like, just change the name where you use it too

def capture(my_vehicle, landmark):

    #Line up for the landmark (ready-made, part 5)
    ### approach(...)

    #Point the plane at the landmark (no waiting this time)

    #Until the photo sells or we have flown past the landmark:
    #    if can_photograph(...): take_photo() returns True if it sold
    #    check often, the plane covers 20 m every second

    pass


#Right-click near a landmark to capture it
@button("Capture this landmark")
def capture_here(my_vehicle, location):
    landmark = min(get_known_landmarks(), key=lambda l: get_distance_meters(location, l.loc))
    capture(my_vehicle, landmark)


@button("Nearest first")
def nearest_first(my_vehicle):

    while True:
        landmarks = get_known_landmarks()
        if not landmarks:
            time.sleep(1)
            continue

        #Pick the nearest landmark and capture it

        time.sleep(1)


#---------- Part 7: Your own strategies ----------
#Add as many @button functions as you like. A button that flies the plane takes over from the one
#that was flying it; one that doesn't (like Take photo) runs alongside.
