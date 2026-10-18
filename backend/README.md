# ZynapseX Backend: Smart Grid Intelligence System

**Detect. Decide. Respond.** FastAPI backend for the ZynapseX dashboard: a seeded grid simulator (T01-T20, 4 substations), an anomaly + risk pipeline with explanations, a rule-based decision-support engine, an illustrative what-if simulator, SQLite persistence, REST and a WebSocket stream.

> **Honest scope**
> - All data is **simulated**. Nothing here talks to real equipment, and the system is **decision support only**: it never controls or switches anything.
> - The **risk score is a prototype risk index** from transparent engineering rules, **not a calibrated probability of real failure**. No model was trained on failure labels and no accuracy figures are claimed.
> - Nothing is deployed on IBM Z / LinuxONE and no IBM service is integrated (see [IBM Z / LinuxONE](#ibm-z--linuxone)).
> - The existing React frontend is now connected to these APIs and the `/ws/grid` stream. See [`docs/FRONTEND_INTEGRATION.md`](docs/FRONTEND_INTEGRATION.md) for the live contracts and local proxy setup.

## Verification status

| Part | Status |
|---|---|
| Backend suite | **70 passed** with `python -m pytest -q --basetemp .pytest_tmp` (2 Pydantic warnings during WebSocket tests) |
| Python syntax | **Passed** with `python -m compileall -q app` |
| REST and fault-flow checks | **Passed**: health, status, assets, detail/history, predictions, recommendations, scenario injection/clear, and illustrative what-if; overheating on T01 yielded anomaly 0.7713, HIGH risk 50.54, two alerts, and an inspection recommendation |
| Frontend production build | **Passed** with `npm run build` (Vite reports a >500 kB chunk advisory) |
| Browser UI | **Not visually verified in this environment**; no browser surface was available. |

Run the backend suite with:

```powershell
cd backend
python -m pytest -v --basetemp .pytest_tmp
```

On Windows environments where pytest cannot access its default temporary folder, pass `--basetemp .pytest_tmp` as above.

## Run locally (Windows PowerShell)

Terminal 1, backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

If PowerShell blocks the activate script: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

Terminal 2, frontend (your existing app):

```powershell
cd frontend
npm install
npm run dev
```

| What | URL |
|---|---|
| Backend | http://127.0.0.1:8000 |
| API docs (Swagger) | http://127.0.0.1:8000/docs |
| Health | http://127.0.0.1:8000/api/health |
| WebSocket | ws://127.0.0.1:8000/ws/grid |
| Frontend (Vite default) | http://localhost:5173 |

Quick check without the frontend (PowerShell):

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/grid/status
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/simulator/scenarios -ContentType 'application/json' -Body '{"asset_id":"T17","scenario":"overheating"}'
# wait ~30 s (about 15 samples), then:
Invoke-RestMethod http://127.0.0.1:8000/api/predictions/T17
Invoke-RestMethod http://127.0.0.1:8000/api/recommendations/T17
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/simulation/run -ContentType 'application/json' -Body '{"scenario_type":"take_offline","asset_id":"T17"}'
```

## Configuration

Environment variables (see `.env.example`; none are secrets). With uvicorn you can load a file via `uvicorn app.main:app --env-file .env`.

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./zynapsex.db` | SQLite file (relative to where you start uvicorn) |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | allowed frontend origins |
| `SAMPLE_INTERVAL_S` | `2.0` | seconds between simulator ticks |
| `SIMULATOR_SEED` | `42` | seed (same seed + same actions = same data) |
| `AUTOSTART_SIMULATOR` | `true` | start the single background loop on startup |
| `SCENARIO_RAMP_TICKS` | `15` | samples for a scenario to reach full strength |
| `READINGS_KEEP_PER_ASSET` / `PREDICTIONS_KEEP_PER_ASSET` | `3000` / `1000` | retention |
| `SIM_LOAD_LIMIT_PCT` / `SIM_CAUTION_PCT` | `100` / `90` | what-if limits (% of rating) |
| `DEPLOYMENT_TARGET` | `local` | label shown in `/api/health` only |

Engineering limits, risk weights and level cut-offs live in `app/config.py` (`DEFAULT_LIMITS`, `DEFAULT_WEIGHTS`, `DEFAULT_RISK_THRESHOLDS`) and are overridable through the `Settings` object.

## How it works

```
simulator tick -> features -> anomaly detection -> risk estimate -> level -> explanation
               -> alerts + recommendations -> SQLite -> WebSocket
```

**Simulator** (`app/simulator`): 20 transformers, 4 substations, ratings 1000-2500 kVA. Per-asset operating point, a slow load cycle, a first-order thermal model and noise. Scenarios (`overheating`, `excessive_load`, `abnormal_current`, `increasing_vibration`, `combined_stress`) ramp in linearly. Runs only in the backend; exactly one background loop exists per app (starting it again is a no-op).

**Features** (`app/processing/features.py`): current vs rated, voltage deviation %, frequency deviation, power-factor shortfall (vs 0.95), plus least-squares slopes of temperature, vibration and load over the last 10 samples.

**Anomaly detection** (`app/ml/anomaly.py`): Isolation Forest (fixed `random_state`) plus a z-score baseline, both fitted **only on simulated normal-operation data** (no labels), calibrated on a held-out normal run. `anomaly_score = max(isolation_forest_score, zscore_score)`; flagged at >= 0.5. On simulated normal data the flag rate was about 0.3-1 % in my checks. That is a false-alarm rate on simulated data, not accuracy on real faults.

**Risk estimate** (`app/ml/failure_prediction.py`), fully documented in the module:

1. Per-metric stress 0-1 from `(ok, warn, crit)` limits (0 below ok, 0.5 at warn, 1.0 at crit).
2. `risk = 100 * clip(0.30*weighted_stress + 0.55*worst_metric + 0.10*trend + 0.05*anomaly)`.
3. Levels: LOW < 25, MEDIUM < 50, HIGH < 70, CRITICAL >= 70 (so one metric at its critical limit gives HIGH; several together give CRITICAL).

Deterministic: same inputs give the same output.

**Explanations** (`app/ml/explainability.py`): factor points follow the additive risk formula and are sorted largest first, with the values and limits that produced them. Values are rounded to two decimals and terms below 0.1 points are omitted, so the displayed points can differ slightly from the rounded risk score.

**Decision engine** (`app/decision/decision_engine.py`): rules over the computed readings, features, anomaly and risk. Actions: inspect (urgent / routine / mechanical / electrical), reduce simulated load, evaluate load distribution, increase monitoring, run what-if. Each carries asset, priority, explanation, the concrete triggering conditions with values, and a timestamp. Recommendations are stored when new, escalated, or after a cooldown.

**Alerts** (`app/pipeline.py`): raised when a metric reaches its warning/critical stress, when risk is HIGH/CRITICAL, or after 3 consecutive anomaly samples. They are de-duplicated, escalate in severity, use hysteresis, and are resolved when the condition clears.

**What-if** (`app/simulation/what_if.py`): **illustrative** load redistribution, labelled as such in every response. Assumptions (also returned in the payload): no real topology or power flow; moved load is shifted in kVA to transformers in the same substation first (other substations only if `allow_cross_substation`); CRITICAL-risk transformers are not used as recipients; recipients are filled proportionally to headroom up to the load limit; voltage, losses and protection are ignored. It returns before/after loads, violations, a verdict (`ACCEPTABLE` / `CAUTION` / `UNSAFE`), an explanation and alternatives. It never changes live state or stored readings; only the run itself is stored.

**Database** (`app/database`): SQLite via SQLAlchemy. Tables: assets, sensor_readings, risk_predictions, alerts, recommendations, simulation_runs, events. Timestamps stored as UTC. Readings and predictions are pruned to the newest N per asset. History survives restarts, and the rolling feature window is re-warmed from it. Alerts left open by a previous run are closed at startup.

## API summary

Full table, JSON samples and WebSocket message types: [`docs/FRONTEND_INTEGRATION.md`](docs/FRONTEND_INTEGRATION.md). Interactive docs: `/docs`.

## IBM Z / LinuxONE

- **Current status: everything runs locally.** Nothing is deployed on IBM Z or LinuxONE and no IBM service is used or tested. `DEPLOYMENT_TARGET` is only a label.
- **Why it should port:** pure Python with no native code of its own (FastAPI, SQLAlchemy, NumPy, pandas, scikit-learn) and settings come from environment variables. I have **not** verified that these libraries install on s390x or on your specific image; run `pip install -r requirements.txt` there first and build from source if a wheel is missing.
- **How you could use the datathon environment:** run the backend on the provided LinuxONE/Linux VM (`uvicorn app.main:app --host 0.0.0.0 --port 8000`), point `CORS_ORIGINS` at the frontend origin, and move SQLite to a managed database by changing `DATABASE_URL` (SQLAlchemy is already used; the models use only portable types, though I have only designed against SQLite).
- Only claim IBM deployment in your presentation once you have actually run it there.

## Git and generated files

The repository root `.gitignore` and `backend/.gitignore` exclude `.env` files, Python virtual environments and caches, SQLite database files, `node_modules`, and Vite build output. Review `git status --short` from the repository root before committing; include the root README, frontend source/configuration, and backend source/tests/docs. Do not force-push or commit local databases, caches, build output, or secrets.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: app` | run uvicorn/pytest from inside `backend/` |
| Port 8000 in use | `uvicorn app.main:app --reload --port 8001` and update the Vite proxy |
| Browser CORS error | use the Vite proxy from the integration guide, or add your origin to `CORS_ORIGINS` |
| WebSocket stays "connecting" | the proxy needs `ws: true`; check `/api/health` shows `simulator_running: true` |
| `/api/predictions/T01` returns 503 | wait one sample interval after startup (no data yet) |
| Database locked | stop other processes using `zynapsex.db`, or delete the file to start fresh |
| `Activate.ps1` blocked | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| Want a clean slate | stop the server, delete `backend/zynapsex.db*` |

## Layout

```
backend/
  app/
    main.py  config.py  schemas.py  pipeline.py  streaming.py
    api/ (assets, sensors, alerts, predictions, decisions, simulation, deps)
    simulator/ (generator, scenarios)   processing/features.py
    ml/ (anomaly, failure_prediction, explainability)
    decision/decision_engine.py         simulation/what_if.py
    database/ (connection, models, repository)
  tests/    docs/FRONTEND_INTEGRATION.md
  requirements.txt  .env.example  .gitignore  pytest.ini
```

`pipeline.py` and `streaming.py` are additions to your suggested structure: the first is the single streaming loop that ties the modules together, the second is the WebSocket client registry.
