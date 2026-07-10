'use strict';

const state = {
  map: null,
  data: null,
  obstacles: [],
  nextObstacleId: 1,
  placing: false,
  layers: {},
  fleet: [],
  frame: 0,
  timer: null,
  requestController: null,
  requestSerial: 0,
  replanTimer: null,
};

const COLORS = {
  primary: '#22d3ee',
  escort: '#60a5fa',
  backup: '#facc15',
  building: '#64748b',
  powerline: '#facc15',
  sensitive: '#a78bfa',
  restricted: '#ef4444',
  weather: '#fb923c',
};

function by(id) { return document.getElementById(id); }
function num(id) { return Number(by(id).value); }
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}
function metric(value, suffix = '') {
  return value === undefined || value === null ? '--' : `${value}${suffix}`;
}
function pickup() { return { lon: num('pickupLon'), lat: num('pickupLat'), id: by('pickupId').value }; }
function dropoff() { return { lon: num('dropoffLon'), lat: num('dropoffLat'), id: by('dropoffId').value }; }
function latLng(point) { return [Number(point.lat), Number(point.lon)]; }

function currentPrimaryPoint() {
  const primary = state.fleet[0];
  if (!primary || !primary.trajectory.length) return null;
  return primary.trajectory[Math.min(state.frame, primary.trajectory.length - 1)];
}

function makeDivIcon(html, size, anchor) {
  return L.divIcon({ className: '', html, iconSize: size, iconAnchor: anchor });
}

function medicalIcon(kind) {
  const isPickup = kind === 'pickup';
  const color = isPickup ? '#34d399' : '#fb7185';
  const label = isPickup ? '血' : '医';
  return makeDivIcon(
    `<div class="medical-icon" style="background:${color};color:#06101d">${label}</div>`,
    [32, 32], [16, 16],
  );
}

function quadcopterIcon(color, label, role) {
  const html = `
    <div class="uav-shell" style="color:${color}">
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <g fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round">
          <path d="M20 20L44 44M44 20L20 44"/>
          <circle cx="14" cy="14" r="9"/>
          <circle cx="50" cy="14" r="9"/>
          <circle cx="14" cy="50" r="9"/>
          <circle cx="50" cy="50" r="9"/>
        </g>
        <rect x="23" y="23" width="18" height="18" rx="5" fill="${color}" stroke="#fff" stroke-width="2"/>
        <circle cx="32" cy="32" r="4" fill="#06101d"/>
      </svg>
      <div class="uav-label">${esc(label)} · ${esc(role)}</div>
    </div>`;
  return makeDivIcon(html, [120, 58], [27, 27]);
}

function simpleBadgeIcon(text, background) {
  return makeDivIcon(
    `<div class="agent-icon" style="background:${background}">${esc(text)}</div>`,
    [27, 27], [13, 13],
  );
}

function initMap() {
  if (!window.L) {
    by('err').textContent = 'Leaflet 未加载，请检查当前网络或改用本地离线模式。';
    return;
  }
  const center = [
    (num('pickupLat') + num('dropoffLat')) / 2,
    (num('pickupLon') + num('dropoffLon')) / 2,
  ];
  state.map = L.map('map', { zoomControl: true, preferCanvas: true }).setView(center, 12);
  const dark = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 20,
    attribution: '&copy; OpenStreetMap &copy; CARTO',
  });
  const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap',
  });
  dark.addTo(state.map);

  ['medical', 'dynamic', 'system', 'astar', 'routes', 'coordination', 'fleet'].forEach((name) => {
    state.layers[name] = L.layerGroup().addTo(state.map);
  });

  L.control.layers(
    { '暗色底图': dark, '标准 OSM': osm },
    {
      '医疗点位': state.layers.medical,
      '动态障碍': state.layers.dynamic,
      '系统风险障碍': state.layers.system,
      'A* 离散航点': state.layers.astar,
      '三机航路': state.layers.routes,
      '接力/协同节点': state.layers.coordination,
      '无人机编队': state.layers.fleet,
    },
    { collapsed: false },
  ).addTo(state.map);

  state.map.on('click', (event) => {
    if (!state.placing) return;
    addObstacle(event.latlng.lat, event.latlng.lng);
  });
  drawMedicalPoints();
  renderAgentChain();
  renderTimeline();
  renderObstacleTable();
  renderFleetStatus();
}

function drawMedicalPoints() {
  if (!state.map) return;
  state.layers.medical.clearLayers();
  L.marker(latLng(pickup()), { icon: medicalIcon('pickup') })
    .bindPopup(`<b>血站/取货点</b><br>${esc(by('pickupId').value)}`)
    .addTo(state.layers.medical);
  L.marker(latLng(dropoff()), { icon: medicalIcon('dropoff') })
    .bindPopup(`<b>医院/接收点</b><br>${esc(by('dropoffId').value)}`)
    .addTo(state.layers.medical);
  state.map.fitBounds(L.latLngBounds([latLng(pickup()), latLng(dropoff())]).pad(0.5));
}

function deliveryPoints(useCurrent) {
  const current = currentPrimaryPoint();
  const fromCurrent = useCurrent && by('fromCurrent').checked && current;
  const start = fromCurrent ? {
    id: 'UAV_CURRENT_POSITION', lon: Number(current.lon), lat: Number(current.lat),
    role: 'pickup', ready_time: by('pickupReady').value,
  } : {
    id: by('pickupId').value, lon: num('pickupLon'), lat: num('pickupLat'),
    role: 'pickup', ready_time: by('pickupReady').value,
  };
  return [start, {
    id: by('dropoffId').value, lon: num('dropoffLon'), lat: num('dropoffLat'),
    role: 'dropoff', deadline: by('dropoffDeadline').value,
  }];
}

function buildPayload(useCurrent = false) {
  return {
    task_id: by('taskId').value.trim(),
    requirement_xml_path: by('xmlPath').value.trim() || 'data/requirement.xml',
    mission_type: by('missionType').value,
    delivery_points: deliveryPoints(useCurrent),
    cargo_weight_kg: num('cargoWeight'),
    priority: num('priority'),
    environmental_constraints: {
      max_wind_speed_mps: 10,
      max_precipitation_mm_h: 5,
      minimum_visibility_km: 2,
      maximum_altitude_m: 120,
      custom_obstacles: state.obstacles,
    },
    output_requirements: {
      format: 'json', need_risk_assessment: true,
      need_orchestration_trace: true, need_llm_analysis: true,
    },
    simulation_scenario: by('scenario').value,
  };
}

async function submitTask(useCurrent = false) {
  clearTimeout(state.replanTimer);
  if (state.requestController) state.requestController.abort();
  state.requestController = new AbortController();
  const serial = ++state.requestSerial;
  by('err').textContent = '';
  by('submitBtn').disabled = true;
  by('submitBtn').textContent = '调度计算中…';
  pause();
  drawMedicalPoints();
  try {
    const response = await fetch('/api/v1/task/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload(useCurrent)),
      signal: state.requestController.signal,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(result));
    if (serial !== state.requestSerial) return;
    renderResult(result);
  } catch (error) {
    if (error.name !== 'AbortError') by('err').textContent = `请求失败：${error.message}`;
  } finally {
    if (serial === state.requestSerial) {
      by('submitBtn').disabled = false;
      by('submitBtn').textContent = '启动多智能体调度';
    }
  }
}

function scheduleReplan() {
  if (!by('autoReplan').checked) return;
  clearTimeout(state.replanTimer);
  state.replanTimer = setTimeout(() => submitTask(true), 420);
}

function solution() {
  return state.data?.recommended_solution || state.data?.final_dispatch_solution || {};
}

function renderResult(data) {
  state.data = data;
  const sol = solution();
  const risk = data.risk_assessment || {};
  by('src').textContent = sol.telemetry_source || 'LIVE_SIMULATION';
  by('algo').textContent = `算法：${sol.algorithm_used || sol.algorithm || '--'}`;
  by('risk').textContent = `风险：${risk.risk_level || '--'} ${risk.risk_score ?? ''}`;
  state.fleet = normalizeFleet(sol);
  state.frame = 0;
  renderOverview(sol, data);
  renderFleetMatrix();
  renderFleetStatus();
  renderRouteSelection(sol);
  renderAvoidance(sol);
  renderObstacleTable();
  drawAllLayers(sol);
  setFrame(0);
  by('raw').textContent = JSON.stringify(data, null, 2);
  play();
}

function normalizeFleet(sol) {
  const backend = sol.multi_uav_plan?.uavs || [];
  if (backend.length >= 2) {
    return backend.map((uav, index) => normalizeUav(uav, index));
  }
  const base = sol.smoothed_trajectory || sol.telemetry_stream || sol.route_polyline_geo || [];
  if (!base.length) return [];
  return [
    normalizeUav({ uav_id: sol.uav_id || 'UAV-MED-001', role: '主运输机', assignment: '血液/样本主运输', altitude_layer_m: 86, color: COLORS.primary, trajectory: base }, 0),
    normalizeUav({ uav_id: 'UAV-MED-002', role: '护航中继机', assignment: '高风险航段伴飞和通信中继', altitude_layer_m: 102, color: COLORS.escort, delay_seconds: 7, trajectory: offsetTrajectory(base, 0.0021, 0.0015, 14) }, 1),
    normalizeUav({ uav_id: 'UAV-CARGO-003', role: '备援接管机', assignment: '机巢待命，主机异常时接管', altitude_layer_m: 116, color: COLORS.backup, delay_seconds: 16, trajectory: backupTrajectory(base) }, 2),
  ];
}

function normalizeUav(uav, index) {
  return {
    id: uav.uav_id || `UAV-${index + 1}`,
    role: uav.role || ['主运输机', '护航中继机', '备援接管机'][index] || '协同无人机',
    assignment: uav.assignment || uav.action || '执行协同任务',
    altitude: Number(uav.altitude_layer_m || 86 + index * 15),
    delay: Number(uav.delay_seconds || index * 6),
    color: uav.color || [COLORS.primary, COLORS.escort, COLORS.backup][index] || '#fff',
    trajectory: (uav.trajectory || []).map((p) => ({ ...p, lon: Number(p.lon), lat: Number(p.lat) })),
    marker: null,
    trail: null,
    status: index === 2 ? '待命' : '执行中',
  };
}

function offsetTrajectory(points, dLon, dLat, altitudeOffset) {
  return points.map((p) => ({
    ...p,
    lon: Number(p.lon) + dLon,
    lat: Number(p.lat) + dLat,
    altitude_m: Number(p.altitude_m || 88) + altitudeOffset,
  }));
}

function backupTrajectory(points) {
  const shifted = offsetTrajectory(points, -0.0023, 0.0010, 28);
  const holdCount = Math.max(10, Math.floor(shifted.length * 0.28));
  const first = shifted[0];
  return [...Array.from({ length: holdCount }, (_, i) => ({ ...first, t_seconds: i })), ...shifted];
}

function renderOverview(sol, data) {
  const values = [
    ['任务状态', data.mission_status || '--'],
    ['主算法', sol.algorithm_used || sol.algorithm || '--'],
    ['协同策略', '主运输 + 护航中继 + 备援'],
    ['任务距离', metric(sol.flight_distance_km, ' km')],
    ['耗时', metric(sol.estimated_duration_mins, ' min')],
    ['能耗', metric(sol.estimated_energy_kj, ' kJ')],
    ['A* 航点', sol.raw_astar_waypoints?.length || 0],
    ['在线 UAV', state.fleet.length],
    ['动态障碍', state.obstacles.length],
    ['重规划触发', sol.replanning_trigger || 'initial_plan'],
  ];
  by('overview').innerHTML = values.map(([name, value]) => `<div class="mini"><small>${esc(name)}</small><b>${esc(value)}</b></div>`).join('');
}

function renderAgentChain() {
  const agents = [
    ['任务解析', 'Orchestrator', '#34d399', 'READY'],
    ['环境感知', 'Air/Weather/UAV/Dock', '#34d399', 'DONE'],
    ['三维航路', 'A* Planner', '#22d3ee', 'ACTIVE'],
    ['多机分配', 'CoordField Agent', '#22d3ee', 'ACTIVE'],
    ['风险评估', 'Risk Agent', '#a78bfa', 'DONE'],
    ['派发执行', 'Dispatch Agent', '#a78bfa', 'READY'],
  ];
  by('agentChain').innerHTML = agents.map(([name, system, color, status]) => `
    <div class="agentNode"><span class="dot" style="background:${color}"></span><div><b>${name}</b><small>${system}</small></div><em>${status}</em></div>`).join('');
}

function renderTimeline() {
  const stages = [['任务接收', 18], ['环境并行检查', 36], ['A* 航路搜索', 58], ['多 UAV 分配', 76], ['风险评估', 90], ['派发执行', 100]];
  by('dispatchTimeline').innerHTML = stages.map(([name, progress]) => `
    <div class="tl"><b>${name}</b><div class="tlbar"><span style="width:${progress}%"></span></div><small>${progress}%</small></div>`).join('');
}

function renderFleetMatrix() {
  if (!state.fleet.length) {
    by('uavMatrix').textContent = '等待调度。';
    return;
  }
  by('uavMatrix').innerHTML = `<table class="table"><tr><th>UAV</th><th>角色</th><th>高度层</th><th>任务</th></tr>${state.fleet.map((uav) => `
    <tr><td style="color:${uav.color}">${esc(uav.id)}</td><td>${esc(uav.role)}</td><td>${uav.altitude} m</td><td>${esc(uav.assignment)}</td></tr>`).join('')}</table>`;
}

function renderFleetStatus() {
  if (!state.fleet.length) {
    by('fleetStatus').innerHTML = '';
    by('uavCount').textContent = '0';
    return;
  }
  by('uavCount').textContent = String(state.fleet.length);
  by('fleetStatus').innerHTML = state.fleet.map((uav) => `
    <div class="fleetCard"><div class="roleLine"><span class="roleDot" style="background:${uav.color}"></span><b>${esc(uav.id)}</b></div><small>${esc(uav.role)} · ${esc(uav.status)}</small></div>`).join('');
}

function renderRouteSelection(sol) {
  const candidates = sol.candidate_corridors || [];
  let html = '';
  if (candidates.length) {
    html += `<table class="table"><tr><th>候选</th><th>耗时</th><th>能耗</th><th>结果</th></tr>${candidates.map((candidate) => `
      <tr><td>${esc(candidate.corridor_name)}</td><td>${candidate.duration_mins}</td><td>${candidate.energy_kj}</td><td>${candidate.corridor_name === sol.selected_corridor ? '已选' : '未选'}</td></tr>`).join('')}</table>`;
  }
  html += `<div class="step"><b>多智能体决策说明</b><p>${esc(sol.replanning_explanation || '调度器联合时间窗、能耗、障碍风险、UAV 电量和备援资源选择主航路，并为护航机与备援机分配高度层和时序。')}</p></div>`;
  by('routeSelection').innerHTML = html;
}

function renderAvoidance(sol) {
  const explanations = sol.obstacle_avoidance_explanation || [];
  by('avoidance').innerHTML = explanations.length ? explanations.map((text) => `<div class="step"><b>A* 避障</b><p>${esc(text)}</p></div>`).join('') : '暂无避障解释。';
}

function addObstacle(lat, lon) {
  const kind = by('obsType').value;
  state.obstacles.push({
    id: `USER_OBS_${String(state.nextObstacleId++).padStart(3, '0')}`,
    kind,
    center_lon: Number(lon),
    center_lat: Number(lat),
    radius_km: Math.max(0.15, num('obsRadius')),
    name: kindLabel(kind),
  });
  renderObstacleTable();
  drawDynamicObstacles();
  scheduleReplan();
}

function removeObstacle(id, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  state.obstacles = state.obstacles.filter((item) => item.id !== id);
  renderObstacleTable();
  drawDynamicObstacles();
  scheduleReplan();
}
window.removeObstacle = removeObstacle;

function changeObstacle(id, field, value) {
  const obstacle = state.obstacles.find((item) => item.id === id);
  if (!obstacle) return;
  if (field === 'kind') obstacle.kind = value;
  if (field === 'radius') obstacle.radius_km = Math.max(0.15, Number((obstacle.radius_km + Number(value)).toFixed(2)));
  renderObstacleTable();
  drawDynamicObstacles();
  scheduleReplan();
}
window.changeObstacle = changeObstacle;

function clearObstacles() {
  state.obstacles = [];
  renderObstacleTable();
  drawDynamicObstacles();
  scheduleReplan();
}

function kindLabel(kind) {
  return ({ building: '高层建筑群', powerline: '高压线走廊', sensitive: '人口密集敏感区', restricted: '临时受限区', weather: '恶劣天气单元' })[kind] || kind;
}

function renderObstacleTable() {
  if (!state.obstacles.length) {
    by('obsPanel').textContent = '暂无障碍。';
    return;
  }
  by('obsPanel').innerHTML = `<table class="table"><tr><th>ID</th><th>类型</th><th>半径</th><th>操作</th></tr>${state.obstacles.map((obstacle) => `
    <tr><td>${obstacle.id}</td><td><select onchange="changeObstacle('${obstacle.id}','kind',this.value)"><option value="building" ${obstacle.kind === 'building' ? 'selected' : ''}>建筑群</option><option value="powerline" ${obstacle.kind === 'powerline' ? 'selected' : ''}>高压线</option><option value="sensitive" ${obstacle.kind === 'sensitive' ? 'selected' : ''}>敏感区</option><option value="restricted" ${obstacle.kind === 'restricted' ? 'selected' : ''}>受限区</option><option value="weather" ${obstacle.kind === 'weather' ? 'selected' : ''}>天气</option></select></td><td>${obstacle.radius_km.toFixed(2)} km</td><td><button class="ghost" onclick="changeObstacle('${obstacle.id}','radius',-0.1)">−</button><button class="ghost" onclick="changeObstacle('${obstacle.id}','radius',0.1)">＋</button><button class="danger" onclick="removeObstacle('${obstacle.id}',event)">删除</button></td></tr>`).join('')}</table>`;
}

function drawAllLayers(sol) {
  drawMedicalPoints();
  drawDynamicObstacles();
  drawSystemObstacles(sol);
  drawAstar(sol);
  drawFleet(sol);
  const routePoints = state.fleet.flatMap((uav) => uav.trajectory.map(latLng));
  const bounds = [latLng(pickup()), latLng(dropoff()), ...routePoints, ...state.obstacles.map((o) => [o.center_lat, o.center_lon])];
  if (bounds.length > 1) state.map.fitBounds(L.latLngBounds(bounds).pad(0.2));
}

function drawDynamicObstacles() {
  if (!state.map) return;
  state.layers.dynamic.clearLayers();
  state.obstacles.forEach((obstacle) => drawObstacle(obstacle, state.layers.dynamic, true));
}

function drawSystemObstacles(sol) {
  state.layers.system.clearLayers();
  (sol.obstacle_zones || []).filter((obstacle) => obstacle.source !== 'frontend_dynamic_obstacle').forEach((obstacle) => drawObstacle(obstacle, state.layers.system, false));
}

function obstacleKind(raw) {
  return ({ building_cluster: 'building', linear_obstacle: 'powerline', sensitive_area: 'sensitive', no_fly_zone: 'restricted', weather_cell: 'weather' })[raw] || raw;
}

function obstaclePopup(obstacle, editable) {
  const kind = obstacleKind(obstacle.kind);
  const deleteButton = editable ? `<br><button class="danger" onclick="removeObstacle('${obstacle.id}',event)">删除该障碍</button>` : '';
  return `<b>${esc(obstacle.id || kindLabel(kind))}</b><br>${esc(kindLabel(kind))}<br>影响半径 ${metric(obstacle.radius_km, ' km')}${deleteButton}`;
}

function drawObstacle(obstacle, layer, editable) {
  const kind = obstacleKind(obstacle.kind);
  const lat = Number(obstacle.center_lat);
  const lon = Number(obstacle.center_lon);
  const radius = Number(obstacle.radius_km || 0.45);
  if (kind === 'building') {
    const offsets = [[0, 0], [0.0022, 0.0018], [-0.0018, 0.0014], [0.0012, -0.0021]];
    offsets.forEach(([dy, dx], index) => {
      L.rectangle([[lat + dy - 0.0013, lon + dx - 0.0012], [lat + dy + 0.0017 + index * 0.0002, lon + dx + 0.0012]], {
        color: '#cbd5e1', weight: 1, fillColor: COLORS.building, fillOpacity: 0.52,
      }).addTo(layer);
    });
    L.marker([lat, lon], { icon: makeDivIcon('<div class="building-icon"><span></span><span></span><span></span></div>', [52, 40], [26, 20]) })
      .bindPopup(obstaclePopup(obstacle, editable)).addTo(layer);
    return;
  }
  if (kind === 'powerline') {
    const sourceLine = obstacle.polyline_geo?.length ? obstacle.polyline_geo.map(latLng) : [[lat - radius * 0.005, lon - radius * 0.012], [lat + radius * 0.005, lon + radius * 0.012]];
    const shifted = sourceLine.map(([y, x]) => [y + 0.0012, x - 0.0007]);
    L.polyline(sourceLine, { color: COLORS.powerline, weight: 5, dashArray: '11 8', opacity: 0.9 }).bindPopup(obstaclePopup(obstacle, editable)).addTo(layer);
    L.polyline(shifted, { color: COLORS.powerline, weight: 2, opacity: 0.45 }).addTo(layer);
    sourceLine.forEach((point) => L.marker(point, { icon: simpleBadgeIcon('塔', '#d8b400') }).addTo(layer));
    return;
  }
  if (kind === 'sensitive') {
    const polygon = polygonAround(lat, lon, radius, 7, 1.35, 0.35);
    L.polygon(polygon, { color: COLORS.sensitive, weight: 3, fillColor: COLORS.sensitive, fillOpacity: 0.22, dashArray: '8 6' })
      .bindPopup(obstaclePopup(obstacle, editable)).addTo(layer);
    L.marker([lat, lon], { icon: simpleBadgeIcon('敏', COLORS.sensitive) }).addTo(layer);
    return;
  }
  if (kind === 'restricted') {
    const polygon = polygonAround(lat, lon, radius, 8, 1.15, 0.18);
    L.polygon(polygon, { color: COLORS.restricted, weight: 4, fillColor: COLORS.restricted, fillOpacity: 0.16, dashArray: '4 4' })
      .bindPopup(obstaclePopup(obstacle, editable)).addTo(layer);
    polygon.forEach((point, index) => { if (index % 2 === 0) L.circleMarker(point, { radius: 4, color: '#fff', fillColor: COLORS.restricted, fillOpacity: 1 }).addTo(layer); });
    L.marker([lat, lon], { icon: makeDivIcon('<div class="forbid-icon">禁</div>', [32, 32], [16, 16]) }).addTo(layer);
    return;
  }
  L.circle([lat, lon], { radius: radius * 1000, color: COLORS.weather, weight: 2, fillColor: COLORS.weather, fillOpacity: 0.18, dashArray: '5 7' })
    .bindPopup(obstaclePopup(obstacle, editable)).addTo(layer);
  L.marker([lat, lon], { icon: makeDivIcon('<div class="weather-icon">☁⚡</div>', [36, 30], [18, 15]) }).addTo(layer);
}

function polygonAround(lat, lon, radius, count, scaleX, rotation) {
  return Array.from({ length: count }, (_, index) => {
    const angle = rotation + Math.PI * 2 * index / count;
    return [lat + Math.sin(angle) * radius * 0.009, lon + Math.cos(angle) * radius * 0.009 * scaleX];
  });
}

function drawAstar(sol) {
  state.layers.astar.clearLayers();
  const raw = sol.raw_astar_waypoints || [];
  if (!raw.length) return;
  L.polyline(raw.map(latLng), { color: '#94a3b8', weight: 2, dashArray: '4 8', opacity: 0.7 }).addTo(state.layers.astar);
  raw.forEach((point, index) => { if (index % 3 === 0) L.circleMarker(latLng(point), { radius: 3, color: '#94a3b8', fillOpacity: 0.9 }).addTo(state.layers.astar); });
}

function drawFleet() {
  state.layers.routes.clearLayers();
  state.layers.coordination.clearLayers();
  state.layers.fleet.clearLayers();
  state.fleet.forEach((uav, index) => {
    if (!uav.trajectory.length) return;
    uav.trail = L.polyline(uav.trajectory.map(latLng), {
      color: uav.color, weight: index === 0 ? 6 : 3,
      opacity: index === 0 ? 0.9 : 0.65,
      dashArray: index === 0 ? null : '9 7',
    }).bindPopup(`<b>${esc(uav.id)}</b><br>${esc(uav.role)}<br>${esc(uav.assignment)}`).addTo(state.layers.routes);
    const start = uav.trajectory[0];
    uav.marker = L.marker(latLng(start), { icon: quadcopterIcon(uav.color, uav.id, uav.role), zIndexOffset: 1000 - index * 50 })
      .bindPopup(`<b>${esc(uav.id)}</b><br>${esc(uav.role)}<br>高度层 ${uav.altitude} m`).addTo(state.layers.fleet);
    if (index > 0) {
      const relay = uav.trajectory[Math.floor(uav.trajectory.length * (index === 1 ? 0.48 : 0.68))];
      L.marker(latLng(relay), { icon: makeDivIcon('<div class="relay-icon">R</div>', [29, 29], [14, 14]) })
        .bindPopup(index === 1 ? '护航中继节点' : '备援接管节点').addTo(state.layers.coordination);
    }
  });
}

function setFrame(frame) {
  if (!state.fleet.length) {
    by('progress').style.width = '0%';
    return;
  }
  const maxLength = Math.max(...state.fleet.map((uav) => uav.trajectory.length), 1);
  state.frame = Math.max(0, Math.min(frame, maxLength - 1));
  state.fleet.forEach((uav, index) => {
    if (!uav.marker || !uav.trajectory.length) return;
    const delayedFrame = Math.max(0, state.frame - Math.round(uav.delay / 2));
    const positionIndex = Math.min(delayedFrame, uav.trajectory.length - 1);
    const point = uav.trajectory[positionIndex];
    uav.marker.setLatLng(latLng(point));
    uav.status = positionIndex >= uav.trajectory.length - 1 ? '已到达' : (index === 2 && state.frame < Math.round(uav.delay / 2) ? '机巢待命' : '执行中');
  });
  const primary = state.fleet[0];
  const point = primary.trajectory[Math.min(state.frame, primary.trajectory.length - 1)];
  by('timeNow').textContent = `T+${point?.t_seconds ?? state.frame}s`;
  by('phase').textContent = point?.phase || 'coordinated_flight';
  by('pos').textContent = point ? `${point.lon.toFixed(5)}, ${point.lat.toFixed(5)}` : '--';
  by('alt').textContent = `${point?.altitude_m ?? primary.altitude} m`;
  by('speed').textContent = `${point?.speed_kmh ?? 50} km/h`;
  by('progress').style.width = `${((state.frame + 1) / maxLength) * 100}%`;
  renderFleetStatus();
}

function play() {
  pause();
  if (!state.fleet.length) return;
  state.timer = setInterval(() => {
    const maxLength = Math.max(...state.fleet.map((uav) => uav.trajectory.length), 1);
    setFrame(state.frame + 1);
    if (state.frame >= maxLength - 1) pause();
  }, 220);
}
function pause() { if (state.timer) clearInterval(state.timer); state.timer = null; }
function restart() { setFrame(0); play(); }

function togglePlacement() {
  state.placing = !state.placing;
  by('placeBtn').textContent = state.placing ? '关闭地图放障碍' : '开启地图放障碍';
  by('placeState').textContent = `放障碍：${state.placing ? 'ON' : 'OFF'}`;
  by('placeState').className = `tag ${state.placing ? 'red' : 'yellow'}`;
  if (state.map) state.map.getContainer().style.cursor = state.placing ? 'crosshair' : '';
}

function bindEvents() {
  by('submitBtn').addEventListener('click', () => submitTask(false));
  by('placeBtn').addEventListener('click', togglePlacement);
  by('clearBtn').addEventListener('click', clearObstacles);
  by('weatherBtn').addEventListener('click', () => { by('scenario').value = 'bad_weather'; submitTask(false); });
  by('playBtn').addEventListener('click', play);
  by('pauseBtn').addEventListener('click', pause);
  by('restartBtn').addEventListener('click', restart);
  by('replanBtn').addEventListener('click', () => submitTask(true));
}

bindEvents();
initMap();
