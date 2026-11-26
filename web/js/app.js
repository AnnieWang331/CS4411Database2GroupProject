// Hash routes, so the site is plain static files (S3 + CloudFront needs no rewrite rules).
//   #/                student: type the join code
//   #/room/<room_id>  student: the board (join with a name, post, vote, comment)
//   #/host            instructor: start a room, your rooms
//   #/host/<room_id>  instructor: the join code for the projector
import { hostHome, hostProjector } from "./host.js";
import { studentBoard, studentHome } from "./student.js";

const app = document.getElementById("app");

const routes = [
  [/^#\/?$/, () => studentHome()],
  [/^#\/room\/([^/]+)$/, (m) => studentBoard(decodeURIComponent(m[1]))],
  [/^#\/host\/?$/, () => hostHome()],
  [/^#\/host\/([^/]+)$/, (m) => hostProjector(decodeURIComponent(m[1]))],
];

// A view may set `teardown` on the element it returns (the board closes its WebSocket); it runs
// when the next view replaces it.
let teardown = null;
let renders = 0;

async function render() {
  const hash = location.hash || "#/";
  const current = ++renders;
  for (const [pattern, view] of routes) {
    const match = hash.match(pattern);
    if (match) {
      const el = await view(match);
      if (current !== renders) {
        el.teardown?.(); // the route changed while this view was loading
        return;
      }
      teardown?.();
      teardown = el.teardown ?? null;
      app.replaceChildren(el);
      app.focus();
      return;
    }
  }
  location.replace("#/");
}

window.addEventListener("hashchange", render);
render();
