// Replace with the operations backend WebSocket URL when available.
export function connectGridSocket(onMessage) {
  const url = import.meta.env.VITE_GRID_WS_URL;
  if (!url) return { close() {} };
  const socket = new WebSocket(url);
  socket.addEventListener('message', event => { try { onMessage(JSON.parse(event.data)); } catch { /* Ignore malformed messages. */ } });
  return socket;
}
