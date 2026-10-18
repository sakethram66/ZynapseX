import { useEffect, useState } from 'react';
import { getGridData } from '../services/api';
export default function useGridData() {
  const [data, setData] = useState({ assets: [], alerts: [], system: {}, updatedAt: null });
  useEffect(() => { let live = true; getGridData().then(value => { if (live) setData(value); }); return () => { live = false; }; }, []);
  return data;
}
