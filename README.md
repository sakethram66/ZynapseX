# ZynapseX — Smart Grid Intelligence System

**Real-Time AI for Critical Decisions: Detect. Decide. Respond.**

ZynapseX is a simulation and decision-support prototype for monitoring a fleet of 20 simulated transformers. The React + Vite dashboard consumes live sensor data, risk assessments, alerts, and recommendations from a FastAPI backend. The backend persists readings and events in SQLite and streams updates over WebSockets.

## Scope and limitations

- All sensor and scenario data is simulated. The system does not communicate with or control electrical equipment.
- The Isolation Forest plus z-score novelty detector is fitted to simulated normal-operation data; it has no measured real-world accuracy.
- The risk score is a transparent prototype risk index, not a calibrated failure probability.
- A separate Random Forest provides a 12-tick synthetic event classification. Its uncalibrated score and provisional category are shown separately from the anomaly detector; the dashboard displays its held-out synthetic evaluation. Metrics do not represent real-world accuracy, and calibrated probabilities are not exposed.
- What-if load redistribution is illustrative and omits real topology, power flow, protection, and losses.
- The project runs locally. IBM Z/LinuxONE deployment has not been configured or verified.

## Architecture

```text
Backend simulator → feature processing → anomaly detection + separate synthetic failure classifier
                  → prototype risk scoring and explanations → alerts/recommendations → SQLite
                  → FastAPI REST + WebSocket → React/Vite dashboard
```

The simulator is the single source of sensor data. The frontend uses the REST API for initial state and history, then applies WebSocket snapshots and ticks for live updates. During development, Vite proxies `/api` and `/ws` to `127.0.0.1:8000`.

## Prerequisites

- Windows 10/11 with Python 3.10+ and Node.js 18+ (tested here with Python 3.13 and Node 24).
- PowerShell.
- Internet access for the first Python and npm dependency installation.

## Run locally on Windows

Open two PowerShell terminals from the repository directory.

**Terminal 1 — backend**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

If PowerShell blocks virtual-environment activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal and activate again. If the `uvicorn` command is unavailable, use `python -m uvicorn app.main:app --reload`.

**Terminal 2 — frontend**

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies REST and WebSocket requests to the local backend. Optional frontend overrides are documented in `frontend/.env.example`; copy it to `frontend/.env.local` only if needed. Never put secrets in Vite environment variables.

## Verify

Run from the repository root:

```powershell
cd backend
python -m pytest -q --basetemp .pytest_tmp
python -m compileall -q app
cd ..\frontend
npm run build
```

`--basetemp .pytest_tmp` avoids access-denied errors some Windows setups encounter with pytest's default temporary directory.

## Demo procedure

1. Start both services and open <http://localhost:5173>. Confirm the status strip reports the simulator and WebSocket connection.
2. Show the live asset readings, risk counts, charts, recommendations, and active alerts.
3. On the dashboard's **What if simulator**, select an asset and choose **overheating** (or **increasing vibration**, **excessive load**, **abnormal current**, or **combined stress**), then select **Inject scenario**. Effects ramp over 15 samples (about 30 seconds at the default interval).
4. Open that asset's card to show its updated reading, rule-based risk, separate anomaly score, synthetic failure-horizon classification, top model drivers, and recommendation. The classifier is explicitly synthetic-only and provides no calibrated probability. Open **Alerts** to review warnings; model-horizon alerts require three consecutive flagged ticks.
5. Return to the simulator and use **Run illustrative simulation** to compare taking an asset offline or reducing its load. The what-if calculation does not change live simulator state.
6. Select **Clear** for the asset to remove its injected scenario.

If a scenario does not create an alert, use a longer ramp period or a higher intensity and wait for the configured thresholds; the simulator never guarantees a particular risk result for every asset or scenario.

## Useful endpoints

| Purpose | URL |
|---|---|
| Dashboard | <http://localhost:5173> |
| Health | <http://127.0.0.1:8000/api/health> |
| Grid status | <http://127.0.0.1:8000/api/grid/status> |
| Assets | <http://127.0.0.1:8000/api/assets> |
| Active alerts | <http://127.0.0.1:8000/api/alerts?active_only=true> |
| Swagger | <http://127.0.0.1:8000/docs> |
| WebSocket | `ws://127.0.0.1:8000/ws/grid` |
| Failure-model evaluation | <http://127.0.0.1:8000/api/model/failure> |

For all routes, schemas, and WebSocket event details, see [`backend/docs/FRONTEND_INTEGRATION.md`](backend/docs/FRONTEND_INTEGRATION.md). Backend details and configuration are in [`backend/README.md`](backend/README.md).

For the synthetic dataset, label/horizon definition, repeatable Random Forest training, measured synthetic holdout metrics, and limitations, see [`backend/docs/FAILURE_MODEL.md`](backend/docs/FAILURE_MODEL.md).
