// Live updates (#10): one WebSocket per open board, server -> client only (api.md "WebSocket API").
//
// Messages can arrive twice or out of order across items (data-model.md section 6), so callers
// apply each one on its own and ignore what they already have. Nothing sent before a socket opens
// (or while it was down) reaches it, so every time one opens the caller reloads the board.
import { WS_URL } from "../config.js";

// API Gateway closes a socket after 10 minutes with no messages, so a quiet board sends one now
// and then. The $default route ignores it.
const KEEPALIVE_MS = 5 * 60 * 1000;
const RETRY_FIRST_MS = 1000;
const RETRY_MAX_MS = 30 * 1000;

// connectLive(roomId, handlers) -> { stop() }
//   onMessage(message)  one parsed message for this room
//   onSync()            a socket opened, or failed to open: reload the board. Return false (or a
//                       promise of false) to stop for good, e.g. the room turned out closed.
//   onState(state)      "connecting" | "live" | "offline"
export function connectLive(roomId, { onMessage, onSync, onState = () => {} }) {
  let socket = null;
  let stopped = false;
  let attempt = 0;
  let retryTimer = null;
  let keepalive = null;

  function open() {
    clearTimeout(retryTimer);
    retryTimer = null;
    if (stopped || socket) return;
    onState("connecting");
    const url = `${WS_URL.replace(/\/$/, "")}/?room_id=${encodeURIComponent(roomId)}`;
    const ws = new WebSocket(url);
    socket = ws;
    let opened = false;

    ws.addEventListener("open", async () => {
      opened = true;
      attempt = 0;
      keepalive = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send("ping"), KEEPALIVE_MS);
      onState("live");
      await sync();
    });
    ws.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message && message.room_id === roomId) onMessage(message);
    });
    ws.addEventListener("close", async () => {
      clearInterval(keepalive);
      if (socket === ws) socket = null;
      if (stopped) return;
      onState("offline");
      // A refused socket (closed or gone room) never opens and the browser doesn't say why, so
      // ask the HTTP API (api.md). After a plain drop the reload waits for the next open.
      if (!opened && !(await sync())) return;
      retry();
    });
  }

  // Run onSync; stop for good if it says so.
  async function sync() {
    let keepGoing = true;
    try {
      keepGoing = (await onSync()) !== false;
    } catch (err) {
      console.warn("reloading the board failed", err);
    }
    if (!keepGoing) stop();
    return keepGoing;
  }

  function retry() {
    if (stopped || retryTimer) return;
    // 1s, 2s, 4s ... up to 30s, with jitter so a classroom of phones doesn't reconnect at once.
    const base = Math.min(RETRY_MAX_MS, RETRY_FIRST_MS * 2 ** attempt);
    attempt += 1;
    retryTimer = setTimeout(open, base / 2 + Math.random() * (base / 2));
  }

  // A phone waking up or a laptop back on Wi-Fi: try now instead of waiting out the backoff.
  function wake() {
    if (stopped || socket || document.visibilityState === "hidden") return;
    attempt = 0;
    open();
  }

  function stop() {
    stopped = true;
    clearTimeout(retryTimer);
    clearInterval(keepalive);
    window.removeEventListener("online", wake);
    document.removeEventListener("visibilitychange", wake);
    if (socket) socket.close();
    socket = null;
  }

  window.addEventListener("online", wake);
  document.addEventListener("visibilitychange", wake);
  open();
  return { stop };
}
