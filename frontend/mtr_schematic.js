const SVG_NS = "http://www.w3.org/2000/svg";
const TOPOLOGY_URL = "/frontend/assets/mtr_topology.json";
const PREDICTION_URL = "/mtr/delay-prediction";
const REFRESH_INTERVAL_MS = 15000;

const state = {
    topology: null,
    predictions: {},
    estimatedTrains: [],
    nodeMap: new Map(),
    trainMap: new Map(),
    selectedKey: null,
    lastUpdate: "",
    zoom: {
        scale: 1,
        tx: 0,
        ty: 0,
        minScale: 0.5,
        maxScale: 8,
        isPanning: false,
    },
    viewportLayer: null,
    mapLayer: null,
    pathLayer: null,
    stationLayer: null,
    trainLayer: null,
    pathElements: [],
    lineStrokeByCode: new Map(),
    viewMode: "network",
    selectedLineCode: null,
    selectedDirection: "forward",
    stationMetaByCode: new Map(),
};

const dom = {
    svg: document.getElementById("schematic-svg"),
    canvasPanel: document.getElementById("canvas-panel"),
    refreshBtn: document.getElementById("refresh-btn"),
    lastUpdate: document.getElementById("last-update"),
    detailsPlaceholder: document.getElementById("details-placeholder"),
    stationDetails: document.getElementById("station-details"),
    detailLine: document.getElementById("detail-line"),
    detailStation: document.getElementById("detail-station"),
    detailUp: document.getElementById("detail-up"),
    detailDown: document.getElementById("detail-down"),
    detailRisk: document.getElementById("detail-risk"),
    detailDuration: document.getElementById("detail-duration"),
    detailAffected: document.getElementById("detail-affected"),
    detailTransfers: document.getElementById("detail-transfers"),
    detailTrains: document.getElementById("detail-trains"),
    eventsSummary: document.getElementById("events-summary"),
    eventsList: document.getElementById("events-list"),
    hoverCard: document.getElementById("hover-card"),
    stationPopup: document.getElementById("station-popup"),
    networkLineLegend: document.getElementById("network-line-legend"),
    lineBackBtn: document.getElementById("line-back-btn"),
    lineModeHeader: document.getElementById("line-mode-header"),
    lineModeTitle: document.getElementById("line-mode-title"),
    lineModeSubtitle: document.getElementById("line-mode-subtitle"),
    lineDirectionToggle: document.getElementById("line-direction-toggle"),
    directionForwardBtn: document.getElementById("direction-forward-btn"),
    directionReverseBtn: document.getElementById("direction-reverse-btn"),
};


async function init() {
    dom.refreshBtn.addEventListener("click", () => refreshData(true));
    dom.lineBackBtn.addEventListener("click", () => returnToNetworkView());
    dom.directionForwardBtn.addEventListener("click", () => switchLineDirection("forward"));
    dom.directionReverseBtn.addEventListener("click", () => switchLineDirection("reverse"));
    state.topology = await fetchJson(TOPOLOGY_URL);
    state.topology.stations.forEach((station) => {
        state.stationMetaByCode.set(station.code, station);
    });
    renderNetworkLegend();
    renderSchematic();
    await refreshData(true);
    setInterval(() => refreshData(false), REFRESH_INTERVAL_MS);
}


async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch ${url}`);
    }
    return response.json();
}


function renderSchematic() {
    const isLineMode = state.viewMode === "line";
    const currentLine = getCurrentLine();
    const lineLayoutNodes = isLineMode && currentLine ? buildLineLayoutNodes(currentLine) : [];
    const viewBox = isLineMode ? { minX: 0, minY: 0, width: 1200, height: 760 } : state.topology.meta.viewBox;
    const { minX, minY, width, height } = viewBox;
    dom.svg.setAttribute("viewBox", `${minX} ${minY} ${width} ${height}`);
    dom.svg.innerHTML = "";
    state.nodeMap.clear();
    state.trainMap.clear();
    state.pathElements = [];
    state.lineStrokeByCode.clear();

    const viewportLayer = document.createElementNS(SVG_NS, "g");
    const mapLayer = document.createElementNS(SVG_NS, "g");
    const pathLayer = document.createElementNS(SVG_NS, "g");
    const stationLayer = document.createElementNS(SVG_NS, "g");
    const trainLayer = document.createElementNS(SVG_NS, "g");
    viewportLayer.setAttribute("id", "viewport-layer");
    mapLayer.setAttribute("id", "map-layer");
    pathLayer.setAttribute("id", "path-layer");
    stationLayer.setAttribute("id", "station-layer");
    trainLayer.setAttribute("id", "train-layer");

    if (!isLineMode) {
        (state.topology.background_paths || []).forEach((shapeDef) => {
            const shape = document.createElementNS(SVG_NS, "path");
            shape.setAttribute("class", "map-shape");
            shape.setAttribute("d", shapeDef.path);
            shape.setAttribute("fill", shapeDef.fill || "#1e293b");
            shape.setAttribute("fill-opacity", `${shapeDef.opacity ?? 0.3}`);
            mapLayer.appendChild(shape);
        });
    }

    const pathsToRender = isLineMode && currentLine
        ? [{ line: currentLine.code, color: currentLine.color, stroke_width: 6, path: buildSmoothLinePath(lineLayoutNodes) }]
        : state.topology.paths;
    pathsToRender.forEach((pathDef) => {
        const path = document.createElementNS(SVG_NS, "path");
        path.setAttribute("class", "line-path");
        path.setAttribute("d", pathDef.path);
        path.setAttribute("stroke", pathDef.color);
        const baseStroke = (Number(pathDef.stroke_width) || 6) * 1.35;
        path.setAttribute("stroke-width", `${baseStroke}`);
        path.setAttribute("data-base-stroke", `${baseStroke}`);
        path.setAttribute("data-line-code", pathDef.line || "");
        pathLayer.appendChild(path);
        state.pathElements.push(path);
        const current = state.lineStrokeByCode.get(pathDef.line);
        if (!current || baseStroke > current) {
            state.lineStrokeByCode.set(pathDef.line, baseStroke);
        }
    });

    const nodesToRender = isLineMode && currentLine ? lineLayoutNodes : state.topology.line_station_nodes;
    nodesToRender.forEach((node) => {
        const group = document.createElementNS(SVG_NS, "g");
        group.setAttribute("class", "station-node");
        group.setAttribute("data-key", node.id);
        group.setAttribute("transform", `translate(${node.x}, ${node.y})`);

        const circle = document.createElementNS(SVG_NS, "circle");
        circle.setAttribute("class", "station-circle");
        const lineStroke = state.lineStrokeByCode.get(node.line) || 6;
        const baseRadius = node.is_interchange
            ? Math.max(5.0, lineStroke * 0.95)
            : Math.max(4.1, lineStroke * 0.72);
        circle.setAttribute("r", `${baseRadius}`);
        circle.setAttribute("fill", "#22c55e");
        circle.setAttribute("stroke", node.color);

        const label = document.createElementNS(SVG_NS, "text");
        label.setAttribute("class", "station-label");
        label.setAttribute("text-anchor", "middle");
        label.setAttribute("y", "-7.8");
        label.style.fontSize = "9.4px";
        label.textContent = node.station_code;

        group.appendChild(circle);
        group.appendChild(label);
        stationLayer.appendChild(group);

        group.addEventListener("click", () => selectStation(node.id));
        group.addEventListener("mousemove", () => showHoverCard(node));
        group.addEventListener("mouseleave", hideHoverCard);

        state.nodeMap.set(node.id, { node, element: group, circle, label });
    });

    viewportLayer.appendChild(mapLayer);
    viewportLayer.appendChild(pathLayer);
    if (isLineMode) {
        viewportLayer.appendChild(stationLayer);
        viewportLayer.appendChild(trainLayer);
    } else {
        viewportLayer.appendChild(trainLayer);
        viewportLayer.appendChild(stationLayer);
    }
    dom.svg.appendChild(viewportLayer);

    state.viewportLayer = viewportLayer;
    state.mapLayer = mapLayer;
    state.pathLayer = pathLayer;
    state.stationLayer = stationLayer;
    state.trainLayer = trainLayer;
    state.zoom.scale = 1;
    state.zoom.tx = 0;
    state.zoom.ty = 0;
    applyViewportTransform();
    bindPanAndZoom();
    updateModeOverlays();

    dom.svg.onclick = (event) => {
        if (event.target.closest(".station-node")) {
            return;
        }
        dom.stationPopup.classList.add("hidden");
    };
}


function renderNetworkLegend() {
    dom.networkLineLegend.innerHTML = "";
    state.topology.lines.forEach((line) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "network-line-item";
        button.dataset.lineCode = line.code;
        button.innerHTML = `
            <span class="network-line-title">
                <span class="line-chip" style="background:${line.color}"></span>${line.name}
            </span>
        `;
        button.addEventListener("click", () => enterLineView(line.code));
        dom.networkLineLegend.appendChild(button);
    });
}


function updateModeOverlays() {
    const isLineMode = state.viewMode === "line";
    dom.networkLineLegend.classList.toggle("hidden", isLineMode);
    dom.lineBackBtn.classList.toggle("hidden", !isLineMode);
    dom.lineModeHeader.classList.toggle("hidden", !isLineMode);
    dom.lineDirectionToggle.classList.toggle("hidden", !isLineMode);
    updateLineModeHeader();
    updateDirectionToggle();
}


function updateLineModeHeader() {
    const currentLine = getCurrentLine();
    if (!currentLine || state.viewMode !== "line") {
        dom.lineModeTitle.textContent = "";
        dom.lineModeSubtitle.textContent = "";
        return;
    }
    const forwardDestination = getStationName(currentLine.stations[currentLine.stations.length - 1]);
    const reverseDestination = getStationName(currentLine.stations[0]);
    const directionDestination = state.selectedDirection === "forward" ? forwardDestination : reverseDestination;
    dom.lineModeTitle.textContent = `${currentLine.name}`;
    dom.lineModeSubtitle.textContent = `Towards ${directionDestination}`;
}


function updateDirectionToggle() {
    const currentLine = getCurrentLine();
    if (!currentLine || state.viewMode !== "line") {
        return;
    }
    const forwardDestination = getStationName(currentLine.stations[currentLine.stations.length - 1]);
    const reverseDestination = getStationName(currentLine.stations[0]);
    dom.directionForwardBtn.textContent = `To ${forwardDestination}`;
    dom.directionReverseBtn.textContent = `To ${reverseDestination}`;
    dom.directionForwardBtn.classList.toggle("active", state.selectedDirection === "forward");
    dom.directionReverseBtn.classList.toggle("active", state.selectedDirection === "reverse");
}


function getCurrentLine() {
    if (!state.selectedLineCode) {
        return null;
    }
    return state.topology.lines.find((line) => line.code === state.selectedLineCode) || null;
}


function getStationName(stationCode) {
    return state.stationMetaByCode.get(stationCode)?.name || stationCode;
}


function enterLineView(lineCode) {
    state.viewMode = "line";
    state.selectedLineCode = lineCode;
    state.selectedDirection = "forward";
    state.selectedKey = null;
    dom.stationPopup.classList.add("hidden");
    renderSchematic();
    updateStationStyles();
    state.estimatedTrains = estimateTrainsForCurrentView();
    updateTrainLayer();
}


function returnToNetworkView() {
    state.viewMode = "network";
    state.selectedLineCode = null;
    state.selectedDirection = "forward";
    state.selectedKey = null;
    dom.stationPopup.classList.add("hidden");
    renderSchematic();
    updateStationStyles();
    state.estimatedTrains = estimateTrainsForCurrentView();
    updateTrainLayer();
}


function switchLineDirection(direction) {
    if (state.viewMode !== "line" || (direction !== "forward" && direction !== "reverse")) {
        return;
    }
    state.selectedDirection = direction;
    updateLineModeHeader();
    updateDirectionToggle();
    clearTrainLayerImmediately();
    state.estimatedTrains = estimateTrainsForCurrentView();
    updateTrainLayer();
    if (state.selectedKey) {
        selectStation(state.selectedKey);
    }
}


function buildLineLayoutNodes(line) {
    const stationCodes = line.stations;
    const count = stationCodes.length;
    if (!count) {
        return [];
    }
    const left = 120;
    const right = 1080;
    const centerY = 380;
    const amplitude = clamp(70 + count * 7.5, 110, 220);
    const span = Math.max(1, count - 1);

    return stationCodes.map((code, index) => {
        const ratio = index / span;
        const x = left + (right - left) * ratio;
        const y = centerY + amplitude * Math.sin(Math.PI * 2 * ratio);
        const stationMeta = state.stationMetaByCode.get(code);
        return {
            id: `${line.code}-${code}`,
            line: line.code,
            station_code: code,
            station_name: stationMeta?.name || code,
            x,
            y,
            x_real: x,
            y_real: y,
            color: line.color,
            is_interchange: Boolean(stationMeta?.is_interchange),
            transfer_lines: stationMeta?.lines || [line.code],
        };
    });
}


function buildSmoothLinePath(nodes) {
    if (!nodes.length) {
        return "";
    }
    if (nodes.length === 1) {
        return `M${nodes[0].x.toFixed(3)},${nodes[0].y.toFixed(3)}`;
    }
    let path = `M${nodes[0].x.toFixed(3)},${nodes[0].y.toFixed(3)}`;
    for (let index = 0; index < nodes.length - 1; index += 1) {
        const p0 = nodes[Math.max(0, index - 1)];
        const p1 = nodes[index];
        const p2 = nodes[index + 1];
        const p3 = nodes[Math.min(nodes.length - 1, index + 2)];
        const c1x = p1.x + (p2.x - p0.x) / 6;
        const c1y = p1.y + (p2.y - p0.y) / 6;
        const c2x = p2.x - (p3.x - p1.x) / 6;
        const c2y = p2.y - (p3.y - p1.y) / 6;
        path += ` C${c1x.toFixed(3)},${c1y.toFixed(3)} ${c2x.toFixed(3)},${c2y.toFixed(3)} ${p2.x.toFixed(3)},${p2.y.toFixed(3)}`;
    }
    return path;
}


async function refreshData(forceRefresh) {
    dom.refreshBtn.disabled = true;
    dom.refreshBtn.textContent = forceRefresh ? "Refreshing..." : "Checking...";

    try {
        const payload = await fetchJson(PREDICTION_URL);
        state.predictions = payload.predictions || {};
        state.lastUpdate = payload.last_update || new Date().toLocaleTimeString();
        state.estimatedTrains = estimateTrainsForCurrentView();

        dom.lastUpdate.textContent = state.lastUpdate;
        updateStationStyles();
        updateEventPanel();
        updateTrainLayer();

        if (state.selectedKey) {
            selectStation(state.selectedKey);
        }
    } catch (error) {
        console.error(error);
        dom.lastUpdate.textContent = "Failed to load";
    } finally {
        dom.refreshBtn.disabled = false;
        dom.refreshBtn.textContent = "Refresh Now";
    }
}


function updateStationStyles() {
    state.nodeMap.forEach(({ node, element, circle }) => {
        const prediction = state.predictions[node.id];
        const fill = getRiskColor(prediction?.color_code);
        circle.setAttribute("fill", fill);
        element.classList.toggle("delayed-severe", prediction?.color_code === "red");
    });
}


function updateEventPanel() {
    const events = Object.entries(state.predictions)
        .filter(([, prediction]) => prediction.color_code === "red" || prediction.color_code === "yellow")
        .map(([key, prediction]) => ({ key, ...prediction }))
        .sort((left, right) => (right.delay_risk_probability || 0) - (left.delay_risk_probability || 0));

    dom.eventsList.innerHTML = "";

    if (!events.length) {
        dom.eventsSummary.textContent = "No active delay events detected across the network.";
        return;
    }

    dom.eventsSummary.textContent = `Detected ${events.length} delayed station(s).`;

    events.forEach((event) => {
        const li = document.createElement("li");
        const severity = event.color_code === "red" ? "Severe" : "Minor";
        li.innerHTML = `
            <strong>${event.key}</strong><br>
            ${severity} risk, ${(event.delay_risk_probability * 100).toFixed(1)}% probability<br>
            Est. ${formatValue(event.delay_duration_minutes)} mins, affects ${formatValue(event.affected_trains_count)} train(s)
        `;
        li.addEventListener("click", () => selectStation(event.key));
        dom.eventsList.appendChild(li);
    });
}


function selectStation(key) {
    const stationEntry = state.nodeMap.get(key);
    if (!stationEntry) {
        return;
    }

    state.selectedKey = key;
    state.nodeMap.forEach(({ element }) => element.classList.toggle("active", false));
    stationEntry.element.classList.toggle("active", true);

    const prediction = state.predictions[key] || {};
    const nearbyTrains = state.estimatedTrains.filter((train) => train.line === stationEntry.node.line && (
        train.from_station === stationEntry.node.station_code || train.to_station === stationEntry.node.station_code
    ));

    dom.detailsPlaceholder.classList.add("hidden");
    dom.stationDetails.classList.remove("hidden");

    dom.detailLine.textContent = stationEntry.node.line;
    dom.detailStation.textContent = `${stationEntry.node.station_name} (${stationEntry.node.station_code})`;
    dom.detailUp.textContent = formatValue(prediction.up_ttnt);
    dom.detailDown.textContent = formatValue(prediction.down_ttnt);
    dom.detailRisk.textContent = prediction.delay_risk_probability !== undefined
        ? `${(prediction.delay_risk_probability * 100).toFixed(1)}%`
        : "N/A";
    dom.detailDuration.textContent = formatValue(prediction.delay_duration_minutes);
    dom.detailAffected.textContent = formatValue(prediction.affected_trains_count);
    dom.detailTransfers.textContent = stationEntry.node.transfer_lines.join(", ");

    dom.detailTrains.innerHTML = "";
    if (!nearbyTrains.length) {
        const li = document.createElement("li");
        li.textContent = "No nearby estimated train markers right now.";
        dom.detailTrains.appendChild(li);
    } else {
        nearbyTrains.forEach((train) => {
            const li = document.createElement("li");
            li.textContent = `${train.directionLabel}: ${train.from_name} -> ${train.to_name}, ETA ${Math.round(train.eta_seconds / 60)} min`;
            dom.detailTrains.appendChild(li);
        });
    }

    showStationPopup(stationEntry.node, prediction, nearbyTrains);
}


function estimateTrains() {
    const trains = [];

    state.topology.lines.forEach((line) => {
        trains.push(...estimateLineDirection(line.code, line.color, line.stations, "up_ttnt", "Outbound"));
        trains.push(...estimateLineDirection(line.code, line.color, [...line.stations].reverse(), "down_ttnt", "Inbound"));
    });

    return trains;
}


function estimateTrainsForCurrentView() {
    if (state.viewMode !== "line") {
        return [];
    }
    const currentLine = getCurrentLine();
    if (!currentLine) {
        return [];
    }
    const forwardDestination = getStationName(currentLine.stations[currentLine.stations.length - 1]);
    const reverseDestination = getStationName(currentLine.stations[0]);
    const forwardTrains = estimateLineDirection(
        currentLine.code,
        currentLine.color,
        currentLine.stations,
        "up_ttnt",
        `To ${forwardDestination}`,
        "forward"
    );
    const reverseTrains = estimateLineDirection(
        currentLine.code,
        currentLine.color,
        [...currentLine.stations].reverse(),
        "down_ttnt",
        `To ${reverseDestination}`,
        "reverse"
    );

    if (state.selectedDirection === "forward") {
        if (forwardTrains.length) {
            return forwardTrains;
        }
        return estimateLineDirection(
            currentLine.code,
            currentLine.color,
            currentLine.stations,
            "down_ttnt",
            `To ${forwardDestination} (estimated)`,
            "forward"
        );
    }
    if (reverseTrains.length) {
        return reverseTrains;
    }
    return estimateLineDirection(
        currentLine.code,
        currentLine.color,
        [...currentLine.stations].reverse(),
        "up_ttnt",
        `To ${reverseDestination} (estimated)`,
        "reverse"
    );
}


function estimateLineDirection(lineCode, lineColor, stationCodes, fieldName, directionLabel, directionKey = null) {
    const trains = [];

    for (let index = 1; index < stationCodes.length; index += 1) {
        const fromCode = stationCodes[index - 1];
        const toCode = stationCodes[index];
        const toPrediction = state.predictions[`${lineCode}-${toCode}`];

        const etaMinutes = toNumber(toPrediction?.[fieldName]);
        if (!etaMinutes || etaMinutes <= 0) {
            continue;
        }

        const prevPrediction = state.predictions[`${lineCode}-${fromCode}`];
        const prevEtaMinutes = toNumber(prevPrediction?.[fieldName]);

        const fromNode = state.nodeMap.get(`${lineCode}-${fromCode}`)?.node;
        const toNode = state.nodeMap.get(`${lineCode}-${toCode}`)?.node;
        if (!fromNode || !toNode) {
            continue;
        }

        const etaDelta = (prevEtaMinutes !== null && prevEtaMinutes !== undefined)
            ? etaMinutes - prevEtaMinutes
            : null;
        let segmentDuration = inferSegmentDuration(prevEtaMinutes, etaMinutes);
        if (etaDelta !== null && etaDelta > 0.12 && etaDelta < 10) {
            segmentDuration = clamp(etaDelta, 0.8, 7.5);
        }

        const referenceEta = (prevEtaMinutes !== null && prevEtaMinutes !== undefined && prevEtaMinutes >= 0)
            ? prevEtaMinutes
            : etaMinutes;
        const normalizedEta = clamp(referenceEta / Math.max(segmentDuration, 0.8), 0, 1.25);
        let progress = clamp(1 - normalizedEta, 0.14, 0.9);
        if (etaDelta === null || Math.abs(etaDelta) <= 0.12) {
            const nowSec = Date.now() / 1000;
            const periodSec = Math.max(30, etaMinutes * 60);
            const phase = ((nowSec + index * 11) % periodSec) / periodSec;
            progress = clamp(0.14 + phase * 0.72, 0.14, 0.86);
        }

        const x = lerp(fromNode.x, toNode.x, progress);
        const y = lerp(fromNode.y, toNode.y, progress);

        trains.push({
            id: `${lineCode}-${directionLabel}-${fromCode}-${toCode}`,
            line: lineCode,
            directionLabel,
            direction_key: directionKey,
            from_station: fromCode,
            to_station: toCode,
            from_name: fromNode.station_name,
            to_name: toNode.station_name,
            eta_seconds: Math.round(etaMinutes * 60),
            progress,
            segment_index: index - 1,
            segment_count: stationCodes.length - 1,
            x,
            y,
            color: lineColor,
        });
    }

    return trains;
}


function clearTrainLayerImmediately() {
    state.trainMap.forEach((entry) => {
        if (entry.group.parentNode) {
            entry.group.parentNode.removeChild(entry.group);
        }
    });
    state.trainMap.clear();
}


function updateTrainLayer() {
    const trainLayer = state.trainLayer || document.getElementById("train-layer");
    if (state.viewMode !== "line") {
        clearTrainLayerImmediately();
        return;
    }
    const trainsForDirection = state.estimatedTrains.filter((train) => (
        !train.direction_key || train.direction_key === state.selectedDirection
    ));
    const activeIds = new Set();

    trainsForDirection.forEach((train) => {
        activeIds.add(train.id);
        let entry = state.trainMap.get(train.id);

        if (!entry) {
            const group = document.createElementNS(SVG_NS, "g");
            group.setAttribute("class", "train-estimate");
            group.setAttribute("transform", `translate(${train.x} ${train.y})`);

            const marker = document.createElementNS(SVG_NS, "text");
            marker.setAttribute("class", "train-icon");
            marker.setAttribute("text-anchor", "middle");
            marker.setAttribute("dominant-baseline", "middle");
            marker.textContent = "🚆";

            group.appendChild(marker);
            trainLayer.appendChild(group);

            entry = { group, marker, x: train.x, y: train.y };
            state.trainMap.set(train.id, entry);
        }

        entry.marker.style.color = train.color;
        animateTrainTo(entry, train.x, train.y);
        entry.group.style.opacity = "1";
    });

    state.trainMap.forEach((entry, id) => {
        if (activeIds.has(id)) {
            return;
        }
        entry.group.style.opacity = "0";
        window.setTimeout(() => {
            const staleEntry = state.trainMap.get(id);
            if (staleEntry && staleEntry.group.parentNode) {
                staleEntry.group.parentNode.removeChild(staleEntry.group);
            }
            state.trainMap.delete(id);
        }, 250);
    });
}


function animateTrainTo(entry, nextX, nextY) {
    const fromX = entry.x ?? nextX;
    const fromY = entry.y ?? nextY;

    const oldAnimation = entry.group.querySelector("animateTransform");
    if (oldAnimation) {
        oldAnimation.remove();
    }

    if (fromX === nextX && fromY === nextY) {
        entry.group.setAttribute("transform", `translate(${nextX} ${nextY})`);
        entry.x = nextX;
        entry.y = nextY;
        return;
    }

    const animation = document.createElementNS(SVG_NS, "animateTransform");
    animation.setAttribute("attributeName", "transform");
    animation.setAttribute("attributeType", "XML");
    animation.setAttribute("type", "translate");
    animation.setAttribute("dur", `${(REFRESH_INTERVAL_MS - 1000) / 1000}s`);
    animation.setAttribute("fill", "freeze");
    animation.setAttribute("from", `${fromX} ${fromY}`);
    animation.setAttribute("to", `${nextX} ${nextY}`);

    entry.group.setAttribute("transform", `translate(${fromX} ${fromY})`);
    entry.group.appendChild(animation);
    animation.beginElement();
    entry.group.setAttribute("transform", `translate(${nextX} ${nextY})`);
    entry.x = nextX;
    entry.y = nextY;
}


function showHoverCard(node) {
    dom.hoverCard.innerHTML = `
        <strong>${node.station_name}</strong>
    `;
    dom.hoverCard.classList.remove("hidden");
    placeCardNearStation(node.id, dom.hoverCard, { x: 10, y: -46 });
}


function hideHoverCard() {
    dom.hoverCard.classList.add("hidden");
}


function showStationPopup(node, prediction, nearbyTrains) {
    const trainItems = nearbyTrains.length
        ? nearbyTrains
            .slice(0, 4)
            .map((train) => `<li>${train.directionLabel}: ${train.from_name} -> ${train.to_name}, ETA ${Math.round(train.eta_seconds / 60)} min</li>`)
            .join("")
        : "<li>No nearby estimated trains.</li>";

    dom.stationPopup.innerHTML = `
        <h4>${node.station_name} (${node.station_code})</h4>
        <p>Line: ${node.line}</p>
        <p>UP: ${formatValue(prediction.up_ttnt)} min, DOWN: ${formatValue(prediction.down_ttnt)} min</p>
        <p>Risk: ${prediction.delay_risk_probability !== undefined ? `${(prediction.delay_risk_probability * 100).toFixed(1)}%` : "N/A"}</p>
        <p>Duration: ${formatValue(prediction.delay_duration_minutes)} min, Affected: ${formatValue(prediction.affected_trains_count)}</p>
        <ul>${trainItems}</ul>
    `;
    dom.stationPopup.classList.remove("hidden");
    placeCardNearStation(node.id, dom.stationPopup, { x: 12, y: -12 });
}


function autoAlignPathLayer(pathLayer, mapLayer) {
    const nodeBounds = computeNodeBounds();
    const pathBounds = computePathBounds(pathLayer);
    if (!nodeBounds || !pathBounds || pathBounds.width === 0 || pathBounds.height === 0) {
        return;
    }

    const sx = nodeBounds.width / pathBounds.width;
    const sy = nodeBounds.height / pathBounds.height;
    const nodeCenterX = nodeBounds.minX + nodeBounds.width / 2;
    const nodeCenterY = nodeBounds.minY + nodeBounds.height / 2;
    const pathCenterX = pathBounds.minX + pathBounds.width / 2;
    const pathCenterY = pathBounds.minY + pathBounds.height / 2;
    const tx = nodeCenterX - pathCenterX * sx;
    const ty = nodeCenterY - pathCenterY * sy;
    const transformMatrix = `matrix(${sx} 0 0 ${sy} ${tx} ${ty})`;
    pathLayer.setAttribute("transform", transformMatrix);
    if (mapLayer) {
        mapLayer.setAttribute("transform", transformMatrix);
    }
}


function computeNodeBounds() {
    const nodes = state.topology.line_station_nodes;
    if (!nodes.length) {
        return null;
    }
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    nodes.forEach((node) => {
        minX = Math.min(minX, node.x);
        maxX = Math.max(maxX, node.x);
        minY = Math.min(minY, node.y);
        maxY = Math.max(maxY, node.y);
    });
    return { minX, maxX, minY, maxY, width: maxX - minX, height: maxY - minY };
}


function computePathBounds(pathLayer) {
    const paths = pathLayer.querySelectorAll("path");
    if (!paths.length) {
        return null;
    }
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    paths.forEach((path) => {
        const box = path.getBBox();
        minX = Math.min(minX, box.x);
        maxX = Math.max(maxX, box.x + box.width);
        minY = Math.min(minY, box.y);
        maxY = Math.max(maxY, box.y + box.height);
    });
    return { minX, maxX, minY, maxY, width: maxX - minX, height: maxY - minY };
}


function bindPanAndZoom() {
    dom.svg.onwheel = (event) => {
        event.preventDefault();
        const pointer = clientToSvg(event.clientX, event.clientY);
        if (!pointer) {
            return;
        }
        const zoomStep = event.deltaY > 0 ? 0.9 : 1.1;
        const nextScale = clamp(state.zoom.scale * zoomStep, state.zoom.minScale, state.zoom.maxScale);
        if (nextScale === state.zoom.scale) {
            return;
        }
        const worldX = (pointer.x - state.zoom.tx) / state.zoom.scale;
        const worldY = (pointer.y - state.zoom.ty) / state.zoom.scale;
        state.zoom.tx = pointer.x - worldX * nextScale;
        state.zoom.ty = pointer.y - worldY * nextScale;
        state.zoom.scale = nextScale;
        applyViewportTransform();
    };

    dom.svg.onmousedown = (event) => {
        if (event.button !== 0) {
            return;
        }
        if (event.target.closest(".station-node")) {
            return;
        }
        event.preventDefault();
        state.zoom.isPanning = true;
        dom.svg.classList.add("is-panning");
        const start = clientToSvg(event.clientX, event.clientY);
        if (!start) {
            return;
        }
        const startTx = state.zoom.tx;
        const startTy = state.zoom.ty;

        const onMove = (moveEvent) => {
            if (!state.zoom.isPanning) {
                return;
            }
            const point = clientToSvg(moveEvent.clientX, moveEvent.clientY);
            if (!point) {
                return;
            }
            state.zoom.tx = startTx + (point.x - start.x);
            state.zoom.ty = startTy + (point.y - start.y);
            applyViewportTransform();
        };

        const onUp = () => {
            state.zoom.isPanning = false;
            dom.svg.classList.remove("is-panning");
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
        };

        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
    };
}


function applyViewportTransform() {
    if (!state.viewportLayer) {
        return;
    }
    state.viewportLayer.setAttribute(
        "transform",
        `translate(${state.zoom.tx} ${state.zoom.ty}) scale(${state.zoom.scale})`
    );
    updateZoomResponsiveStyles();

    if (state.selectedKey) {
        placeCardNearStation(state.selectedKey, dom.stationPopup, { x: 12, y: -12 });
    }
}


function updateZoomResponsiveStyles() {
    const zoomScale = state.zoom.scale || 1;
    const lineFactor = getMapScaleFactor() * zoomScale;
    state.pathElements.forEach((path) => {
        const baseStroke = Number(path.getAttribute("data-base-stroke")) || 6;
        path.setAttribute("stroke-width", `${(baseStroke * lineFactor).toFixed(3)}`);
    });
}


function getMapScaleFactor() {
    const viewBox = dom.svg.viewBox?.baseVal;
    const rect = dom.svg.getBoundingClientRect();
    if (!viewBox || !rect.width || !rect.height || !viewBox.width || !viewBox.height) {
        return 1;
    }
    return Math.min(rect.width / viewBox.width, rect.height / viewBox.height);
}


function clientToSvg(clientX, clientY) {
    const point = dom.svg.createSVGPoint();
    point.x = clientX;
    point.y = clientY;
    const ctm = dom.svg.getScreenCTM();
    if (!ctm) {
        return null;
    }
    return point.matrixTransform(ctm.inverse());
}


function placeCardNearStation(stationId, cardEl, offset) {
    const stationEntry = state.nodeMap.get(stationId);
    if (!stationEntry || cardEl.classList.contains("hidden")) {
        return;
    }
    const panelRect = dom.canvasPanel.getBoundingClientRect();
    const stationRect = stationEntry.element.getBoundingClientRect();
    const x = stationRect.left - panelRect.left + (offset?.x || 0);
    const y = stationRect.top - panelRect.top + (offset?.y || 0);
    cardEl.style.left = `${x}px`;
    cardEl.style.top = `${y}px`;
}


function getRiskColor(colorCode) {
    if (colorCode === "red") {
        return "#ef4444";
    }
    if (colorCode === "yellow") {
        return "#f59e0b";
    }
    return "#22c55e";
}


function inferSegmentDuration(prevEtaMinutes, etaMinutes) {
    if (prevEtaMinutes && etaMinutes && etaMinutes >= prevEtaMinutes) {
        return clamp(etaMinutes - prevEtaMinutes, 1.5, 4.5);
    }
    return 3.0;
}


function formatValue(value) {
    if (value === undefined || value === null || Number.isNaN(Number(value))) {
        return "N/A";
    }
    return `${value}`;
}


function toNumber(value) {
    if (value === undefined || value === null || value === "") {
        return null;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
}


function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}


function lerp(start, end, ratio) {
    return start + (end - start) * ratio;
}


document.addEventListener("DOMContentLoaded", () => {
    init().catch((error) => {
        console.error(error);
        dom.lastUpdate.textContent = "Initialization failed";
    });
});
