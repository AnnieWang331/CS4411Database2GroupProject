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

export function alertBox() {
  return h("p", { class: "alert", role: "alert" });
}
