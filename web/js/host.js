// Instructor screens (#8): start a room, list your rooms, show a room's join code, close it.
// The projector counts who has joined, live (#10).
import * as api from "./api.js";
import { alertBox, busy, formatWhen, h, reducedMotion, slideOnClick, slideTo } from "./dom.js";
import { connectLive } from "./live.js";
import { studentBoard } from "./student.js";

const MAX_TOPIC = 200; // api.md "Text limits"

// Draw the current route again (app.js listens for hashchange).
const rerender = () => window.dispatchEvent(new HashChangeEvent("hashchange"));

function wordmark(props = {}) {
  return h("a", { class: "wordmark", href: "#/host", ...props }, "Brainstorm Board");
}

function masthead(...extra) {
  return h("header", { class: "masthead" }, wordmark(), ...extra);
}

function statusBadge(room) {
  return room.status === "open"
    ? h("span", { class: "status status-open" }, "Open")
    : h("span", { class: "status status-closed" }, "Closed");
}

// Two clicks to close: the first turns the button red and asks again, the second closes.
// Closing can't be undone, and the button sits next to "Open Room".
function closeButton(room, alert, onClosed) {
  let timer;
  let armed = false;
  const button = h("button", { class: "button button-danger", type: "button" }, "Close Room");
  const disarm = () => {
    armed = false;
    delete button.dataset.armed;
    button.textContent = "Close Room";
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
  const codeHref = `#/host/${encodeURIComponent(room.room_id)}`;
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
      ),
      // Its own line, however wide the row is.
      h("p", { class: "room-expiry" }, `Will be cleared after ${formatWhen(room.expires_at)}`),
    ),
    h(
      "div",
      { class: "room-actions" },
      room.status === "open" ? closeButton(room, alert, refresh) : null,
      h("a", { class: "button button-quiet", href: codeHref, onclick: slideOnClick(codeHref) }, "Open Room"),
    ),
    alert,
  );
}

// A new room's row: the list opens a gap, then the row pops into it. Resolves after a short
// pause, so it can be seen before the page swipes to the code.
async function popIn(row) {
  row.scrollIntoView({ block: "nearest" });
  if (reducedMotion()) return;
  const { paddingTop } = getComputedStyle(row);
  const gap = row.animate(
    { height: ["0px", `${row.offsetHeight}px`], paddingBlock: ["0px", paddingTop], overflow: ["hidden", "hidden"] },
    { duration: 220, easing: "ease-out" },
  );
  const pop = row.animate(
    { opacity: [0, 1], transform: ["scale(0.75)", "none"] },
    { duration: 380, delay: 160, easing: "cubic-bezier(0.34, 1.56, 0.64, 1)", fill: "backwards" },
  );
  await Promise.allSettled([gap.finished, pop.finished]);
  await new Promise((resolve) => setTimeout(resolve, 450));
}

export async function hostHome() {
  const listAlert = alertBox();
  const list = h("div", { class: "host-list" });

  // Newest first, like the API's order.
  async function addRoom(room) {
    let rows = list.querySelector(".rooms");
    if (!rows) {
      rows = h("ul", { class: "rooms" });
      list.replaceChildren(rows);
    }
    const row = roomRow(room, refresh);
    rows.prepend(row);
    list.scrollTop = 0;
    await popIn(row);
  }

  async function refresh() {
    listAlert.textContent = "";
    try {
      const rooms = await api.myRooms();
      list.replaceChildren(
        rooms.length
          ? h("ul", { class: "rooms" }, rooms.map((room) => roomRow(room, refresh)))
          : h("p", { class: "empty" }, "No rooms were created in the last 24 hours!"),
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
    "aria-label": "Topic",
    autocomplete: "off",
    placeholder: "Topic of the day",
  });
  const createAlert = alertBox();
  const submit = h(
    "button",
    { class: "button button-primary", type: "submit", "aria-label": "Start", title: "Start" },
    h("span", { class: "icon-arrow", "aria-hidden": "true" }),
  );
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
        // The button stays disabled through the animation, so a room can't be started twice.
        const room = await busy(submit, createAlert, async () => {
          const created = await api.createRoom(topic);
          input.value = "";
          await addRoom(created);
          return created;
        });
        // Don't pull people back if they went somewhere else meanwhile.
        if (room && page.isConnected) slideTo(`#/host/${encodeURIComponent(room.room_id)}`);
      },
    },
    input,
    submit,
    createAlert,
  );

  const page = h(
    "div",
    { class: "page page-host" },
    // The wordmark here leads to the student side, the same as "Student? Join a room".
    h("header", { class: "masthead" }, wordmark({ href: "#/", onclick: slideOnClick("#/", "open") })),
    h(
      "section",
      { class: "host-panel host-panel-start", "aria-labelledby": "start-heading" },
      h(
        "div",
        { class: "panel-heading" },
        h("h1", { id: "start-heading" }, "Start a Brainstorm Board"),
        h("a", { class: "link", href: "#/", onclick: slideOnClick("#/", "open") }, "Student? Join a room"),
      ),
      h("p", { class: "lede" }, "Rooms will stay open for 24 hours, can be manually closed in advance."),
      form,
    ),
    h(
      "section",
      { class: "host-panel host-panel-rooms", "aria-labelledby": "rooms-heading" },
      h("h2", { id: "rooms-heading" }, "List of Rooms"),
      h("p", { class: "lede" }, "Record of a room will be cleared after 24 hours of creation."),
      listAlert,
      list,
    ),
  );
  await refresh();
  return page;
}

// Where students go to join: the site's home page asks for the code.
function joinAddress() {
  const path = location.pathname.replace(/index\.html$/, "").replace(/\/$/, "");
  return location.host + path;
}

export async function hostProjector(roomId) {
  let room;
  let mine = false;
  const joined = new Set(); // user ids
  try {
    const [data, rooms, people] = await Promise.all([api.board(roomId), api.myRooms(), api.participants(roomId)]);
    room = data.room;
    mine = rooms.some((r) => r.room_id === roomId);
    people.forEach((p) => joined.add(p.user_id));
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
  const code = (extra) =>
    h(
      "p",
      { class: `code ${extra}`, "aria-label": `Join code ${chars.join(" ")}` },
      [chars.slice(0, 3), chars.slice(3)].map((group) =>
        h("span", { class: "code-group", "aria-hidden": "true" }, group.map((c) => h("span", { class: "code-char" }, c))),
      ),
    );
  const how = () =>
    open
      ? ["Go to ", h("strong", {}, joinAddress()), " and type this code to join."]
      : ["This room is closed. Nothing new can be added."];

  // The board, read-only, below the fold. It updates itself live; Refresh reloads it, and a
  // room found closed on a reload redraws this page.
  const refreshButton = h("button", { class: "button button-quiet", type: "button" }, "Refresh");
  const board = await studentBoard(roomId, {
    embedded: true,
    onLoad: (fresh) => {
      if (fresh.status !== room.status) rerender();
    },
  });
  refreshButton.addEventListener("click", () => board.refresh?.(refreshButton));

  // How many people have joined, next to the status in both the big view and the banner.
  const counts = [h("span", { class: "joined", role: "status" }), h("span", { class: "joined" })];
  const drawCount = () => {
    const text = joined.size === 1 ? "1 person joined" : `${joined.size} people joined`;
    for (const count of counts) count.textContent = text;
  };
  drawCount();

  // Each piece twice: small in the banner (the real content), big in the full-screen view
  // (a copy for the eye, hidden from screen readers). Scrolling morphs one into the other.
  const small = {
    topic: h("h1", { class: "proj-topic" }, room.topic),
    code: code("code-small"),
    how: h("p", { class: "proj-how" }, ...how()),
    status: h("p", { class: "proj-status" }, statusBadge(room), counts[0]),
  };
  const big = {
    topic: h("p", { class: "projector-topic" }, room.topic),
    code: code(""),
    how: h("p", { class: "projector-how" }, ...how()),
    status: h("p", { class: "projector-status" }, statusBadge(room), counts[1]),
  };
  const refreshGroup = h("div", { class: "refresh" }, board.liveStatus ?? null, refreshButton);
  const hint = h(
    "p",
    { class: "proj-hint" },
    h("span", { class: "icon-arrow", "aria-hidden": "true" }),
    "Scroll down for Brainstorm Board",
    h("span", { class: "icon-arrow", "aria-hidden": "true" }),
  );
  const hero = h(
    "div",
    { class: "proj-hero", "aria-hidden": "true" },
    h("div", { class: "projector-main" }, big.topic, big.code, h("div", { class: "projector-join" }, big.how, big.status)),
    hint,
  );
  const head = h(
    "header",
    { class: "proj-head" },
    h(
      "div",
      { class: "projector-bar" },
      wordmark({ onclick: slideOnClick("#/host", "back") }),
      h("div", { class: "actions" }, open && mine ? closeButton(room, alert, rerender) : null),
    ),
    h(
      "div",
      { class: "proj-info" },
      h("div", { class: "proj-line" }, small.topic, small.code, small.status, refreshGroup),
      small.how,
      alert,
    ),
    hero,
  );
  const spacer = h("div", { class: "proj-spacer" });
  const page = h("div", { class: `projector${open ? "" : " projector-closed"}` }, head, spacer, board);
  scrollMorph({ page, head, hero, spacer, board, small, big, hint, refreshGroup });

  // Leaving the page stops both sockets: this one (who joined) and the board's (ideas).
  let live = null;
  page.teardown = () => {
    live?.stop();
    board.teardown?.();
  };
  if (open) {
    live = connectLive(roomId, {
      onMessage: (message) => {
        if (message.type === "participant_joined") {
          joined.add(message.participant.user_id);
          drawCount();
        } else if (message.type === "room_closed" || message.type === "room_expired") {
          live.stop();
          rerender();
        }
      },
      // Catch up on anyone who joined while the socket was down, and notice a closed room.
      onSync: async () => {
        const [data, people] = await Promise.all([api.board(roomId), api.participants(roomId)]).catch((err) => {
          if (err.code !== "room_not_found") throw err;
          return [null, []];
        });
        if (data?.room.status !== "open") {
          rerender();
          return false;
        }
        people.forEach((p) => joined.add(p.user_id));
        drawCount();
        return true;
      },
    });
  }
  return page;
}

// ---- Projector scroll morph ----
// At the top the page is the full-screen view. Scrolling down one screen shrinks it into the
// banner: each big piece slides and scales onto its small twin, and they swap halfway. The
// banner is sticky, and the big view sits inside it, so both stay put while the page scrolls.

const ramp = (p, from, to) => Math.min(1, Math.max(0, (p - from) / (to - from)));

function scrollMorph({ page, head, hero, spacer, board, small, big, hint, refreshGroup }) {
  const keys = Object.keys(small);
  let moves = null; // per piece: how far and how much bigger the big one is
  let range = 1;

  function measure() {
    if (!page.isConnected) return;
    for (const key of keys) {
      small[key].style.transform = "";
      big[key].style.transform = "";
    }
    // One screen of scrolling, minus the banner, takes the page from big to small. The board
    // is at least that tall, so even a short one can be scrolled all the way.
    const headHeight = head.offsetHeight;
    spacer.style.height = `calc(100svh - ${headHeight}px)`;
    board.style.minHeight = `calc(100svh - ${headHeight}px)`;
    range = Math.max(1, spacer.offsetHeight);
    moves = {};
    for (const key of keys) {
      const s = small[key].getBoundingClientRect();
      const b = big[key].getBoundingClientRect();
      const scale = parseFloat(getComputedStyle(big[key]).fontSize) / parseFloat(getComputedStyle(small[key]).fontSize);
      moves[key] = {
        x: b.left + b.width / 2 - (s.left + s.width / 2),
        y: b.top + b.height / 2 - (s.top + s.height / 2),
        scale,
      };
    }
    draw();
  }

  function draw() {
    if (!moves) return;
    let p = Math.min(1, Math.max(0, window.scrollY / range));
    if (reducedMotion()) p = p < 0.5 ? 0 : 1;
    // Ease out, so the pieces clear the middle of the screen before the board scrolls up.
    const e = 1 - (1 - p) ** 2;
    for (const key of keys) {
      const { x, y, scale } = moves[key];
      small[key].style.transform = `translate(${x * (1 - e)}px, ${y * (1 - e)}px) scale(${scale + (1 - scale) * e})`;
      small[key].style.opacity = ramp(p, 0.45, 0.55);
      big[key].style.transform = `translate(${-x * e}px, ${-y * e}px) scale(${1 + (1 / scale - 1) * e})`;
      big[key].style.opacity = 1 - ramp(p, 0.4, 0.5);
    }
    hint.style.opacity = 1 - ramp(p, 0, 0.2);
    hero.style.visibility = p >= 0.5 ? "hidden" : "";
    refreshGroup.style.opacity = ramp(p, 0.5, 0.8);
    refreshGroup.style.visibility = p >= 0.5 ? "" : "hidden"; // no clicking what you can't see
    head.classList.toggle("proj-stuck", p >= 1);
  }

  // Snap: the page is never left half-way. One scroll down from the big view glides all the
  // way to the banner; one scroll up from the top of the board glides back. Below that, the
  // board scrolls normally.
  let gliding = false;
  let glideTimer = 0;
  let lastY = window.scrollY;
  let direction = 0; // +1 down, -1 up: the way the last scroll went

  function glide(top) {
    gliding = true;
    clearTimeout(glideTimer);
    glideTimer = setTimeout(() => (gliding = false), 900); // in case scrollend never comes
    window.scrollTo({ top, behavior: reducedMotion() ? "auto" : "smooth" });
  }

  const between = () => window.scrollY > 1 && window.scrollY < range - 1;

  const onWheel = (event) => {
    if (!moves || event.ctrlKey) return; // ctrl+wheel is zoom
    const y = window.scrollY;
    if (gliding && y < range + 1) {
      event.preventDefault(); // the rest of this flick would cut the glide short
      return;
    }
    if (event.deltaY > 0 && y < range - 1) {
      event.preventDefault();
      glide(range);
    } else if (event.deltaY < 0 && y > 1 && y <= range + 1) {
      event.preventDefault();
      glide(0);
    }
  };

  // Touch, keys and the scrollbar: when a scroll stops part-way, finish it in the direction
  // it was going.
  const settle = () => {
    clearTimeout(glideTimer);
    if (gliding) {
      gliding = false;
      return;
    }
    if (moves && between()) glide(direction >= 0 ? range : 0);
  };
  let settleTimer = 0;

  let frame = 0;
  const onScroll = () => {
    if (!page.isConnected) {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("scrollend", settle);
      observer.disconnect();
      return;
    }
    const y = window.scrollY;
    if (y !== lastY) direction = Math.sign(y - lastY);
    lastY = y;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(draw);
    if (!("onscrollend" in window)) {
      clearTimeout(settleTimer);
      settleTimer = setTimeout(settle, 150);
    }
  };
  // Fires once the page is on screen, then on any resize (window, fonts, a wrapping topic).
  const observer = new ResizeObserver(() => measure());
  observer.observe(head);
  observer.observe(hero);
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("wheel", onWheel, { passive: false });
  window.addEventListener("scrollend", settle);
  document.fonts?.ready.then(measure);
}
