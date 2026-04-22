(function () {
    const SVG_NS = "http://www.w3.org/2000/svg";
    const TOPOLOGY_URL = "/frontend/assets/mtr_topology.json";
    const REFRESH_INTERVAL_MS = 15000;

    const state = {
        initialized: false,
        topology: null,
        predictions: {},
        estimatedTrains: [],
        nodeMap: new Map(),
        trainMap: new Map(),
        selectedKey: null,
        zoom: { scale: 1, tx: 0, ty: 0, minScale: 0.5, maxScale: 8, isPanning: false },
        viewportLayer: null,
        pathLayer: null,
        stationLayer: null,
        trainLayer: null,
        pathElements: [],
        lineStrokeByCode: new Map(),
        viewMode: "network",
        selectedLineCode: null,
        selectedDirection: "forward",
        stationMetaByCode: new Map(),
        dom: {},
    };

    function byId(id) {
        return document.getElementById(id);
    }

    async function init() {
        if (state.initialized) {
            return;
        }
        state.dom = {
            svg: byId("embed-schematic-svg"),
            canvasPanel: byId("embed-canvas-panel"),
            lineBackBtn: byId("embed-line-back-btn"),
            lineModeHeader: byId("embed-line-mode-header"),
            lineModeTitle: byId("embed-line-mode-title"),
            lineModeSubtitle: byId("embed-line-mode-subtitle"),
            networkLineLegend: byId("embed-network-line-legend"),
            lineDirectionToggle: byId("embed-line-direction-toggle"),
            directionForwardBtn: byId("embed-direction-forward-btn"),
            directionReverseBtn: byId("embed-direction-reverse-btn"),
            hoverCard: byId("embed-hover-card"),
            stationPopup: byId("embed-station-popup"),
        };
        state.dom.lineBackBtn.addEventListener("click", () => returnToNetworkView());
        state.dom.directionForwardBtn.addEventListener("click", () => switchLineDirection("forward"));
        state.dom.directionReverseBtn.addEventListener("click", () => switchLineDirection("reverse"));

        state.topology = await fetchJson(TOPOLOGY_URL);
        state.topology.stations.forEach((station) => state.stationMetaByCode.set(station.code, station));
        renderNetworkLegend();
        renderSchematic();
        state.initialized = true;
    }

    async function fetchJson(url) {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Failed to fetch ${url}`);
        }
        return response.json();
    }

    function setPredictions(predictions) {
        state.predictions = predictions || {};
        if (!state.initialized) {
            return;
        }
        state.estimatedTrains = estimateTrainsForCurrentView();
        updateTrainLayer();
        if (state.selectedKey) {
            selectStation(state.selectedKey);
        }
    }

    function renderNetworkLegend() {
        const legend = state.dom.networkLineLegend;
        legend.innerHTML = "";
        state.topology.lines.forEach((line) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "embed-network-line-item";
            button.innerHTML = `<span class="embed-line-chip" style="background:${line.color}"></span>${line.name}`;
            button.addEventListener("click", () => enterLineView(line.code));
            legend.appendChild(button);
        });
    }

    function renderSchematic() {
        const isLineMode = state.viewMode === "line";
        const currentLine = getCurrentLine();
        const lineLayoutNodes = isLineMode && currentLine ? buildLineLayoutNodes(currentLine) : [];
        const viewBox = isLineMode ? { minX: 0, minY: 0, width: 1200, height: 760 } : state.topology.meta.viewBox;
        state.dom.svg.setAttribute("viewBox", `${viewBox.minX} ${viewBox.minY} ${viewBox.width} ${viewBox.height}`);
        state.dom.svg.innerHTML = "";
        state.nodeMap.clear();
        state.trainMap.clear();
        state.pathElements = [];
        state.lineStrokeByCode.clear();

        const viewportLayer = document.createElementNS(SVG_NS, "g");
        const mapLayer = document.createElementNS(SVG_NS, "g");
        const pathLayer = document.createElementNS(SVG_NS, "g");
        const stationLayer = document.createElementNS(SVG_NS, "g");
        const trainLayer = document.createElementNS(SVG_NS, "g");

        if (!isLineMode) {
            (state.topology.background_paths || []).forEach((shapeDef) => {
                const shape = document.createElementNS(SVG_NS, "path");
                shape.setAttribute("class", "embed-map-shape");
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
            path.setAttribute("class", "embed-line-path");
            path.setAttribute("d", pathDef.path);
            path.setAttribute("stroke", pathDef.color);
            const baseStroke = (Number(pathDef.stroke_width) || 6) * 1.35;
            path.setAttribute("stroke-width", `${baseStroke}`);
            path.setAttribute("data-base-stroke", `${baseStroke}`);
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
            group.setAttribute("class", "embed-station-node");
            group.setAttribute("data-key", node.id);
            group.setAttribute("transform", `translate(${node.x}, ${node.y})`);

            const circle = document.createElementNS(SVG_NS, "circle");
            circle.setAttribute("class", "embed-station-circle");
            const lineStroke = state.lineStrokeByCode.get(node.line) || 6;
            const baseRadius = node.is_interchange ? Math.max(5.0, lineStroke * 0.95) : Math.max(4.1, lineStroke * 0.72);
            circle.setAttribute("r", `${baseRadius}`);
            circle.setAttribute("fill", "#22c55e");
            circle.setAttribute("stroke", node.color);

            const label = document.createElementNS(SVG_NS, "text");
            label.setAttribute("class", "embed-station-label");
            label.setAttribute("text-anchor", "middle");
            label.setAttribute("y", "-7.8");
            label.textContent = node.station_code;

            group.appendChild(circle);
            group.appendChild(label);
            stationLayer.appendChild(group);

            group.addEventListener("click", () => selectStation(node.id));
            group.addEventListener("mousemove", () => showHoverCard(node));
            group.addEventListener("mouseleave", () => state.dom.hoverCard.classList.add("hidden"));

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
        state.dom.svg.appendChild(viewportLayer);

        state.viewportLayer = viewportLayer;
        state.pathLayer = pathLayer;
        state.stationLayer = stationLayer;
        state.trainLayer = trainLayer;
        state.zoom.scale = 1;
        state.zoom.tx = 0;
        state.zoom.ty = 0;
        applyViewportTransform();
        bindPanAndZoom();
        updateModeOverlays();

        state.dom.svg.onclick = (event) => {
            if (event.target.closest(".embed-station-node")) return;
            state.dom.stationPopup.classList.add("hidden");
        };
        state.estimatedTrains = estimateTrainsForCurrentView();
        updateTrainLayer();
    }

    function updateModeOverlays() {
        const isLineMode = state.viewMode === "line";
        state.dom.networkLineLegend.classList.toggle("hidden", isLineMode);
        state.dom.lineBackBtn.classList.toggle("hidden", !isLineMode);
        state.dom.lineModeHeader.classList.toggle("hidden", !isLineMode);
        state.dom.lineDirectionToggle.classList.toggle("hidden", !isLineMode);
        updateLineModeHeader();
        updateDirectionToggle();
    }

    function getCurrentLine() {
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
        state.dom.stationPopup.classList.add("hidden");
        renderSchematic();
    }
    function returnToNetworkView() {
        state.viewMode = "network";
        state.selectedLineCode = null;
        state.selectedDirection = "forward";
        state.selectedKey = null;
        state.dom.stationPopup.classList.add("hidden");
        renderSchematic();
    }
    function switchLineDirection(direction) {
        if (state.viewMode !== "line") return;
        state.selectedDirection = direction;
        clearTrainLayerImmediately();
        updateLineModeHeader();
        updateDirectionToggle();
        state.estimatedTrains = estimateTrainsForCurrentView();
        updateTrainLayer();
    }

    function updateLineModeHeader() {
        const line = getCurrentLine();
        if (!line || state.viewMode !== "line") {
            state.dom.lineModeTitle.textContent = "";
            state.dom.lineModeSubtitle.textContent = "";
            return;
        }
        const destination = state.selectedDirection === "forward"
            ? getStationName(line.stations[line.stations.length - 1])
            : getStationName(line.stations[0]);
        state.dom.lineModeTitle.textContent = line.name;
        state.dom.lineModeSubtitle.textContent = `Towards ${destination}`;
    }
    function updateDirectionToggle() {
        const line = getCurrentLine();
        if (!line || state.viewMode !== "line") return;
        state.dom.directionForwardBtn.textContent = `To ${getStationName(line.stations[line.stations.length - 1])}`;
        state.dom.directionReverseBtn.textContent = `To ${getStationName(line.stations[0])}`;
        state.dom.directionForwardBtn.classList.toggle("active", state.selectedDirection === "forward");
        state.dom.directionReverseBtn.classList.toggle("active", state.selectedDirection === "reverse");
    }

    function buildLineLayoutNodes(line) {
        const count = line.stations.length;
        const left = 120;
        const right = 1080;
        const centerY = 380;
        const amplitude = clamp(70 + count * 7.5, 110, 220);
        const span = Math.max(1, count - 1);
        return line.stations.map((code, index) => {
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
                color: line.color,
                is_interchange: Boolean(stationMeta?.is_interchange),
                transfer_lines: stationMeta?.lines || [line.code],
            };
        });
    }
    function buildSmoothLinePath(nodes) {
        if (!nodes.length) return "";
        let path = `M${nodes[0].x.toFixed(3)},${nodes[0].y.toFixed(3)}`;
        for (let i = 0; i < nodes.length - 1; i += 1) {
            const p0 = nodes[Math.max(0, i - 1)];
            const p1 = nodes[i];
            const p2 = nodes[i + 1];
            const p3 = nodes[Math.min(nodes.length - 1, i + 2)];
            const c1x = p1.x + (p2.x - p0.x) / 6;
            const c1y = p1.y + (p2.y - p0.y) / 6;
            const c2x = p2.x - (p3.x - p1.x) / 6;
            const c2y = p2.y - (p3.y - p1.y) / 6;
            path += ` C${c1x.toFixed(3)},${c1y.toFixed(3)} ${c2x.toFixed(3)},${c2y.toFixed(3)} ${p2.x.toFixed(3)},${p2.y.toFixed(3)}`;
        }
        return path;
    }

    function estimateTrainsForCurrentView() {
        if (state.viewMode !== "line") return [];
        const line = getCurrentLine();
        if (!line) return [];
        const forwardDestination = getStationName(line.stations[line.stations.length - 1]);
        const reverseDestination = getStationName(line.stations[0]);
        const forward = estimateLineDirection(line.code, line.color, line.stations, "up_ttnt", `To ${forwardDestination}`, "forward");
        const reverse = estimateLineDirection(line.code, line.color, [...line.stations].reverse(), "down_ttnt", `To ${reverseDestination}`, "reverse");
        if (state.selectedDirection === "forward") {
            return forward.length ? forward : estimateLineDirection(line.code, line.color, line.stations, "down_ttnt", `To ${forwardDestination} (estimated)`, "forward");
        }
        return reverse.length ? reverse : estimateLineDirection(line.code, line.color, [...line.stations].reverse(), "up_ttnt", `To ${reverseDestination} (estimated)`, "reverse");
    }

    function estimateLineDirection(lineCode, lineColor, stationCodes, fieldName, directionLabel, directionKey) {
        const trains = [];
        for (let index = 1; index < stationCodes.length; index += 1) {
            const fromCode = stationCodes[index - 1];
            const toCode = stationCodes[index];
            const etaMinutes = toNumber(state.predictions[`${lineCode}-${toCode}`]?.[fieldName]);
            if (!etaMinutes || etaMinutes <= 0) continue;
            const prevEtaMinutes = toNumber(state.predictions[`${lineCode}-${fromCode}`]?.[fieldName]);
            const fromNode = state.nodeMap.get(`${lineCode}-${fromCode}`)?.node;
            const toNode = state.nodeMap.get(`${lineCode}-${toCode}`)?.node;
            if (!fromNode || !toNode) continue;

            const etaDelta = (prevEtaMinutes !== null && prevEtaMinutes !== undefined) ? etaMinutes - prevEtaMinutes : null;
            let segmentDuration = inferSegmentDuration(prevEtaMinutes, etaMinutes);
            if (etaDelta !== null && etaDelta > 0.12 && etaDelta < 10) {
                segmentDuration = clamp(etaDelta, 0.8, 7.5);
            }
            const referenceEta = (prevEtaMinutes !== null && prevEtaMinutes !== undefined && prevEtaMinutes >= 0) ? prevEtaMinutes : etaMinutes;
            const normalizedEta = clamp(referenceEta / Math.max(segmentDuration, 0.8), 0, 1.25);
            let progress = clamp(1 - normalizedEta, 0.14, 0.9);
            if (etaDelta === null || Math.abs(etaDelta) <= 0.12) {
                const nowSec = Date.now() / 1000;
                const periodSec = Math.max(30, etaMinutes * 60);
                const phase = ((nowSec + index * 11) % periodSec) / periodSec;
                progress = clamp(0.14 + phase * 0.72, 0.14, 0.86);
            }
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
                x: lerp(fromNode.x, toNode.x, progress),
                y: lerp(fromNode.y, toNode.y, progress),
                color: lineColor,
            });
        }
        return trains;
    }

    function clearTrainLayerImmediately() {
        state.trainMap.forEach((entry) => {
            if (entry.group.parentNode) entry.group.parentNode.removeChild(entry.group);
        });
        state.trainMap.clear();
    }
    function updateTrainLayer() {
        if (state.viewMode !== "line") {
            clearTrainLayerImmediately();
            return;
        }
        const activeIds = new Set();
        state.estimatedTrains.filter((train) => train.direction_key === state.selectedDirection).forEach((train) => {
            activeIds.add(train.id);
            let entry = state.trainMap.get(train.id);
            if (!entry) {
                const group = document.createElementNS(SVG_NS, "g");
                group.setAttribute("transform", `translate(${train.x} ${train.y})`);
                const marker = document.createElementNS(SVG_NS, "text");
                marker.setAttribute("class", "embed-train-icon");
                marker.setAttribute("text-anchor", "middle");
                marker.setAttribute("dominant-baseline", "middle");
                marker.textContent = "🚆";
                group.appendChild(marker);
                state.trainLayer.appendChild(group);
                entry = { group, marker, x: train.x, y: train.y };
                state.trainMap.set(train.id, entry);
            }
            entry.marker.style.color = train.color;
            animateTrainTo(entry, train.x, train.y);
            entry.group.style.opacity = "1";
        });
        state.trainMap.forEach((entry, id) => {
            if (activeIds.has(id)) return;
            entry.group.style.opacity = "0";
            setTimeout(() => {
                if (entry.group.parentNode) entry.group.parentNode.removeChild(entry.group);
                state.trainMap.delete(id);
            }, 250);
        });
    }
    function animateTrainTo(entry, nextX, nextY) {
        const fromX = entry.x ?? nextX;
        const fromY = entry.y ?? nextY;
        const oldAnimation = entry.group.querySelector("animateTransform");
        if (oldAnimation) oldAnimation.remove();
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

    function selectStation(key) {
        const stationEntry = state.nodeMap.get(key);
        if (!stationEntry) return;
        state.selectedKey = key;
        state.nodeMap.forEach(({ element }) => element.classList.toggle("active", false));
        stationEntry.element.classList.toggle("active", true);
        const prediction = state.predictions[key] || {};
        const nearbyTrains = state.estimatedTrains.filter((train) => train.line === stationEntry.node.line && (
            train.from_station === stationEntry.node.station_code || train.to_station === stationEntry.node.station_code
        ));
        showStationPopup(stationEntry.node, prediction, nearbyTrains);
    }
    function showHoverCard(node) {
        state.dom.hoverCard.innerHTML = `<strong>${node.station_name}</strong>`;
        state.dom.hoverCard.classList.remove("hidden");
        placeCardNearStation(node.id, state.dom.hoverCard, { x: 10, y: -46 });
    }
    function showStationPopup(node, prediction, nearbyTrains) {
        const trainItems = nearbyTrains.length
            ? nearbyTrains.slice(0, 4).map((train) => `<li>${train.directionLabel}: ${train.from_name} -> ${train.to_name}, ETA ${Math.round(train.eta_seconds / 60)} min</li>`).join("")
            : "<li>No nearby estimated trains.</li>";
        state.dom.stationPopup.innerHTML = `
            <h4>${node.station_name} (${node.station_code})</h4>
            <p>Line: ${node.line}</p>
            <p>UP: ${formatValue(prediction.up_ttnt)} min, DOWN: ${formatValue(prediction.down_ttnt)} min</p>
            <p>Risk: ${prediction.delay_risk_probability !== undefined ? `${(prediction.delay_risk_probability * 100).toFixed(1)}%` : "N/A"}</p>
            <p>Duration: ${formatValue(prediction.delay_duration_minutes)} min, Affected: ${formatValue(prediction.affected_trains_count)}</p>
            <ul>${trainItems}</ul>`;
        state.dom.stationPopup.classList.remove("hidden");
        placeCardNearStation(node.id, state.dom.stationPopup, { x: 12, y: -12 });
    }

    function bindPanAndZoom() {
        state.dom.svg.onwheel = (event) => {
            event.preventDefault();
            const pointer = clientToSvg(event.clientX, event.clientY);
            if (!pointer) return;
            const zoomStep = event.deltaY > 0 ? 0.9 : 1.1;
            const nextScale = clamp(state.zoom.scale * zoomStep, state.zoom.minScale, state.zoom.maxScale);
            if (nextScale === state.zoom.scale) return;
            const worldX = (pointer.x - state.zoom.tx) / state.zoom.scale;
            const worldY = (pointer.y - state.zoom.ty) / state.zoom.scale;
            state.zoom.tx = pointer.x - worldX * nextScale;
            state.zoom.ty = pointer.y - worldY * nextScale;
            state.zoom.scale = nextScale;
            applyViewportTransform();
        };
        state.dom.svg.onmousedown = (event) => {
            if (event.button !== 0 || event.target.closest(".embed-station-node")) return;
            event.preventDefault();
            state.zoom.isPanning = true;
            state.dom.svg.classList.add("is-panning");
            const start = clientToSvg(event.clientX, event.clientY);
            if (!start) return;
            const startTx = state.zoom.tx;
            const startTy = state.zoom.ty;
            const onMove = (moveEvent) => {
                if (!state.zoom.isPanning) return;
                const point = clientToSvg(moveEvent.clientX, moveEvent.clientY);
                if (!point) return;
                state.zoom.tx = startTx + (point.x - start.x);
                state.zoom.ty = startTy + (point.y - start.y);
                applyViewportTransform();
            };
            const onUp = () => {
                state.zoom.isPanning = false;
                state.dom.svg.classList.remove("is-panning");
                window.removeEventListener("mousemove", onMove);
                window.removeEventListener("mouseup", onUp);
            };
            window.addEventListener("mousemove", onMove);
            window.addEventListener("mouseup", onUp);
        };
    }
    function applyViewportTransform() {
        if (!state.viewportLayer) return;
        state.viewportLayer.setAttribute("transform", `translate(${state.zoom.tx} ${state.zoom.ty}) scale(${state.zoom.scale})`);
        updateZoomResponsiveStyles();
        if (state.selectedKey) {
            placeCardNearStation(state.selectedKey, state.dom.stationPopup, { x: 12, y: -12 });
        }
    }
    function updateZoomResponsiveStyles() {
        const lineFactor = getMapScaleFactor() * (state.zoom.scale || 1);
        state.pathElements.forEach((path) => {
            const baseStroke = Number(path.getAttribute("data-base-stroke")) || 6;
            path.setAttribute("stroke-width", `${(baseStroke * lineFactor).toFixed(3)}`);
        });
    }
    function getMapScaleFactor() {
        const viewBox = state.dom.svg.viewBox?.baseVal;
        const rect = state.dom.svg.getBoundingClientRect();
        if (!viewBox || !rect.width || !rect.height || !viewBox.width || !viewBox.height) return 1;
        return Math.min(rect.width / viewBox.width, rect.height / viewBox.height);
    }
    function clientToSvg(clientX, clientY) {
        const point = state.dom.svg.createSVGPoint();
        point.x = clientX;
        point.y = clientY;
        const ctm = state.dom.svg.getScreenCTM();
        if (!ctm) return null;
        return point.matrixTransform(ctm.inverse());
    }
    function placeCardNearStation(stationId, cardEl, offset) {
        const stationEntry = state.nodeMap.get(stationId);
        if (!stationEntry || cardEl.classList.contains("hidden")) return;
        const panelRect = state.dom.canvasPanel.getBoundingClientRect();
        const stationRect = stationEntry.element.getBoundingClientRect();
        cardEl.style.left = `${stationRect.left - panelRect.left + (offset?.x || 0)}px`;
        cardEl.style.top = `${stationRect.top - panelRect.top + (offset?.y || 0)}px`;
    }
    function inferSegmentDuration(prevEtaMinutes, etaMinutes) {
        if (prevEtaMinutes && etaMinutes && etaMinutes >= prevEtaMinutes) return clamp(etaMinutes - prevEtaMinutes, 1.5, 4.5);
        return 3.0;
    }
    function formatValue(value) {
        if (value === undefined || value === null || Number.isNaN(Number(value))) return "N/A";
        return `${value}`;
    }
    function toNumber(value) {
        if (value === undefined || value === null || value === "") return null;
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }
    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }
    function lerp(start, end, ratio) {
        return start + (end - start) * ratio;
    }

    window.MTREmbedMonitor = { init, setPredictions };
})();
