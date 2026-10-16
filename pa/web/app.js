const joinForm = document.querySelector("#join-form");
const messageForm = document.querySelector("#message-form");
const messageInput = document.querySelector("#message-input");
const sendButton = document.querySelector(".send-button");
const messageList = document.querySelector("#message-list");
const emptyState = document.querySelector("#empty-state");
const statusPanel = document.querySelector("#connection-status");
const statusLabel = document.querySelector("#status-label");
const liveIndicator = document.querySelector("#live-indicator");
const activeRoom = document.querySelector("#active-room");
const roomSubtitle = document.querySelector("#room-subtitle");
const httpEndpointInput = document.querySelector("#http-endpoint");
const wsEndpointInput = document.querySelector("#ws-endpoint");
const seenMessageIds = new Set();

let socket;
let currentRoom = "";
let currentUsername = "";

httpEndpointInput.value = localStorage.getItem("relay-http-endpoint") || "";
wsEndpointInput.value = localStorage.getItem("relay-ws-endpoint") || "";

function setStatus(state, label) {
  statusPanel.dataset.state = state;
  statusLabel.textContent = label;
  liveIndicator.dataset.active = String(state === "connected");
}

function setComposerEnabled(enabled) {
  messageInput.disabled = !enabled;
  sendButton.disabled = !enabled;
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
}

function addMessage(message) {
  if (!message || typeof message.id !== "string" || seenMessageIds.has(message.id)) return;
  seenMessageIds.add(message.id);
  emptyState.hidden = true;

  const row = document.createElement("article");
  row.className = "message";

  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = (message.username || "?").trim().slice(0, 1).toUpperCase();

  const content = document.createElement("div");
  content.className = "message-content";
  const meta = document.createElement("p");
  meta.className = "message-meta";
  const name = document.createElement("span");
  name.className = "message-name";
  name.textContent = message.username || "Anonymous";
  const time = document.createElement("time");
  time.className = "message-time";
  time.dateTime = message.sentAt || "";
  time.textContent = formatTime(message.sentAt);
  meta.append(name, time);

  const text = document.createElement("p");
  text.className = "message-text";
  text.textContent = message.text || "";
  content.append(meta, text);
  row.append(avatar, content);
  messageList.append(row);
  messageList.scrollTop = messageList.scrollHeight;
}

function endpointValues() {
  const httpUrl = httpEndpointInput.value.trim().replace(/\/+$/, "");
  const wsUrl = wsEndpointInput.value.trim();
  if (!httpUrl || !wsUrl) {
    throw new Error("Add your HTTP and WebSocket API URLs in Connection settings first.");
  }
  const http = new URL(httpUrl);
  const ws = new URL(wsUrl);
  if (!["https:", "http:"].includes(http.protocol) || !["wss:", "ws:"].includes(ws.protocol)) {
    throw new Error("Use an HTTP(S) URL and a WebSocket (WS(S)) URL.");
  }
  return { httpUrl: http.toString().replace(/\/+$/, ""), wsUrl: ws.toString() };
}

async function loadHistory(roomId, httpUrl, activeSocket) {
  const response = await fetch(`${httpUrl}/rooms/${encodeURIComponent(roomId)}/messages`);
  if (!response.ok) {
    throw new Error(`Could not load room history (HTTP ${response.status}).`);
  }
  const result = await response.json();
  if (socket !== activeSocket) return;
  for (const message of result.messages || []) addMessage(message);
}

joinForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!joinForm.reportValidity()) return;

  let endpoints;
  try {
    endpoints = endpointValues();
  } catch (error) {
    setStatus("offline", error.message);
    document.querySelector(".endpoint-settings").open = true;
    return;
  }

  const formData = new FormData(joinForm);
  const roomId = String(formData.get("roomId")).trim();
  const username = String(formData.get("username")).trim();
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(roomId)) {
    setStatus("offline", "Room names use letters, numbers, _ or - (up to 64).");
    return;
  }
  if (!username || username.length > 32) {
    setStatus("offline", "Display names must be 1-32 characters.");
    return;
  }

  if (socket) socket.close();
  currentRoom = roomId;
  currentUsername = username;
  activeRoom.textContent = roomId;
  roomSubtitle.textContent = "Connecting to your conversation…";
  messageList.querySelectorAll(".message").forEach((message) => message.remove());
  emptyState.hidden = false;
  seenMessageIds.clear();
  setComposerEnabled(false);
  setStatus("connecting", "Connecting…");

  const activeSocket = new WebSocket(endpoints.wsUrl);
  socket = activeSocket;
  activeSocket.addEventListener("open", () => {
    if (socket !== activeSocket) return;
    activeSocket.send(JSON.stringify({ action: "join", roomId, username }));
  });
  activeSocket.addEventListener("message", async (event) => {
    if (socket !== activeSocket) return;
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      setStatus("connected", "Received an unreadable server response.");
      return;
    }
    if (data.type === "joined") {
      roomSubtitle.textContent = "Messages sync live for everyone in this room";
      setStatus("connected", `Connected as ${currentUsername}`);
      setComposerEnabled(true);
      try {
        await loadHistory(currentRoom, endpoints.httpUrl, activeSocket);
      } catch (error) {
        if (socket === activeSocket) setStatus("connected", error.message);
      }
    } else if (data.type === "message") {
      addMessage(data.message);
    } else if (data.type === "error") {
      setStatus("connected", data.message || "The server could not process that action.");
    }
  });
  activeSocket.addEventListener("error", () => {
    if (socket !== activeSocket) return;
    setStatus("offline", "Could not connect. Check the WebSocket URL and try again.");
    setComposerEnabled(false);
  });
  activeSocket.addEventListener("close", () => {
    if (socket !== activeSocket) return;
    setStatus("offline", "Not connected");
    roomSubtitle.textContent = "Connection closed";
    setComposerEnabled(false);
  });
});

messageForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text || !socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ action: "sendMessage", roomId: currentRoom, text }));
  messageInput.value = "";
  messageInput.focus();
});

document.querySelector("#save-settings").addEventListener("click", () => {
  try {
    endpointValues();
    localStorage.setItem("relay-http-endpoint", httpEndpointInput.value.trim().replace(/\/+$/, ""));
    localStorage.setItem("relay-ws-endpoint", wsEndpointInput.value.trim());
    setStatus("offline", "Endpoints saved. Join a room to connect.");
  } catch (error) {
    setStatus("offline", error.message);
  }
});
