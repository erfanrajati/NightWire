"use strict";

const workspaceMode = document.body.dataset.scope === "workspace";
const state = { folder: null, breadcrumbs: [], folders: [], files: [], texts: [], workspace: null, user: null };
const items = document.querySelector("#items");
const notice = document.querySelector("#notice");

function scopeBase() { return workspaceMode ? `/api/workspaces/${state.workspace.id}` : "/api/library"; }

async function api(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (response.status === 401) { window.location.replace("/library/login"); throw new Error("Sign in required."); }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function json(method, payload) {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) };
}

function showNotice(message, error = false) {
  notice.textContent = message; notice.classList.toggle("error", error); notice.hidden = false;
  window.setTimeout(() => { notice.hidden = true; }, 5000);
}

function formatSize(bytes) {
  if (bytes === null || bytes === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"]; let value = bytes; let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

async function loadUsage() {
  if (workspaceMode && !state.workspace) return;
  const usage = await api(`${scopeBase()}/usage`);
  const text = document.querySelector("#usageText"), meter = document.querySelector("#usageMeter");
  text.textContent = usage.limit_bytes ? `${formatSize(usage.used_bytes)} of ${formatSize(usage.limit_bytes)}` : `${formatSize(usage.used_bytes)} used · unlimited`;
  meter.max = usage.limit_bytes || Math.max(usage.used_bytes, 1); meter.value = usage.used_bytes;
}

function actionButton(label, action) {
  const button = document.createElement("button"); button.type = "button"; button.textContent = label;
  button.addEventListener("click", action); return button;
}

function render() {
  document.querySelector("#folderName").textContent = state.folder.name;
  const count = state.folders.length + state.files.length + state.texts.length;
  document.querySelector("#itemCount").textContent = `${count} item${count === 1 ? "" : "s"}`;
  const crumbs = document.querySelector("#breadcrumbs"); crumbs.replaceChildren();
  state.breadcrumbs.forEach((folder, index) => {
    const rootLabel = workspaceMode ? state.workspace.name : "My Library";
    const button = actionButton(index ? folder.name : rootLabel, () => load(folder.id));
    if (folder.id === state.folder.id) button.setAttribute("aria-current", "page");
    crumbs.append(button); if (index < state.breadcrumbs.length - 1) crumbs.append(" / ");
  });
  items.replaceChildren();
  [...state.folders, ...state.texts, ...state.files].forEach((item) => items.append(renderItem(item)));
  document.querySelector("#emptyState").hidden = count !== 0;
}

function resultBase(item) {
  return item.scope?.kind === "workspace" ? `/api/workspaces/${item.scope.id}` : "/api/library";
}

function textEditorUrl(item, base = scopeBase()) {
  const workspaceMatch = base.match(/^\/api\/workspaces\/([^/]+)/);
  return workspaceMatch
    ? `/workspaces/${encodeURIComponent(workspaceMatch[1])}/texts/${encodeURIComponent(item.id)}`
    : `/library/texts/${encodeURIComponent(item.id)}`;
}

function fileDetailUrl(item, base = scopeBase()) {
  const workspaceMatch = base.match(/^\/api\/workspaces\/([^/]+)/);
  return workspaceMatch
    ? `/workspaces/${encodeURIComponent(workspaceMatch[1])}/files/${encodeURIComponent(item.id)}`
    : `/library/files/${encodeURIComponent(item.id)}`;
}

function renderSearch(data) {
  document.querySelector("#folderName").textContent = `Search: ${data.query}`;
  document.querySelector("#itemCount").textContent = `${data.results.length} result${data.results.length === 1 ? "" : "s"}`;
  const crumbs = document.querySelector("#breadcrumbs"); crumbs.replaceChildren();
  crumbs.append(actionButton("Back to folder", () => { document.querySelector("#searchInput").value = ""; load(); }));
  items.replaceChildren();
  data.results.forEach((item) => {
    const row = document.createElement("div"); row.className = "item-row";
    const name = document.createElement("button"); name.className = "item-name"; name.type = "button";
    const icon = document.createElement("span"); icon.setAttribute("aria-hidden", "true"); icon.textContent = "▤";
    const label = document.createElement("strong"); label.textContent = item.name;
    const path = document.createElement("small"); path.className = "search-path"; path.textContent = `${item.scope.name} · ${item.path}`;
    const text = document.createElement("span"); text.append(label, path); name.append(icon, text);
    name.addEventListener("click", () => item.type === "text" ? openTextDetails(item, resultBase(item)) : openFileDetails(item, resultBase(item)));
    const size = document.createElement("span"); size.textContent = item.type === "text" ? `${item.mode} Text` : formatSize(item.size);
    const updated = document.createElement("span"); updated.textContent = new Date(item.updated_at).toLocaleDateString();
    const action = item.type === "text"
      ? actionButton("View", () => openTextDetails(item, resultBase(item)))
      : actionButton("Download", () => window.location.assign(`${resultBase(item)}/files/${item.id}/download`));
    row.append(name, size, updated, action); items.append(row);
  });
  document.querySelector("#emptyState").hidden = data.results.length !== 0;
}

let searchTimer;
async function performSearch() {
  const input = document.querySelector("#searchInput"), query = input?.value.trim();
  if (!query) { await load(); return; }
  try {
    const selected = document.querySelector("#searchScope").value;
    const data = await api(`/api/library/search?q=${encodeURIComponent(query)}&scope=${encodeURIComponent(selected)}`);
    renderSearch(data);
  } catch (error) { showNotice(error.message, true); }
}

function renderItem(item) {
  const row = document.createElement("div"); row.className = "item-row"; row.setAttribute("role", "row");
  const name = document.createElement("button"); name.className = "item-name"; name.type = "button";
  name.innerHTML = `<span aria-hidden="true">${item.type === "folder" ? "◇" : item.type === "text" ? "¶" : "▤"}</span><strong></strong>`;
  name.querySelector("strong").textContent = item.name;
  name.addEventListener("click", () => item.type === "folder" ? load(item.id) : item.type === "text" ? openTextDetails(item) : openFileDetails(item));
  const size = document.createElement("span"); size.textContent = item.type === "file" ? formatSize(item.size) : item.type === "text" ? `${item.mode} Text` : "Folder";
  const updated = document.createElement("span"); updated.textContent = new Date(item.updated_at).toLocaleDateString();
  const details = document.createElement("details"); details.className = "item-menu";
  const summary = document.createElement("summary"); summary.setAttribute("aria-label", `Actions for ${item.name}`); summary.textContent = "•••";
  const menu = document.createElement("div");
  if (item.type === "file") {
    menu.append(actionButton("Details", () => openFileDetails(item)));
    menu.append(actionButton("Download", () => window.location.assign(`${scopeBase()}/files/${item.id}/download`)));
  }
  if (item.type === "text") {
    menu.append(actionButton("Edit", () => openTextDetails(item)));
    menu.append(actionButton("Share", () => createShare(item, scopeBase())));
  }
  menu.append(actionButton("Rename", () => promptName("Rename item", item.name, async (nameValue) => {
    await api(`${scopeBase()}/${item.type}s/${item.id}`, json("PATCH", { name: nameValue })); await load();
  })));
  menu.append(actionButton("Move", () => promptMove(item)));
  if (item.type !== "text") {
    menu.append(actionButton("Copy", async () => { try { await api(`${scopeBase()}/${item.type}s/${item.id}/copy`, json("POST", { parent_id: state.folder.id })); await load(); } catch (error) { showNotice(error.message, true); } }));
    menu.append(actionButton("Duplicate", async () => { try { await api(`${scopeBase()}/${item.type}s/${item.id}/duplicate`, json("POST", {})); await load(); } catch (error) { showNotice(error.message, true); } }));
  }
  const trash = actionButton("Move to Trash", async () => { if (!window.confirm(`Move “${item.name}” to Trash?`)) return; try { await api(`${scopeBase()}/${item.type}s/${item.id}`, { method: "DELETE" }); await load(); } catch (error) { showNotice(error.message, true); } });
  trash.className = "danger-action"; menu.append(trash); details.append(summary, menu);
  row.append(name, size, updated, details); return row;
}

async function openTextDetails(item, base = scopeBase()) {
  window.location.assign(textEditorUrl(item, base));
}

function detailDialog() {
  let dialog = document.querySelector("#fileDetailsDialog");
  if (dialog) return dialog;
  dialog = document.createElement("dialog"); dialog.id = "fileDetailsDialog"; dialog.className = "file-details-dialog";
  dialog.innerHTML = `<div class="file-details"><header><div><p class="eyebrow">FILE DETAILS</p><h3></h3></div><button type="button" class="secondary-button close-details">Close</button></header><section><div class="detail-section-heading"><h4>Versions</h4><label class="secondary-button version-upload">Add version<input type="file"></label></div><div class="version-list detail-list"></div></section><section><h4>Derived Outputs</h4><div class="derived-list detail-list"></div></section><section><div class="detail-section-heading"><h4>Shares</h4><button type="button" class="secondary-button create-share">Create share</button></div><div class="share-list detail-list"></div></section></div>`;
  document.body.append(dialog);
  dialog.querySelector(".close-details").addEventListener("click", () => dialog.close());
  return dialog;
}

function detailRow(title, subtitle, actions = []) {
  const row = document.createElement("div"), text = document.createElement("div");
  const strong = document.createElement("strong"); strong.textContent = title;
  const small = document.createElement("small"); small.textContent = subtitle; text.append(strong, small);
  const buttons = document.createElement("div"); actions.forEach(([label, action]) => buttons.append(actionButton(label, action)));
  row.append(text, buttons); return row;
}

async function openFileDetails(item, base = scopeBase()) {
  window.location.assign(fileDetailUrl(item, base));
  return;
  const dialog = detailDialog();
  try {
    const [details, shareData] = await Promise.all([
      api(`${base}/files/${item.id}`), api(`${base}/files/${item.id}/shares`),
    ]);
    dialog.querySelector("h3").textContent = details.file.name;
    const versions = dialog.querySelector(".version-list"); versions.replaceChildren();
    details.versions.forEach((version, index) => {
      const actions = [["Download", () => window.location.assign(`${base}/files/${item.id}/versions/${version.id}/download`)]];
      if (index) actions.push(["Restore", async () => { await api(`${base}/files/${item.id}/versions/${version.id}/restore`, { method: "POST" }); await openFileDetails(item, base); await load(); }]);
      versions.append(detailRow(`Version ${version.version}${index === 0 ? " · Current" : ""}`, `${formatSize(version.size)} · ${new Date(version.created_at).toLocaleString()} · ${version.source_kind}`, actions));
    });
    const outputs = dialog.querySelector(".derived-list"); outputs.replaceChildren();
    details.derived_outputs.forEach((output) => {
      const actions = output.promoted_version_id ? [] : [["Promote", async () => { await api(`${base}/files/${item.id}/derived-outputs/${output.id}/promote`, { method: "POST" }); await openFileDetails(item, base); await load(); }]];
      outputs.append(detailRow(output.operation, `${formatSize(output.size)} · ${new Date(output.created_at).toLocaleString()}${output.promoted_version_id ? " · Promoted" : ""}`, actions));
    });
    if (!details.derived_outputs.length) outputs.append(detailRow("No derived outputs", "Processors can attach generic outputs through the public API."));
    const shares = dialog.querySelector(".share-list"); shares.replaceChildren();
    shareData.shares.forEach((share) => {
      const actions = [];
      if (share.share_url) actions.push(["Copy", () => copyShareUrl(share.share_url)], ["QR", () => showShareResult(share)]);
      if (share.status === "active") actions.push(["Revoke", async () => { if (!window.confirm(`Revoke share for “${share.name}”?`)) return; await api(`/api/library/shares/${share.id}`, { method: "DELETE" }); await openFileDetails(item, base); }]);
      const keyNote = share.access_key_required && !share.share_url ? " · protected key not recoverable" : "";
      shares.append(detailRow(share.status === "active" ? "Active share" : `${share.status[0].toUpperCase()}${share.status.slice(1)} share`, `${share.expires_at ? new Date(share.expires_at).toLocaleString() : "No expiry"}${keyNote}`, actions));
    });
    if (!shareData.shares.length) shares.append(detailRow("No shares", "Create a read-only external grant for this version."));
    dialog.querySelector(".create-share").onclick = () => createShare(item, base);
    const versionInput = dialog.querySelector(".version-upload input");
    versionInput.onchange = async () => {
      const file = versionInput.files[0]; if (!file) return;
      try { await api(`${base}/files/${item.id}/versions`, { method: "PUT", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file }); await openFileDetails(item, base); await load(); }
      catch (error) { showNotice(error.message, true); }
      versionInput.value = "";
    };
    if (!dialog.open) dialog.showModal();
  } catch (error) { showNotice(error.message, true); }
}

async function copyShareUrl(value) {
  try { await navigator.clipboard.writeText(value); showNotice("Share URL copied."); }
  catch (_) { window.prompt("Copy this share URL", value); }
}

function showShareResult(share, oneTimeKey = false) {
  const dialog = document.createElement("dialog"); dialog.className = "share-result-dialog";
  const box = document.createElement("div"); box.className = "share-result";
  const title = document.createElement("h3"); title.textContent = oneTimeKey ? "Save this protected URL now" : "Share link";
  const note = document.createElement("p"); note.textContent = oneTimeKey ? "The Access Key is stored only as a digest and this complete URL cannot be recovered later." : "This URL stays reusable until expiry or revocation.";
  const code = document.createElement("code"); code.textContent = share.share_url;
  const image = document.createElement("img"); image.src = share.qr_url; image.alt = "QR code for share URL";
  const footer = document.createElement("footer"), copy = actionButton("Copy URL", () => copyShareUrl(share.share_url));
  const close = actionButton("Done", () => { dialog.close(); dialog.remove(); }); footer.append(copy, close);
  box.append(title, note, code, image, footer); dialog.append(box); document.body.append(dialog); dialog.showModal();
}

function createShare(item, base) {
  const dialog = document.createElement("dialog"); dialog.className = "share-result-dialog";
  const form = document.createElement("form"); form.className = "share-create-form";
  const title = document.createElement("h3"); title.textContent = `Share ${item.name}`;
  const expiryLabel = document.createElement("label"); expiryLabel.textContent = "Expiry";
  const expiry = document.createElement("select"); [["No expiry",0],["1 hour",3600],["1 day",86400],["7 days",604800],["30 days",2592000]].forEach(([label,value]) => { const option = document.createElement("option"); option.textContent = label; option.value = value; expiry.append(option); }); expiryLabel.append(expiry);
  const protectLabel = document.createElement("label"); protectLabel.className = "checkbox-label"; const protect = document.createElement("input"); protect.type = "checkbox"; protectLabel.append(protect, " Require reusable Access Key");
  const footer = document.createElement("footer"), cancel = actionButton("Cancel", () => { dialog.close(); dialog.remove(); }), create = document.createElement("button"); create.type = "submit"; create.className = "primary-button"; create.textContent = "Create share"; footer.append(cancel, create);
  form.append(title, expiryLabel, protectLabel, footer); dialog.append(form); document.body.append(dialog); dialog.showModal();
  form.onsubmit = async (event) => { event.preventDefault(); create.disabled = true; try { const data = await api(`${base}/${item.type === "text" ? "texts" : "files"}/${item.id}/shares`, json("POST", { expires_in_seconds: Number(expiry.value), access_key_protected: protect.checked })); dialog.close(); dialog.remove(); showShareResult(data.share, Boolean(data.access_key)); if (item.type !== "text") await openFileDetails(item, base); } catch (error) { showNotice(error.message, true); create.disabled = false; } };
}

async function load(folderId = state.folder?.id) {
  try {
    const data = folderId ? await api(`${scopeBase()}/folders/${folderId}`) : await api(scopeBase());
    Object.assign(state, data); if (data.user) document.querySelector("#currentName").textContent = data.user.display_name;
    render();
    await loadUsage();
  } catch (error) { showNotice(error.message, true); }
}

function promptName(title, value, callback) {
  const dialog = document.querySelector("#nameDialog"); const form = document.querySelector("#nameForm");
  document.querySelector("#dialogTitle").textContent = title; document.querySelector("#nameInput").value = value || "";
  document.querySelector("#dialogError").textContent = ""; dialog.showModal(); document.querySelector("#nameInput").focus();
  form.onsubmit = async (event) => { event.preventDefault(); if (event.submitter?.value === "cancel") { dialog.close(); return; } try { await callback(document.querySelector("#nameInput").value); dialog.close(); } catch (error) { document.querySelector("#dialogError").textContent = error.message; } };
}

async function allFolders() {
  const root = state.breadcrumbs[0]; const found = [];
  async function walk(folder) { found.push(folder); const data = await api(`${scopeBase()}/folders/${folder.id}`); for (const child of data.folders) await walk(child); }
  await walk(root); return found;
}

async function promptMove(item) {
  const dialog = document.querySelector("#moveDialog"); const select = document.querySelector("#moveDestination");
  try {
    const folders = await allFolders(); select.replaceChildren();
    folders.filter((folder) => folder.id !== item.id).forEach((folder) => {
      const option = document.createElement("option"); option.value = folder.id; option.textContent = folder.name; select.append(option);
    });
    select.value = state.folder.id; document.querySelector("#moveError").textContent = ""; dialog.showModal();
    document.querySelector("#moveForm").onsubmit = async (event) => { event.preventDefault(); if (event.submitter?.value === "cancel") { dialog.close(); return; } try { await api(`${scopeBase()}/${item.type}s/${item.id}`, json("PATCH", { parent_id: select.value })); dialog.close(); await load(); } catch (error) { document.querySelector("#moveError").textContent = error.message; } };
  } catch (error) { showNotice(error.message, true); }
}

function confirmDuplicate(data) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog"); dialog.className = "duplicate-dialog";
    const box = document.createElement("div"); box.className = "duplicate-warning";
    const title = document.createElement("h3"); title.textContent = "Possible duplicate";
    const intro = document.createElement("p"); intro.textContent = "Nothing was added. Review the matches, then upload anyway if this is intentional.";
    const list = document.createElement("ul");
    data.warnings.forEach((warning) => warning.candidates.forEach((candidate) => {
      const line = document.createElement("li");
      line.textContent = `${warning.kind === "checksum_match" ? "Same content" : "Same name"}: ${candidate.path} (${formatSize(candidate.size)})`;
      list.append(line);
    }));
    const footer = document.createElement("footer"), cancel = actionButton("Cancel", () => finish(false));
    const proceed = actionButton("Upload anyway", () => finish(true)); proceed.className = "primary-button";
    function finish(value) { dialog.close(); dialog.remove(); resolve(value); }
    footer.append(cancel, proceed); box.append(title, intro, list, footer); dialog.append(box); document.body.append(dialog); dialog.showModal();
  });
}

function upload(file, confirmed = false, existingEntry = null) {
  const queue = document.querySelector("#uploadQueue"); queue.hidden = false;
  const entry = existingEntry || document.createElement("div"); entry.className = "upload-entry";
  if (!existingEntry) { const label = document.createElement("span"); label.textContent = file.name; const progress = document.createElement("progress"); const status = document.createElement("span"); entry.append(label, progress, status); queue.append(entry); }
  const progress = entry.querySelector("progress"), status = entry.querySelector("span:last-child"); progress.max = file.size || 1; progress.value = 0; status.textContent = confirmed ? "Confirming…" : "0%"; entry.classList.remove("failed");
  const confirmation = confirmed ? "&confirm_duplicates=true" : "";
  const xhr = new XMLHttpRequest(); xhr.open("PUT", `${scopeBase()}/folders/${state.folder.id}/upload?name=${encodeURIComponent(file.name)}${confirmation}`); xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
  xhr.upload.onprogress = (event) => { if (event.lengthComputable) { progress.max = event.total; progress.value = event.loaded; status.textContent = `${Math.round(event.loaded / event.total * 100)}%`; } };
  xhr.onload = async () => { if (xhr.status >= 200 && xhr.status < 300) { status.textContent = "Done"; await load(); return; } try { const data = JSON.parse(xhr.responseText); if (xhr.status === 409 && data.code === "duplicate_warning") { status.textContent = "Review needed"; if (await confirmDuplicate(data)) upload(file, true, entry); else entry.classList.add("failed"); return; } status.textContent = data.error || "Upload failed"; } catch (_) { status.textContent = "Upload failed"; } entry.classList.add("failed"); };
  xhr.onerror = () => { status.textContent = "Upload failed"; entry.classList.add("failed"); }; xhr.send(file);
}

document.querySelector("#newFolderButton")?.addEventListener("click", () => promptName("New folder", "", async (name) => { await api(`${scopeBase()}/folders`, json("POST", { parent_id: state.folder.id, name })); await load(); }));
function openNewTextDialog() {
  const dialog = document.querySelector("#newTextDialog"), form = document.querySelector("#newTextForm");
  form.reset(); form.querySelector(".new-text-error").textContent = ""; form.querySelector(".new-text-language").hidden = true; dialog.showModal(); form.elements.title.focus();
}
document.querySelector("#newTextButton")?.addEventListener("click", openNewTextDialog);
document.querySelector("#newTextForm")?.elements.mode.addEventListener("change", (event) => { document.querySelector(".new-text-language").hidden = event.target.value !== "code"; });
document.querySelector("[data-cancel-text]")?.addEventListener("click", () => document.querySelector("#newTextDialog").close());
document.querySelector("#newTextForm")?.addEventListener("submit", async (event) => {
  event.preventDefault(); const form = event.currentTarget, submit = form.querySelector("button[type=submit]"); submit.disabled = true;
  try {
    const payload = Object.fromEntries(new FormData(form)); if (payload.mode !== "code") payload.language = null; else if (!payload.language) payload.language = null;
    const data = await api(`${scopeBase()}/folders/${state.folder.id}/texts`, json("POST", payload));
    window.location.assign(textEditorUrl(data.text));
  } catch (error) { form.querySelector(".new-text-error").textContent = error.message; submit.disabled = false; }
});
document.querySelector("#fileInput")?.addEventListener("change", (event) => { [...event.target.files].forEach(upload); event.target.value = ""; });
document.querySelector("#librarySearch")?.addEventListener("submit", (event) => { event.preventDefault(); performSearch(); });
document.querySelector("#searchInput")?.addEventListener("input", () => { window.clearTimeout(searchTimer); searchTimer = window.setTimeout(performSearch, 220); });
document.querySelector("#searchScope")?.addEventListener("change", performSearch);
document.querySelector("#logoutButton").addEventListener("click", async () => { await api("/api/library/auth/logout", { method: "POST" }); window.location.assign("/library/login"); });

function renderMembers(data) {
  const list = document.querySelector("#memberList"); list.replaceChildren();
  document.querySelector("#addMemberForm").hidden = data.workspace.owner_user_id !== data.user.id;
  data.members.forEach((member) => {
    const row = document.createElement("div"); const label = document.createElement("span");
    label.textContent = `${member.display_name} · ${member.email}${member.is_owner ? " · Owner" : ""}`; row.append(label);
    if (data.workspace.owner_user_id === data.user.id && !member.is_owner) row.append(actionButton("Remove", async () => { try { await api(`/api/workspaces/${data.workspace.id}/members/${member.id}`, { method: "DELETE" }); await start(); } catch (error) { showNotice(error.message, true); } }));
    list.append(row);
  });
}

async function start() {
  if (!workspaceMode) { await load(); return; }
  try {
    const data = await api("/api/workspaces"); state.user = data.user; document.querySelector("#currentName").textContent = data.user.display_name;
    if (!data.workspace) { document.querySelector("#workspaceOnboarding").hidden = false; document.querySelector("#workspaceApp").hidden = true; return; }
    state.workspace = data.workspace; document.querySelector("#workspaceOnboarding").hidden = true; document.querySelector("#workspaceApp").hidden = false; document.querySelector("#workspaceName").textContent = data.workspace.name; renderMembers(data); await load();
  } catch (error) { showNotice(error.message, true); }
}

document.querySelector("#createWorkspaceForm")?.addEventListener("submit", async (event) => { event.preventDefault(); try { await api("/api/workspaces", json("POST", Object.fromEntries(new FormData(event.target)))); await start(); } catch (error) { showNotice(error.message, true); } });
document.querySelector("#addMemberForm")?.addEventListener("submit", async (event) => { event.preventDefault(); try { await api(`/api/workspaces/${state.workspace.id}/members`, json("POST", Object.fromEntries(new FormData(event.target)))); event.target.reset(); await start(); } catch (error) { showNotice(error.message, true); } });
document.querySelector("#leaveWorkspaceButton")?.addEventListener("click", async () => { if (!window.confirm("Leave this Workspace?")) return; try { await api(`/api/workspaces/${state.workspace.id}/members/me`, { method: "DELETE" }); state.workspace = null; await start(); } catch (error) { showNotice(error.message, true); } });
start();
