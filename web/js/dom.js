// Tiny DOM helpers. Text always goes in through textContent, never innerHTML, so topics and
// ideas typed by users can't inject markup.

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key in el && key !== "list") el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  el.append(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
  return el;
}

const when = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  hour: "numeric",
  minute: "2-digit",
});

// "Tue 2:30 p.m." from an ISO timestamp or epoch seconds.
export function formatWhen(value) {
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  return when.format(date);
}

const time = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

// "2:30 p.m." from an ISO timestamp or a Date. Rooms last a day, so the time is enough.
export function formatTime(value) {
  return time.format(value instanceof Date ? value : new Date(value));
}

// Run an async action with its button disabled, and show any error in `alert`.
export async function busy(button, alert, action) {
  button.disabled = true;
  alert.textContent = "";
  try {
    return await action();
  } catch (err) {
    alert.textContent = err.message;
    console.error(err);
    return undefined;
  } finally {
    button.disabled = false;
  }
}

export const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// Go to a route with the page swipe (app.js plays it), instead of a plain link's instant swap.
// "forward" brings the new page in from the right, "back" from the left. "close" slides the
// instructor page's two halves in from the sides like doors; "open" slides them back out.
// "morph" moves the join page's code field into the board's writing box, and back.
let slideNext = null;

export function slideTo(hash, direction = "forward") {
  slideNext = direction;
  location.hash = hash;
}

// onclick for a link that swipes. Ctrl/Cmd/Shift+click still opens a new tab or window.
export function slideOnClick(hash, direction) {
  return (event) => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    slideTo(hash, direction);
  };
}

// app.js: the direction if slideTo started this navigation, else null. Asking resets it.
export function takeSlide() {
  const direction = slideNext;
  slideNext = null;
  return direction;
}

export function alertBox() {
  return h("p", { class: "alert", role: "alert" });
}
