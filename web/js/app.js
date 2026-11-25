// Hash routes, so the site is plain static files (S3 + CloudFront needs no rewrite rules).
//   #/host            instructor: start a room, your rooms
//   #/host/<room_id>  instructor: the join code for the projector
import { hostHome, hostProjector } from "./host.js";

const app = document.getElementById("app");

const routes = [
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
  // The student home page comes with #9; until then everything else goes to the instructor page.
  location.replace("#/host");
}

window.addEventListener("hashchange", render);
render();
