# Frontend integration guide

> This guide documents the verified backend contract used by the connected React frontend.
> The frontend adapts backend payloads in `frontend/src/services/api.js`; the Vite development
> server proxies `/api` and `/ws` to the local FastAPI service. The API fields below are returned
> by the running backend.

Units: voltage **kV**, current **A**, temperature **°C**, frequency **Hz**, load **%**, vibration **mm/s**,
power factor 0-1. All timestamps are ISO-8601 UTC (e.g. `2026-10-18T08:00:54Z`).

## 1. Dev connection (no CORS problems)

`frontend/vite.config.js` already proxies the API and WebSocket locally. Optional overrides can be
set in `frontend/.env.local` using the names in `.env.example`.

```js
export default defineConfig({
  // ...your existing plugins/config
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
```

The backend also allows CORS for `http://localhost:5173` and `http://127.0.0.1:5173`
(change with `CORS_ORIGINS`), so you can alternatively set `VITE_API_BASE_URL=http://127.0.0.1:8000`.

## 2. REST endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness, simulator state, WebSocket client count |
| GET | `/api/grid/status` | overview cards: totals, risk counts, anomalies, active alerts, average load |
| GET | `/api/assets` | all 20 assets with latest reading + risk summary |
| GET | `/api/assets/{id}` | asset detail: latest reading, full assessment, recommendations, active alerts |
| GET | `/api/assets/{id}/readings?limit=100&since=ISO` | chart history, oldest to newest |
| GET | `/api/readings/latest` | latest reading for every asset |
| GET | `/api/alerts?asset_id=&active_only=&limit=` | alerts, newest first |
| GET | `/api/events?asset_id=&limit=` | event timeline (alerts raised/resolved, scenarios injected/cleared) |
| GET | `/api/predictions` | latest risk assessment for every asset |
| GET | `/api/predictions/{id}?history=N` | assessment + explanation (+ last N scores for a sparkline) |
| GET | `/api/recommendations` | all currently active recommendations, most urgent first |
| GET | `/api/recommendations/{id}` | active recommendations for one asset |
| GET | `/api/recommendations/{id}/history?limit=` | stored recommendation history |
| GET | `/api/simulator/scenarios` | available scenarios + currently active injections |
| POST | `/api/simulator/scenarios` | inject: `{"asset_id":"T17","scenario":"overheating","intensity":1.0,"duration_ticks":null}` |
| DELETE | `/api/simulator/scenarios` or `/api/simulator/scenarios/{id}` | clear all / one |
| POST | `/api/simulation/run` | what-if (see below) |
| GET | `/api/simulation/history?limit=` | stored what-if runs |

Scenarios: `normal` (clears), `overheating`, `excessive_load`, `abnormal_current`,
`increasing_vibration`, `combined_stress`. Effects ramp in over about 15 samples.

What-if request: `{"scenario_type":"take_offline"|"reduce_load","asset_id":"T17","reduction_pct":25,"allow_cross_substation":true}`
(`reduction_pct` is required for `reduce_load`).

**Errors** always look like `{"error": {"code": 404, "message": "..."}}`; validation errors (422) add
`details: [{"field","message"}]`. Before the first simulator tick, `/api/predictions/{id}` returns 503 and
`/api/simulation/run` returns 409. Show a "waiting for data" state, not fake data.

## 3. WebSocket `/ws/grid`

Every message is `{"type": string, "timestamp": ISO, "data": ...}`.

| type | when | `data` |
|---|---|---|
| `snapshot` | once, right after connect | `status`, `assets[]`, `readings[]`, `risks[]` |
| `tick` | every sample interval (default 2 s) | `tick`, `readings[]` (20), `risks[]` (20, full assessments), `status` |
| `alert` | a new alert is raised | one alert |
| `recommendation` | a new or escalated recommendation is stored | one recommendation |
| `scenario` | a scenario is injected/cleared | `event`, `message`, `active` |
| `pong` | reply to the text message `ping` | `{}` |

Reconnect with backoff and treat each new `snapshot` as the source of truth after a reconnect.

## 4. Real response samples

Generated from the actual pipeline running the simulator with T17 overheating (values are simulated).

**Tick event** (trimmed to 1 reading / 1 risk)
```json
{
  "type": "tick",
  "timestamp": "2026-10-18T07:48:50.310368+00:00",
  "data": {
    "tick": 21,
    "readings": [
      {
        "timestamp": "2026-10-18T08:00:40Z",
        "asset_id": "T01",
        "substation_id": "SS-01",
        "voltage": 11.0322,
        "current": 30.41,
        "temperature": 53.35,
        "frequency": 49.9867,
        "load_pct": 57.58,
        "vibration": 1.577,
        "power_factor": 0.9585
      }
    ],
    "risks": [
      {
        "asset_id": "T01",
        "timestamp": "2026-10-18T08:00:40Z",
        "anomaly_score": 0.0,
        "is_anomaly": false,
        "anomaly_detail": "{...}",
        "risk_score": 0.0,
        "risk_level": "LOW",
        "components": {
          "weighted_stress": 0.0,
          "worst_stress": 0.0,
          "worst_factor": "temperature",
          "trend_stress": 0.0,
          "anomaly_score": 0.0
        },
        "trends": {
          "temp_slope": 0.0585,
          "vibration_slope": -0.0008,
          "load_slope": -0.033
        },
        "contributions": "[...]",
        "summary": "Risk LOW (0/100): all monitored factors are within normal ranges.",
        "disclaimer": "Prototype risk estimate from transparent engineering rules on simulated data. It is NOT a calibrated probability of real equipment failure."
      }
    ],
    "status": {
      "mode": "simulated",
      "deployment_target": "local",
      "simulator_running": false,
      "tick": 21,
      "sample_interval_s": 2.0,
      "last_update": "2026-10-18T08:00:40+00:00",
      "total_assets": 20,
      "substations": 4,
      "assets_reporting": 20,
      "risk_counts": {
        "LOW": 20,
        "MEDIUM": 0,
        "HIGH": 0,
        "CRITICAL": 0
      },
      "anomalies": 0,
      "active_alerts": 0,
      "average_load_pct": 62.0,
      "active_scenarios": {
        "T17": {
          "scenario": "overheating",
          "intensity": 1.0,
          "age_ticks": 1,
          "duration_ticks": null
        }
      }
    }
  }
}
```

**Asset summary** (`GET /api/assets` item)
```json
{
  "asset_id": "T17",
  "name": "Transformer T17",
  "substation_id": "SS-04",
  "rating_kva": 1250.0,
  "rated_current_a": 65.6,
  "latest_reading": {
    "timestamp": "2026-10-18T08:01:38Z",
    "asset_id": "T17",
    "substation_id": "SS-04",
    "voltage": 10.9709,
    "current": 44.15,
    "temperature": 98.56,
    "frequency": 50.0296,
    "load_pct": 67.19,
    "vibration": 1.777,
    "power_factor": 0.9546
  },
  "risk": {
    "risk_score": 67.5,
    "risk_level": "HIGH",
    "anomaly_score": 1.0,
    "is_anomaly": true,
    "summary": "Risk HIGH (68/100). Main contributors: winding/oil temperature (+62), statistical anomaly (+5)."
  },
  "active_scenario": {
    "scenario": "overheating",
    "intensity": 1.0,
    "age_ticks": 30,
    "duration_ticks": null
  }
}
```

**Risk assessment** (`GET /api/predictions/T17`, contributions trimmed to 2)
```json
{
  "asset_id": "T17",
  "timestamp": "2026-10-18T08:01:38Z",
  "anomaly_score": 1.0,
  "is_anomaly": true,
  "anomaly_detail": {
    "isolation_forest_score": 0.2259,
    "zscore_score": 1.0,
    "max_abs_z": 11.939,
    "top_deviations": [
      {
        "feature": "temperature",
        "abs_z": 11.94
      },
      {
        "feature": "current_ratio",
        "abs_z": 1.05
      },
      {
        "feature": "load_pct",
        "abs_z": 1.04
      }
    ]
  },
  "risk_score": 67.5,
  "risk_level": "HIGH",
  "components": {
    "weighted_stress": 0.25,
    "worst_stress": 1.0,
    "worst_factor": "temperature",
    "trend_stress": 0.0,
    "anomaly_score": 1.0
  },
  "trends": {
    "temp_slope": -0.1654,
    "vibration_slope": -0.0058,
    "load_slope": -0.3433
  },
  "contributions": [
    {
      "factor": "temperature",
      "label": "Winding/oil temperature",
      "value": 98.56,
      "unit": "°C",
      "stress": 1.0,
      "contribution_points": 62.5,
      "detail": "98.6 (above critical limit; ok≤65.0, warn≤80.0, crit≤95.0)"
    },
    {
      "factor": "anomaly",
      "label": "Statistical anomaly",
      "value": 1.0,
      "unit": "score",
      "stress": 1.0,
      "contribution_points": 5.0,
      "detail": "anomaly score 1.00 (flagged at ≥0.5)"
    }
  ],
  "summary": "Risk HIGH (68/100). Main contributors: winding/oil temperature (+62), statistical anomaly (+5).",
  "disclaimer": "Prototype risk estimate from transparent engineering rules on simulated data. It is NOT a calibrated probability of real equipment failure."
}
```

**Alert**
```json
{
  "id": 1,
  "asset_id": "T17",
  "code": "TEMP_HIGH",
  "severity": "WARNING",
  "message": "Temperature 81°C is at/above the warning limit (80.0°C).",
  "value": 80.99,
  "threshold": 80.0,
  "timestamp": "2026-10-18T08:00:54Z",
  "resolved_at": null
}
```

**Recommendation** (`id` is `null` for a live recommendation that has not been stored yet)
```json
{
  "id": null,
  "asset_id": "T17",
  "priority": "HIGH",
  "action": "INSPECT",
  "title": "Schedule an inspection of T17",
  "explanation": "Prototype risk index is HIGH, driven mainly by winding/oil temperature. Decision support only: nothing here controls real equipment or switching.",
  "triggering_conditions": [
    "risk_score=68/100 (HIGH)"
  ],
  "risk_level": "HIGH",
  "timestamp": "2026-10-18T08:01:38Z"
}
```

**Grid status**
```json
{
  "mode": "simulated",
  "deployment_target": "local",
  "simulator_running": false,
  "tick": 50,
  "sample_interval_s": 2.0,
  "last_update": "2026-10-18T08:01:38+00:00",
  "total_assets": 20,
  "substations": 4,
  "assets_reporting": 20,
  "risk_counts": {
    "LOW": 19,
    "MEDIUM": 0,
    "HIGH": 1,
    "CRITICAL": 0
  },
  "anomalies": 1,
  "active_alerts": 3,
  "average_load_pct": 61.32,
  "active_scenarios": {
    "T17": {
      "scenario": "overheating",
      "intensity": 1.0,
      "age_ticks": 30,
      "duration_ticks": null
    }
  }
}
```

**What-if result** (changes/assumptions trimmed)
```json
{
  "scenario_type": "take_offline",
  "asset_id": "T17",
  "reduction_pct": 100.0,
  "verdict": "ACCEPTABLE",
  "safe": true,
  "changes": [
    {
      "asset_id": "T16",
      "substation_id": "SS-04",
      "role": "recipient",
      "load_pct_before": 61.28,
      "load_pct_after": 72.29,
      "limit_pct": 100.0,
      "status_after": "OK"
    },
    {
      "asset_id": "T17",
      "substation_id": "SS-04",
      "role": "target",
      "load_pct_before": 67.19,
      "load_pct_after": 0.0,
      "limit_pct": 100.0,
      "status_after": "OFFLINE"
    }
  ],
  "violations": [],
  "unserved_kva": 0.0,
  "explanation": "Taking T17 offline moves about 840 kVA to 4 other transformer(s); all stay within the 100% limit and below the 90% caution level.",
  "alternatives": [],
  "assumptions": [
    "Illustrative simplified load redistribution; no real network topology or power-flow is modelled.",
    "Moved load is shifted to other transformers in kVA (load % x rating), same substation first.",
    "..."
  ],
  "illustrative": true,
  "timestamp": "2026-10-18T07:48:50.570535Z"
}
```

## 5. Reference wiring (illustrative and untested; adapt to your files)

`services/api.js`
```js
const BASE = import.meta.env.VITE_API_BASE_URL ?? ''   // '' = same origin via the Vite proxy

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const err = new Error(body?.error?.message ?? `HTTP ${res.status}`)
    err.status = res.status
    throw err               // surface it in the UI; do NOT fall back to fake data
  }
  return body
}

export const getGridStatus = () => request('/api/grid/status')
export const getAssets = () => request('/api/assets')
export const getAsset = (id) => request(`/api/assets/${id}`)
export const getReadings = (id, limit = 100) => request(`/api/assets/${id}/readings?limit=${limit}`)
export const getAlerts = (params = '') => request(`/api/alerts${params}`)
export const getEvents = (limit = 50) => request(`/api/events?limit=${limit}`)
export const getRecommendations = () => request('/api/recommendations')
export const injectScenario = (asset_id, scenario, intensity = 1) =>
  request('/api/simulator/scenarios', { method: 'POST', body: JSON.stringify({ asset_id, scenario, intensity }) })
export const clearScenario = (id) => request(`/api/simulator/scenarios/${id}`, { method: 'DELETE' })
export const runWhatIf = (payload) => request('/api/simulation/run', { method: 'POST', body: JSON.stringify(payload) })
```

`services/websocket.js`
```js
export function connectGrid(onMessage, onStatus) {
  let ws, retry = 0, closed = false, timer
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/grid`
  const open = () => {
    onStatus('connecting')
    ws = new WebSocket(url)
    ws.onopen = () => { retry = 0; onStatus('connected') }
    ws.onmessage = (e) => onMessage(JSON.parse(e.data))
    ws.onclose = () => {
      onStatus('disconnected')
      if (!closed) timer = setTimeout(open, Math.min(1000 * 2 ** retry++, 15000))
    }
  }
  open()
  return () => { closed = true; clearTimeout(timer); ws?.close() }
}
```

Hook sketch: on `snapshot` replace state; on `tick` append each reading to a per-asset array capped at
about 120 points and replace risks/status; on `alert`/`recommendation` prepend to their lists; expose
`connection` (`connecting|connected|disconnected`) and `error` so the UI can show loading, empty,
disconnected and error states.
