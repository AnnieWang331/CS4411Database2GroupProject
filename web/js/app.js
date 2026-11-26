// Hash routes, so the site is plain static files (S3 + CloudFront needs no rewrite rules).
//   #/                student: type the join code
//   #/room/<room_id>  student: the board (join with a name, post, vote, comment)
//   #/host            instructor: start a room, your rooms
//   #/host/<room_id>  instructor: the join code for the projector
import { reducedMotion, takeSlide } from "./dom.js";
import { hostHome, hostProjector } from "./host.js";
import { studentBoard, studentHome } from "./student.js";

const app = document.getElementById("app");

const routes = [
  [/^#\/?$/, () => studentHome()],
  [/^#\/room\/([^/]+)$/, (m) => studentBoard(decodeURIComponent(m[1]))],
  [/^#\/host\/?$/, () => hostHome()],
  [/^#\/host\/([^/]+)$/, (m) => hostProjector(decodeURIComponent(m[1]))],
];

// Replace the page with a transition if asked (see dom.js slideTo). Browsers without view
// transitions just swap. Each kind is a class on <html> that style.css animates.
const KINDS = {
  forward: "slide-forward",
  back: "slide-back",
  close: "doors-close",
  open: "doors-open",
  morph: "morph",
};
let current = null; // the running transition

// Morph: the line above the board's field ("Pick a name…" or your name) has nothing to turn
// into on the join page, so it rides along with the field instead, fading in or out. Its
// distance is only known once both pages exist, so it's animated here rather than in CSS.
const FIELD = ".page-join .field > .input, .bar .bar-field > .input";
const MORPH = { duration: 450, easing: "cubic-bezier(0.65, 0, 0.2, 1)" };

function fieldTop() {
  return document.querySelector(FIELD)?.getBoundingClientRect().top;
}

function labelFollowsField(transition) {
  const before = fieldTop();
  let after;
  transition.updateCallbackDone.then(() => (after = fieldTop())).catch(() => {});
  transition.ready
    .then(() => {
      if (before === undefined || after === undefined) return;
      const html = document.documentElement;
      const shift = (px) => `translateY(${px}px)`;
      // Joining: the line arrives with the field. Going back: it leaves with it.
      html.animate(
        { transform: [shift(before - after), "none"], opacity: [0, 1] },
        { ...MORPH, pseudoElement: "::view-transition-new(compose-label)" },
      );
      html.animate(
        { transform: ["none", shift(after - before)], opacity: [1, 0] },
        { ...MORPH, pseudoElement: "::view-transition-old(compose-label)" },
      );
    })
    .catch(() => {});
}

function show(view, slide) {
  const swap = () => {
    app.replaceChildren(view);
    app.focus();
  };
  if (!slide || reducedMotion() || !document.startViewTransition) {
    swap();
    return;
  }
  view.classList.add("slid-in");
  const root = document.documentElement.classList;
  root.remove(...Object.values(KINDS));
  root.add("transitioning", KINDS[slide]);
  const transition = document.startViewTransition(swap);
  current = transition;
  transition.ready.catch(() => {}); // Skipped (e.g. hidden tab): the swap still happens.
  if (slide === "morph") labelFollowsField(transition);
  transition.finished.finally(() => {
    // A newer transition cuts this one short and needs the classes.
    if (current === transition) root.remove("transitioning", ...Object.values(KINDS));
  });
}

// A view may set `teardown` on the element it returns (the board closes its WebSocket); it runs
// when the next view replaces it.
let teardown = null;
let renders = 0;

async function render() {
  const slide = takeSlide();
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
      show(el, slide);
      return;
    }
  }
  location.replace("#/");
}

window.addEventListener("hashchange", render);
render();
