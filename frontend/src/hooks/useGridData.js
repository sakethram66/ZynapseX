import { useCallback, useEffect, useState } from 'react';
import { getAlerts, getEvents, getGridData, mapAlert, mapAsset } from '../services/api';

const initial = { assets: [], alerts: [], recommendations: [], events: [], system: {}, status: {}, readings: {}, histories: {}, risks: {}, loading: true, error: null };
export default function useGridData() {
  const [data, setData] = useState(initial);
  useEffect(() => {
    let active = true;
    getGridData().then(value => { if (active) setData({ ...initial, ...value, loading: false }); })
      .catch(error => { if (active) setData(current => ({ ...current, loading: false, error: error.message })); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    const refresh = () => Promise.all([getAlerts(), getEvents()]).then(([alerts, events]) => {
      if (active) setData(current => ({ ...current, alerts: alerts.map(a => mapAlert(a, current.assets)), events }));
    }).catch(() => {});
    const timer = setInterval(refresh, 10000);
    return () => { active = false; clearInterval(timer); };
  }, []);

  const handleMessage = useCallback(message => {
    const payload = message?.data ?? {};
    setData(current => {
      if (message.type === 'snapshot') return { ...current, assets: (payload.assets ?? []).map(mapAsset), system: payload.status ?? current.system,
        status: payload.status ?? current.status, readings: Object.fromEntries((payload.readings ?? []).map(r => [r.asset_id, r])), histories: Object.fromEntries((payload.readings ?? []).map(r => [r.asset_id, [r]])),
        risks: Object.fromEntries((payload.risks ?? []).map(r => [r.asset_id, r])), error: null };
      if (message.type === 'tick') {
        const readings = { ...current.readings };
        const histories = { ...current.histories };
        (payload.readings ?? []).forEach(r => { readings[r.asset_id] = r; histories[r.asset_id] = [...(histories[r.asset_id] ?? []), r].slice(-120); });
        const risks = { ...current.risks };
        (payload.risks ?? []).forEach(r => { risks[r.asset_id] = r; });
        const byId = new Map(current.assets.map(a => [a.id, a]));
        (payload.readings ?? []).forEach(r => { const old = byId.get(r.asset_id); if (old) byId.set(r.asset_id, mapAsset({ ...old, asset_id: old.id, latest_reading: r, risk: risks[r.asset_id], active_scenario: payload.status?.active_scenarios?.[r.asset_id] ?? null })); });
        return { ...current, readings, histories, risks, assets: [...byId.values()], system: payload.status ?? current.system,
          status: payload.status ?? current.status, updatedAt: message.timestamp };
      }
      if (message.type === 'alert') {
        const alert = mapAlert(payload, current.assets);
        const event = { id: `ws-${alert.id}`, timestamp: message.timestamp, type: 'alert_raised', asset_id: alert.asset_id, message: alert.message };
        return { ...current, alerts: [alert, ...current.alerts.filter(a => a.id !== alert.id)], events: [event, ...current.events] };
      }
      if (message.type === 'recommendation') return { ...current, recommendations: [payload, ...current.recommendations.filter(r => r.id !== payload.id)] };
      if (message.type === 'scenario') {
        const event = { id: `ws-${message.timestamp}`, timestamp: message.timestamp, type: payload.event, asset_id: null, message: payload.message };
        return { ...current, events: [event, ...current.events] };
      }
      return current;
    });
  }, []);
  return { ...data, handleMessage };
}
