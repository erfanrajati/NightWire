"use strict";

const workspaceMode = window.location.pathname.startsWith("/workspaces");
const notice = document.querySelector("#notice");
let workspace = null;

async function api(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  let data = {}; try { data = await response.json(); } catch (_) {}
  if (response.status === 401) { window.location.replace("/library/login"); throw new Error("Sign in required."); }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function base() { return workspaceMode ? `/api/workspaces/${workspace.id}` : "/api/library"; }

function showNotice(message, error = false) {
  notice.textContent = message; notice.classList.toggle("error", error); notice.hidden = false;
  window.setTimeout(() => { notice.hidden = true; }, 5000);
}

function button(label, action, className = "") {
  const element = document.createElement("button"); element.type = "button"; element.textContent = label;
  element.className = className; element.addEventListener("click", action); return element;
}

function renderItem(item) {
  const row = document.createElement("div"); row.className = "item-row trash-row";
  const name = document.createElement("span"); name.className = "item-name";
  const icon = document.createElement("span"); icon.textContent = item.type === "folder" ? "◇" : "▤";
  const strong = document.createElement("strong"); strong.textContent = item.name; name.append(icon, strong);
  const type = document.createElement("span"); type.textContent = item.type === "folder" ? "Folder tree" : item.type === "text" ? "Text" : "File";
  const deleted = document.createElement("span"); deleted.textContent = new Date(item.trashed_at).toLocaleString();
  const actions = document.createElement("div"); actions.className = "trash-actions";
  actions.append(button("Restore", async () => { try { await api(`${base()}/trash/${item.type}s/${item.id}/restore`, { method: "POST" }); showNotice(`Restored “${item.name}”.`); await load(); } catch (error) { showNotice(error.message, true); } }, "secondary-button"));
  actions.append(button("Delete forever", async () => { if (!window.confirm(`Permanently delete “${item.name}”? This cannot be undone.`)) return; try { await api(`${base()}/trash/${item.type}s/${item.id}`, { method: "DELETE" }); showNotice(`Permanently deleted “${item.name}”.`); await load(); } catch (error) { showNotice(error.message, true); } }, "danger-button"));
  row.append(name, type, deleted, actions); return row;
}

async function load() {
  try {
    const data = await api(`${base()}/trash`); const all = [...data.folders, ...(data.texts || []), ...data.files];
    document.querySelector("#trashItems").replaceChildren(...all.map(renderItem));
    document.querySelector("#itemCount").textContent = `${all.length} item${all.length === 1 ? "" : "s"}`;
    document.querySelector("#emptyState").hidden = all.length !== 0;
    const days = Math.round(data.retention_seconds / 86400);
    document.querySelector("#retentionText").textContent = `Items are automatically removed after ${days} day${days === 1 ? "" : "s"}.`;
    if (data.user) document.querySelector("#currentName").textContent = data.user.display_name;
  } catch (error) { showNotice(error.message, true); }
}

async function start() {
  if (workspaceMode) {
    const data = await api("/api/workspaces");
    if (!data.workspace) { window.location.replace("/workspaces"); return; }
    workspace = data.workspace; document.querySelector("#scopeLabel").textContent = workspace.name;
    document.querySelector("#trashTitle").textContent = `${workspace.name} Trash`;
    document.querySelector("#backLink").href = "/workspaces"; document.querySelector("#returnLink").href = "/workspaces";
    document.querySelector("#returnLink").textContent = "Back to Workspace";
  }
  await load();
}

document.querySelector("#logoutButton").addEventListener("click", async () => { await api("/api/library/auth/logout", { method: "POST" }); window.location.assign("/library/login"); });
start();
