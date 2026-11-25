// Talks to the HTTP API (docs/api.md). Every request carries this browser's user id.
import { API_URL } from "../config.js";

const USER_KEY = "brainstorm.userId";

// Made-up user id, kept in localStorage so the same browser keeps its rooms and votes.
// The API accepts 1-64 of [A-Za-z0-9_-]. getRandomValues (unlike randomUUID) also works on
// plain http, e.g. a phone opening the local server by its LAN address.
function newUserId() {
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  return "u-" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

let cachedUserId = null;

export function userId() {
  if (cachedUserId) return cachedUserId;
  try {
    cachedUserId = localStorage.getItem(USER_KEY);
  } catch {
    // Storage blocked (private mode, etc.): the id just lasts until the page reloads.
  }
  if (!cachedUserId || !/^[A-Za-z0-9_-]{1,64}$/.test(cachedUserId)) {
    cachedUserId = newUserId();
    try {
      localStorage.setItem(USER_KEY, cachedUserId);
    } catch {
      // See above.
    }
  }
  return cachedUserId;
}

// What to show people for each error code in docs/api.md ("Errors").
const MESSAGES = {
  invalid_input: "That doesn't look right. Check the text and try again.",
  missing_user: "Your browser's user id is missing. Reload the page and try again.",
  not_room_owner: "Only the person who created this room can close it.",
  not_found: "That page doesn't exist.",
  room_not_found: "We couldn't find that room. Check the code, or the room may have expired.",
  idea_not_found: "That idea isn't in this room any more.",
  room_closed: "This room is closed, so nothing can be added to it.",
  already_voted: "You already voted for this idea.",
  not_voted: "You haven't voted for this idea.",
  code_unavailable: "We couldn't make a join code just now. Try again.",
  busy: "Lots of people are using the board right now. Try again in a moment.",
  internal_error: "Something went wrong on our side. Try again.",
  network: "We couldn't reach the server. Check your connection and try again.",
};

export class ApiError extends Error {
  constructor(status, code, detail) {
    super(MESSAGES[code] ?? MESSAGES.internal_error);
    this.status = status;
    this.code = code;
    this.detail = detail; // the API's own message, for the console
  }
}

async function request(method, path, body) {
  const headers = { "X-User-Id": userId() };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(API_URL + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    throw new ApiError(0, "network", String(err));
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new ApiError(response.status, data?.error ?? "internal_error", data?.message);
    console.warn(`${method} ${path}: ${response.status} ${error.code}`, error.detail);
    throw error;
  }
  return data;
}

const room = (roomId) => `/rooms/${encodeURIComponent(roomId)}`;
const idea = (roomId, ideaSk) => `${room(roomId)}/ideas/${encodeURIComponent(ideaSk)}`;

// Instructor (#8)
export const createRoom = (topic) => request("POST", "/rooms", { topic });
export const myRooms = () => request("GET", "/my-rooms").then((r) => r.rooms);
export const closeRoom = (roomId) => request("POST", `${room(roomId)}/close`);

// Board and student flow (#9)
export const roomByCode = (code) => request("GET", `/codes/${encodeURIComponent(code.trim())}`);
export const board = (roomId, { withComments = false } = {}) =>
  request("GET", `${room(roomId)}${withComments ? "?comments=true" : ""}`);
export const joinRoom = (roomId, displayName) =>
  request("POST", `${room(roomId)}/join`, { display_name: displayName });
export const participants = (roomId) =>
  request("GET", `${room(roomId)}/participants`).then((r) => r.participants);
export const postIdea = (roomId, displayName, body) =>
  request("POST", `${room(roomId)}/ideas`, { display_name: displayName, body });
export const vote = (roomId, ideaSk) => request("PUT", `${idea(roomId, ideaSk)}/vote`);
export const unvote = (roomId, ideaSk) => request("DELETE", `${idea(roomId, ideaSk)}/vote`);
export const myVotes = (roomId) =>
  request("GET", `${room(roomId)}/my-votes`).then((r) => r.idea_ids);
export const postComment = (roomId, ideaSk, displayName, body) =>
  request("POST", `${idea(roomId, ideaSk)}/comments`, { display_name: displayName, body });
export const comments = (roomId, ideaSk) =>
  request("GET", `${idea(roomId, ideaSk)}/comments`).then((r) => r.comments);
