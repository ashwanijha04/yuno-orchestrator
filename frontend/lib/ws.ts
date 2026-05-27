// WebSocket subscriber for live run events. Yields a snapshot first, then live
// events forwarded from the Redis run channel.

import { API_URL } from "./api";

export interface RunEvent {
  type: string;
  run_id?: string;
  [k: string]: unknown;
}

export function subscribeRun(
  runId: string,
  onEvent: (event: RunEvent) => void,
): () => void {
  const url = API_URL.replace(/^http/, "ws") + `/ws/runs/${runId}`;
  const socket = new WebSocket(url);

  socket.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as RunEvent);
    } catch {
      /* ignore malformed frames */
    }
  };

  return () => {
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close();
    }
  };
}
