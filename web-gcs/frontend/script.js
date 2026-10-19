const connectButton = document.getElementById('connectButton');
const disconnectButton = document.getElementById('disconnectButton');
const statusButton = document.getElementById('statusButton');
const takeoffButton = document.getElementById('takeoffButton');
const altitudeInput = document.getElementById('altitudeInput');
// const statusDiv = document.getElementById('status');
const telemetryList = document.getElementById('telemetryData');
const telemetryState = document.getElementById('telemetryState');

const backendUrl = 'http://127.0.0.1:5000'; // Your Flask backend URL

// --- Map Variables ---
let map = null;
let droneMarker = null;
let initialCenterSet = false; // Track if map centered on first fix
let flightPathCoordinates = []; // Array to store [lat, lon] points for the trail
let flightPathPolyline = null;  // Leaflet Polyline object

// --- State Variables ---
let isConnected = false;
let statusInterval = null; // To hold the interval timer for fetching status
let landmarkInterval = null; // Timer for fetching the landmarks
let waypoints = []; // [{lat, lng, marker}] added with right-click -> Add waypoint
let landmarkLayer = null; // Landmarks and their photo zones
let landmarkViews = []; // [{lm, zone, dot, label}] for colouring them as the plane moves
let droneCone = null; // What the camera sees: FIELD_OF_VIEW wide, CONE_LENGTH long
let lastTelemetry = null;
let lastButtonError = null; // Number of the last button crash we showed

// --- Map Initialization ---
function initMap() {
    // Check if map is already initialized
    if (map) return;

    // Initialize the map - Start zoomed out, will center on first drone location
    // Using coordinates near Volos, Greece as a fallback center if needed later
    map = L.map('map', {
        contextmenu: true,
        contextmenuWidth: 140,
        contextmenuItems: [
          {
            text: 'Go to this point',
            callback: function(e) {
              const { lat, lng } = e.latlng;
              sendGoToCommand(lat, lng);
            }
          },
          {
            text: 'Add waypoint',
            callback: function(e) {
              addWaypoint(e.latlng.lat, e.latlng.lng);
            }
          },
          {
            text: 'Clear waypoints',
            callback: function(e) {
              clearWaypoints();
            }
          },
          {
            text: 'Return to home',
            callback: function(e) {
              sendReturnToHome();
            }
          },
          {
            text: 'Land here',
            callback: function(e) {
              const { lat, lng } = e.latlng;
              sendLandCommand(lat, lng);
            }
          },
          '-', // Separator
          {
            text: 'Center map here',
            callback: function(e) {
              map.panTo(e.latlng);
            }
          }
        ]
      }).setView([39.36, 22.94], 5); // Start relatively zoomed out

    // Add OpenStreetMap tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    console.log("Map initialized");
}

// Toast notification helper
function showToast(message, type = 'info', duration = 3000) {
    // Set color based on type
    let background;
    switch(type) {
        case 'success': background = "#28a745"; break;
        case 'error': background = "#dc3545"; duration = 5000; break; // Longer duration for errors
        case 'warning': background = "#ffc107"; break;
        default: background = "#007bff"; // info
    }

    // Toastify comes from a CDN; if it is blocked (ad blocker, offline), log instead
    // so the button that called us still does its job
    if (typeof Toastify === 'undefined') {
        console.log(`[${type}] ${message}`);
        return;
    }

    Toastify({
        text: message,
        duration: duration,
        close: true,
        gravity: "top",
        position: "right",
        style: {
            background: background
        }
    }).showToast();
}

function sendGoToCommand(lat, lng) {
    showToast("Sending go-to command...", "info");
    
    fetch(`${backendUrl}/api/goto`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ lat, lng, altitude: 30 })
    })
    .then(response => {
        // Always try to parse the JSON first, even for error responses
        return response.json().then(data => {
            // If response is not ok, throw an error with the message from the server
            if (!response.ok) {
                throw new Error(data.message || `Server responded with status: ${response.status}`);
            }
            // If response is ok, return the data for the next .then()
            return data;
        });
    })
    .then(data => {
        if (data.status === 'success') {
            showToast("Vehicle moving to selected location", "success");
            
            // Add a marker at the target location
            L.marker([lat, lng], {
                icon: L.divIcon({
                    className: 'goto-marker',
                    html: '<i class="fas fa-crosshairs"></i>'
                })
            }).addTo(map);
        } else {
            showToast(`Command failed: ${data.message}`, "error");
        }
    })
    .catch(error => {
        console.error("Go-to fetch error:", error);
        showToast(`Error: ${error.message}`, "error");
    });
}

function sendTakeOff() {
    const altitude = parseFloat(altitudeInput.value);
    if (!(altitude > 0)) {
        showToast("Takeoff altitude must be a positive number", "warning");
        return;
    }

    showToast("Sending takeoff command...", "info");

    fetch(`${backendUrl}/api/takeoff`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({altitude})
    })
    .then(response => {
        // Always try to parse the JSON first, even for error responses
        return response.json().then(data => {
            // If response is not ok, throw an error with the message from the server
            if (!response.ok) {
                throw new Error(data.message || `Server responded with status: ${response.status}`);
            }
            // If response is ok, return the data for the next .then()
            return data;
        });
    })
    .then(data => {
        if (data.status === 'success') {
            showToast("Taking off...", "success");
        } else {
            showToast(`Command failed: ${data.message}`, "error");
        }
    })
    .catch(error => {
        console.error("Takeoff fetch error:", error);
        showToast(`Error: ${error.message}`, "error");
    });
}

function sendReturnToHome() {
    showToast("Sending return to home command...", "info");
    fetch(`${backendUrl}/api/rtl`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({})
    }).then(response => {
        // Always try to parse the JSON first, even for error responses
        return response.json().then(data => {
            // If response is not ok, throw an error with the message from the server
            if (!response.ok) {
                throw new Error(data.message || `Server responded with status: ${response.status}`);
            }
            // If response is ok, return the data for the next .then()
            return data;
        });
    }
    ).then(data => {
        if (data.status === 'success') {
            showToast("Returning to home...", "success");
        } else {
            showToast(`Command failed: ${data.message}`, "error");
        }
    }
    ).catch(error => {
        console.error("Return to home fetch error:", error);
        showToast(`Error: ${error.message}`, "error");
    }
    );
}

function sendLandCommand(lat, lng) {
    showToast("Sending land command...", "info");
    fetch(`${backendUrl}/api/land`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ lat, lng })
    }).then(response => {
        // Always try to parse the JSON first, even for error responses
        return response.json().then(data => {
            // If response is not ok, throw an error with the message from the server
            if (!response.ok) {
                throw new Error(data.message || `Server responded with status: ${response.status}`);
            }
            // If response is ok, return the data for the next .then()
            return data;
        });
    }
    ).then(data => {
        if (data.status === 'success') {
            showToast("Landing...", "success");
        } else {
            showToast(`Command failed: ${data.message}`, "error");
        }
    }
    ).catch(error => {
        console.error("Land fetch error:", error);
        showToast(`Error: ${error.message}`, "error");
    }
    );
}

// --- Waypoints (sent along with every workshop button) ---
function addWaypoint(lat, lng) {
    const marker = L.marker([lat, lng], {
        keep: true, // Survives reconnecting, like after saving workshop.py
        icon: L.divIcon({
            className: 'waypoint-marker',
            html: `${waypoints.length + 1}`,
            iconSize: [24, 24]
        })
    }).addTo(map);
    waypoints.push({ lat, lng, marker });
}

function clearWaypoints() {
    waypoints.forEach(w => map.removeLayer(w.marker));
    waypoints = [];
}

// --- Workshop buttons: one per @button function in workshop.py ---
// Plain buttons go in the top bar (what doesn't fit goes under "More"), buttons whose function
// takes a location go in the right-click menu. Clicking a running button stops it.
let workshopButtons = []; // [{name, location}] in workshop.py order
let contextMenuItems = []; // Right-click menu entries we added, to remove them again
let shownRunning = ''; // The running buttons we last drew, to redraw only when that changes

async function loadWorkshopButtons() {
    try {
        const response = await fetch(`${backendUrl}/api/buttons`);
        workshopButtons = (await response.json()).buttons;
    } catch (error) {
        console.error('Could not load the workshop buttons:', error);
        workshopButtons = [];
    }
    drawWorkshopButtons([]);
}

function buttonLabel(name, running) {
    return running.includes(name) ? `■ ${name}` : name;
}

function drawWorkshopButtons(running) {
    shownRunning = running.join('\n');
    const pills = workshopButtons.filter(b => !b.location).map(b => {
        const pill = document.createElement('button');
        pill.className = 'pill workshop-button';
        pill.classList.toggle('running', running.includes(b.name));
        pill.textContent = buttonLabel(b.name, running);
        pill.title = running.includes(b.name) ? 'Running: click to stop' : '';
        pill.addEventListener('click', () => runWorkshopButton(b.name));
        return pill;
    });
    document.getElementById('moreMenu').replaceChildren(); // Old pills, fitWorkshopButtons refills it
    document.getElementById('workshopButtons').replaceChildren(...pills);
    fitWorkshopButtons();

    contextMenuItems.forEach(item => map.contextmenu.removeItem(item));
    contextMenuItems = [];
    const located = workshopButtons.filter(b => b.location);
    if (located.length) {
        contextMenuItems.push(map.contextmenu.insertItem({ separator: true }, 0));
        located.slice().reverse().forEach(b => {
            contextMenuItems.push(map.contextmenu.insertItem({
                text: buttonLabel(b.name, running),
                callback: e => runWorkshopButton(b.name, [e.latlng.lat, e.latlng.lng])
            }, 0));
        });
    }
}

// Moves the pills that don't fit in the top bar into the "More" menu
function fitWorkshopButtons() {
    const bar = document.getElementById('workshopButtons');
    const more = document.getElementById('moreButton');
    const menu = document.getElementById('moreMenu');
    const pills = [...bar.children, ...menu.children];
    bar.replaceChildren(...pills);
    more.hidden = true;
    const overflowing = () => {
        const right = bar.getBoundingClientRect().right - 4; // Minus the padding that leaves room for shadows
        return pills.filter(pill => pill.getBoundingClientRect().right > right + 1);
    };
    if (overflowing().length) {
        more.hidden = false;
        // Showing "More" takes room too, so check again
        menu.replaceChildren(...overflowing());
    } else {
        menu.replaceChildren();
        menu.hidden = true;
    }
    more.classList.toggle('running', Boolean(menu.querySelector('.running'))); // Something under More is running
}

function runWorkshopButton(name, location = null) {
    document.getElementById('moreMenu').hidden = true;
    postJson('/api/buttons/run', { name, location, waypoints: waypoints.map(w => [w.lat, w.lng]) })
        .then(data => showToast(data.message, "success"))
        .catch(error => showToast(`Error: ${error.message}`, "error"));
}

function postJson(path, body) {
    return fetch(`${backendUrl}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    }).then(response => response.json().then(data => {
        if (!response.ok || data.status !== 'success') {
            throw new Error(data.message || `Server responded with status: ${response.status}`);
        }
        return data;
    }));
}

function showRunningButtons(data) {
    const running = (data && data.running_buttons) || [];
    if (running.join('\n') !== shownRunning) {
        drawWorkshopButtons(running);
    }
    const error = data && data.button_error;
    if (error && error[0] !== lastButtonError) {
        lastButtonError = error[0];
        showToast(`Crashed: ${error[1]} (details in the backend terminal)`, "error", 8000);
    }
}

// --- Landmarks: a dot plus its photo zone, the slice of ring on the side it must be photographed from ---
// A photo counts when the plane is inside a landmark's slice and the landmark is inside the plane's cone,
// the same rule as can_photograph. The slice turns green with the plane in it, the cone with a landmark
// in it, and the label says "✓ photo" when both hold for the same landmark.
const FIELD_OF_VIEW = 60; // degrees, as in game.py
const CONE_LENGTH = 150; // m, the far edge of the photo zones
const ZONE_GREEN = '#2e7d32';

function distanceMeters(lat1, lon1, lat2, lon2) {
    const north = (lat2 - lat1) * 111319.5;
    const east = (lon2 - lon1) * 111319.5 * Math.cos(lat1 * Math.PI / 180);
    return Math.hypot(north, east);
}

function directionDegrees(lat1, lon1, lat2, lon2) {
    const north = (lat2 - lat1) * 111319.5;
    const east = (lon2 - lon1) * 111319.5 * Math.cos(lat1 * Math.PI / 180);
    return (Math.atan2(east, north) * 180 / Math.PI + 360) % 360;
}

function angleBetween(a, b) {
    return Math.abs(((a - b) % 360 + 540) % 360 - 180);
}

function offsetLatLng(lat, lon, distance, direction) {
    const d = direction * Math.PI / 180;
    return [lat + distance * Math.cos(d) / 111319.5,
            lon + distance * Math.sin(d) / (111319.5 * Math.cos(lat * Math.PI / 180))];
}

function photoZone(lm) {
    const points = [];
    for (let i = 0; i <= 12; i++) {
        points.push(offsetLatLng(lm.lat, lm.lon, lm.outer, lm.approach_from - lm.view_width / 2 + lm.view_width * i / 12));
    }
    for (let i = 12; i >= 0; i--) {
        points.push(offsetLatLng(lm.lat, lm.lon, lm.inner, lm.approach_from - lm.view_width / 2 + lm.view_width * i / 12));
    }
    return points;
}

async function fetchLandmarks() {
    try {
        const response = await fetch(`${backendUrl}/api/landmarks`);
        const data = await response.json();
        if (!landmarkLayer) {
            landmarkLayer = L.layerGroup().addTo(map);
        }
        landmarkLayer.clearLayers();
        landmarkViews = data.landmarks.map(lm => {
            const color = lm.public ? '#f9a825' : '#8e24aa';
            const zone = L.polygon(photoZone(lm), { color, weight: 1, fillOpacity: 0.25 }).addTo(landmarkLayer);
            const dot = L.circleMarker([lm.lat, lm.lon], { radius: 6, color, fillOpacity: 1 })
                .bindTooltip(`${lm.name} · ${lm.price}`, { permanent: true, direction: 'top', offset: [0, -6] })
                .addTo(landmarkLayer);
            return { lm, color, zone, dot, label: null };
        });
        showPhotoRule(lastTelemetry);
    } catch (error) {
        console.error('Landmark Fetch Error:', error);
    }
}

function conePoints(lat, lon, heading) {
    const points = [[lat, lon]];
    for (let i = 0; i <= 8; i++) {
        points.push(offsetLatLng(lat, lon, CONE_LENGTH, heading - FIELD_OF_VIEW / 2 + FIELD_OF_VIEW * i / 8));
    }
    return points;
}

function showPhotoRule(data) {
    if (!data || typeof data.lat !== 'number' || typeof data.lon !== 'number') {
        return;
    }
    const heading = data.heading ?? 0;
    let anyInCone = false;
    landmarkViews.forEach(view => {
        const lm = view.lm;
        const distance = distanceMeters(lm.lat, lm.lon, data.lat, data.lon);
        const inZone = distance >= lm.inner && distance <= lm.outer
            && angleBetween(directionDegrees(lm.lat, lm.lon, data.lat, data.lon), lm.approach_from) <= lm.view_width / 2;
        const inCone = distance <= CONE_LENGTH
            && angleBetween(directionDegrees(data.lat, data.lon, lm.lat, lm.lon), heading) <= FIELD_OF_VIEW / 2;
        anyInCone ||= inCone;
        view.zone.setStyle({ color: inZone ? ZONE_GREEN : view.color });
        const label = `${lm.name} · ${lm.price}` + (inZone && inCone ? ' ✓ photo' : '');
        if (label !== view.label) {
            view.dot.setTooltipContent(label);
            view.label = label;
        }
    });

    // Grey while the camera recharges after a photo that didn't count
    const points = conePoints(data.lat, data.lon, heading);
    const coneColor = data.camera_ready === false ? '#9e9e9e' : anyInCone ? ZONE_GREEN : '#e53935';
    const style = { color: coneColor, weight: 1, fillOpacity: 0.15 };
    if (droneCone) {
        droneCone.setLatLngs(points).setStyle(style);
    } else {
        droneCone = L.polygon(points, { ...style, interactive: false }).addTo(map);
    }
}

// --- UI Update Functions ---
// function //updateStatus(message, isError = false) {
//     statusDiv.innerHTML = `<strong>Status:</strong> ${message}`;
//     statusDiv.style.color = isError ? 'red' : 'black';
// }

// Formats a telemetry number, or a dash when the vehicle hasn't reported it
function formatValue(value, digits, unit = '') {
    return typeof value === 'number' ? `${value.toFixed(digits)}${unit}` : '–';
}

function renderTelemetry(data) {
    const connected = Boolean(data && data.is_connected);
    telemetryState.textContent = connected ? 'online' : 'offline';
    telemetryState.classList.toggle('online', connected);

    const d = connected ? data : {};
    const rows = [
        ['Mode', d.mode ?? '–'],
        ['Armed', connected ? (d.armed ? 'Yes' : 'No') : '–'],
        ['Altitude', formatValue(d.alt, 1, ' m')],
        ['Groundspeed', formatValue(d.groundspeed, 1, ' m/s')],
        ['Airspeed', formatValue(d.airspeed, 1, ' m/s')],
        ['Heading', formatValue(d.heading, 0, '°')],
        ['Battery', formatValue(d.battery_voltage, 2, ' V')],
        ['Latitude', formatValue(d.lat, 6)],
        ['Longitude', formatValue(d.lon, 6)],
    ];
    telemetryList.replaceChildren(...rows.flatMap(([label, value]) => {
        const dt = document.createElement('dt');
        dt.textContent = label;
        const dd = document.createElement('dd');
        dd.textContent = value;
        return [dt, dd];
    }));
}

function updateTelemetry(data) {
    renderTelemetry(data);
    showRunningButtons(data);

    if (map && data && data.is_connected) {
        const lat = data.lat;
        const lon = data.lon;

        if (typeof lat === 'number' && typeof lon === 'number') {
            const droneLatLng = [lat, lon];

            // The plane is an arrow pointing where its nose points, like on the live map
            if (droneMarker) {
                droneMarker.setLatLng(droneLatLng);
            } else {
                droneMarker = L.marker(droneLatLng, {
                    icon: L.divIcon({
                        className: 'drone-icon',
                        html: '<svg viewBox="0 0 24 24"><path d="M12 2 L20 21 L12 17 L4 21 Z"/></svg>',
                        iconSize: [32, 32],
                        iconAnchor: [16, 16]
                    })
                }).addTo(map).bindPopup(`Drone Location`);
                console.log("Drone marker created at:", droneLatLng);
            }
            const arrow = droneMarker.getElement()?.querySelector('svg');
            if (arrow) {
                arrow.style.transform = `rotate(${data.heading ?? 0}deg)`;
            }
            lastTelemetry = data;
            showPhotoRule(data);
            if (!initialCenterSet) {
                map.setView(droneLatLng, 17);
                initialCenterSet = true;
                console.log("Map centered on initial drone location.");
            }
             if (droneMarker) {
                 droneMarker.setPopupContent(`Drone Location<br>Lat: ${lat.toFixed(6)}, Lon: ${lon.toFixed(6)}<br>Alt: ${data.alt?.toFixed(2)}m | Mode: ${data.mode}`);
            }

            // ----> Start: Add point to flight path trail <----
            // Optional: Add a check to prevent adding points if the drone hasn't moved significantly
            const lastCoord = flightPathCoordinates.length > 0 ? flightPathCoordinates[flightPathCoordinates.length - 1] : null;
            // Simple check: Add if it's the first point or if lat/lon differs from the last point
            if (!lastCoord || lastCoord[0] !== lat || lastCoord[1] !== lon) {

                flightPathCoordinates.push(droneLatLng); // Add new coordinate to history

                if (flightPathPolyline) {
                    // If polyline exists, add the new point
                    flightPathPolyline.addLatLng(droneLatLng);
                } else {
                    // If polyline doesn't exist, create it (needs at least one point)
                    flightPathPolyline = L.polyline(flightPathCoordinates, {
                        color: 'blue',  // Trail color
                        weight: 3,       // Trail thickness
                        opacity: 0.7     // Trail opacity
                    }).addTo(map);
                    console.log("Flight path polyline created.");
                }
            }
            // ----> End: Add point to flight path trail <----

        } // End if valid lat/lon
    } // End if map and connected
}


function setUIConnected(connected) {
    isConnected = connected;
    // connectButton.disabled = connected;
    // disconnectButton.disabled = !connected;
    statusButton.disabled = !connected;
    takeoffButton.disabled = !connected;
    // Enable/disable other command buttons here later

    if (connected) {
        // ----> Start: Clear previous flight path on new connection <----
        flightPathCoordinates = []; // Clear the history
        if (flightPathPolyline) {
            map.removeLayer(flightPathPolyline); // Remove old line from map
            flightPathPolyline = null;
        }
        // ----> End: Clear previous flight path <----

        //updateStatus('Connected');
        connectButton.hidden = true;
        disconnectButton.hidden = false;
        fetchStatus(); // Fetch immediately
        if (!statusInterval) {
            statusInterval = setInterval(fetchStatus, 100); // Poll every 100 ms
        }
        loadWorkshopButtons();
        fetchLandmarks();
        if (!landmarkInterval) {
            landmarkInterval = setInterval(fetchLandmarks, 1000);
        }
    } else {
        connectButton.hidden = false;
        disconnectButton.hidden = true;

        //updateStatus('Disconnected');
        updateTelemetry(null); // Clear telemetry text

        // Stop polling
        if (statusInterval) {
            clearInterval(statusInterval);
            statusInterval = null;
        }
        if (landmarkInterval) {
            clearInterval(landmarkInterval);
            landmarkInterval = null;
        }
        if (landmarkLayer) {
            landmarkLayer.clearLayers();
        }
        workshopButtons = [];
        drawWorkshopButtons([]);

        // Clean up map marker
        if (droneCone) {
            map.removeLayer(droneCone);
            droneCone = null;
        }
        landmarkViews = [];
        lastTelemetry = null;
        if (droneMarker) {
            map.removeLayer(droneMarker);
            droneMarker = null;
            console.log("Drone marker removed.");
        }

        // Remove all other L.Marker instances (e.g., go-to markers), but keep the waypoints
        map.eachLayer(function (layer) {
            if (layer instanceof L.Marker && !layer.options.keep) {
                map.removeLayer(layer);
            }
        });
        initialCenterSet = false; // Reset centering flag

        // ----> Start: Clear flight path on disconnect <----
        flightPathCoordinates = []; // Clear the history
        if (flightPathPolyline) {
            map.removeLayer(flightPathPolyline); // Remove line from map
            flightPathPolyline = null;
        }
         // ----> End: Clear flight path <----

        // Optional: Reset map view to initial state on disconnect
        if (map) {
             map.setView([39.36, 22.94], 5); // Reset to initial wider view
        }
    }
}


// --- API Call Functions ---
async function connectToDrone() {
    //updateStatus('Attempting connection...');
    showToast("Connecting to SITL (this can take up to a minute)...", "info", 5000);
    connectButton.disabled = true;
    try {
        const response = await fetch(`${backendUrl}/api/connect`, { method: 'POST' });
        const data = await response.json();

        if (response.ok && data.status === 'success') {
            showToast("Connected to SITL", "success");
            setUIConnected(true);
        } else {
            //updateStatus(`Connection Failed: ${data.message}`, true);
            showToast(`Connection failed: ${data.message}`, "error");
            setUIConnected(false);
        }
    } catch (error) {
        console.error('Connection Error:', error);
        //updateStatus(`Connection Error: ${error.message}`, true);
        showToast(`Connection error: ${error.message} (is the backend running?)`, "error");
        setUIConnected(false);
    } finally {
        connectButton.disabled = false;
    }
}

function disconnectFromDrone() {
    //updateStatus('Disconnecting...');
    fetch(`${backendUrl}/api/disconnect`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                setUIConnected(false);
            } else {
                //updateStatus(`Disconnection Failed: ${data.message}`, true);
            }
        })
        .catch(error => {
            console.error('Disconnection Error:', error);
            //updateStatus(`Disconnection Error: ${error.message}`, true);
        });
}

async function fetchStatus() {
    try {
        const response = await fetch(`${backendUrl}/api/status`, { method: 'GET' });
        const result = await response.json();

        if (response.ok && result.status === 'success') {
            // Call updateTelemetry which now handles both text and map
            updateTelemetry(result.data);

            if (!result.data.is_connected) {
                console.warn("Backend reports vehicle disconnected.");
                setUIConnected(false);
                //updateStatus("Connection lost (reported by backend)", true);
            }
        } else {
            //updateStatus(`Error fetching status: ${result.message}`, true);
        }
    } catch (error) {
        console.error('Status Fetch Error:', error);
        //updateStatus(`Status Fetch Error: ${error.message}`, true);
        // If fetching fails, you might want to stop polling or indicate stale data
        // clearInterval(statusInterval); statusInterval = null; // Example: stop polling on error
    }
}

// --- Event Listeners ---
document.getElementById('moreButton').addEventListener('click', () => {
    const menu = document.getElementById('moreMenu');
    menu.hidden = !menu.hidden;
});
window.addEventListener('resize', fitWorkshopButtons);
document.getElementById('telemetryToggle').addEventListener('click', () => {
    document.getElementById('telemetry').classList.toggle('collapsed');
});
renderTelemetry(null); // Empty rows until the first status arrives
// On a phone the panel would cover half the map, so it starts folded
if (window.matchMedia('(max-width: 600px)').matches) {
    document.getElementById('telemetry').classList.add('collapsed');
}

connectButton.addEventListener('click', connectToDrone);
disconnectButton.addEventListener('click', disconnectFromDrone);
statusButton.addEventListener('click', fetchStatus); // Manual status fetch
takeoffButton.addEventListener('click', sendTakeOff); // Manual status fetch

// --- Initialization ---
// Ensure map is initialized after the DOM is ready
document.addEventListener('DOMContentLoaded', (event) => {
    initMap(); // Initialize the map
    setUIConnected(false); // Set initial UI state after map div exists
});