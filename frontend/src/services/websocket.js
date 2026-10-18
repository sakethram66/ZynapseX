export function connectGridSocket(onMessage, onStatus = () => {}) {
  let socket;
  let retry = 0;
  let closed = false;
  let timer;
  const base = import.meta.env.VITE_GRID_WS_URL;
  const url = base || `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/grid`;
  const open = () => {
    if (closed) return;
    onStatus('connecting');
    socket = new WebSocket(url);
    socket.onopen = () => { retry = 0; onStatus('connected'); };
    socket.onmessage = event => {
      try { onMessage(JSON.parse(event.data)); } catch { /* Ignore malformed stream messages. */ }
    };
    socket.onerror = () => socket.close();
    socket.onclose = () => {
      onStatus('disconnected');
      if (!closed) timer = setTimeout(open, Math.min(1000 * 2 ** retry++, 15000));
    };
  };
  open();
  return () => { closed = true; clearTimeout(timer); socket?.close(); };
}
