// Instructor screens (#8): start a room, list your rooms, show a room's join code, close it.
import * as api from "./api.js";
import { alertBox, busy, formatWhen, h } from "./dom.js";

const MAX_TOPIC = 200; // api.md "Text limits"

// Draw the current route again (app.js listens for hashchange).
const rerender = () => window.dispatchEvent(new HashChangeEvent("hashchange"));

function masthead(...extra) {
  return h("header", { class: "masthead" }, h("a", { class: "wordmark", href: "#/host" }, "Brainstorm board"), ...extra);
}

function statusBadge(room) {
  return room.status === "open"
    ? h("span", { class: "status status-open" }, "Open")
    : h("span", { class: "status status-closed" }, "Closed");
}

// Two clicks to close: the first turns the button red and asks again, the second closes.
// Closing can't be undone, and the button sits next to "Show code".
function closeButton(room, alert, onClosed) {
  let timer;
  let armed = false;
  const button = h("button", { class: "button button-danger", type: "button" }, "Close room");
  const disarm = () => {
    armed = false;
    delete button.dataset.armed;
    button.textContent = "Close room";
  };
  button.addEventListener("click", async () => {
    if (!armed) {
      armed = true;
      button.dataset.armed = "";
      button.textContent = "Close for good";
      timer = setTimeout(disarm, 4000);
      return;
    }
    clearTimeout(timer);
    const done = await busy(button, alert, () => api.closeRoom(room.room_id).then(() => true));
    disarm();
    if (done) onClosed();
  });
  button.addEventListener("blur", () => {
    clearTimeout(timer);
    disarm();
  });
  return button;
}

function roomRow(room, refresh) {
  const alert = alertBox();
  return h(
    "li",
    { class: "room" },
    h(
      "div",
      {},
      h("p", { class: "room-topic" }, room.topic),
      h(
        "p",
        { class: "room-meta" },
        statusBadge(room),
        h("span", {}, "Code ", h("span", { class: "room-code" }, room.code)),
        h("span", {}, `Started ${formatWhen(room.created_at)}`),
        h("span", {}, `Deleted after ${formatWhen(room.expires_at)}`),
      ),
    ),
    h(
      "div",
      { class: "room-actions" },
      h("a", { class: "button button-quiet", href: `#/host/${encodeURIComponent(room.room_id)}` }, "Show code"),
      room.status === "open" ? closeButton(room, alert, refresh) : null,
    ),
    alert,
  );
}

export async function hostHome() {
  const listAlert = alertBox();
  const list = h("div", {});

  async function refresh() {
    listAlert.textContent = "";
    try {
      const rooms = await api.myRooms();
      list.replaceChildren(
        rooms.length
          ? h("ul", { class: "rooms" }, rooms.map((room) => roomRow(room, refresh)))
          : h("p", { class: "empty" }, "No rooms yet. Start one above and its code shows up here."),
      );
    } catch (err) {
      listAlert.textContent = err.message;
    }
  }

  const input = h("input", {
    class: "input",
    id: "topic",
    name: "topic",
    maxLength: MAX_TOPIC,
    "aria-describedby": "topic-hint",
    autocomplete: "off",
    placeholder: "e.g. Ways to speed up the course search page",
  });
  const createAlert = alertBox();
  const submit = h("button", { class: "button button-primary", type: "submit" }, "Start room");
  const form = h(
    "form",
    {
      class: "field",
      onsubmit: async (event) => {
        event.preventDefault();
        const topic = input.value.trim();
        if (!topic) {
          input.setAttribute("aria-invalid", "true");
          createAlert.textContent = "Type a topic first.";
          input.focus();
          return;
        }
        input.removeAttribute("aria-invalid");
        const room = await busy(submit, createAlert, () => api.createRoom(topic));
        if (room) location.hash = `#/host/${encodeURIComponent(room.room_id)}`;
      },
    },
    h("label", { htmlFor: "topic" }, "What should the class brainstorm?"),
    input,
    submit,
    h("p", { class: "hint", id: "topic-hint" }, "Rooms stay open until you close them, and are deleted after 24 hours."),
  );

  const page = h(
    "div",
    { class: "page" },
    masthead(),
    h(
      "section",
      { class: "section", "aria-labelledby": "start-heading" },
      h("h1", { id: "start-heading" }, "Start a room"),
      h("p", { class: "lede" }, "You get a six-letter code to put on the screen. Students type it on their phones to join."),
      form,
      createAlert,
    ),
    h("section", { class: "section", "aria-labelledby": "rooms-heading" }, h("h2", { id: "rooms-heading" }, "Your rooms"), listAlert, list),
  );
  await refresh();
  return page;
}

// Where students go to join. Students join on the site's home page (#9).
function joinAddress() {
  const path = location.pathname.replace(/index\.html$/, "").replace(/\/$/, "");
  return location.host + path;
}

export async function hostProjector(roomId) {
  let room;
  let mine = false;
  try {
    const [data, rooms] = await Promise.all([api.board(roomId), api.myRooms()]);
    room = data.room;
    mine = rooms.some((r) => r.room_id === roomId);
  } catch (err) {
    return h(
      "div",
      { class: "page" },
      masthead(),
      h("h1", {}, err.code === "room_not_found" ? "This room is gone" : "Couldn't load this room"),
      h("p", { class: "lede" }, err.message),
      h("p", { class: "lede" }, h("a", { class: "link", href: "#/host" }, "Back to your rooms")),
    );
  }

  const open = room.status === "open";
  const alert = alertBox();
  const chars = [...room.code];
  const code = h(
    "p",
    { class: "code", "aria-label": `Join code ${chars.join(" ")}` },
    [chars.slice(0, 3), chars.slice(3)].map((group) =>
      h("span", { class: "code-group", "aria-hidden": "true" }, group.map((c) => h("span", { class: "code-char" }, c))),
    ),
  );

  return h(
    "div",
    { class: `projector${open ? "" : " projector-closed"}` },
    h(
      "div",
      { class: "projector-bar" },
      h("a", { class: "link", href: "#/host" }, "Your rooms"),
      h(
        "div",
        { class: "actions" },
        open && mine ? closeButton(room, alert, rerender) : null,
      ),
    ),
    h(
      "div",
      { class: "projector-main" },
      h("h1", { class: "projector-topic" }, room.topic),
      code,
      open
        ? h("p", { class: "projector-how" }, "Go to ", h("strong", {}, joinAddress()), " and type this code to join.")
        : h("p", { class: "projector-how" }, "This room is closed. Nothing new can be added."),
      alert,
    ),
    h("div", { class: "projector-foot" }, statusBadge(room)),
  );
}
