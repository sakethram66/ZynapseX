import { useEffect, useState } from 'react';
import { connectGridSocket } from '../services/websocket';
export default function useWebSocket(onMessage) {
  const [connected, setConnected] = useState(false);
  useEffect(() => { const socket = connectGridSocket(message => onMessage?.(message)); socket.addEventListener?.('open', () => setConnected(true)); socket.addEventListener?.('close', () => setConnected(false)); return () => socket.close(); }, [onMessage]);
  return connected;
}
