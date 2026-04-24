// Global Variables
let map;
let roadLayer;
let mtrLayer;
let busLayer;
let geojsonData = null;
let mtrGeojsonData = null;

let predictionData = {};
let mtrPredictionData = {};
let busData = {};

let mapConfig = {};
let lastBackendUpdateTime = "";
let lastMtrUpdateTime = "";
let lastBusUpdateTime = "";

// System State
let currentSystem = 'mtr'; // 'road' or 'mtr' or 'bus'
let currentMTRView = 'network'; // 'network' or 'schematic'

// Initialize application
async function init() {
    try {
        // 1. Fetch Configuration
        const configRes = await fetch('/map_config');
        mapConfig = await configRes.json();
        
        // 2. Initialize Map
        const center = mapConfig.map_center || [22.3193, 114.1694];
        map = L.map('map').setView(center, 12);
        
        // Add OpenStreetMap tiles
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            subdomains: 'abcd',
            maxZoom: 20
        }).addTo(map);

        // 3. Load both GeoJSON Networks
        await Promise.all([loadRoadNetwork(), loadMTRNetwork(), loadBusNetwork()]);

        // Initialize MTR Embedded Schematic
        if (window.MTREmbedMonitor) {
            await window.MTREmbedMonitor.init();
        }

        // 4. Setup Event Listeners
        document.getElementById('refresh-btn').addEventListener('click', forceRefresh);
        document.getElementById('btn-road').addEventListener('click', () => switchSystem('road'));
        document.getElementById('btn-mtr').addEventListener('click', () => switchSystem('mtr'));
        document.getElementById('btn-bus').addEventListener('click', () => switchSystem('bus'));

        // 5. Initial System Setup
        switchSystem('mtr');

        // 6. Auto-refresh loop
        setInterval(autoRefresh, 15000); // Check every 15s (MTR needs 15s, Road 5m)

    } catch (err) {
        console.error("Initialization Error:", err);
        alert("Failed to load map data. See console for details.");
    }
}

// --- Data Loading ---

async function loadRoadNetwork() {
    console.log("Loading road network...");
    const res = await fetch('/road_network');
    if (!res.ok) throw new Error("Failed to fetch road network");
    geojsonData = await res.json();
    
    roadLayer = L.geoJSON(geojsonData, {
        style: styleRoadFeature,
        onEachFeature: onEachRoadFeature
    });
}

async function loadMTRNetwork() {
    console.log("Loading MTR network...");
    const res = await fetch('/mtr_network');
    if (!res.ok) {
        console.warn("MTR network GeoJSON not found. Using empty layer.");
        mtrLayer = L.layerGroup();
        return;
    }
    mtrGeojsonData = await res.json();
    
    mtrLayer = L.geoJSON(mtrGeojsonData, {
        style: styleMTRFeature,
        pointToLayer: function(feature, latlng) {
            return L.circleMarker(latlng, {
                radius: 6,
                fillColor: "#ffffff",
                color: "#000",
                weight: 1,
                opacity: 1,
                fillOpacity: 0.8
            });
        },
        onEachFeature: onEachMTRFeature
    });
}

async function loadBusNetwork() {
    console.log("Initializing Bus network layer...");
    busLayer = L.layerGroup();
    // We will populate it dynamically in refreshBusPredictions
}

// --- Refresh Logic ---

async function forceRefresh() {
    if (currentSystem === 'road') {
        await refreshRoadPredictions(true);
    } else if (currentSystem === 'mtr') {
        await refreshMTRPredictions(true);
    } else if (currentSystem === 'bus') {
        await refreshBusPredictions(true);
    }
}

async function autoRefresh() {
    if (currentSystem === 'road') {
        await refreshRoadPredictions(false);
    } else if (currentSystem === 'mtr') {
        await refreshMTRPredictions(false);
    } else if (currentSystem === 'bus') {
        await refreshBusPredictions(false);
    }
}

async function refreshRoadPredictions(force = false) {
    if (force) updateRefreshBtn(true);
    try {
        const endpoint = mapConfig.prediction_api_endpoint || '/predictions';
        const res = await fetch(endpoint);
        if (!res.ok) throw new Error("Failed to fetch predictions");
        
        const data = await res.json();
        
        if (!force && data.last_update && data.last_update === lastBackendUpdateTime) {
            updateLastUpdateText(lastBackendUpdateTime, true);
            return;
        }
        
        predictionData = data.predictions || {};
        lastBackendUpdateTime = data.last_update || "";
        
        if (roadLayer && currentSystem === 'road') {
            roadLayer.setStyle(styleRoadFeature);
        }
        updateLastUpdateText(lastBackendUpdateTime, false);
    } catch (err) {
        console.error("Road Prediction Error:", err);
    } finally {
        if (force) updateRefreshBtn(false);
    }
}

async function refreshMTRPredictions(force = false) {
    if (force) updateRefreshBtn(true);
    try {
        const res = await fetch('/mtr/delay-prediction');
        if (!res.ok) throw new Error("Failed to fetch MTR predictions");
        
        const data = await res.json();
        
        if (!force && data.last_update && data.last_update === lastMtrUpdateTime) {
            updateLastUpdateText(lastMtrUpdateTime, true);
            return;
        }
        
        mtrPredictionData = data.predictions || {};
        lastMtrUpdateTime = data.last_update || "";
        
        if (currentSystem === 'mtr') {
            if (currentMTRView === 'network') {
                if (mtrLayer) {
                    // Need to recreate style to apply blinking animations to DOM elements
                    mtrLayer.setStyle(styleMTRFeature);
                    mtrLayer.eachLayer(layer => {
                        if (layer.feature && layer.feature.geometry.type === 'Point') {
                            applyMTRMarkerStyle(layer);
                        }
                    });
                }
            } else if (currentMTRView === 'schematic' && window.MTREmbedMonitor) {
                window.MTREmbedMonitor.setPredictions(mtrPredictionData);
            }
        }
        
        updateLastUpdateText(lastMtrUpdateTime, false);
        updateMTREventsPanel();
    } catch (err) {
        console.error("MTR Prediction Error:", err);
    } finally {
        if (force) updateRefreshBtn(false);
    }
}

async function refreshBusPredictions(force = false) {
    if (force) updateRefreshBtn(true);
    try {
        const res = await fetch('/bus/routes');
        if (!res.ok) throw new Error("Failed to fetch Bus data");
        
        const data = await res.json();
        
        if (!force && data.last_update && data.last_update === lastBusUpdateTime) {
            updateLastUpdateText(lastBusUpdateTime, true);
            return;
        }
        
        busData = data.routes || [];
        lastBusUpdateTime = data.last_update || "";
        
        if (currentSystem === 'bus' && busLayer) {
            busLayer.clearLayers();
            buildBusSidebarList(busData);
            if (busData.length > 0) {
                selectBusRoute(0);
            }
        }
        
        updateLastUpdateText(lastBusUpdateTime, false);
    } catch (err) {
        console.error("Bus Data Error:", err);
    } finally {
        if (force) updateRefreshBtn(false);
    }
}

function buildBusSidebarList(routes) {
    const container = document.getElementById('bus-routes-container');
    container.innerHTML = '';
    
    routes.forEach((routeInfo, index) => {
        const color = getColorForRoute(index);
        
        const itemDiv = document.createElement('div');
        itemDiv.className = 'bus-route-item';
        itemDiv.id = `bus-route-item-${index}`;
        
        const headerDiv = document.createElement('div');
        headerDiv.className = 'bus-route-header';
        headerDiv.innerHTML = `<span class="bus-route-color" style="background-color: ${color};"></span> Route ${routeInfo.route} (${routeInfo.bound})`;
        
        const stopsList = document.createElement('ol');
        stopsList.className = 'bus-stops-list';
        stopsList.id = `bus-stops-list-${index}`;
        
        const stops = routeInfo.stops || [];
        stops.forEach(stop => {
            const li = document.createElement('li');
            li.innerText = stop.name_tc || stop.name_en;
            stopsList.appendChild(li);
        });
        
        itemDiv.appendChild(headerDiv);
        itemDiv.appendChild(stopsList);
        
        itemDiv.addEventListener('click', () => {
            selectBusRoute(index);
        });
        
        container.appendChild(itemDiv);
    });
}

let activeBusRouteIndex = -1;
let busEtaInterval = null;
let busLiveIconsLayer = null;

function selectBusRoute(selectedIndex) {
    if (selectedIndex === activeBusRouteIndex) return; // Prevent redundant clicks
    activeBusRouteIndex = selectedIndex;
    
    // Clear previous ETA polling
    if (busEtaInterval) {
        clearInterval(busEtaInterval);
        busEtaInterval = null;
    }

    // Update sidebar UI
    document.querySelectorAll('.bus-route-item').forEach((el, idx) => {
        const stopsList = document.getElementById(`bus-stops-list-${idx}`);
        if (idx === selectedIndex) {
            el.classList.add('active');
            stopsList.classList.add('expanded');
        } else {
            el.classList.remove('active');
            stopsList.classList.remove('expanded');
        }
    });
    
    // Update map
    if (!busLayer) return;
    busLayer.clearLayers();
    
    if (busLiveIconsLayer) {
        map.removeLayer(busLiveIconsLayer);
    }
    busLiveIconsLayer = L.layerGroup().addTo(map);
    
    const routeInfo = busData[selectedIndex];
    if (!routeInfo) return;
    
    const stops = routeInfo.stops || [];
    if (stops.length < 2) return;
    
    const color = getColorForRoute(selectedIndex);
    const coords = stops.map(s => [parseFloat(s.lat), parseFloat(s.long)]);
    
    // Draw line
    const polyline = L.polyline(coords, {
        color: color,
        weight: 5,
        opacity: 0.8
    });
    polyline.bindTooltip(`<b>Route: ${routeInfo.route}</b> (${routeInfo.bound})`);
    busLayer.addLayer(polyline);
    
    // Dictionary to hold marker references by sequence string
    const stopMarkers = {};
    
    // Draw stops
    stops.forEach((stop, index) => {
        const marker = L.circleMarker([parseFloat(stop.lat), parseFloat(stop.long)], {
            radius: 5,
            fillColor: "#ffffff",
            color: color,
            weight: 2,
            opacity: 1,
            fillOpacity: 0.9
        });
        
        // Initial Tooltip
        marker.bindTooltip(`<b>${index + 1}. ${stop.name_tc || stop.name_en}</b><br/><i>Fetching ETA...</i>`);
        busLayer.addLayer(marker);
        stopMarkers[stop.seq] = {
            marker: marker,
            name: stop.name_tc || stop.name_en,
            index: index + 1,
            lat: parseFloat(stop.lat),
            long: parseFloat(stop.long)
        };
    });
    
    // Fit map to route bounds
    if (map && polyline) {
        map.fitBounds(polyline.getBounds(), { padding: [50, 50] });
    }

    // Fetch ETA immediately and then every 30s
    fetchAndDisplayETA(routeInfo, stopMarkers);
    busEtaInterval = setInterval(() => fetchAndDisplayETA(routeInfo, stopMarkers), 30000);
}

async function fetchAndDisplayETA(routeInfo, stopMarkers) {
    if (!routeInfo || !routeInfo.route) return;
    
    try {
        const res = await fetch(`/bus/eta/${routeInfo.route}`);
        if (!res.ok) throw new Error("ETA fetch failed");
        
        const data = await res.json();
        if (!data || !data.data) return;
        
        // Filter ETA data for current bound ('I' -> 'I' or 'O' -> 'O')
        // In KMB API, dir is 'I' or 'O'
        const dirFilter = routeInfo.bound;
        
        // Group ETAs by stop sequence
        const etaBySeq = {};
        data.data.forEach(item => {
            if (item.dir === dirFilter && item.eta) {
                const seq = String(item.seq);
                if (!etaBySeq[seq]) etaBySeq[seq] = [];
                etaBySeq[seq].push(item.eta);
            }
        });
        
        // Update map tooltips and sidebar list
        const activeIdx = busData.indexOf(routeInfo);
        const stopsListEl = document.getElementById(`bus-stops-list-${activeIdx}`);
        const listItems = stopsListEl ? stopsListEl.querySelectorAll('li') : [];

        if (busLiveIconsLayer) busLiveIconsLayer.clearLayers();

        // We will keep track of buses to draw them on the map.
        // A bus is considered to be between Stop N-1 and Stop N if Stop N has an ETA.
        // We use a simple heuristic to place the bus marker slightly before Stop N based on the ETA.
        // NOTE: Bus icons on the road are removed as requested to avoid useless static icons
        // if the route isn't drawn properly or if it lacks interaction.
        
        for (const [seq, info] of Object.entries(stopMarkers)) {
            const etas = etaBySeq[seq] || [];
            let etaText = "No ETA available";
            let shortEtaText = "";
            
            if (etas.length > 0) {
                // Sort by time
                etas.sort();
                const now = new Date();

                const minutesList = etas.map(etaStr => {
                    const etaTime = new Date(etaStr);
                    const dMs = etaTime - now;
                    const dMins = Math.max(0, Math.floor(dMs / 60000));
                    return dMins === 0 ? "Arriving" : `${dMins} min`;
                });
                
                etaText = `<b>Next buses:</b><br/>${minutesList.join('<br/>')}`;
                shortEtaText = ` <span style="color: #d9534f; font-weight: bold;">[${minutesList[0]}]</span>`;
                
                // Animate marker if arriving soon
                if (minutesList[0] === "Arriving" || minutesList[0] === "1 min") {
                    info.marker.setStyle({ fillColor: '#ffeb3b', radius: 7 });
                    if (info.marker._path) info.marker._path.classList.add('blinking-marker');
                } else {
                    info.marker.setStyle({ fillColor: '#ffffff', radius: 5 });
                    if (info.marker._path) info.marker._path.classList.remove('blinking-marker');
                }
            }
            
            // Update Tooltip
            info.marker.setTooltipContent(`<b>${info.index}. ${info.name}</b><br/>${etaText}`);
            
            // Update Sidebar List item
            if (listItems[info.index - 1]) {
                listItems[info.index - 1].innerHTML = `${info.name}${shortEtaText}`;
            }
        }
        
    } catch (err) {
        console.error("ETA Polling Error:", err);
    }
}

function getColorForRoute(index) {
    const colors = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe"];
    return colors[index % colors.length];
}

// --- System Switching ---

function switchSystem(sys) {
    currentSystem = sys;
    
    // Update Buttons
    document.getElementById('btn-road').classList.toggle('active', sys === 'road');
    document.getElementById('btn-mtr').classList.toggle('active', sys === 'mtr');
    document.getElementById('btn-bus').classList.toggle('active', sys === 'bus');
    
    // Update Title
    if (sys === 'road') document.getElementById('dashboard-title').innerText = 'HK Road Traffic';
    else if (sys === 'mtr') document.getElementById('dashboard-title').innerText = 'MTR Delay System';
    else if (sys === 'bus') document.getElementById('dashboard-title').innerText = 'Bus Network System';
    
    const mapEl = document.getElementById('map');
    const schematicEl = document.getElementById('mtr-schematic-container');
    
    // Clean up bus polling if switching away
    if (sys !== 'bus') {
        if (busEtaInterval) {
            clearInterval(busEtaInterval);
            busEtaInterval = null;
        }
        if (busLiveIconsLayer && map.hasLayer(busLiveIconsLayer)) {
            map.removeLayer(busLiveIconsLayer);
        }
    }
    
    // Toggle Map Layers
    if (sys === 'road') {
        if (map.hasLayer(mtrLayer)) map.removeLayer(mtrLayer);
        if (map.hasLayer(busLayer)) map.removeLayer(busLayer);
        if (!map.hasLayer(roadLayer)) roadLayer.addTo(map);
        
        mapEl.style.display = 'block';
        if (schematicEl) schematicEl.style.display = 'none';
        
        buildRoadLegend();
        document.getElementById('events-panel').style.display = 'none';
        document.getElementById('details-panel').style.display = 'block';
        document.getElementById('bus-list-panel').style.display = 'none';
        refreshRoadPredictions(true);
    } else if (sys === 'mtr') {
        if (map.hasLayer(roadLayer)) map.removeLayer(roadLayer);
        if (map.hasLayer(busLayer)) map.removeLayer(busLayer);
        
        // MTR has two views, let's use schematic by default if available
        if (schematicEl && window.MTREmbedMonitor) {
            currentMTRView = 'schematic';
            mapEl.style.display = 'none';
            schematicEl.style.display = 'block';
            if (map.hasLayer(mtrLayer)) map.removeLayer(mtrLayer);
        } else {
            currentMTRView = 'network';
            mapEl.style.display = 'block';
            if (schematicEl) schematicEl.style.display = 'none';
            if (!map.hasLayer(mtrLayer)) mtrLayer.addTo(map);
        }
        
        buildMTRLegend();
        document.getElementById('events-panel').style.display = 'flex';
        document.getElementById('details-panel').style.display = 'block';
        document.getElementById('bus-list-panel').style.display = 'none';
        refreshMTRPredictions(true);
    } else if (sys === 'bus') {
        if (map.hasLayer(roadLayer)) map.removeLayer(roadLayer);
        if (map.hasLayer(mtrLayer)) map.removeLayer(mtrLayer);
        
        mapEl.style.display = 'block';
        if (schematicEl) schematicEl.style.display = 'none';
        
        if (!map.hasLayer(busLayer)) busLayer.addTo(map);
        if (busLiveIconsLayer && !map.hasLayer(busLiveIconsLayer)) busLiveIconsLayer.addTo(map);
        
        buildBusLegend();
        document.getElementById('events-panel').style.display = 'none';
        document.getElementById('details-panel').style.display = 'none';
        document.getElementById('bus-list-panel').style.display = 'flex';
        
        // Reset activeBusRouteIndex to force a full redraw when switching back
        activeBusRouteIndex = -1;
        refreshBusPredictions(true);
    }
    
    // Reset Details Panel
    resetDetailsPanel();
    setTimeout(() => map.invalidateSize(), 60);
}

function resetDetailsPanel() {
    document.getElementById('details-placeholder').style.display = 'block';
    document.getElementById('segment-info').style.display = 'none';
    document.getElementById('mtr-info').style.display = 'none';
    
    // Reset highlights
    if (roadLayer) roadLayer.resetStyle();
    if (mtrLayer) mtrLayer.resetStyle();
}

function buildRoadLegend() {
    const panel = document.getElementById('legend-panel');
    panel.innerHTML = `
        <h3>Congestion Prediction</h3>
        <div class="legend-item"><span class="color-box" style="background-color: #28a745;"></span> Clear (0 min)</div>
        <div class="legend-item"><span class="color-box" style="background-color: #ffc107;"></span> Slow (< 5 mins)</div>
        <div class="legend-item"><span class="color-box" style="background-color: #fd7e14;"></span> Congested (5-20 mins)</div>
        <div class="legend-item"><span class="color-box" style="background-color: #dc3545;"></span> Heavy (> 20 mins)</div>
        <div class="legend-item"><span class="color-box" style="background-color: #6c757d;"></span> No Data</div>
    `;
}

function buildMTRLegend() {
    const panel = document.getElementById('legend-panel');
    panel.innerHTML = `
        <h3>Delay Risk Status</h3>
        <div class="legend-item"><span class="color-circle" style="background-color: #28a745;"></span> Normal Operation</div>
        <div class="legend-item"><span class="color-circle" style="background-color: #ffc107;"></span> Minor Delay Risk</div>
        <div class="legend-item"><span class="color-circle" style="background-color: #dc3545; animation: blink 1.5s infinite;"></span> Severe Delay (Active)</div>
    `;
}

function buildBusLegend() {
    const panel = document.getElementById('legend-panel');
    panel.innerHTML = `
        <h3>Bus Routes</h3>
        <div class="legend-item"><span class="color-box" style="background-color: #007bff;"></span> KMB Routes</div>
        <p style="font-size: 12px; color: #666; margin-top: 5px;">Routes are generated via PySpark by joining route list and physical stops coordinates.</p>
    `;
}

// --- Road Styling & Interaction ---

function styleRoadFeature(feature) {
    const segId = feature.properties.segment_id;
    const pred = predictionData[segId];
    
    let color = '#6c757d'; 
    let weight = 2;
    let opacity = 0.6;
    
    if (pred !== undefined) {
        const [greenT, yellowT, orangeT] = mapConfig.color_thresholds || [0, 5, 20];
        if (pred <= greenT) { color = '#28a745'; weight = 3; opacity = 0.8; }
        else if (pred <= yellowT) { color = '#ffc107'; weight = 4; opacity = 0.9; }
        else if (pred <= orangeT) { color = '#fd7e14'; weight = 5; opacity = 1.0; }
        else { color = '#dc3545'; weight = 6; opacity = 1.0; }
    }
    
    return { color, weight, opacity };
}

function onEachRoadFeature(feature, layer) {
    const segId = feature.properties.segment_id;
    const street = feature.properties.STREET_ENAME || 'Unknown Street';
    
    layer.bindTooltip(() => {
        const pred = predictionData[segId];
        const predText = pred !== undefined ? `${pred} mins` : 'No data';
        return `<b>${street}</b><br/>Congestion: ${predText}`;
    }, { sticky: true });
    
    layer.on('click', () => {
        resetDetailsPanel();
        document.getElementById('details-placeholder').style.display = 'none';
        document.getElementById('segment-info').style.display = 'block';
        
        document.getElementById('seg-id').innerText = segId;
        document.getElementById('seg-street').innerText = street;
        
        const pred = predictionData[segId];
        document.getElementById('seg-pred').innerText = pred !== undefined ? pred : 'N/A';
        
        layer.setStyle({ weight: 8, color: '#007bff', opacity: 1 });
        layer.bringToFront();
    });
}

// --- MTR Styling & Interaction ---

function styleMTRFeature(feature) {
    // Default line style
    if (feature.geometry.type !== 'Point') {
        return { color: feature.properties.color || '#6c757d', weight: 4, opacity: 0.7 };
    }
    // Marker styles handled in pointToLayer / applyMTRMarkerStyle
    return {};
}

function applyMTRMarkerStyle(layer) {
    const props = layer.feature.properties;
    const key = `${props.line}-${props.sta}`;
    const pred = mtrPredictionData[key];
    
    let fillColor = "#28a745"; // Green
    let className = "";
    let radius = 6;
    
    if (pred) {
        if (pred.color_code === "red") {
            fillColor = "#dc3545";
            className = "blinking-marker";
            radius = 8;
        } else if (pred.color_code === "yellow") {
            fillColor = "#ffc107";
            radius = 7;
        }
    }
    
    layer.setStyle({ fillColor, radius });
    
    if (layer._path) {
        if (className) layer._path.classList.add(className);
        else layer._path.classList.remove('blinking-marker');
    }
}

function onEachMTRFeature(feature, layer) {
    if (feature.geometry.type !== 'Point') return;
    
    const line = feature.properties.line;
    const sta = feature.properties.sta;
    const name = feature.properties.name || `${line}-${sta}`;
    const key = `${line}-${sta}`;
    
    layer.bindTooltip(() => {
        const pred = mtrPredictionData[key];
        if (!pred) return `<b>${name}</b><br/>No data`;
        return `<b>${name}</b><br/>
                Next Train (UP): ${pred.up_ttnt !== undefined ? pred.up_ttnt : '?'} mins<br/>
                Next Train (DOWN): ${pred.down_ttnt !== undefined ? pred.down_ttnt : '?'} mins<br/>
                Risk: ${(pred.delay_risk_probability * 100).toFixed(1)}%`;
    }, { sticky: true });
    
    layer.on('click', () => {
        resetDetailsPanel();
        document.getElementById('details-placeholder').style.display = 'none';
        document.getElementById('mtr-info').style.display = 'block';
        
        document.getElementById('mtr-line').innerText = line;
        document.getElementById('mtr-sta').innerText = sta;
        
        const pred = mtrPredictionData[key];
        if (pred) {
            document.getElementById('mtr-up').innerText = pred.up_ttnt !== undefined ? pred.up_ttnt : 'N/A';
            document.getElementById('mtr-down').innerText = pred.down_ttnt !== undefined ? pred.down_ttnt : 'N/A';
            document.getElementById('mtr-risk').innerText = `${(pred.delay_risk_probability * 100).toFixed(1)}%`;
            document.getElementById('mtr-duration').innerText = pred.delay_duration_minutes;
            document.getElementById('mtr-affected').innerText = pred.affected_trains_count;
        } else {
            document.getElementById('mtr-up').innerText = 'N/A';
            document.getElementById('mtr-down').innerText = 'N/A';
            document.getElementById('mtr-risk').innerText = 'N/A';
            document.getElementById('mtr-duration').innerText = 'N/A';
            document.getElementById('mtr-affected').innerText = 'N/A';
        }
    });
}

function updateMTREventsPanel() {
    const listEl = document.getElementById('events-list');
    const summaryEl = document.getElementById('events-summary');
    listEl.innerHTML = '';
    
    let activeEvents = [];
    for (const [key, pred] of Object.entries(mtrPredictionData)) {
        if (pred.color_code === "red" || pred.color_code === "yellow") {
            activeEvents.push({ key, ...pred });
        }
    }
    
    if (activeEvents.length === 0) {
        summaryEl.innerText = "No active delays detected across the network.";
        summaryEl.style.color = "#28a745";
        return;
    }
    
    summaryEl.innerText = `Detected ${activeEvents.length} delayed station(s).`;
    summaryEl.style.color = "#dc3545";
    
    activeEvents.sort((a, b) => b.delay_risk_probability - a.delay_risk_probability);
    
    activeEvents.forEach(evt => {
        const li = document.createElement('li');
        const icon = evt.color_code === "red" ? "🔴" : "🟡";
        li.innerHTML = `
            <div class="event-title">${icon} ${evt.key}</div>
            <p class="event-desc">Risk: ${(evt.delay_risk_probability * 100).toFixed(1)}% | Est. ${evt.delay_duration_minutes}m</p>
            <p class="event-desc">Affects ~${evt.affected_trains_count} trains</p>
        `;
        // Click on list item to simulate click on map
        li.addEventListener('click', () => {
            if (mtrLayer) {
                mtrLayer.eachLayer(layer => {
                    if (layer.feature && layer.feature.geometry.type === 'Point' && 
                        `${layer.feature.properties.line}-${layer.feature.properties.sta}` === evt.key) {
                        map.setView(layer.getLatLng(), 15);
                        layer.fire('click');
                    }
                });
            }
        });
        listEl.appendChild(li);
    });
}

// --- UI Helpers ---

function updateRefreshBtn(isRefreshing) {
    const btn = document.getElementById('refresh-btn');
    btn.disabled = isRefreshing;
    btn.innerText = isRefreshing ? "Checking..." : "Refresh Now";
}

function updateLastUpdateText(timeStr, isCached) {
    const displayTime = timeStr || new Date().toLocaleTimeString();
    const prefix = isCached ? "Checked at" : "Data generated at";
    const cacheNote = isCached ? ` (Data from ${displayTime})` : "";
    const now = isCached ? new Date().toLocaleTimeString() : displayTime;
    
    document.getElementById('last-update').innerText = `${prefix}: ${now}${cacheNote}`;
}

// Start app
document.addEventListener('DOMContentLoaded', init);