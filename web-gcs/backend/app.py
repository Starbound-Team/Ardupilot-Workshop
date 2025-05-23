import time
import collections
import collections.abc
collections.MutableMapping = collections.abc.MutableMapping # Fix for newer Python versions with dronekit

from flask import Flask, jsonify, request
from flask_cors import CORS # Import CORS
# Make sure all necessary DroneKit classes are imported
from dronekit import connect, VehicleMode, APIException, LocationGlobalRelative, Command
import logging
import math
#workshop
from workshop import *

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global Variables ---
vehicle = None
connection_string = 'udp:127.0.0.1:14550' # Default SITL address

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app) # Enable CORS for all routes, allowing requests from your frontend


# --- API Endpoints ---
@app.route('/')
def index():
    """Basic route to check if backend is running."""
    return jsonify({"message": "GCS Backend Running!"})

@app.route('/api/connect', methods=['POST'])
def connect_drone():
    """Attempts to connect to the drone via DroneKit."""
    global vehicle
    global connection_string

    # Prevent reconnecting if already connected
    if vehicle:
         logging.info("Already connected.")
         return jsonify({"status": "success", "message": "Already connected"})

    logging.info(f"Attempting connection to {connection_string}...")
    try:
        # Connect to the Vehicle
        # wait_ready=True waits for parameters, mode, armed status, etc.
        # heartbeat_timeout checks for MAVLink heartbeat
        vehicle = connect(connection_string, wait_ready=True, timeout=60, heartbeat_timeout=30)

        # Check if connection object was successfully created
        if not vehicle:
             # This case might be rare if connect raises exceptions on failure
            logging.error("Connection attempt returned None without raising an exception.")
            vehicle = None
            return jsonify({"status": "error", "message": "Failed to connect (vehicle object is None)"}), 500

        logging.info("Connection Successful!")
        # Log some details after connection
        try:
            logging.info(f"  Mode: {vehicle.mode.name}")
            logging.info(f"  Armed: {vehicle.armed}")
            # wait_for_location might be useful if GPS takes time after connection
            # vehicle.wait_for_location(timeout=10)
            alt = vehicle.location.global_relative_frame.alt if vehicle.location.global_relative_frame else 'N/A'
            lat = vehicle.location.global_relative_frame.lat if vehicle.location.global_relative_frame else 'N/A'
            lon = vehicle.location.global_relative_frame.lon if vehicle.location.global_relative_frame else 'N/A'
            logging.info(f"  Location: Lat={lat}, Lon={lon}, Alt={alt}")
            logging.info(f"  System status: {vehicle.system_status.state}")
            logging.info(f"  Is Armable: {vehicle.is_armable}")
        except Exception as e:
             logging.warning(f"Could not retrieve all vehicle details immediately after connection: {e}")

        return jsonify({"status": "success", "message": "Connected to Vehicle"})

    # Specific DroneKit exceptions
    except APIException as e:
        logging.error(f"DroneKit API Connection Exception: {e}", exc_info=True)
        vehicle = None
        return jsonify({"status": "error", "message": f"DroneKit API Error: {e}"}), 500
    # Timeout specific to the connect() call
    except TimeoutError: # This specifically catches connect(timeout=...)
         logging.error(f"Connection timed out after specified duration.")
         vehicle = None
         return jsonify({"status": "error", "message": f"Connection timed out."}), 500
    # Catch other potential exceptions during connection
    except Exception as e:
        logging.error(f"An unexpected error occurred during connection: {e}", exc_info=True)
        vehicle = None
        return jsonify({"status": "error", "message": f"Unexpected Error connecting: {e}"}), 500


@app.route('/api/disconnect', methods=['POST'])
def disconnect_drone():
    """Disconnects the DroneKit vehicle object."""
    global vehicle
    if vehicle:
        logging.info("Closing vehicle connection...")
        try:
            vehicle.close()
            vehicle = None # Set to None after closing
            logging.info("Vehicle connection closed.")
            return jsonify({"status": "success", "message": "Disconnected"})
        except Exception as e:
            logging.error(f"Error during vehicle.close(): {e}", exc_info=True)
            # Ensure vehicle is set to None even if close() fails
            vehicle = None
            return jsonify({"status": "error", "message": f"Error closing connection: {e}"}), 500
    else:
        logging.info("No active vehicle connection to disconnect.")
        return jsonify({"status": "success", "message": "Already disconnected"})


@app.route('/api/status')
def get_status():
    """Gets basic vehicle status if connected."""
    # Check if vehicle object exists and is connected
    if vehicle:
         try:
             # Safely access location attributes
             lat, lon, alt = None, None, None
             if vehicle.location.global_relative_frame:
                 lat = vehicle.location.global_relative_frame.lat
                 lon = vehicle.location.global_relative_frame.lon
                 alt = vehicle.location.global_relative_frame.alt

             # Safely access battery attributes
             batt_voltage, batt_level = None, None
             if vehicle.battery:
                batt_voltage = vehicle.battery.voltage
                batt_level = vehicle.battery.level # Battery level percentage

             status = {
                 "is_connected": True,
                 "mode": vehicle.mode.name,
                 "armed": vehicle.armed,
                 "is_armable": vehicle.is_armable, # Important for user feedback
                 "lat": lat,
                 "lon": lon,
                 "alt": alt,
                 "airspeed": vehicle.airspeed if hasattr(vehicle, 'airspeed') else None,
                 "groundspeed": vehicle.groundspeed if hasattr(vehicle, 'groundspeed') else None,
                 "heading": vehicle.heading if hasattr(vehicle, 'heading') else None,
                 "battery_voltage": batt_voltage,
                 "battery_level": batt_level,
                 "system_status": vehicle.system_status.state,
                 "ekf_ok": vehicle.ekf_ok if hasattr(vehicle, 'ekf_ok') else None, # EKF status
             }
             return jsonify({"status": "success", "data": status})
         except APIException as e:
             # Handle potential API errors during status fetching
             logging.error(f"DroneKit API Error fetching status: {e}", exc_info=True)
             return jsonify({"status": "error", "message": f"API Error fetching status: {e}"}), 500
         except Exception as e:
             logging.error(f"Error fetching status: {e}", exc_info=True)
             return jsonify({"status": "error", "message": f"Error fetching status: {e}"}), 500
    else:
        # Explicitly handle case where vehicle exists but is not connected
        if vehicle:
            logging.warning("Status requested, but vehicle object exists but is not connected.")
        return jsonify({"status": "success", "data": {"is_connected": False}})


@app.route('/api/takeoff', methods=['POST'])
def takeoff():
    """
    Commands the vehicle to take off to a specified altitude.
    Handles mode setting (GUIDED), arming, and takeoff command.
    """
    global vehicle
    # 1. Check connection
    if not vehicle:
        logging.warning("Takeoff request failed: Vehicle not connected.")
        # 400 Bad Request is suitable as the client made a request that cannot be fulfilled due to state
        return jsonify({"status": "error", "message": "Vehicle not connected"}), 400

    try:
        # 2. Receive and validate altitude from JSON body
        data = request.get_json()
        if not data or 'altitude' not in data:
            logging.warning("Takeoff request failed: Missing 'altitude' in request.")
            return jsonify({"status": "error", "message": "Missing 'altitude' in request body"}), 400

        target_altitude = float(data['altitude'])
        logging.info(f"Commanding takeoff to {target_altitude}m...")
        workshop_takeoff(vehicle, target_altitude)

        logging.info("Takeoff completed.")
        return jsonify({
            "status": "success", 
            "message": f"Takeoff to {target_altitude}m initiated",
            "details": {
                "altitude": target_altitude
            }
        })

    except APIException as e:
        # Catch specific DroneKit errors during the process
        logging.error(f"DroneKit API Exception during takeoff sequence: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"DroneKit API Error during takeoff: {e}"}), 500
    except Exception as e:
        # Catch any other unexpected errors
        logging.error(f"An unexpected error occurred during takeoff: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Unexpected Error during takeoff: {e}"}), 500

@app.route('/api/example_mission', methods=['POST'])
def example_mission():
    """Example mission endpoint."""
    global vehicle
    if not vehicle:
        return jsonify({"status": "error", "message": "Vehicle not connected"}), 500
    
    try:
        logging.info("Circle example mission...")

        workshop_create_circle(
            vehicle,
            vehicle.location.global_relative_frame.lat,
            vehicle.location.global_relative_frame.lon,
            altitude=20,
            radius=30
        )

        logging.info("Mission completed.")
        
        return jsonify({"status": "success", "message": "Mission executed"})
    except Exception as e:
        logging.error(f"Mission execution failed: {str(e)}")
        return jsonify({"status": "error", "message": f"Mission execution failed: {str(e)}"}), 500

@app.route("/api/simple_mission", methods=['POST'])
def simple_mission():
    """Example mission endpoint."""
    global vehicle
    if not vehicle:
        return jsonify({"status": "error", "message": "Vehicle not connected"}), 500

    try:
        logging.info("Executing example mission...")

        workshop_simple_mission(vehicle)
        logging.info("Mission completed.")

        return jsonify({"status": "success", "message": "Mission executed"})
    except Exception as e:
        logging.error(f"Mission execution failed: {str(e)}")
        return jsonify({"status": "error", "message": f"Mission execution failed: {str(e)}"}), 500
    
@app.route('/api/rtl', methods=['POST'])
def rtl():
    """Return to Launch (RTL) command."""
    global vehicle
    if vehicle:
        logging.info("Returning to Launch...")
        vehicle.mode = VehicleMode("RTL")
        return jsonify({"status": "success", "message": "Returning to Launch"})
    else:
        return jsonify({"status": "error", "message": "Vehicle not connected"}), 500

@app.route('/api/goto', methods=['POST'])
def goto_point():
    """Commands the vehicle to go to a specific lat/lon coordinate."""
    global vehicle
    if not vehicle:
        logging.warning("Goto request failed: Vehicle not connected.")
        return jsonify({"status": "error", "message": "Vehicle not connected"}), 400

    try:
        # Get coordinates from the request
        data = request.get_json()
        if not data or 'lat' not in data or 'lng' not in data:
            return jsonify({"status": "error", 
                           "message": "Missing required parameters (lat, lng)"}), 400

        # Get altitude from request or use current altitude
        target_lat = float(data['lat'])
        target_lng = float(data['lng'])
        
        # Use provided altitude or default to current altitude + 5m
        if 'altitude' in data and data['altitude'] is not None:
            target_alt = float(data['altitude'])
        elif vehicle.location.global_relative_frame and \
             vehicle.location.global_relative_frame.alt is not None:
            # Use current altitude if available
            target_alt = vehicle.location.global_relative_frame.alt
        else:
            # Default altitude if current altitude unknown
            target_alt = 20.0
            
        logging.info(f"Going to: lat={target_lat}, lon={target_lng}, alt={target_alt}m")
        
        # Ensure vehicle is in GUIDED mode
        if vehicle.mode.name != "GUIDED":
            logging.info("Changing to GUIDED mode for goto command")
            vehicle.mode = VehicleMode("GUIDED")
            # Wait briefly for mode change
            time.sleep(1)
            
        # Command the vehicle to move to the location
        target_location = LocationGlobalRelative(target_lat, target_lng, target_alt)
        vehicle.simple_goto(target_location)
        
        return jsonify({
            "status": "success", 
            "message": "Vehicle moving to target",
            "details": {
                "lat": target_lat,
                "lng": target_lng,
                "alt": target_alt
            }
        })
        
    except ValueError as e:
        logging.error(f"Invalid coordinates: {e}")
        return jsonify({"status": "error", "message": f"Invalid coordinates: {e}"}), 400
    except Exception as e:
        logging.error(f"Error during goto command: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Error: {e}"}), 500

# --- Main Execution ---
if __name__ == '__main__':
    # Run on 0.0.0.0 to be accessible from other devices on the network if needed,
    # otherwise use 127.0.0.1 for local access only.
    # Debug=True auto-reloads on code changes, but disable for production.
    app.run(host='127.0.0.1', port=5000, debug=True)