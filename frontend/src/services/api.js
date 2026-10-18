const BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(body?.error?.message ?? `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return body;
}

const titleCase = value => value ? value[0] + value.slice(1).toLowerCase() : 'Unknown';
const regionName = id => (id ?? '').replace('SS-', 'Substation ');
export function mapAsset(item) {
  const reading = item.latest_reading ?? {};
  const level = item.risk?.risk_level ?? 'LOW';
  const risk = item.risk?.risk_score ?? 0;
  const index = Math.max(0, Number((item.asset_id ?? 'T01').replace(/\D/g, '')) - 1);
  const slot = index % 5;
  const cluster = item.substation_id?.slice(-1) ?? '1';
  const centers = { '1': [27, 28], '2': [72, 29], '3': [29, 72], '4': [72, 72] };
  const [cx, cy] = centers[cluster] ?? [50, 50];
  return {
    ...item, id: item.asset_id, region: regionName(item.substation_id), type: 'Power transformer',
    load: reading.load_pct ?? 0, risk, temp: reading.temperature ?? 0,
    status: level === 'LOW' ? 'Healthy' : level === 'CRITICAL' ? 'Critical' : 'Warning', riskLevel: level, health: Math.max(0, Math.round(100 - risk)),
    left: cx + (slot % 3 - 1) * 8, top: cy + (Math.floor(slot / 3) - 0.5) * 10,
    voltage: `${item.rating_kva} kVA`, current: reading.current ?? 0, latest_reading: reading,
  };
}
export function mapAlert(alert, assets = []) {
  const asset = assets.find(item => item.id === alert.asset_id);
  const level = alert.severity === 'CRITICAL' ? 'critical' : alert.severity === 'WARNING' ? 'warning' : 'info';
  return { ...alert, level, title: alert.code.replaceAll('_', ' '), asset: `${alert.asset_id}${asset ? ` · ${asset.name}` : ''}`,
    time: alert.timestamp ? new Date(alert.timestamp).toLocaleString() : '', detail: alert.message };
}
export async function getGridData() {
  const [status, rawAssets, rawAlerts, recommendations, events] = await Promise.all([
    request('/api/grid/status'), request('/api/assets'), request('/api/alerts?active_only=true&limit=100'),
    request('/api/recommendations'), request('/api/events?limit=20'),
  ]);
  const assets = rawAssets.map(mapAsset);
  return { assets, alerts: rawAlerts.map(a => mapAlert(a, assets)), recommendations, events,
    updatedAt: status.last_update, status, system: status };
}
export async function getAsset(id) { return request(`/api/assets/${encodeURIComponent(id)}`); }
export async function getAssetReadings(id, limit = 120) { return request(`/api/assets/${encodeURIComponent(id)}/readings?limit=${limit}`); }
export async function getPrediction(id, history = 100) { return request(`/api/predictions/${encodeURIComponent(id)}?history=${history}`); }
export async function getAlerts() { return request('/api/alerts?active_only=true&limit=100'); }
export async function getEvents(limit = 50) { return request(`/api/events?limit=${limit}`); }
export async function getScenarios() { return request('/api/simulator/scenarios'); }
export async function injectScenario(asset_id, scenario, intensity = 1, duration_ticks = null) {
  return request('/api/simulator/scenarios', { method: 'POST', body: JSON.stringify({ asset_id, scenario, intensity, duration_ticks }) });
}
export async function clearScenario(id) { return request(`/api/simulator/scenarios/${encodeURIComponent(id)}`, { method: 'DELETE' }); }
export async function runWhatIf(payload) { return request('/api/simulation/run', { method: 'POST', body: JSON.stringify(payload) }); }
