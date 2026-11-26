// Student screens (#9): join by code, then the board (post, vote, comment).
// Changes from other people arrive over the WebSocket (#10, live.js) and are applied in place.
import * as api from "./api.js";
import { alertBox, busy, formatTime, h, slideOnClick, slideTo } from "./dom.js";
import { connectLive } from "./live.js";

// api.md "Text limits"
const MAX_NAME = 50;
const MAX_IDEA = 500;
const MAX_COMMENT = 300;
const CODE_LENGTH = 6;

// The API has no "who am I in this room" route, so the browser remembers the name it joined
// each room with. The last name used fills in the next join form.
const NAMES_KEY = "brainstorm.names";
const LAST_NAME_KEY = "brainstorm.lastName";

function readJson(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function savedName(roomId) {
  return readJson(NAMES_KEY, {})[roomId] ?? null;
}

function saveName(roomId, name) {
  try {
    const names = readJson(NAMES_KEY, {});
    names[roomId] = name;
    localStorage.setItem(NAMES_KEY, JSON.stringify(names));
    localStorage.setItem(LAST_NAME_KEY, JSON.stringify(name));
  } catch {
    // Storage blocked: the name lasts until the page reloads.
  }
}

function masthead(...extra) {
  return h("header", { class: "masthead" }, h("a", { class: "wordmark", href: "#/" }, "Brainstorm Board"), ...extra);
}

// ---- Home: type the join code ----

// Same alphabet as the API's codes (keys.py): no I, L, O, 0 or 1.
const CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";

// A made-up code for the placeholder, grouped like the projector shows it: "KXT 4PM".
function exampleCode() {
  const pick = () => CODE_ALPHABET[Math.floor(Math.random() * CODE_ALPHABET.length)];
  const chars = Array.from({ length: CODE_LENGTH }, pick);
  return `${chars.slice(0, 3).join("")} ${chars.slice(3).join("")}`;
}

export function studentHome() {
  const input = h("input", {
    class: "input input-code",
    id: "code",
    name: "code",
    maxLength: CODE_LENGTH + 2, // room for a space or dash in the middle
    autocomplete: "off",
    autocapitalize: "characters",
    spellcheck: false,
    enterKeyHint: "go",
    placeholder: exampleCode(),
    "aria-label": "Join code",
  });
  // Pasted codes lose their spaces and line breaks before maxLength can cut them short.
  input.addEventListener("paste", (event) => {
    event.preventDefault();
    const text = event.clipboardData.getData("text").replace(/\s+/g, "");
    const { selectionStart: start, selectionEnd: end, value, maxLength } = input;
    const space = maxLength - (value.length - (end - start));
    input.setRangeText(text.slice(0, space), start, end, "end");
  });
  const alert = alertBox();
  const submit = h("button", { class: "button button-primary", type: "submit" }, "Join");
  const form = h(
    "form",
    {
      class: "field",
      onsubmit: async (event) => {
        event.preventDefault();
        const code = input.value.replace(/[\s-]/g, "").toUpperCase();
        if (code.length !== CODE_LENGTH) {
          input.setAttribute("aria-invalid", "true");
          alert.textContent = "A join code is 6 letters and numbers, like KXT 4PM.";
          input.focus();
          return;
        }
        input.removeAttribute("aria-invalid");
        const room = await busy(submit, alert, () =>
          api.roomByCode(code).catch((err) => {
            // Closing a room frees its code, so a closed room isn't found either.
            if (err.code === "room_not_found") err.message = "No open room has that code. Check it and try again.";
            throw err;
          }),
        );
        // The field and button drop down into the board's writing box (style.css "morph").
        if (room) slideTo(`#/room/${encodeURIComponent(room.room_id)}`, "morph");
      },
    },
    input,
    submit,
    alert,
  );

  return h(
    "div",
    { class: "page page-join" },
    // The wordmark here leads to the instructor side, the same as "Teaching? Start a room".
    h(
      "header",
      { class: "masthead" },
      h("a", { class: "wordmark", href: "#/host", onclick: slideOnClick("#/host", "close") }, "Brainstorm Board"),
    ),
    h(
      "section",
      { class: "join-panel", "aria-labelledby": "join-heading" },
      h(
        "div",
        { class: "panel-heading" },
        h("h1", { id: "join-heading" }, "Join a Brainstorm Board"),
        h("a", { class: "link", href: "#/host", onclick: slideOnClick("#/host", "close") }, "Teaching? Start a room"),
      ),
      h("p", { class: "lede" }, "Type in the code on the board!"),
      form,
    ),
  );
}

// ---- Board ----

function gonePage(err) {
  return h(
    "div",
    { class: "page" },
    masthead(),
    h("h1", {}, err.code === "room_not_found" ? "This room is gone" : "Couldn't load this room"),
    h("p", { class: "lede" }, err.message),
    h("p", { class: "lede" }, h("a", { class: "link", href: "#/" }, "Join another room")),
  );
}

// Browsers with CSS field-sizing grow the textarea themselves; the rest get fit() below.
const growsItself = globalThis.CSS?.supports?.("field-sizing", "content") ?? false;

function fit(textarea) {
  if (growsItself || !textarea.isConnected) return;
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight + textarea.offsetHeight - textarea.clientHeight}px`;
}

// A one-line textarea that grows with its text, with a "n left" counter that only shows near
// the limit. Enter sends; Shift+Enter starts a new line.
function textBox({ id, label, max, placeholder, value = "" }) {
  const counterId = `${id}-count`;
  const textarea = h("textarea", {
    class: "input textarea",
    id,
    maxLength: max,
    rows: 1,
    placeholder,
    value,
    enterKeyHint: "send",
    "aria-label": label,
    "aria-describedby": counterId,
  });
  const counter = h("span", { class: "counter", id: counterId });
  const update = () => {
    const left = max - textarea.value.length;
    counter.textContent = left <= Math.min(50, max / 5) ? `${left} left` : "";
    counter.classList.toggle("counter-low", left <= Math.min(30, max / 10));
    fit(textarea);
  };
  textarea.addEventListener("input", update);
  textarea.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    textarea.form?.requestSubmit();
  });
  update();
  return { textarea, counter, update };
}

// The blue send button: an up arrow, named for screen readers.
function sendButton(label) {
  return h(
    "button",
    { class: "button button-primary button-send", type: "submit", "aria-label": label, title: label },
    h("span", { class: "icon-arrow icon-up", "aria-hidden": "true" }),
  );
}

// The board. With embedded: true it's just the idea list, read-only, for the instructor's
// projector page: no name, so no posting, voting or commenting. onLoad(room) runs after every
// load, and the returned element has refresh(button), liveStatus and teardown().
export async function studentBoard(roomId, { embedded = false, onLoad } = {}) {
  const state = {
    room: null,
    ideas: [], // newest first, as the API returns them
    comments: {}, // idea_id -> [oldest first]
    voted: new Set(), // idea ids
    sort: "newest",
    name: embedded ? null : savedName(roomId),
    renaming: false,
    expanded: new Set(), // idea ids with their comments open
    drafts: new Map(), // idea id -> unsent comment
  };
  const me = api.userId();
  // Drawn idea rows by idea id, so a live update changes one row and leaves the rest alone
  // (someone typing a comment keeps their focus).
  const rows = new Map();
  // Live vote updates seen per idea id. A vote's own response only adjusts the count if none
  // arrived meanwhile: the message already carries the total.
  const voteUpdates = new Map();

  const fetchBoard = () => Promise.all([api.board(roomId, { withComments: true }), api.myVotes(roomId)]);

  try {
    const [board, voted] = await fetchBoard();
    state.room = board.room;
    state.ideas = board.ideas;
    state.comments = board.comments;
    state.voted = new Set(voted);
    onLoad?.(state.room);
  } catch (err) {
    if (embedded) return h("p", { class: "alert", role: "alert" }, err.message);
    return gonePage(err);
  }

  let page; // the element returned below: the whole board, or the embedded list

  const isOpen = () => state.room.status === "open";
  const canWrite = () => isOpen() && state.name && !state.renaming;

  // Any write can find the room closed (or expired) since the last load.
  function handleRoomGone(err) {
    if (err.code === "room_closed") {
      roomClosed();
      return true;
    }
    if (err.code === "room_not_found") {
      roomGone(err);
      return true;
    }
    return false;
  }

  function roomGone(err) {
    live.stop();
    // The embedded list sits inside the projector page, so it just says so in place.
    page.replaceWith(embedded ? h("p", { class: "alert", role: "alert" }, err.message) : gonePage(err));
  }

  // Like dom.busy, but a closed or deleted room redraws the page instead of showing an alert.
  async function attempt(button, alert, action) {
    button.disabled = true;
    alert.textContent = "";
    try {
      await action();
      return true;
    } catch (err) {
      console.error(err);
      if (!handleRoomGone(err)) alert.textContent = err.message;
      return false;
    } finally {
      button.disabled = false;
    }
  }

  // -- Top: topic, code, status --

  const head = h("div", { class: "board-head" });
  function drawHead() {
    const room = state.room;
    const chars = [...room.code];
    head.classList.toggle("board-closed", !isOpen());
    head.replaceChildren(
      h("h1", { class: "board-topic" }, room.topic),
      h(
        "p",
        { class: "board-code", "aria-label": `Join code ${chars.join(" ")}` },
        h("span", { "aria-hidden": "true" }, `${room.code.slice(0, 3)} ${room.code.slice(3)}`),
      ),
      isOpen()
        ? h("p", { class: "status status-open" }, "Open")
        : h("p", { class: "status status-closed" }, "Closed"),
      // Live and Refresh sit right after the status (built further down, kept across redraws).
      refreshGroup,
    );
  }


  // -- Bottom bar: the name form, the idea composer, or a closed notice --

  const nameInput = h("input", {
    class: "input",
    id: "display-name",
    maxLength: MAX_NAME,
    autocomplete: "nickname",
    enterKeyHint: "go",
    placeholder: "Your name",
    "aria-label": "Your name",
  });
  const nameAlert = alertBox();
  const joinButton = h("button", { class: "button button-primary", type: "submit" }, "Join");
  const nameRow = h("div", { class: "bar-row" });
  const cancelRename = h(
    "button",
    {
      class: "button-link",
      type: "button",
      onclick: () => {
        state.renaming = false;
        nameAlert.textContent = "";
        nameInput.removeAttribute("aria-invalid");
        drawAll();
        idea.textarea.focus();
      },
    },
    "Cancel",
  );
  const joinForm = h(
    "form",
    {
      class: "bar-form",
      onsubmit: async (event) => {
        event.preventDefault();
        const name = nameInput.value.trim();
        if (!name) {
          nameInput.setAttribute("aria-invalid", "true");
          nameAlert.textContent = "Type a name first. It can be a nickname.";
          nameInput.focus();
          return;
        }
        nameInput.removeAttribute("aria-invalid");
        const ok = await attempt(joinButton, nameAlert, async () => {
          const participant = await api.joinRoom(roomId, name);
          state.name = participant.display_name;
          saveName(roomId, state.name);
        });
        if (!ok) return;
        state.renaming = false;
        drawAll();
        idea.textarea.focus();
      },
    },
    nameRow,
    h("div", { class: "bar-field" }, nameInput, joinButton),
    nameAlert,
  );

  const idea = textBox({
    id: "idea-body",
    label: "Your idea",
    max: MAX_IDEA,
    placeholder: "One idea at a time",
  });
  const ideaAlert = alertBox();
  const postStatus = h("p", { class: "visually-hidden", role: "status" });
  const postButton = sendButton("Post idea");
  const who = h("strong", { class: "bar-who" });
  const renameButton = h(
    "button",
    {
      class: "button-link",
      type: "button",
      onclick: () => {
        state.renaming = true;
        nameInput.value = state.name;
        drawAll();
        nameInput.focus();
      },
    },
    "Change name",
  );
  const composer = h(
    "form",
    {
      class: "bar-form",
      onsubmit: async (event) => {
        event.preventDefault();
        const body = idea.textarea.value.trim();
        if (!body) {
          idea.textarea.setAttribute("aria-invalid", "true");
          ideaAlert.textContent = "Type your idea first.";
          idea.textarea.focus();
          return;
        }
        idea.textarea.removeAttribute("aria-invalid");
        const ok = await attempt(postButton, ideaAlert, async () => {
          addIdea(await api.postIdea(roomId, state.name, body));
        });
        if (!ok) return;
        idea.textarea.value = "";
        idea.update();
        postStatus.textContent = "Your idea is on the board.";
      },
    },
    h("div", { class: "bar-row" }, who, renameButton, idea.counter),
    h("div", { class: "bar-field" }, idea.textarea, postButton),
    ideaAlert,
    postStatus,
  );

  const bar = h("div", { class: "bar" });
  function drawBar() {
    if (!isOpen()) {
      bar.replaceChildren(h("p", { class: "banner" }, "This room is closed. You can still read everything, but nothing new can be added."));
    } else if (!state.name || state.renaming) {
      if (!nameInput.value) nameInput.value = readJson(LAST_NAME_KEY, "");
      nameRow.replaceChildren(
        h("p", { class: "bar-label" }, state.renaming ? "Change your name" : "Pick a name to post, vote and comment"),
        ...(state.renaming ? [cancelRename] : []),
      );
      joinButton.textContent = state.renaming ? "Change" : "Join";
      bar.replaceChildren(joinForm);
    } else {
      who.textContent = state.name;
      bar.replaceChildren(composer);
      fit(idea.textarea);
    }
  }

  // -- Idea list --

  const sortButtons = [
    ["newest", "Newest"],
    ["top", "Top voted"],
  ].map(([value, text]) =>
    h(
      "label",
      {},
      h("input", {
        type: "radio",
        name: "sort",
        value,
        checked: state.sort === value,
        onchange: () => {
          state.sort = value;
          drawList();
        },
      }),
      text,
    ),
  );
  const ideaCount = h("h2", { id: "ideas-heading" });
  const list = h("ol", { class: "ideas", "aria-labelledby": "ideas-heading" });

  function sortedIdeas() {
    if (state.sort === "newest") return state.ideas;
    // Data-model pattern 10: sorted here, not by an index. sort() is stable, so ties stay
    // newest first.
    return [...state.ideas].sort((a, b) => b.vote_count - a.vote_count);
  }

  // Returns { button, draw }; draw() shows the current count and whether I voted.
  function voteButton(item, alert) {
    const button = h("button", { class: "vote", type: "button" });
    const draw = () => {
      const voted = state.voted.has(item.idea_id);
      const n = item.vote_count;
      button.setAttribute("aria-pressed", String(voted));
      button.setAttribute("aria-label", `${voted ? "Voted" : "Vote"}, ${n} ${n === 1 ? "vote" : "votes"}`);
      button.disabled = !canWrite();
      button.replaceChildren(h("span", { class: "vote-arrow", "aria-hidden": "true" }), h("span", { class: "vote-count", "aria-hidden": "true" }, String(n)));
    };
    button.addEventListener("click", async () => {
      const voted = state.voted.has(item.idea_id);
      const seen = voteUpdates.get(item.idea_id) ?? 0;
      let resync = false;
      await attempt(button, alert, async () => {
        try {
          if (voted) await api.unvote(roomId, item.idea_sk);
          else await api.vote(roomId, item.idea_sk);
        } catch (err) {
          // Voted (or unvoted) from another tab: the page is out of date, so load it again.
          if (err.code !== "already_voted" && err.code !== "not_voted") throw err;
          resync = true;
          return;
        }
        if ((voteUpdates.get(item.idea_id) ?? 0) === seen) item.vote_count += voted ? -1 : 1;
        if (voted) state.voted.delete(item.idea_id);
        else state.voted.add(item.idea_id);
      });
      // Update this button only. Re-sorting here would move the idea out from under the
      // finger that just voted; the order catches up on the next sort change. Live vote
      // counts don't re-sort either.
      if (resync) await refresh();
      else draw();
      button.focus();
    });
    draw();
    return { button, draw };
  }

  function commentItem(comment) {
    return h(
      "li",
      { class: "comment" },
      h("p", { class: "comment-body" }, comment.body),
      h("p", { class: "byline" }, comment.author_id === me ? "You" : comment.author_name, " · ", formatTime(comment.created_at)),
    );
  }

  // Returns { el, threadList, drawSummary }, or null when there's nothing to show or do.
  function commentsBlock(item) {
    const id = item.idea_id;
    const thread = state.comments[id] ?? [];
    const summary = h("summary");
    const drawSummary = () => {
      const n = item.comment_count;
      summary.textContent = n ? `${n} ${n === 1 ? "comment" : "comments"}` : "Comment";
    };
    drawSummary();
    const threadList = h("ul", { class: "comments" }, thread.map(commentItem));
    if (!item.comment_count && !canWrite()) return null;

    let form = null;
    if (canWrite()) {
      const box = textBox({
        id: `comment-${id}`,
        label: "Your comment",
        max: MAX_COMMENT,
        placeholder: "Add a comment",
        value: state.drafts.get(id) ?? "",
      });
      box.textarea.addEventListener("input", () => state.drafts.set(id, box.textarea.value));
      const alert = alertBox();
      const submit = h("button", { class: "button button-quiet", type: "submit" }, "Comment");
      form = h(
        "form",
        {
          class: "comment-form",
          onsubmit: async (event) => {
            event.preventDefault();
            const body = box.textarea.value.trim();
            if (!body) {
              alert.textContent = "Type your comment first.";
              box.textarea.focus();
              return;
            }
            const ok = await attempt(submit, alert, async () => {
              addComment(await api.postComment(roomId, item.idea_sk, state.name, body));
            });
            if (!ok) return;
            state.drafts.delete(id);
            box.textarea.value = "";
            box.update();
            box.textarea.focus();
          },
        },
        h("div", { class: "bar-field" }, box.textarea, submit),
        box.counter,
        alert,
      );
    }

    const details = h("details", { class: "thread", open: state.expanded.has(id) }, summary, threadList, form);
    details.addEventListener("toggle", () => {
      if (details.open) state.expanded.add(id);
      else state.expanded.delete(id);
    });
    return { el: details, threadList, drawSummary };
  }

  function ideaRow(item) {
    const alert = alertBox();
    const mine = item.author_id === me;
    const vote = voteButton(item, alert);
    const thread = commentsBlock(item);
    const el = h(
      "li",
      { class: "idea" },
      vote.button,
      h(
        "div",
        { class: "idea-main" },
        h("p", { class: "idea-body" }, item.body),
        h("p", { class: "byline" }, mine ? "You" : item.author_name, " · ", formatTime(item.created_at)),
        thread?.el,
        alert,
      ),
    );
    rows.set(item.idea_id, { el, vote, thread });
    return el;
  }

  function drawCount() {
    const n = state.ideas.length;
    ideaCount.textContent = n === 1 ? "1 idea" : `${n} ideas`;
    empty.hidden = n > 0;
    // Only invite a first idea when this person can actually post one: not in a closed room,
    // and not on the instructor's read-only copy.
    if (!isOpen()) empty.textContent = "No ideas here.";
    else if (embedded) empty.textContent = "No ideas yet.";
    else empty.textContent = "No ideas yet. Be the first.";
  }

  function drawList() {
    rows.clear();
    list.replaceChildren(...sortedIdeas().map(ideaRow));
    drawCount();
  }

  // -- Changes, from this browser's own writes, live messages, or a reload --
  // Each one is applied on its own and skipped if already here: messages can come twice, and
  // a comment can arrive before its idea (data-model.md section 6).

  const byId = (ideaId) => state.ideas.find((i) => i.idea_id === ideaId);

  function addIdea(item) {
    if (byId(item.idea_id)) return;
    // Comments that arrived before the idea are already in state.comments.
    const early = state.comments[item.idea_id]?.length ?? 0;
    item = { ...item, comment_count: Math.max(item.comment_count, early) };
    // Keep newest first even if ideas arrive out of order (idea_sk sorts by time).
    const at = state.ideas.findIndex((i) => i.idea_sk < item.idea_sk);
    state.ideas.splice(at === -1 ? state.ideas.length : at, 0, item);
    // Place the row where the current sort would put it, without moving the others.
    const order = sortedIdeas();
    const next = order[order.indexOf(item) + 1];
    list.insertBefore(ideaRow(item), next ? rows.get(next.idea_id)?.el ?? null : null);
    drawCount();
  }

  function setVoteCount(ideaId, count) {
    voteUpdates.set(ideaId, (voteUpdates.get(ideaId) ?? 0) + 1);
    const item = byId(ideaId);
    if (!item || item.vote_count === count) return;
    item.vote_count = count;
    rows.get(ideaId)?.vote.draw();
  }

  function addComment(comment, { count = true } = {}) {
    const id = comment.idea_id;
    const thread = state.comments[id] ?? [];
    if (thread.some((c) => c.comment_id === comment.comment_id)) return;
    // Oldest first; created_at is fixed-width, so string order is time order.
    const at = thread.findIndex((c) => c.created_at > comment.created_at);
    thread.splice(at === -1 ? thread.length : at, 0, comment);
    state.comments[id] = thread;
    const item = byId(id);
    if (!item) return; // its idea_added will pick it up
    if (count) item.comment_count += 1;
    redrawComments(item);
  }

  // Redraw one idea's comments. Rows drawn without a comments block (no comments, can't
  // write) are rebuilt; otherwise the open form and its draft stay as they are.
  function redrawComments(item) {
    const row = rows.get(item.idea_id);
    if (!row) return;
    if (!row.thread) {
      row.el.replaceWith(ideaRow(item));
      return;
    }
    row.thread.threadList.replaceChildren(...(state.comments[item.idea_id] ?? []).map(commentItem));
    row.thread.drawSummary();
  }

  // A fresh copy of the board (after a reconnect, or Refresh): merge it into what's shown.
  function applyBoard(board, voted) {
    const wasOpen = isOpen();
    state.room = board.room;
    state.voted = new Set(voted);
    for (const thread of Object.values(board.comments ?? {})) {
      for (const comment of thread) addComment(comment, { count: false });
    }
    for (const fresh of board.ideas) {
      const item = byId(fresh.idea_id);
      if (!item) {
        addIdea(fresh);
        continue;
      }
      item.vote_count = fresh.vote_count;
      if (item.comment_count !== fresh.comment_count) {
        item.comment_count = fresh.comment_count;
        redrawComments(item);
      }
    }
    if (wasOpen !== isOpen()) {
      drawAll();
      return;
    }
    drawHead();
    for (const row of rows.values()) row.vote.draw();
  }

  function roomClosed() {
    live.stop();
    if (!isOpen()) return;
    state.room.status = "closed";
    drawAll();
  }

  function onMessage(message) {
    switch (message.type) {
      case "idea_added":
        addIdea(message.idea);
        break;
      case "vote_count_changed":
        setVoteCount(message.idea_id, message.vote_count);
        break;
      case "comment_added":
        addComment(message.comment);
        break;
      case "room_closed":
        roomClosed();
        break;
      case "room_expired":
        roomGone({ code: "room_not_found", message: "This room has expired and its ideas were deleted." });
        break;
      // participant_joined: the board doesn't list people (the projector counts them).
    }
  }

  const empty = h("p", { class: "empty" });

  // -- Live status and Refresh --

  const refreshAlert = alertBox();
  const liveStatus = h("span", { class: "live", role: "status" });
  const refreshButton = h("button", { class: "button button-quiet", type: "button" }, "Refresh");
  const refreshGroup = h("div", { class: "refresh" }, liveStatus, refreshButton);

  // Load the board again and merge it in. Live messages that arrive meanwhile wait, then go on
  // top, so a message newer than the copy isn't overwritten by it.
  let queued = null;
  async function reload() {
    queued = [];
    try {
      const [board, voted] = await fetchBoard();
      applyBoard(board, voted);
      onLoad?.(state.room);
    } finally {
      const waiting = queued;
      queued = null;
      waiting.forEach(onMessage);
    }
  }
  async function refresh(button = refreshButton) {
    await attempt(button, refreshAlert, reload);
  }
  refreshButton.addEventListener("click", () => refresh());

  const LIVE_TEXT = { connecting: "Connecting…", live: "Live", offline: "Reconnecting…" };
  function drawLive(liveState) {
    liveStatus.dataset.state = liveState;
    liveStatus.textContent = isOpen() ? LIVE_TEXT[liveState] : "";
  }

  function drawAll() {
    drawHead();
    drawBar();
    drawList();
    if (!isOpen()) liveStatus.textContent = "";
  }

  const listSection = h(
    "section",
    { class: "board-list", "aria-labelledby": "ideas-heading" },
    h(
      "div",
      { class: "list-bar" },
      ideaCount,
      h("fieldset", { class: "sort" }, h("legend", { class: "visually-hidden" }, "Sort ideas"), sortButtons),
    ),
    empty,
    list,
  );

  if (embedded) {
    // The projector shows liveStatus in its own banner, next to its own Refresh button.
    page = h("div", { class: "board-embed" }, refreshAlert, listSection);
    page.refresh = refresh;
    page.liveStatus = liveStatus;
    drawList();
  } else {
    page = h(
      "div",
      { class: "page page-board" },
      h(
        "header",
        { class: "masthead" },
        // Back to the join page: the writing box rises back into the code field.
        h("a", { class: "wordmark", href: "#/", onclick: slideOnClick("#/", "morph") }, "Brainstorm Board"),
      ),
      refreshAlert,
      head,
      listSection,
      bar,
    );
    drawAll();
  }

  // A closed room refuses sockets and gets no more changes, so only open rooms connect.
  const live = isOpen()
    ? connectLive(roomId, {
        onMessage: (message) => (queued ? queued.push(message) : onMessage(message)),
        onSync: async () => {
          try {
            await reload();
          } catch (err) {
            if (!handleRoomGone(err)) throw err;
          }
          return isOpen() && page.isConnected;
        },
        onState: drawLive,
      })
    : { stop() {} };
  page.teardown = () => live.stop();
  return page;
}
