#Your code for the workshop. Fill it in part by part; the cheat sheet says what each part needs.
#Everything you get ready-made (measuring, landmarks, photos, buttons) is in game.py.
import math
import time

from dronekit import VehicleMode, LocationGlobalRelative
from game import *

#Live map on the projector (optional)
#Your name on the map, keep it short and different from everyone else's
PILOT_NAME = ""
#Address of the live map laptop, we will write it on the board (e.g. "http://192.168.1.50:8080")
#Leave it empty to turn the live map off
LIVE_MAP_URL = ""


#---------- Part 1: Takeoff (the Takeoff button in the GCS runs this) ----------

def take_off(my_vehicle, target_altitude):

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


#---------- Part 2: Flying to a point ----------

def fly_to(my_vehicle, location):

    #The plane only follows your commands in GUIDED mode
    if my_vehicle.mode.name != "GUIDED":

        #Set mode to guided here

        #Code below waits for mode change
        #(we assume it failed after a certain time)
        start_time = time.time()
        while my_vehicle.mode.name != "GUIDED":
            if time.time() - start_time > 10:
                raise TimeoutError("Timeout setting mode to GUIDED")
            time.sleep(0.5)

    #Send the plane to location here

    #A plane can't stop or turn on the spot: it passes a point 25 m away or more,
    #and if it misses it circles about 50 m around it, so "arrived" has to mean "within 60 m"
    arrived_distance = 60.0

    while True:
        #Get the plane's current location here

        #Get the distance to location here

        #fill the code so we leave while True once we are closer than arrived_distance
        #if ...
        #    break

        #We will check the distance every second
        time.sleep(1)


#The @button line puts a button in the GCS that runs the function below it.
#This one takes a location too, so it goes in the right-click menu and gets the point you clicked.
#It does nothing useful until fly_to is written (click it again to stop it).

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
    #for ... in ...:

    print("All waypoints travelled!")


#---------- Part 4: Can we take the photo? ----------

def can_photograph(position, heading, landmark):

    #A photo counts when all three are true:

    #1. The distance from the landmark is between landmark.inner and landmark.outer

    #2. We are on the right side: the direction from the landmark to us
    #   is at most landmark.view_width / 2 away from landmark.approach_from

    #3. We are facing it: the direction from us to the landmark
    #   is at most FIELD_OF_VIEW / 2 away from heading

    return False


#---------- Part 5: Lining up ----------

def get_approach_point(landmark, position):

    #Where to turn in towards the landmark: a point on the line it must be approached along
    #(direction landmark.approach_from from it), far enough out that the plane is straight again
    #before it gets close. The more the plane turns there, the further out it has to be.

    #1. A first guess, 300 m out along that line

    #2. turn = how much the plane turns at the guess: the angle between
    #   (direction from position to the guess) and (direction from the guess to the landmark)

    #3. How far the turn swings the plane sideways (given):
    #   swing = SWING_METERS * (1 - math.cos(math.radians(turn)))

    #4. How far out the point must be so that swing still leaves us on the right side (given):
    #   distance = swing / math.tan(math.radians(landmark.view_width / 2 - 10)) + 60
    #   but at least landmark.outer + 50

    #5. Return the point that far out along the line

    return landmark.loc


#---------- Part 6: Photographing a landmark ----------

#Already working: for when you fly there yourself
@button("Take photo")
def photo(my_vehicle):
    take_photo()


#Rename it if you like, just change the name where you use it too

def capture(my_vehicle, landmark):

    #Fly to the approach point

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
