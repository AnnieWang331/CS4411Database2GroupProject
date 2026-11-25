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

async function render() {
  const hash = location.hash || "#/";
  for (const [pattern, view] of routes) {
    const match = hash.match(pattern);
    if (match) {
      app.replaceChildren(await view(match));
      app.focus();
      return;
    }
  }
  location.replace("#/");
}

window.addEventListener("hashchange", render);
render();
