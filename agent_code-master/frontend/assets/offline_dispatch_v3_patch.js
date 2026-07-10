'use strict';

drawObstacle = function drawObstaclePatched(obstacle) {
  const kind = obstacleKind(obstacle.kind);
  const geoLine = obstacle.polyline_geo || [];
  const linePoints = geoLine.map((point) => project(point));
  const fallbackGeo = geoLine.length ? geoLine[Math.floor(geoLine.length / 2)] : pickup();
  const center = project({
    lon: obstacle.center_lon ?? fallbackGeo.lon,
    lat: obstacle.center_lat ?? fallbackGeo.lat,
  });
  const radius = 24 + Number(obstacle.radius_km || 0.45) * 34;
  const editable = obstacle.source === 'frontend';
  let shape = '';

  if (kind === 'building') {
    shape = Array.from({ length: 5 }, (_, index) => `<rect x="${center.x - 28 + index * 12}" y="${center.y - 8 - index % 2 * 15}" width="18" height="${36 + index % 3 * 9}" rx="2" fill="#64748b" stroke="#dbeafe" stroke-width="1" opacity=".78"/>`).join('');
  } else if (kind === 'powerline') {
    const points = linePoints.length ? linePoints : [
      { x: center.x - radius, y: center.y + 14 },
      { x: center.x + radius, y: center.y - 14 },
    ];
    const primaryLine = points.map((point) => `${point.x},${point.y}`).join(' ');
    const secondaryLine = points.map((point) => `${point.x - 2},${point.y + 7}`).join(' ');
    shape = `<polyline points="${primaryLine}" fill="none" stroke="#facc15" stroke-width="6" stroke-dasharray="13 9"/><polyline points="${secondaryLine}" fill="none" stroke="#facc15" stroke-width="2" opacity=".55"/>${points.map((point) => `<path d="M${point.x - 8},${point.y + 25}L${point.x},${point.y - 19}L${point.x + 8},${point.y + 25}Z" fill="none" stroke="#facc15" stroke-width="2"/>`).join('')}`;
  } else if (kind === 'sensitive') {
    shape = `<polygon points="${polygonPoints(center.x, center.y, radius, 7, 1.25, 0.35)}" fill="url(#hatchSensitive)" stroke="#a78bfa" stroke-width="3" stroke-dasharray="8 6"/><text x="${center.x}" y="${center.y + 4}" fill="#e9d5ff" text-anchor="middle" font-size="13" font-weight="900">敏感区</text>`;
  } else if (kind === 'restricted') {
    shape = `<polygon points="${polygonPoints(center.x, center.y, radius, 8, 1.08, 0.18)}" fill="#ef4444" fill-opacity=".16" stroke="#ef4444" stroke-width="4" stroke-dasharray="5 4"/><circle cx="${center.x}" cy="${center.y}" r="17" fill="#ef4444" stroke="#fff" stroke-width="2"/><text x="${center.x}" y="${center.y + 5}" fill="#fff" text-anchor="middle" font-size="14" font-weight="900">禁</text>`;
  } else {
    shape = `<circle cx="${center.x}" cy="${center.y}" r="${radius}" fill="#fb923c" fill-opacity=".15" stroke="#fb923c" stroke-width="2" stroke-dasharray="6 7"/><text x="${center.x}" y="${center.y + 6}" fill="#fdba74" text-anchor="middle" font-size="22">☁⚡</text>`;
  }

  const deleteControl = editable ? `<g class="obstacle-action" data-delete-id="${obstacle.id}" data-interactive="true"><circle cx="${center.x + radius * .72}" cy="${center.y - radius * .72}" r="12" fill="#fb7185" stroke="#fff" stroke-width="2"/><text x="${center.x + radius * .72}" y="${center.y - radius * .72 + 5}" fill="#fff" text-anchor="middle" font-size="16" font-weight="900">×</text></g>` : '';
  return `<g data-interactive="true" data-obstacle-id="${esc(obstacle.id || '')}">${shape}<text x="${center.x + 15}" y="${center.y - radius - 8}" fill="${obstacleColor(kind)}" font-size="11" font-weight="900">${esc(obstacle.id || kindLabel(kind))}</text>${deleteControl}</g>`;
};
