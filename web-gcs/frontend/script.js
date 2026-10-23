const connectButton = document.getElementById('connectButton');
const disconnectButton = document.getElementById('disconnectButton');
const connectWrap = document.getElementById('connectWrap');
const connectChoiceButton = document.getElementById('connectChoiceButton');
const connectMenu = document.getElementById('connectMenu');
const statusButton = document.getElementById('statusButton');
const takeoffButton = document.getElementById('takeoffButton');
const altitudeInput = document.getElementById('altitudeInput');
// const statusDiv = document.getElementById('status');
const telemetryList = document.getElementById('telemetryData');
const telemetryState = document.getElementById('telemetryState');

const backendUrl = ''; // The backend serves this page, so its API is on the same address

// --- Map Variables ---
let map = null;
let droneMarker = null;
let targetMarker = null; // Where the plane is flying to right now (the backend's latest simple_goto)
let initialCenterSet = false; // Track if map centered on first fix
// The trail: the last TRAIL_SECONDS of flight, drawn as TRAIL_PIECES lines that fade towards the old end
const TRAIL_SECONDS = 120;
const TRAIL_PIECES = 12;
let trailPoints = []; // [{latLng, time}], oldest first
let trailLines = []; // TRAIL_PIECES polylines, oldest piece first

// --- State Variables ---
let isConnected = false;
let statusInterval = null; // To hold the interval timer for fetching status
let landmarkInterval = null; // Timer for fetching the landmarks
let waypoints = []; // [{lat, lng, marker}] added with right-click -> Add waypoint
let landmarkLayer = null; // Landmarks and their photo zones
let landmarkViews = []; // [{lm, zone, dot, label}] for colouring them as the plane moves
let droneCone = null; // What the camera sees: FIELD_OF_VIEW wide, CONE_LENGTH long
let lastTelemetry = null;
let lastPhotoShown = null; // Number of the newest photo result we have shown as a toast
let lastButtonError = null; // Number of the last button crash we showed
let backendStart = null; // Which run of the backend we are connected to; a different one means it restarted
let reconnecting = false; // Reconnecting by ourselves after a backend restart
let movingShown = false; // Said once that the plane is being moved to its start position
let lastStatusOk = 0; // When the backend last answered a status request
let warnedNoBackend = false; // Shown the "backend isn't answering" toast since then
const NO_BACKEND_WARNING = 3000; // ms without an answer before that toast

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
          {
            text: 'Reset SITL',
            callback: function(e) {
              resetSitl();
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
        case 'sold': background = "linear-gradient(135deg, #ffe082, #f9a825)"; break;
        default: background = "#007bff"; // info
    }

    // Toastify comes from /vendor; if it is missing or blocked (ad blocker), log instead
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
        // Dark text on the light gold and yellow backgrounds, white on the rest
        style: type === 'sold' ? { background, color: '#3e2700', fontWeight: 700 }
            : type === 'warning' ? { background, color: '#3e2700' }
            : { background }
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

// Restarts the simulator (a forced reboot): the plane goes back to its runway. Then reconnects by itself.
const RECONNECT_AFTER_RESET = 12000; // ms: the simulator needs about 10 s to come back with a GPS fix
function resetSitl() {
    if (!confirm('Restart the simulator? Your plane goes back to the runway, disarmed.')) {
        return;
    }
    postJson('/api/reset_sitl', {})
        .then(() => {
            showToast("Restarting the simulator, reconnecting in a few seconds...", "info", RECONNECT_AFTER_RESET);
            setUIConnected(false);
            setTimeout(connectToDrone, RECONNECT_AFTER_RESET);
        })
        .catch(error => showToast(`Error: ${error.message}`, "error"));
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

// The right-click menu is plain text, so a running button gets a dot there like the pill's
function menuLabel(name, running) {
    return running.includes(name) ? `● ${name}` : name;
}

function drawWorkshopButtons(running) {
    shownRunning = running.join('\n');
    const pills = workshopButtons.filter(b => !b.location).map(b => {
        const pill = document.createElement('button');
        pill.className = 'pill workshop-button';
        pill.classList.toggle('running', running.includes(b.name));
        // Running: green with a white dot, like Connected
        if (running.includes(b.name)) {
            const dot = document.createElement('span');
            dot.className = 'status-dot';
            pill.append(dot);
        }
        pill.append(b.name);
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
                text: menuLabel(b.name, running),
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
        const right = bar.getBoundingClientRect().right;
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

// A new landmark announces itself with a ring that grows and fades, twice
function ripple(lat, lon, color) {
    const ring = L.circleMarker([lat, lon], { radius: 6, color, weight: 3, fill: false, interactive: false }).addTo(map);
    const start = performance.now();
    const PULSE = 750; // ms per pulse
    function step(now) {
        const t = (now - start) / PULSE;
        if (t >= 2) {
            map.removeLayer(ring);
            return;
        }
        const pulse = t % 1;
        ring.setRadius(6 + 40 * pulse);
        ring.setStyle({ opacity: 1 - pulse });
        requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
}

// Sold landmarks fade a little with every sale, but stay visible: what's left can still be worth a detour
function saleFade(sales) {
    return Math.max(0.35, 1 - 0.2 * (sales || 0));
}

function landmarkLabel(lm) {
    let label = `${lm.name} · ${lm.price}`;
    if (lm.head_start > 0) label += ` · ${Math.ceil(lm.head_start)} s alone`;
    else if (lm.sales) label += ` · sold ${lm.sales}×`;
    return label;
}

let shownLandmarks = null; // Names on the map after the last fetch; null = don't ripple the next ones
let shownRound = null; // The round they were from
let areaRectangle = null; // Where new landmarks can appear (it shrinks during a round)

function showArea(area) {
    if (!area) {
        if (areaRectangle) {
            map.removeLayer(areaRectangle);
            areaRectangle = null;
        }
        return;
    }
    const bounds = [[area[0], area[1]], [area[2], area[3]]];
    if (areaRectangle) {
        areaRectangle.setBounds(bounds);
    } else {
        areaRectangle = L.rectangle(bounds, { color: '#455a64', weight: 1.5, dashArray: '6 6', fill: false, interactive: false })
            .addTo(map);
    }
}

async function fetchLandmarks() {
    try {
        const response = await fetch(`${backendUrl}/api/landmarks`);
        const data = await response.json();
        if (!landmarkLayer) {
            landmarkLayer = L.layerGroup().addTo(map);
        }
        // Everything is new at the start of a round, so only ripple landmarks that appear during one
        const round = lastTelemetry && lastTelemetry.round;
        const roundKey = round ? `${round.name}:${round.state}` : 'practice';
        const ripples = shownLandmarks !== null && roundKey === shownRound;
        landmarkLayer.clearLayers();
        landmarkViews = data.landmarks.map(lm => {
            const hidden = !lm.public;
            const color = hidden ? '#8e24aa' : '#f9a825';
            const fade = saleFade(lm.sales);
            const zone = L.polygon(photoZone(lm), { color, weight: hidden ? 2 : 1, opacity: fade, fillOpacity: 0.25 * fade })
                .addTo(landmarkLayer);
            if (hidden) { // A halo, so our own landmark stands out among the public ones
                L.circleMarker([lm.lat, lm.lon], { radius: 13, color, weight: 2, fillOpacity: 0.2, interactive: false })
                    .addTo(landmarkLayer);
            }
            const dot = L.circleMarker([lm.lat, lm.lon], { radius: hidden ? 8 : 6, color, opacity: fade, fillOpacity: fade })
                .bindTooltip(landmarkLabel(lm), { permanent: true, direction: 'top', offset: [0, -6],
                                                  opacity: 0.9 * fade, className: hidden ? 'hidden-label' : '' })
                .addTo(landmarkLayer);
            if (ripples && !shownLandmarks.has(lm.name)) {
                ripple(lm.lat, lm.lon, color);
            }
            return { lm, color, zone, dot, label: null };
        });
        shownLandmarks = new Set(data.landmarks.map(lm => lm.name));
        shownRound = roundKey;
        showArea(data.area);
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
        const label = landmarkLabel(lm) + (inZone && inCone ? ' ✓ photo' : '');
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

// --- Trail ---
function addTrailPoint(latLng) {
    const now = Date.now() / 1000;
    const last = trailPoints[trailPoints.length - 1];
    // Only when the plane moved, so sitting on the runway doesn't fill the trail
    if (!last || last.latLng[0] !== latLng[0] || last.latLng[1] !== latLng[1]) {
        trailPoints.push({ latLng, time: now });
    }
    while (trailPoints.length && trailPoints[0].time < now - TRAIL_SECONDS) {
        trailPoints.shift();
    }
    if (!trailLines.length) {
        for (let i = 0; i < TRAIL_PIECES; i++) {
            trailLines.push(L.polyline([], { color: 'blue', weight: 3, interactive: false }).addTo(map));
        }
    }
    // Split the trail into equal pieces, each sharing its end point with the next so there are no gaps
    const size = Math.ceil(trailPoints.length / TRAIL_PIECES);
    trailLines.forEach((line, i) => {
        line.setLatLngs(trailPoints.slice(i * size, (i + 1) * size + 1).map(p => p.latLng));
        line.setStyle({ opacity: 0.75 * (i + 1) / TRAIL_PIECES });
    });
}

function clearTrail() {
    trailLines.forEach(line => map.removeLayer(line));
    trailLines = [];
    trailPoints = [];
}

// One marker for where the plane is flying to, whoever sent it there; gone once nothing is
function showTarget(target) {
    if (!target) {
        if (targetMarker) {
            map.removeLayer(targetMarker);
            targetMarker = null;
        }
        return;
    }
    if (targetMarker) {
        targetMarker.setLatLng(target);
    } else {
        targetMarker = L.marker(target, {
            zIndexOffset: -1000, // Under the plane and the waypoints
            interactive: false,
            icon: L.divIcon({
                className: 'target-marker',
                html: '<i class="fas fa-crosshairs"></i>',
                iconSize: [24, 24]
            })
        }).addTo(map);
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

function fillGrid(list, rows) {
    list.replaceChildren(...rows.flatMap(([label, value]) => {
        const dt = document.createElement('dt');
        dt.textContent = label;
        const dd = document.createElement('dd');
        dd.textContent = value;
        return [dt, dd];
    }));
}

// Our own score for now; with the game server, also the leader and whoever is just ahead of us
function clock(seconds) {
    const s = Math.max(0, Math.round(seconds));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function describeRound(round) {
    if (!round) return 'Practice';
    const name = round.name === 'real' ? 'Real round' : 'Test round';
    switch (round.state) {
        case 'countdown': return `${name} in ${clock(round.starts_in)}`;
        case 'running': return `${name} · ${clock(round.seconds_left)}`;
        default: return `${name} over`;
    }
}

function renderScore(data) {
    const score = data && data.score;
    const round = data && data.round;
    document.getElementById('scoreBadge').textContent = score ? score.money : 0;
    const rows = [['Round', describeRound(round)], ['Money', score ? score.money : '–']];
    if (score && score.rank) {
        rows.push(['Place', `${score.rank} of ${score.players}`]);
        rows.push(['Leader', `${score.leader.name} ${score.leader.money}`]);
        if (score.ahead) rows.push(['Ahead of you', `${score.ahead.name} ${score.ahead.money}`]);
    }
    rows.push(['Photos sold', score ? score.photos : '–'], ['Last sale', (score && score.last_sale) || '–']);
    fillGrid(document.getElementById('scoreData'), rows);
    announceRound(round);
}

// A toast when a round starts counting down, starts and ends
let lastRoundState = null;
function announceRound(round) {
    const state = round ? `${round.name}:${round.state}` : 'practice';
    if (lastRoundState !== null && state !== lastRoundState && round) {
        const name = round.name === 'real' ? 'Real round' : 'Test round';
        if (round.state === 'countdown') showToast(`${name} starting: your plane flies to its start position`, 'info', 6000);
        if (round.state === 'running') showToast(`${name} started! Go!`, 'success', 5000);
        if (round.state === 'over') showToast(`${name} over`, 'info', 6000);
    }
    lastRoundState = state;
}

// Everyone else's plane: a grey arrow with their name, under our own
let otherMarkers = {}; // name -> marker
function showOthers(others) {
    const seen = new Set();
    for (const other of others || []) {
        seen.add(other.name);
        let marker = otherMarkers[other.name];
        if (!marker) {
            // Names come from participants, so they're set as text, never as HTML
            const label = document.createElement('span');
            label.textContent = other.name;
            marker = L.marker([other.lat, other.lon], {
                zIndexOffset: -500,
                interactive: false,
                icon: L.divIcon({
                    className: 'drone-icon other',
                    html: '<svg viewBox="0 0 24 24"><path d="M12 2 L20 21 L12 17 L4 21 Z"/></svg>',
                    iconSize: [26, 26],
                    iconAnchor: [13, 13]
                })
            }).bindTooltip(label, { permanent: true, direction: 'right', offset: [12, 0], className: 'other-label' }).addTo(map);
            otherMarkers[other.name] = marker;
        }
        marker.setLatLng([other.lat, other.lon]);
        const arrow = marker.getElement()?.querySelector('svg');
        if (arrow) arrow.style.transform = `rotate(${other.heading ?? 0}deg)`;
    }
    for (const name of Object.keys(otherMarkers)) {
        if (!seen.has(name)) {
            map.removeLayer(otherMarkers[name]);
            delete otherMarkers[name];
        }
    }
}

// A toast for each new photo result: gold when it sold
function showPhotoResults(data) {
    const log = (data && data.photo_log) || [];
    const newest = log.length ? log[log.length - 1][0] : 0;
    if (lastPhotoShown === null || newest < lastPhotoShown) { // Just connected, or the backend restarted
        lastPhotoShown = newest;
        return;
    }
    log.filter(([number]) => number > lastPhotoShown).forEach(([, sold, text]) => {
        showToast(text, sold ? 'sold' : 'warning', sold ? 4000 : 3000);
    });
    lastPhotoShown = newest;
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
    fillGrid(telemetryList, rows);
    renderScore(connected ? data : null);
    if (connected) {
        showPhotoResults(data);
    }
}

function updateTelemetry(data) {
    renderTelemetry(data);
    showRunningButtons(data);

    if (map && data && data.is_connected) {
        const lat = data.lat;
        const lon = data.lon;

        // Until its GPS has a fix, SITL says it's at 0, 0 (the middle of the world): ignore that
        if (typeof lat === 'number' && typeof lon === 'number' && (Math.abs(lat) > 0.01 || Math.abs(lon) > 0.01)) {
            const droneLatLng = [lat, lon];

            // The plane is an arrow pointing where its nose points, like on the live map
            if (droneMarker) {
                // A jump (GPS fix, put down at its corner, Reset SITL): follow it, without a trail line across the map
                if (map.distance(droneMarker.getLatLng(), droneLatLng) > 500) {
                    clearTrail();
                    map.panTo(droneLatLng);
                }
                droneMarker.setLatLng(droneLatLng);
            } else {
                droneMarker = L.marker(droneLatLng, {
                    zIndexOffset: 1000, // Above everyone else's
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
            showTarget(data.target);
            showOthers(data.others);
            if (!initialCenterSet) {
                map.setView(droneLatLng, 17);
                initialCenterSet = true;
                console.log("Map centered on initial drone location.");
            }
             if (droneMarker) {
                 droneMarker.setPopupContent(`Drone Location<br>Lat: ${lat.toFixed(6)}, Lon: ${lon.toFixed(6)}<br>Alt: ${data.alt?.toFixed(2)}m | Mode: ${data.mode}`);
            }

            addTrailPoint(droneLatLng);

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
        clearTrail(); // Start a fresh trail on every connection

        //updateStatus('Connected');
        connectWrap.hidden = true;
        connectMenu.hidden = true;
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
        connectWrap.hidden = false;
        disconnectButton.hidden = true;
        backendStart = null;

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
        shownLandmarks = null; // Reconnecting shows them all at once again, without ripples
        showArea(null);
        workshopButtons = [];
        drawWorkshopButtons([]);

        // Clean up map marker
        if (droneCone) {
            map.removeLayer(droneCone);
            droneCone = null;
        }
        showTarget(null);
        showOthers([]);
        lastPhotoShown = null;
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

        clearTrail();

        // Optional: Reset map view to initial state on disconnect
        if (map) {
             map.setView([39.36, 22.94], 5); // Reset to initial wider view
        }
    }
}


// --- API Call Functions ---
// --- Which plane Connect uses: "server" (the organisers' laptop) or "local" (a SITL on this laptop) ---
// Chosen with the arrow next to Connect and remembered in this browser. Connect never switches by itself:
// connection trouble often clears up on its own, so it keeps asking and says what to try instead.
let planeSource = null;

function choosePlaneSource(source) {
    planeSource = source;
    try {
        localStorage.setItem('planeSource', source);
    } catch (e) {} // Private window: just not remembered
    connectMenu.querySelectorAll('.connect-option').forEach(option =>
        option.classList.toggle('selected', option.dataset.source === source));
    const name = source === 'local' ? 'a SITL on this laptop' : "your plane on the organisers' laptop";
    connectButton.title = `Connect to ${name} (change it with the arrow)`;
}

async function loadPlaneSource() {
    let source = null;
    try {
        source = localStorage.getItem('planeSource');
    } catch (e) {}
    if (source !== 'server' && source !== 'local') {
        source = 'server'; // Nothing chosen yet: the server's plane if workshop.py names a server
        try {
            const options = await (await fetch(`${backendUrl}/api/connect/options`)).json();
            if (!options.server) source = 'local';
        } catch (e) {}
    }
    choosePlaneSource(source);
}

function toggleConnectMenu(open = connectMenu.hidden) {
    connectMenu.hidden = !open;
    connectChoiceButton.setAttribute('aria-expanded', String(open));
}

async function connectToDrone(message = "Connecting to SITL (this can take up to a minute)...") {
    //updateStatus('Attempting connection...');
    showToast(message, "info", 5000);
    connectButton.disabled = true;
    connectChoiceButton.disabled = true;
    toggleConnectMenu(false);
    // While Connect waits (for the server, or a SITL starting), the backend says what for
    let lastProgress = null;
    const progress = setInterval(async () => {
        try {
            const status = await (await fetch(`${backendUrl}/api/status`)).json();
            const text = status.data && status.data.connect_progress;
            if (text && text !== lastProgress) showToast(text, "info", 5000);
            lastProgress = text;
        } catch (e) {}
    }, 2000);
    try {
        const response = await fetch(`${backendUrl}/api/connect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: planeSource }),
        });
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
        clearInterval(progress);
        connectButton.disabled = false;
        connectChoiceButton.disabled = false;
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

        lastStatusOk = Date.now();
        warnedNoBackend = false;
        if (response.ok && result.status === 'success') {
            // Call updateTelemetry which now handles both text and map
            updateTelemetry(result.data);

            if (result.data.is_connected) {
                backendStart = result.data.backend_start;
                movingShown = false;
            } else if (result.data.moving) {
                // The round is starting and the backend is moving the plane to its corner: it reconnects itself
                if (!movingShown) {
                    movingShown = true;
                    showToast("Round starting: your plane is being put down at its start position. Back in about 15 s; "
                        + "it can't arm for about 30 s after that, then take off", "info", 12000);
                }
            } else if (backendStart && result.data.backend_start !== backendStart) {
                if (result.data.workshop_error) {
                    showWorkshopError(result.data); // Wait for the save that fixes it, then reconnect
                } else {
                    reconnectAfterRestart();
                }
            } else if (!reconnecting) {
                console.warn("Backend reports vehicle disconnected.");
                setUIConnected(false);
                //updateStatus("Connection lost (reported by backend)", true);
            }
        } else {
            //updateStatus(`Error fetching status: ${result.message}`, true);
        }
    } catch (error) {
        console.error('Status Fetch Error:', error);
        // The backend restarts for a moment on every save of workshop.py; much longer means it stopped
        if (!warnedNoBackend && Date.now() - lastStatusOk > NO_BACKEND_WARNING) {
            warnedNoBackend = true;
            showToast("The backend isn't answering: look at its terminal (a mistake in workshop.py?)", "error", 8000);
        }
    }
}

// A workshop.py with a mistake in it: shown once per save
let shownWorkshopError = null;
function showWorkshopError(data) {
    if (shownWorkshopError === data.backend_start) return;
    shownWorkshopError = data.backend_start;
    showToast(`workshop.py has a mistake, ${data.workshop_error}. Fix it and save (details in the backend terminal)`, "error", 10000);
}

// Saving workshop.py restarts the backend, which drops the plane: connect again by ourselves
async function reconnectAfterRestart() {
    if (reconnecting) return;
    reconnecting = true;
    await connectToDrone("workshop.py changed: reconnecting...");
    reconnecting = false;
}

// --- Event Listeners ---
document.getElementById('moreButton').addEventListener('click', () => {
    const menu = document.getElementById('moreMenu');
    menu.hidden = !menu.hidden;
});
window.addEventListener('resize', fitWorkshopButtons);
document.querySelectorAll('.panel-toggle').forEach(toggle => {
    toggle.addEventListener('click', () => toggle.closest('.panel').classList.toggle('collapsed'));
});
renderTelemetry(null); // Empty rows until the first status arrives
// On a phone the panels would cover half the map, so they start folded
if (window.matchMedia('(max-width: 600px)').matches) {
    document.querySelectorAll('.panel').forEach(panel => panel.classList.add('collapsed'));
}

connectButton.addEventListener('click', () => connectToDrone());
connectChoiceButton.addEventListener('click', event => {
    event.stopPropagation(); // Not a click outside the menu
    toggleConnectMenu();
});
connectMenu.querySelectorAll('.connect-option').forEach(option => option.addEventListener('click', () => {
    choosePlaneSource(option.dataset.source);
    toggleConnectMenu(false);
}));
document.addEventListener('click', event => {
    if (!connectMenu.hidden && !connectWrap.contains(event.target)) toggleConnectMenu(false);
});
loadPlaneSource();
disconnectButton.addEventListener('click', disconnectFromDrone);
statusButton.addEventListener('click', fetchStatus); // Manual status fetch
takeoffButton.addEventListener('click', sendTakeOff); // Manual status fetch

// --- Initialization ---
// Ensure map is initialized after the DOM is ready
document.addEventListener('DOMContentLoaded', (event) => {
    initMap(); // Initialize the map
    setUIConnected(false); // Set initial UI state after map div exists
});