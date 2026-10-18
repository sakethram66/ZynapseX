import { useEffect, useState } from 'react';
import { connectGridSocket } from '../services/websocket';
export default function useWebSocket(onMessage) {
  const [connection, setConnection] = useState('connecting');
  useEffect(() => connectGridSocket(onMessage, setConnection), [onMessage]);
  return connection;
}
