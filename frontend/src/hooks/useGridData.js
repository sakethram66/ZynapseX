import { useCallback, useEffect, useState } from 'react';
import { getAlerts, getGridData, mapAlert, mapAsset } from '../services/api';

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
    const refresh = () => getAlerts().then(items => { if (active) setData(current => ({ ...current, alerts: items.map(a => mapAlert(a, current.assets)) })); }).catch(() => {});
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
        (payload.readings ?? []).forEach(r => { const old = byId.get(r.asset_id); if (old) byId.set(r.asset_id, mapAsset({ ...old, asset_id: old.id, latest_reading: r, risk: risks[r.asset_id] })); });
        return { ...current, readings, histories, risks, assets: [...byId.values()], system: payload.status ?? current.system,
          status: payload.status ?? current.status, updatedAt: message.timestamp };
      }
      if (message.type === 'alert') {
        const alert = mapAlert(payload, current.assets);
        return { ...current, alerts: [alert, ...current.alerts.filter(a => a.id !== alert.id)] };
      }
      if (message.type === 'recommendation') return { ...current, recommendations: [payload, ...current.recommendations.filter(r => r.id !== payload.id)] };
      return current;
    });
  }, []);
  return { ...data, handleMessage };
}
