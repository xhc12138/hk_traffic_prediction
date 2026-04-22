// Global Variables
let map;
let roadLayer;
let mtrLayer;
let geojsonData = null;
let mtrGeojsonData = null;

let predictionData = {};
let mtrPredictionData = {};

let mapConfig = {};
let lastBackendUpdateTime = "";
let lastMtrUpdateTime = "";

// System State
let currentSystem = 'road'; // 'road' or 'mtr'

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
        await Promise.all([loadRoadNetwork(), loadMTRNetwork()]);

        // 4. Setup Event Listeners
        document.getElementById('refresh-btn').addEventListener('click', forceRefresh);
        document.getElementById('btn-road').addEventListener('click', () => switchSystem('road'));
        document.getElementById('btn-mtr').addEventListener('click', () => switchSystem('mtr'));
        if (window.MTREmbedMonitor) {
            await window.MTREmbedMonitor.init();
        }

        // 5. Initial System Setup
        switchSystem('road');

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

// --- Refresh Logic ---

async function forceRefresh() {
    if (currentSystem === 'road') {
        await refreshRoadPredictions(true);
    } else {
        await refreshMTRPredictions(true);
    }
}

async function autoRefresh() {
    if (currentSystem === 'road') {
        await refreshRoadPredictions(false);
    } else {
        await refreshMTRPredictions(false);
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
        if (window.MTREmbedMonitor) {
            window.MTREmbedMonitor.setPredictions(mtrPredictionData);
        }
        
        if (mtrLayer && currentSystem === 'mtr') {
            // Need to recreate style to apply blinking animations to DOM elements
            mtrLayer.setStyle(styleMTRFeature);
            mtrLayer.eachLayer(layer => {
                if (layer.feature && layer.feature.geometry.type === 'Point') {
                    applyMTRMarkerStyle(layer);
                }
            });
        }
        updateLastUpdateText(lastMtrUpdateTime, false);
        updateMTREventsPanel();
    } catch (err) {
        console.error("MTR Prediction Error:", err);
    } finally {
        if (force) updateRefreshBtn(false);
    }
}

// --- System Switching ---

function switchSystem(sys) {
    currentSystem = sys;
    
    // Update Buttons
    document.getElementById('btn-road').classList.toggle('active', sys === 'road');
    document.getElementById('btn-mtr').classList.toggle('active', sys === 'mtr');
    
    // Update Title
    document.getElementById('dashboard-title').innerText = sys === 'road' ? 'HK Road Traffic' : 'MTR Delay System';
    const mapEl = document.getElementById('map');
    const schematicEl = document.getElementById('mtr-schematic-container');
    
    // Toggle Map Layers
    if (sys === 'road') {
        mapEl.style.display = 'block';
        schematicEl.style.display = 'none';
        if (map.hasLayer(mtrLayer)) map.removeLayer(mtrLayer);
        if (!map.hasLayer(roadLayer)) roadLayer.addTo(map);
        buildRoadLegend();
        document.getElementById('events-panel').style.display = 'none';
        refreshRoadPredictions(true);
    } else {
        mapEl.style.display = 'none';
        schematicEl.style.display = 'block';
        if (map.hasLayer(roadLayer)) map.removeLayer(roadLayer);
        if (map.hasLayer(mtrLayer)) map.removeLayer(mtrLayer);
        buildMTRLegend();
        document.getElementById('events-panel').style.display = 'flex';
        refreshMTRPredictions(true);
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