'use strict';

const W = 1200;
const H = 760;
const PAD = 70;
const BOUNDS = { minLon: 114.02, maxLon: 114.18, minLat: 22.50, maxLat: 22.68 };
const state = {
  data: null,
  obstacles: [],
  nextObstacleId: 1,
  placing: false,
  fleet: [],
  frame: 0,
  timer: null,
  requestController: null,
  requestSerial: 0,
  replanTimer: null,
};
const COLORS = { primary: '#22d3ee', escort: '#60a5fa', backup: '#facc15', building: '#64748b', powerline: '#facc15', sensitive: '#a78bfa', restricted: '#ef4444', weather: '#fb923c' };

function by(id) { return document.getElementById(id); }
function num(id) { return Number(by(id).value); }
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char])); }
function metric(value, suffix = '') { return value === undefined || value === null ? '--' : `${value}${suffix}`; }
function pickup() { return { lon: num('pickupLon'), lat: num('pickupLat'), id: by('pickupId').value }; }
function dropoff() { return { lon: num('dropoffLon'), lat: num('dropoffLat'), id: by('dropoffId').value }; }
function project(point) {
  return {
    x: PAD + (Number(point.lon) - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon) * (W - PAD * 2),
    y: H - PAD - (Number(point.lat) - BOUNDS.minLat) / (BOUNDS.maxLat - BOUNDS.minLat) * (H - PAD * 2),
  };
}
function inverse(x, y) {
  return {
    lon: BOUNDS.minLon + (x - PAD) / (W - PAD * 2) * (BOUNDS.maxLon - BOUNDS.minLon),
    lat: BOUNDS.minLat + (H - PAD - y) / (H - PAD * 2) * (BOUNDS.maxLat - BOUNDS.minLat),
  };
}
function currentPrimaryPoint() {
  const primary = state.fleet[0];
  if (!primary || !primary.trajectory.length) return null;
  return primary.trajectory[Math.min(state.frame, primary.trajectory.length - 1)];
}

function deliveryPoints(useCurrent) {
  const current = currentPrimaryPoint();
  const fromCurrent = useCurrent && by('fromCurrent').checked && current;
  const start = fromCurrent ? {
    id: 'UAV_CURRENT_POSITION', lon: Number(current.lon), lat: Number(current.lat), role: 'pickup', ready_time: by('pickupReady').value,
  } : {
    id: by('pickupId').value, lon: num('pickupLon'), lat: num('pickupLat'), role: 'pickup', ready_time: by('pickupReady').value,
  };
  return [start, { id: by('dropoffId').value, lon: num('dropoffLon'), lat: num('dropoffLat'), role: 'dropoff', deadline: by('dropoffDeadline').value }];
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
      max_wind_speed_mps: 10, max_precipitation_mm_h: 5,
      minimum_visibility_km: 2, maximum_altitude_m: 120,
      custom_obstacles: state.obstacles,
    },
    output_requirements: { format: 'json', need_risk_assessment: true, need_orchestration_trace: true, need_llm_analysis: true },
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
  try {
    const response = await fetch('/api/v1/task/submit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload(useCurrent)), signal: state.requestController.signal,
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
      by('submitBtn').textContent = '启动离线任务调度';
    }
  }
}

function scheduleReplan() {
  if (!by('autoReplan').checked) return;
  clearTimeout(state.replanTimer);
  state.replanTimer = setTimeout(() => submitTask(true), 420);
}
function solution() { return state.data?.recommended_solution || state.data?.final_dispatch_solution || {}; }

function renderResult(data) {
  state.data = data;
  const sol = solution();
  const risk = data.risk_assessment || {};
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
  renderAgentChain();
  drawMap(sol);
  setFrame(0);
  by('raw').textContent = JSON.stringify(data, null, 2);
  play();
}

function normalizeFleet(sol) {
  const backend = sol.multi_uav_plan?.uavs || [];
  if (backend.length >= 2) return backend.map((uav, index) => normalizeUav(uav, index));
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
    status: index === 2 ? '待命' : '执行中',
  };
}
function offsetTrajectory(points, dLon, dLat, altitudeOffset) {
  return points.map((p) => ({ ...p, lon: Number(p.lon) + dLon, lat: Number(p.lat) + dLat, altitude_m: Number(p.altitude_m || 88) + altitudeOffset }));
}
function backupTrajectory(points) {
  const shifted = offsetTrajectory(points, -0.0023, 0.0010, 28);
  const holdCount = Math.max(10, Math.floor(shifted.length * 0.28));
  return [...Array.from({ length: holdCount }, (_, i) => ({ ...shifted[0], t_seconds: i })), ...shifted];
}

function renderOverview(sol, data) {
  const items = [
    ['任务状态', data.mission_status || '--'], ['主算法', sol.algorithm_used || sol.algorithm || '--'],
    ['协同策略', '主运输 + 护航中继 + 备援'], ['任务距离', metric(sol.flight_distance_km, ' km')],
    ['耗时', metric(sol.estimated_duration_mins, ' min')], ['能耗', metric(sol.estimated_energy_kj, ' kJ')],
    ['A* 航点', sol.raw_astar_waypoints?.length || 0], ['在线 UAV', state.fleet.length],
    ['动态障碍', state.obstacles.length], ['重规划触发', sol.replanning_trigger || 'initial_plan'],
  ];
  by('overview').innerHTML = items.map(([name, value]) => `<div class="mini"><small>${esc(name)}</small><b>${esc(value)}</b></div>`).join('');
}
function renderFleetMatrix() {
  by('uavMatrix').innerHTML = state.fleet.length ? `<table class="table"><tr><th>UAV</th><th>角色</th><th>高度层</th><th>任务</th></tr>${state.fleet.map((uav) => `<tr><td style="color:${uav.color}">${esc(uav.id)}</td><td>${esc(uav.role)}</td><td>${uav.altitude} m</td><td>${esc(uav.assignment)}</td></tr>`).join('')}</table>` : '等待调度。';
}
function renderFleetStatus() {
  by('uavCount').textContent = String(state.fleet.length);
  by('fleetStatus').innerHTML = state.fleet.map((uav) => `<div class="fleetCard"><div class="roleLine"><span class="roleDot" style="background:${uav.color}"></span><b>${esc(uav.id)}</b></div><small>${esc(uav.role)} · ${esc(uav.status)}</small></div>`).join('');
}
function renderAgentChain() {
  const agents = [['任务解析', 'Orchestrator', '#34d399', 'READY'], ['环境感知', 'Air/Weather/UAV/Dock', '#34d399', 'DONE'], ['三维航路', 'A* Planner', '#22d3ee', 'ACTIVE'], ['多机分配', 'CoordField Agent', '#22d3ee', 'ACTIVE'], ['风险评估', 'Risk Agent', '#a78bfa', 'DONE'], ['派发执行', 'Dispatch Agent', '#a78bfa', 'READY']];
  by('agentChain').innerHTML = agents.map(([name, system, color, status]) => `<div class="agentNode"><span class="dot" style="background:${color}"></span><div><b>${name}</b><small>${system}</small></div><em>${status}</em></div>`).join('');
}
function renderRouteSelection(sol) {
  const candidates = sol.candidate_corridors || [];
  let html = '';
  if (candidates.length) html += `<table class="table"><tr><th>候选</th><th>耗时</th><th>能耗</th><th>结果</th></tr>${candidates.map((item) => `<tr><td>${esc(item.corridor_name)}</td><td>${item.duration_mins}</td><td>${item.energy_kj}</td><td>${item.corridor_name === sol.selected_corridor ? '已选' : '未选'}</td></tr>`).join('')}</table>`;
  html += `<div class="step"><b>调度说明</b><p>${esc(sol.replanning_explanation || '系统联合时间窗、能耗、风险、动态障碍和 UAV 资源状态进行重规划。')}</p></div>`;
  by('routeSelection').innerHTML = html;
}
function renderAvoidance(sol) {
  const explanations = sol.obstacle_avoidance_explanation || [];
  by('avoidance').innerHTML = explanations.length ? explanations.map((text) => `<div class="step"><b>A* 避障</b><p>${esc(text)}</p></div>`).join('') : '暂无避障解释。';
}

function addObstacle(lat, lon) {
  const kind = by('obsType').value;
  state.obstacles.push({ id: `USER_OBS_${String(state.nextObstacleId++).padStart(3, '0')}`, kind, center_lon: Number(lon), center_lat: Number(lat), radius_km: Math.max(0.15, num('obsRadius')), name: kindLabel(kind) });
  renderObstacleTable();
  drawMap(solution());
  scheduleReplan();
}
function removeObstacle(id, event) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  state.obstacles = state.obstacles.filter((item) => item.id !== id);
  renderObstacleTable();
  drawMap(solution());
  scheduleReplan();
}
window.removeObstacle = removeObstacle;
function changeObstacle(id, field, value) {
  const item = state.obstacles.find((obstacle) => obstacle.id === id);
  if (!item) return;
  if (field === 'kind') item.kind = value;
  if (field === 'radius') item.radius_km = Math.max(0.15, Number((item.radius_km + Number(value)).toFixed(2)));
  renderObstacleTable();
  drawMap(solution());
  scheduleReplan();
}
window.changeObstacle = changeObstacle;
function clearObstacles() { state.obstacles = []; renderObstacleTable(); drawMap(solution()); scheduleReplan(); }
function kindLabel(kind) { return ({ building: '高层建筑群', powerline: '高压线走廊', sensitive: '人口密集敏感区', restricted: '临时受限区', weather: '恶劣天气单元', building_cluster: '高层建筑群', linear_obstacle: '高压线走廊', sensitive_area: '人口密集敏感区', no_fly_zone: '临时受限区', weather_cell: '恶劣天气单元' })[kind] || kind; }
function renderObstacleTable() {
  by('obsPanel').innerHTML = state.obstacles.length ? `<table class="table"><tr><th>ID</th><th>类型</th><th>半径</th><th>操作</th></tr>${state.obstacles.map((obstacle) => `<tr><td>${obstacle.id}</td><td><select onchange="changeObstacle('${obstacle.id}','kind',this.value)"><option value="building" ${obstacle.kind === 'building' ? 'selected' : ''}>建筑群</option><option value="powerline" ${obstacle.kind === 'powerline' ? 'selected' : ''}>高压线</option><option value="sensitive" ${obstacle.kind === 'sensitive' ? 'selected' : ''}>敏感区</option><option value="restricted" ${obstacle.kind === 'restricted' ? 'selected' : ''}>受限区</option><option value="weather" ${obstacle.kind === 'weather' ? 'selected' : ''}>天气</option></select></td><td>${obstacle.radius_km.toFixed(2)} km</td><td><button class="ghost" onclick="changeObstacle('${obstacle.id}','radius',-0.1)">−</button><button class="ghost" onclick="changeObstacle('${obstacle.id}','radius',0.1)">＋</button><button class="danger" onclick="removeObstacle('${obstacle.id}',event)">删除</button></td></tr>`).join('')}</table>` : '暂无障碍。';
}

function svgDefs() {
  return `<defs><filter id="uavGlow"><feDropShadow dx="0" dy="0" stdDeviation="5" flood-color="#22d3ee" flood-opacity=".6"/></filter><pattern id="hatchSensitive" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><rect width="10" height="10" fill="#a78bfa" fill-opacity=".12"/><line x1="0" y1="0" x2="0" y2="10" stroke="#c4b5fd" stroke-opacity=".42" stroke-width="3"/></pattern></defs>`;
}
function pathPoints(points) { return points.map((point) => { const p = project(point); return `${p.x},${p.y}`; }).join(' '); }
function drawMap(sol = {}) {
  const svg = by('offlineMap');
  const background = `<image href="/frontend/data/shenzhen_offline_basemap.svg" x="0" y="0" width="1200" height="760" preserveAspectRatio="none"/><rect id="mapHitArea" x="0" y="0" width="1200" height="760" fill="transparent"/>`;
  const systemObstacles = (sol.obstacle_zones || []).filter((obstacle) => obstacle.source !== 'frontend_dynamic_obstacle');
  const obstacles = [...systemObstacles, ...state.obstacles.map((obstacle) => ({ ...obstacle, source: 'frontend' }))];
  const raw = sol.raw_astar_waypoints || [];
  let html = svgDefs() + background;
  html += raw.length ? `<polyline class="map-shape" points="${pathPoints(raw)}" fill="none" stroke="#cbd5e1" stroke-width="2" stroke-dasharray="5 8" opacity=".72"/>` : '';
  html += obstacles.map(drawObstacle).join('');
  html += drawFleetRoutes();
  html += drawMedicalMarker(pickup(), '血', '#34d399', '血站/起点');
  html += drawMedicalMarker(dropoff(), '医', '#fb7185', '医院/终点');
  svg.innerHTML = html;
  setFrame(state.frame);
}
function obstacleKind(kind) { return ({ building_cluster: 'building', linear_obstacle: 'powerline', sensitive_area: 'sensitive', no_fly_zone: 'restricted', weather_cell: 'weather' })[kind] || kind; }
function drawObstacle(obstacle) {
  const kind = obstacleKind(obstacle.kind);
  const center = project({ lon: obstacle.center_lon, lat: obstacle.center_lat });
  const radius = 24 + Number(obstacle.radius_km || 0.45) * 34;
  const editable = obstacle.source === 'frontend';
  let shape = '';
  if (kind === 'building') {
    shape = Array.from({ length: 5 }, (_, index) => `<rect x="${center.x - 28 + index * 12}" y="${center.y - 8 - index % 2 * 15}" width="18" height="${36 + index % 3 * 9}" rx="2" fill="#64748b" stroke="#dbeafe" stroke-width="1" opacity=".78"/>`).join('');
  } else if (kind === 'powerline') {
    const x1 = center.x - radius, x2 = center.x + radius, y1 = center.y + 14, y2 = center.y - 14;
    shape = `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#facc15" stroke-width="6" stroke-dasharray="13 9"/><line x1="${x1}" y1="${y1 + 7}" x2="${x2}" y2="${y2 + 7}" stroke="#facc15" stroke-width="2" opacity=".55"/>${[x1, center.x, x2].map((x, i) => `<path d="M${x - 8},${center.y + 25 - i * 14}L${x},${center.y - 19 - i * 2}L${x + 8},${center.y + 25 - i * 14}Z" fill="none" stroke="#facc15" stroke-width="2"/>`).join('')}`;
  } else if (kind === 'sensitive') {
    shape = `<polygon points="${polygonPoints(center.x, center.y, radius, 7, 1.25, 0.35)}" fill="url(#hatchSensitive)" stroke="#a78bfa" stroke-width="3" stroke-dasharray="8 6"/><text x="${center.x}" y="${center.y + 4}" fill="#e9d5ff" text-anchor="middle" font-size="13" font-weight="900">敏感区</text>`;
  } else if (kind === 'restricted') {
    shape = `<polygon points="${polygonPoints(center.x, center.y, radius, 8, 1.08, 0.18)}" fill="#ef4444" fill-opacity=".16" stroke="#ef4444" stroke-width="4" stroke-dasharray="5 4"/><circle cx="${center.x}" cy="${center.y}" r="17" fill="#ef4444" stroke="#fff" stroke-width="2"/><text x="${center.x}" y="${center.y + 5}" fill="#fff" text-anchor="middle" font-size="14" font-weight="900">禁</text>`;
  } else {
    shape = `<circle cx="${center.x}" cy="${center.y}" r="${radius}" fill="#fb923c" fill-opacity=".15" stroke="#fb923c" stroke-width="2" stroke-dasharray="6 7"/><text x="${center.x}" y="${center.y + 6}" fill="#fdba74" text-anchor="middle" font-size="22">☁⚡</text>`;
  }
  const deleteControl = editable ? `<g class="obstacle-action" data-delete-id="${obstacle.id}" data-interactive="true"><circle cx="${center.x + radius * .72}" cy="${center.y - radius * .72}" r="12" fill="#fb7185" stroke="#fff" stroke-width="2"/><text x="${center.x + radius * .72}" y="${center.y - radius * .72 + 5}" fill="#fff" text-anchor="middle" font-size="16" font-weight="900">×</text></g>` : '';
  return `<g data-interactive="true" data-obstacle-id="${esc(obstacle.id || '')}">${shape}<text x="${center.x + 15}" y="${center.y - radius - 8}" fill="${obstacleColor(kind)}" font-size="11" font-weight="900">${esc(obstacle.id || kindLabel(kind))}</text>${deleteControl}</g>`;
}
function obstacleColor(kind) { return COLORS[kind] || '#94a3b8'; }
function polygonPoints(cx, cy, radius, count, scaleX, rotation) { return Array.from({ length: count }, (_, index) => { const angle = rotation + Math.PI * 2 * index / count; return `${cx + Math.cos(angle) * radius * scaleX},${cy + Math.sin(angle) * radius}`; }).join(' '); }
function drawMedicalMarker(point, label, color, title) {
  const p = project(point);
  return `<g class="map-shape"><circle cx="${p.x}" cy="${p.y}" r="15" fill="${color}" stroke="#fff" stroke-width="3"/><text x="${p.x}" y="${p.y + 5}" fill="#06101d" text-anchor="middle" font-size="14" font-weight="900">${label}</text><text x="${p.x + 20}" y="${p.y - 12}" fill="${color}" font-size="12" font-weight="900">${title}</text></g>`;
}
function drawFleetRoutes() {
  return state.fleet.map((uav, index) => {
    const route = `<polyline class="map-shape" points="${pathPoints(uav.trajectory)}" fill="none" stroke="${uav.color}" stroke-width="${index === 0 ? 7 : 3}" stroke-linecap="round" stroke-linejoin="round" opacity="${index === 0 ? .92 : .62}" ${index === 0 ? '' : 'stroke-dasharray="10 8"'}/>`;
    return route + droneSvg(uav, index);
  }).join('');
}
function droneSvg(uav, index) {
  const id = safeId(uav.id);
  return `<g id="drone-${id}" class="map-shape" filter="url(#uavGlow)"><g transform="scale(.62)"><line x1="-22" y1="-22" x2="22" y2="22" stroke="${uav.color}" stroke-width="5"/><line x1="22" y1="-22" x2="-22" y2="22" stroke="${uav.color}" stroke-width="5"/><circle cx="-26" cy="-26" r="10" fill="none" stroke="${uav.color}" stroke-width="4"/><circle cx="26" cy="-26" r="10" fill="none" stroke="${uav.color}" stroke-width="4"/><circle cx="-26" cy="26" r="10" fill="none" stroke="${uav.color}" stroke-width="4"/><circle cx="26" cy="26" r="10" fill="none" stroke="${uav.color}" stroke-width="4"/><rect x="-13" y="-13" width="26" height="26" rx="6" fill="${uav.color}" stroke="#fff" stroke-width="3"/></g><rect x="-48" y="31" width="96" height="20" rx="7" fill="#020617" fill-opacity=".9" stroke="${uav.color}"/><text x="0" y="45" fill="${uav.color}" text-anchor="middle" font-size="10" font-weight="900">${esc(uav.id)} · ${esc(uav.role)}</text></g>`;
}
function safeId(value) { return String(value).replace(/[^a-zA-Z0-9_-]/g, '_'); }

function setFrame(frame) {
  if (!state.fleet.length) { by('progress').style.width = '0%'; return; }
  const maxLength = Math.max(...state.fleet.map((uav) => uav.trajectory.length), 1);
  state.frame = Math.max(0, Math.min(frame, maxLength - 1));
  state.fleet.forEach((uav, index) => {
    const delayedFrame = Math.max(0, state.frame - Math.round(uav.delay / 2));
    const pointIndex = Math.min(delayedFrame, uav.trajectory.length - 1);
    const point = uav.trajectory[pointIndex];
    const group = document.getElementById(`drone-${safeId(uav.id)}`);
    if (group && point) { const p = project(point); group.setAttribute('transform', `translate(${p.x},${p.y})`); }
    uav.status = pointIndex >= uav.trajectory.length - 1 ? '已到达' : (index === 2 && state.frame < Math.round(uav.delay / 2) ? '机巢待命' : '执行中');
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
function play() { pause(); if (!state.fleet.length) return; state.timer = setInterval(() => { const maxLength = Math.max(...state.fleet.map((uav) => uav.trajectory.length), 1); setFrame(state.frame + 1); if (state.frame >= maxLength - 1) pause(); }, 220); }
function pause() { if (state.timer) clearInterval(state.timer); state.timer = null; }
function restart() { setFrame(0); play(); }
function togglePlacement() { state.placing = !state.placing; by('placeBtn').textContent = state.placing ? '关闭地图放障碍' : '开启地图放障碍'; by('placeState').textContent = `放障碍：${state.placing ? 'ON' : 'OFF'}`; by('placeState').className = `tag ${state.placing ? 'red' : 'yellow'}`; by('offlineMap').style.cursor = state.placing ? 'crosshair' : 'default'; }

function handleMapClick(event) {
  const deleteTarget = event.target.closest('[data-delete-id]');
  if (deleteTarget) { event.preventDefault(); event.stopPropagation(); removeObstacle(deleteTarget.dataset.deleteId, event); return; }
  if (!state.placing) return;
  if (event.target.closest('[data-interactive="true"]')) return;
  const rect = by('offlineMap').getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width * W;
  const y = (event.clientY - rect.top) / rect.height * H;
  if (x < PAD || x > W - PAD || y < PAD || y > H - PAD) return;
  const point = inverse(x, y);
  addObstacle(point.lat, point.lon);
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
  by('offlineMap').addEventListener('click', handleMapClick);
}

bindEvents();
renderAgentChain();
renderObstacleTable();
drawMap({});
