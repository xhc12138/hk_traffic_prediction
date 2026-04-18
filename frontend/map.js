// Global Variables
let map;
let roadLayer;
let geojsonData = null;
let predictionData = {};
let mapConfig = {};
let lastBackendUpdateTime = "";

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
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 20
        }).addTo(map);

        // 3. Fetch GeoJSON Network
        await loadRoadNetwork();

        // 4. Fetch Initial Predictions
        await refreshPredictions();

        // 5. Setup Refresh Button
        document.getElementById('refresh-btn').addEventListener('click', refreshPredictions);

        // 6. Auto-refresh every 30 seconds
        setInterval(refreshPredictions, 30000);

    } catch (err) {
        console.error("Initialization Error:", err);
        alert("Failed to load map data. See console for details.");
    }
}

// Load Road Network
async function loadRoadNetwork() {
    console.log("Loading road network...");
    const res = await fetch('/road_network');
    if (!res.ok) throw new Error("Failed to fetch road network");
    geojsonData = await res.json();
    
    // Add to map
    roadLayer = L.geoJSON(geojsonData, {
        style: styleFeature,
        onEachFeature: onEachFeature
    }).addTo(map);
    
    // Fit bounds to network
    map.fitBounds(roadLayer.getBounds());
}

// Fetch Predictions
async function refreshPredictions() {
    console.log("Checking for new predictions...");
    const btn = document.getElementById('refresh-btn');
    btn.disabled = true;
    btn.innerText = "Checking...";
    
    try {
        const endpoint = mapConfig.prediction_api_endpoint || '/predictions';
        const res = await fetch(endpoint);
        if (!res.ok) throw new Error("Failed to fetch predictions");
        
        const data = await res.json();
        
        // Check if the backend data is actually newer
        if (data.last_update && data.last_update === lastBackendUpdateTime) {
            console.log("No new data from backend yet.");
            // Even if no new data, update the "last checked" UI locally
            document.getElementById('last-update').innerText = `Checked at ${new Date().toLocaleTimeString()} (Data from ${lastBackendUpdateTime})`;
            return;
        }
        
        console.log("New data received! Updating map...");
        predictionData = data.predictions || {};
        lastBackendUpdateTime = data.last_update || "";
        
        // Update map styling
        if (roadLayer) {
            roadLayer.setStyle(styleFeature);
        }
        
        // Update UI with the actual generation time of the data
        const displayTime = lastBackendUpdateTime ? lastBackendUpdateTime : new Date().toLocaleTimeString();
        document.getElementById('last-update').innerText = `Data generated at: ${displayTime}`;
    } catch (err) {
        console.error("Prediction Error:", err);
    } finally {
        btn.disabled = false;
        btn.innerText = "Refresh Now";
    }
}

// Feature Styling
function styleFeature(feature) {
    const segId = feature.properties.segment_id;
    const pred = predictionData[segId];
    
    let color = '#6c757d'; // Gray for no data
    let weight = 2;
    let opacity = 0.6;
    
    if (pred !== undefined) {
        const [greenT, yellowT, orangeT] = mapConfig.color_thresholds || [0, 5, 20];
        
        if (pred <= greenT) {
            color = '#28a745'; // Green
            weight = 3;
            opacity = 0.8;
        } else if (pred <= yellowT) {
            color = '#ffc107'; // Yellow
            weight = 4;
            opacity = 0.9;
        } else if (pred <= orangeT) {
            color = '#fd7e14'; // Orange
            weight = 5;
            opacity = 1.0;
        } else {
            color = '#dc3545'; // Red
            weight = 6;
            opacity = 1.0;
        }
    }
    
    return {
        color: color,
        weight: weight,
        opacity: opacity
    };
}

// Feature Interaction
function onEachFeature(feature, layer) {
    const segId = feature.properties.segment_id;
    const street = feature.properties.STREET_ENAME || 'Unknown Street';
    
    // Add tooltip
    layer.bindTooltip(() => {
        const pred = predictionData[segId];
        const predText = pred !== undefined ? `${pred} mins` : 'No data';
        return `<b>${street}</b><br/>Congestion: ${predText}`;
    }, { sticky: true });
    
    // Click event to update details panel
    layer.on('click', () => {
        document.querySelector('.placeholder-text').style.display = 'none';
        document.getElementById('segment-info').style.display = 'block';
        
        document.getElementById('seg-id').innerText = segId;
        document.getElementById('seg-street').innerText = street;
        
        const pred = predictionData[segId];
        document.getElementById('seg-pred').innerText = pred !== undefined ? pred : 'N/A';
        
        // Highlight clicked layer
        if (roadLayer) {
            roadLayer.resetStyle();
        }
        layer.setStyle({
            weight: 8,
            color: '#007bff',
            opacity: 1
        });
        layer.bringToFront();
    });
}

// Start app
document.addEventListener('DOMContentLoaded', init);