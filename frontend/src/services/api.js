const assets = [
  { id: 'TX-2048', name: 'North Creek Substation', region: 'North district', type: 'Power transformer', load: 82, risk: 78, temp: 91, status: 'Critical', lat: 23, left: 28, top: 30, voltage: '132 kV', age: '18 years', health: 42 },
  { id: 'TX-1903', name: 'Riverside Substation', region: 'Central district', type: 'Power transformer', load: 68, risk: 36, temp: 74, status: 'Healthy', lat: 54, left: 57, top: 54, voltage: '220 kV', age: '9 years', health: 86 },
  { id: 'TX-2187', name: 'East Point Substation', region: 'East district', type: 'Power transformer', load: 91, risk: 64, temp: 83, status: 'Warning', lat: 71, left: 79, top: 33, voltage: '132 kV', age: '14 years', health: 61 },
  { id: 'TX-1762', name: 'Lakeview Substation', region: 'West district', type: 'Power transformer', load: 54, risk: 21, temp: 68, status: 'Healthy', lat: 35, left: 25, top: 73, voltage: '66 kV', age: '6 years', health: 94 },
  { id: 'TX-2311', name: 'South Ridge Substation', region: 'South district', type: 'Power transformer', load: 76, risk: 52, temp: 79, status: 'Warning', lat: 72, left: 71, top: 77, voltage: '132 kV', age: '12 years', health: 68 },
  { id: 'TX-1654', name: 'Meadow Park Substation', region: 'North district', type: 'Power transformer', load: 46, risk: 18, temp: 64, status: 'Healthy', lat: 42, left: 49, top: 23, voltage: '66 kV', age: '4 years', health: 97 }
];
const alerts = [
  { id: 1, level: 'critical', title: 'Thermal overload detected', asset: 'TX-2048 · North Creek', time: '2 min ago', detail: 'Top oil temperature exceeded 90°C threshold' },
  { id: 2, level: 'warning', title: 'Load trending above forecast', asset: 'TX-2187 · East Point', time: '18 min ago', detail: 'Projected to reach 96% capacity in 4 hours' },
  { id: 3, level: 'warning', title: 'Unusual vibration pattern', asset: 'TX-2311 · South Ridge', time: '41 min ago', detail: 'Vibration signature differs from 30-day baseline' },
  { id: 4, level: 'info', title: 'Scheduled maintenance due', asset: 'TX-1903 · Riverside', time: '1 hr ago', detail: 'Routine inspection window opens in 7 days' }
];
export async function getGridData() { return { assets, alerts, updatedAt: new Date().toISOString(), system: { availability: 99.97, frequency: 50.02, activeAlerts: 3, monitoredAssets: 24 } }; }
export async function getAsset(id) { return assets.find(asset => asset.id === id) ?? assets[0]; }
export async function getAlerts() { return alerts; }
