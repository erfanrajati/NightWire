"use strict";

// Drop-owned v1.0.2 frontend behavior, loaded by the shared application shell.

const state = {
  files: [],
  info: null,
  clientId: getClientId(),
  uploads: new Map(),
  clipboardEntries: [],
  clipboardRevision: -1,
  detectedClipboardText: "",
  lastDetectedClipboardText: "",
  clipboardWatching: false,
  clipboardWatchBusy: false,
  suppressCopyCapture: false,
  initialClipboardLoaded: false,
  currentRoute: "files",
  devices: [],
  settingsTarget: null,
  passwordAction: null,
  expiryReloadPending: false,
  dropCredentials: {},
  voiceRecorder: null,
  voiceStream: null,
  voiceChunks: [],
  voiceAudioContext: null,
  voiceAnalyser: null,
  voiceAnimationFrame: null,
  voiceStartedAt: 0,
};

function credentialFor(file) {
  const credential = state.dropCredentials[file.name];
  if (!credential || credential.created_at !== file.created_at) return null;
  return credential;
}

function rememberDropCredential(file, accessKey, shareUrl) {
  const durableShareUrl = file.access_key_required
    ? shareUrl
    : (() => {
        const parsed = new URL(shareUrl, window.location.href);
        return `${parsed.origin}${parsed.pathname}`;
      })();
  state.dropCredentials[file.name] = {
    access_key: file.access_key_required ? accessKey : "",
    share_url: durableShareUrl,
    created_at: file.created_at,
  };
}

function withLocalCredential(file) {
  const credential = credentialFor(file);
  return credential ? { ...file, ...credential } : file;
}

const elements = {
  statusText: document.querySelector("#statusText"),
  statusPill: document.querySelector(".status-pill"),
  navItems: [...document.querySelectorAll("[data-route]")],
  routeLinks: [...document.querySelectorAll("[data-route-link]")],
  pageViews: [...document.querySelectorAll("[data-page]")],
  networkAddress: document.querySelector("#networkAddress"),
  networkAlternates: document.querySelector("#networkAlternates"),
  copyAddressButton: document.querySelector("#copyAddressButton"),
  fileInput: document.querySelector("#fileInput"),
  dropzone: document.querySelector("#dropzone"),
  fileExpiryPreset: document.querySelector("#fileExpiryPreset"),
  fileCustomExpiryWrap: document.querySelector("#fileCustomExpiryWrap"),
  fileCustomExpiry: document.querySelector("#fileCustomExpiry"),
  filePassword: document.querySelector("#filePassword"),
  filePasswordConfirmWrap: document.querySelector("#filePasswordConfirmWrap"),
  filePasswordConfirm: document.querySelector("#filePasswordConfirm"),
  dropTextInput: document.querySelector("#dropTextInput"),
  dropTextTitle: document.querySelector("#dropTextTitle"),
  dropTextMode: document.querySelector("#dropTextMode"),
  dropTextLanguageWrap: document.querySelector("#dropTextLanguageWrap"),
  dropTextLanguage: document.querySelector("#dropTextLanguage"),
  dropTextCharacterCount: document.querySelector("#dropTextCharacterCount"),
  shareTextDropButton: document.querySelector("#shareTextDropButton"),
  quickDropExpiryPreset: document.querySelector("#fileExpiryPreset"),
  quickDropCustomExpiryWrap: document.querySelector("#fileCustomExpiryWrap"),
  quickDropCustomExpiry: document.querySelector("#fileCustomExpiry"),
  recordVoiceButton: document.querySelector("#recordVoiceButton"),
  stopVoiceButton: document.querySelector("#stopVoiceButton"),
  voiceStatus: document.querySelector("#voiceStatus"),
  voiceCaptureInput: document.querySelector("#voiceCaptureInput"),
  voiceVisualizer: document.querySelector("#voiceVisualizer"),
  voiceElapsed: document.querySelector("#voiceElapsed"),
  activeDropsPanel: document.querySelector("#activeDropsPanel"),
  activeDropsUnavailable: document.querySelector("#activeDropsUnavailable"),
  fileCount: document.querySelector("#fileCount"),
  storageFree: document.querySelector("#storageFree"),
  protectedFileCount: document.querySelector("#protectedFileCount"),
  transferPanel: document.querySelector("#transferPanel"),
  transferList: document.querySelector("#transferList"),
  queueSummary: document.querySelector("#queueSummary"),
  searchInput: document.querySelector("#searchInput"),
  refreshButton: document.querySelector("#refreshButton"),
  fileList: document.querySelector("#fileList"),
  emptyState: document.querySelector("#emptyState"),
  clipboardSummary: document.querySelector("#clipboardSummary"),
  clipboardInput: document.querySelector("#clipboardInput"),
  clipboardCharacterCount: document.querySelector("#clipboardCharacterCount"),
  clipboardRecommendation: document.querySelector("#clipboardRecommendation"),
  clipboardRecommendationPreview: document.querySelector("#clipboardRecommendationPreview"),
  dismissClipboardButton: document.querySelector("#dismissClipboardButton"),
  shareDetectedClipboardButton: document.querySelector("#shareDetectedClipboardButton"),
  watchClipboardButton: document.querySelector("#watchClipboardButton"),
  clipboardWatchHint: document.querySelector("#clipboardWatchHint"),
  shareClipboardButton: document.querySelector("#shareClipboardButton"),
  clipboardExpiryPreset: document.querySelector("#clipboardExpiryPreset"),
  clipboardCustomExpiryWrap: document.querySelector("#clipboardCustomExpiryWrap"),
  clipboardCustomExpiry: document.querySelector("#clipboardCustomExpiry"),
  clipboardPassword: document.querySelector("#clipboardPassword"),
  clipboardPasswordConfirmWrap: document.querySelector("#clipboardPasswordConfirmWrap"),
  clipboardPasswordConfirm: document.querySelector("#clipboardPasswordConfirm"),
  clipboardList: document.querySelector("#clipboardList"),
  clipboardEmptyState: document.querySelector("#clipboardEmptyState"),
  deviceList: document.querySelector("#deviceList"),
  deviceSummary: document.querySelector("#deviceSummary"),
  clientsOnlineBadge: document.querySelector("#clientsOnlineBadge"),
  serverDirectory: document.querySelector("#serverDirectory"),
  versionText: document.querySelector("#versionText"),
  qrImage: document.querySelector("#qrImage"),
  qrLoading: document.querySelector("#qrLoading"),
  qrAddress: document.querySelector("#qrAddress"),
  copyQrAddressButton: document.querySelector("#copyQrAddressButton"),
  settingsModal: document.querySelector("#settingsModal"),
  settingsForm: document.querySelector("#settingsForm"),
  settingsTitle: document.querySelector("#settingsTitle"),
  settingsSubtitle: document.querySelector("#settingsSubtitle"),
  closeSettingsButton: document.querySelector("#closeSettingsButton"),
  cancelSettingsButton: document.querySelector("#cancelSettingsButton"),
  saveSettingsButton: document.querySelector("#saveSettingsButton"),
  settingsExpiryPreset: document.querySelector("#settingsExpiryPreset"),
  settingsCustomExpiryWrap: document.querySelector("#settingsCustomExpiryWrap"),
  settingsCustomExpiry: document.querySelector("#settingsCustomExpiry"),
  settingsExpiryStatus: document.querySelector("#settingsExpiryStatus"),
  settingsUnlimitedOption: document.querySelector("#settingsUnlimitedOption"),
  passwordModal: document.querySelector("#passwordModal"),
  passwordForm: document.querySelector("#passwordForm"),
  passwordTitle: document.querySelector("#passwordTitle"),
  passwordSubtitle: document.querySelector("#passwordSubtitle"),
  passwordInput: document.querySelector("#passwordInput"),
  submitPasswordButton: document.querySelector("#submitPasswordButton"),
  shareModal: document.querySelector("#shareModal"),
  shareUrlInput: document.querySelector("#shareUrlInput"),
  closeShareButton: document.querySelector("#closeShareButton"),
  dismissShareButton: document.querySelector("#dismissShareButton"),
  copyShareButton: document.querySelector("#copyShareButton"),
  shareQrImage: document.querySelector("#shareQrImage"),
  closePasswordButton: document.querySelector("#closePasswordButton"),
  cancelPasswordButton: document.querySelector("#cancelPasswordButton"),
  toastRegion: document.querySelector("#toastRegion"),
};

function getClientId() {
  const key = "nightwire-client-id";
  try {
    const stored = localStorage.getItem(key);
    if (stored && /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/.test(stored)) return stored;
  } catch (_) {}
  const value = globalThis.crypto?.randomUUID?.() || `nw-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  try { localStorage.setItem(key, value); } catch (_) {}
  return value;
}

async function api(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (data.error) message = data.error;
    } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

function setServerOnline(online) {
  elements.statusText.textContent = online ? "Online" : "Offline";
  elements.statusPill.classList.toggle("offline", !online);
}

function toast(message, type = "info") {
  const item = document.createElement("div");
  item.className = `toast${type === "error" ? " error" : type === "success" ? " success" : ""}`;
  item.textContent = message;
  elements.toastRegion.append(item);
  setTimeout(() => item.remove(), 3900);
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB", "PB"];
  let value = bytes;
  let index = -1;
  do { value /= 1024; index += 1; } while (value >= 1024 && index < units.length - 1);
  return `${value >= 10 ? value.toFixed(1) : value.toFixed(2)} ${units[index]}`;
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown date";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function relativeTime(value) {
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "Active now";
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 5) return "Active now";
  if (seconds < 60) return `Active ${seconds}s ago`;
  return `Active ${Math.floor(seconds / 60)}m ago`;
}

function formatCountdown(value) {
  if (!value) return "Unlimited";
  const remaining = Math.max(0, Math.floor((new Date(value).getTime() - Date.now()) / 1000));
  if (remaining <= 0) return "Deleting now";
  const days = Math.floor(remaining / 86400);
  const hours = Math.floor((remaining % 86400) / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  const seconds = remaining % 60;
  if (days) return `Deletes in ${days}d ${hours}h`;
  if (hours) return `Deletes in ${hours}h ${minutes}m`;
  if (minutes) return `Deletes in ${minutes}m ${seconds}s`;
  return `Deletes in ${seconds}s`;
}

function fileExtension(name) {
  const parts = name.split(".");
  return parts.length > 1 ? parts.pop().slice(0, 4) : "file";
}

async function copyText(value) {
  if (!value) return false;
  state.suppressCopyCapture = true;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
    throw new Error("Clipboard API unavailable");
  } catch (_) {
    const input = document.createElement("textarea");
    input.value = value;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.append(input);
    input.select();
    const copied = document.execCommand("copy");
    input.remove();
    return copied;
  } finally {
    setTimeout(() => { state.suppressCopyCapture = false; }, 0);
  }
}

function routeFromPath() {
  const route = window.location.pathname.split("/").filter(Boolean)[0] || "files";
  return ["files", "clipboard", "clients"].includes(route) ? route : "files";
}

function setRoute(route, push = false) {
  const resolved = ["files", "clipboard", "clients"].includes(route) ? route : "files";
  state.currentRoute = resolved;
  for (const item of elements.navItems) {
    const active = item.dataset.route === resolved;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  }
  for (const page of elements.pageViews) page.hidden = page.dataset.page !== resolved;
  const labels = { files: "Secure Drop", clipboard: "Clipboard", clients: "Clients" };
  document.title = `NightWire — ${labels[resolved]}`;
  if (push && window.location.pathname !== `/${resolved}`) history.pushState({ route: resolved }, "", `/${resolved}`);
  window.scrollTo(0, 0);
  if (resolved === "files") renderFiles();
  else if (resolved === "clipboard") renderClipboard();
  else if (resolved === "clients" && state.devices.length) renderDevices(state.devices);
}

async function loadInfo() {
  const info = await api("/api/info");
  state.info = info;
  const dropMaximum = info.drop_max_expiry_seconds || 365 * 86400;
  elements.fileCustomExpiry.max = String(Math.floor(dropMaximum / 60));
  for (const select of new Set([elements.fileExpiryPreset, elements.quickDropExpiryPreset])) {
    for (const option of select.options) {
      const seconds = Number.parseInt(option.value, 10);
      const unavailable = Number.isFinite(seconds) && seconds > dropMaximum;
      option.hidden = unavailable;
      option.disabled = unavailable;
    }
  }
  const base = info.primary_network_url;
  const primary = `${base}/files`;
  elements.networkAddress.textContent = primary;
  elements.networkAddress.title = primary;
  elements.qrAddress.textContent = primary;
  if (elements.serverDirectory) elements.serverDirectory.textContent = info.directory;
  elements.versionText.textContent = info.version;
  elements.clipboardInput.maxLength = info.clipboard_max_text_length || 32768;
  const maximumMinutes = String(Math.floor((info.item_max_expiry_seconds || 365 * 86400) / 60));
  elements.settingsCustomExpiry.max = maximumMinutes;
  elements.clipboardCustomExpiry.max = maximumMinutes;
  updateClipboardCharacterCount();

  const alternatives = (info.network_urls || []).filter((url) => url !== base).map((url) => `${url}/files`);
  elements.networkAlternates.textContent = alternatives.length ? `Also available: ${alternatives.join(" · ")}` : "";
  elements.networkAlternates.classList.toggle("hidden", alternatives.length === 0);
  for (const button of [elements.copyAddressButton, elements.copyQrAddressButton]) {
    button.dataset.address = primary;
    button.disabled = false;
  }
  elements.qrLoading.textContent = "Generating QR code…";
  elements.qrLoading.classList.remove("hidden");
  elements.qrImage.classList.remove("loaded");
  elements.qrImage.src = `/api/qr?url=${encodeURIComponent(primary)}&v=${Date.now()}`;
}

async function loadFiles({ quiet = true } = {}) {
  if (!state.info?.active_drop_browsing) {
    state.files = [];
    elements.activeDropsPanel.classList.add("hidden");
    elements.activeDropsUnavailable.classList.remove("hidden");
    if (elements.fileCount) elements.fileCount.textContent = "—";
    if (elements.protectedFileCount) elements.protectedFileCount.textContent = "—";
    return;
  }
  elements.activeDropsPanel.classList.remove("hidden");
  elements.activeDropsUnavailable.classList.add("hidden");
  try {
    const data = await api("/api/drops");
    state.files = (data.drops || []).map(withLocalCredential);
    const activeNames = new Set(state.files.map((file) => file.name));
    for (const name of Object.keys(state.dropCredentials)) {
      if (!activeNames.has(name)) delete state.dropCredentials[name];
    }
    if (elements.fileCount) elements.fileCount.textContent = String(state.files.length);
    if (elements.protectedFileCount) elements.protectedFileCount.textContent = String(state.files.filter((file) => file.password_protected).length);
    if (elements.storageFree) elements.storageFree.textContent = data.usage?.limit_bytes
      ? `${formatBytes(data.usage.available_bytes)} quota available`
      : `${formatBytes(data.storage?.free)} host free`;
    if (state.currentRoute === "files") renderFiles();
    setServerOnline(true);
  } catch (error) {
    setServerOnline(false);
    if (!quiet) toast(error.message, "error");
    throw error;
  }
}

function createStatusBadge(label, kind = "") {
  const badge = document.createElement("span");
  badge.className = `status-badge${kind ? ` ${kind}` : ""}`;
  badge.textContent = label;
  return badge;
}

const securityStates = {
  clean: { label: "Security: clean", kind: "security-clean" },
  suspicious: { label: "Warning: suspicious", kind: "security-warning" },
  malicious: { label: "Danger: malicious", kind: "security-danger" },
  scan_failed: { label: "Warning: scan failed", kind: "security-warning" },
  unscanned: { label: "Warning: unscanned", kind: "security-warning" },
};

function securityState(file) {
  const verdict = file.security?.verdict || file.security_verdict || "unscanned";
  return { verdict, ...(securityStates[verdict] || securityStates.unscanned) };
}

function renderFiles() {
  const term = elements.searchInput?.value.trim().toLowerCase() || "";
  const files = state.files.filter((file) => file.name.toLowerCase().includes(term));
  elements.fileList.replaceChildren();
  elements.emptyState.classList.toggle("hidden", files.length > 0);
  if (!files.length) {
    elements.emptyState.querySelector("h4").textContent = term ? "No matching Drops" : "No active Drops";
    elements.emptyState.querySelector("p").textContent = term ? "Try another filter." : "Create one above. It will remain available through its private link until expiration.";
    return;
  }

  for (const file of files) {
    const row = document.createElement("article");
    row.className = "file-row";

    const icon = document.createElement("div");
    icon.className = "file-icon";
    icon.textContent = fileExtension(file.name);

    const meta = document.createElement("div");
    meta.className = "file-meta";
    const name = document.createElement("strong");
    name.textContent = file.name;
    name.title = file.name;
    const detail = document.createElement("div");
    detail.className = "file-detail";
    const size = document.createElement("span");
    size.textContent = formatBytes(file.size);
    const modified = document.createElement("span");
    modified.textContent = formatDate(file.modified);
    detail.append(size, modified);
    const statuses = document.createElement("div");
    statuses.className = "item-status-line";
    if (file.password_protected) statuses.append(createStatusBadge("Password protected", "locked"));
    const security = securityState(file);
    statuses.append(createStatusBadge(security.label, security.kind));
    const expiry = createStatusBadge(formatCountdown(file.expires_at), file.expires_at ? "expiring" : "unlimited");
    expiry.dataset.expiresAt = file.expires_at || "";
    expiry.dataset.itemKind = "file";
    statuses.append(expiry);
    meta.append(name, detail, statuses);

    const actions = document.createElement("div");
    actions.className = "file-actions";
    const download = actionButton(
      security.verdict === "malicious"
        ? "Hold to download"
        : (file.password_protected ? "Unlock & download" : "Download"),
      security.verdict === "malicious" ? "danger-action" : "primary-action",
    );
    if (security.verdict === "malicious") armHoldToConfirm(download, () => downloadFile(file, true));
    else download.addEventListener("click", () => downloadFile(file));
    const shareUrl = credentialFor(file)?.share_url || file.share_url;
    const share = actionButton(shareUrl ? "Access link & QR" : "Access link unavailable");
    share.disabled = !shareUrl;
    if (shareUrl) share.addEventListener("click", () => showShareUrl(shareUrl));
    const remove = actionButton("Delete", "danger-action");
    remove.addEventListener("click", () => deleteFile(file));
    actions.append(download, share, remove);
    row.append(icon, meta, actions);
    elements.fileList.append(row);
  }
}

function actionButton(label, className = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `action-button${className ? ` ${className}` : ""}`;
  button.textContent = label;
  return button;
}

function armHoldToConfirm(button, confirmedAction) {
  const holdMilliseconds = 1800;
  const idleLabel = button.textContent;
  let timer = null;
  let startedAt = 0;
  let animation = null;
  let confirmed = false;

  const reset = () => {
    if (timer) clearTimeout(timer);
    if (animation) cancelAnimationFrame(animation);
    timer = null;
    animation = null;
    startedAt = 0;
    button.textContent = idleLabel;
    button.classList.remove("hold-confirming");
  };
  const update = () => {
    if (!startedAt) return;
    const percent = Math.min(100, Math.round(((performance.now() - startedAt) / holdMilliseconds) * 100));
    button.textContent = `Keep holding… ${percent}%`;
    if (percent < 100) animation = requestAnimationFrame(update);
  };
  const begin = (event) => {
    if (button.disabled || timer) return;
    event.preventDefault();
    confirmed = false;
    startedAt = performance.now();
    button.classList.add("hold-confirming");
    toast("Keep holding to deliberately download this malicious Drop.", "error");
    update();
    timer = setTimeout(() => {
      timer = null;
      confirmed = true;
      reset();
      confirmedAction();
    }, holdMilliseconds);
  };
  const cancel = (event) => {
    if (confirmed) return;
    event.preventDefault();
    if (timer) reset();
  };

  button.addEventListener("click", (event) => event.preventDefault());
  button.addEventListener("pointerdown", begin);
  for (const eventName of ["pointerup", "pointercancel", "pointerleave"]) button.addEventListener(eventName, cancel);
  button.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) begin(event); });
  button.addEventListener("keyup", (event) => { if (["Enter", " "].includes(event.key)) cancel(event); });
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

async function downloadProtectedFile(file, password, confirmedMalicious = false) {
  const credential = credentialFor(file);
  if (file.access_key_required && !credential) throw new Error("This browser no longer has the Drop Access Key. Open the complete share URL instead.");
  const keyQuery = file.access_key_required && credential ? `?key=${encodeURIComponent(credential.access_key)}` : "";
  const response = await fetch(`/api/files/${encodeURIComponent(file.name)}/download${keyQuery}`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password, confirm_malicious: confirmedMalicious }),
  });
  if (!response.ok) {
    let message = `Download failed (${response.status})`;
    try { message = (await response.json()).error || message; } catch (_) {}
    throw new Error(message);
  }
  triggerDownload(await response.blob(), file.name);
  toast("Download started.", "success");
}

function downloadFile(file, confirmedMalicious = false) {
  const credential = credentialFor(file);
  if (file.access_key_required && !credential) {
    toast("This browser no longer has the Drop Access Key. Open the complete share URL instead.", "error");
    return;
  }
  if (securityState(file).verdict === "malicious" && !confirmedMalicious) {
    toast("Hold the download button to deliberately confirm this malicious download.", "error");
    return;
  }
  if (!file.password_protected) {
    const query = new URLSearchParams();
    if (file.access_key_required && credential) query.set("key", credential.access_key);
    if (confirmedMalicious) query.set("confirm_malicious", "true");
    const queryString = query.toString();
    const anchor = document.createElement("a");
    anchor.href = `/download/${encodeURIComponent(file.name)}${queryString ? `?${queryString}` : ""}`;
    anchor.download = file.name;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    return;
  }
  askPassword("Unlock file", file.name, "Download", (password) => downloadProtectedFile(file, password, confirmedMalicious));
}

async function performDeleteFile(file, password = undefined) {
  await api(`/api/files/${encodeURIComponent(file.name)}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(password === undefined ? {} : { password }),
  });
  state.files = state.files.filter((item) => item.name !== file.name);
  delete state.dropCredentials[file.name];
  renderFiles();
  if (elements.fileCount) elements.fileCount.textContent = String(state.files.length);
  if (elements.protectedFileCount) elements.protectedFileCount.textContent = String(state.files.filter((item) => item.password_protected).length);
  toast("File deleted.", "success");
}

function deleteFile(file) {
  if (!file.password_protected) {
    if (!confirm(`Delete “${file.name}” for every connected client?`)) return;
    performDeleteFile(file).catch((error) => toast(error.message, "error"));
    return;
  }
  askPassword("Delete protected file", file.name, "Delete", async (password) => {
    if (!confirm(`Permanently delete “${file.name}”?`)) return;
    await performDeleteFile(file, password);
  });
}

function selectedExpirySeconds(select, customInput, label, maximumSeconds = state.info?.item_max_expiry_seconds || 365 * 86400) {
  const value = select.value;
  if (value !== "custom") return Number.parseInt(value, 10);
  const minutes = Number(customInput.value);
  const maximum = Math.floor(maximumSeconds / 60);
  if (!Number.isFinite(minutes) || minutes < 1 || minutes > maximum) {
    throw new Error(`${label} countdown must be between 1 and ${maximum.toLocaleString()} minutes.`);
  }
  return Math.round(minutes * 60);
}

function selectedCreationPassword(input, confirmation, label) {
  const password = input.value;
  if (!password) return "";
  if (password !== confirmation.value) throw new Error(`${label} password confirmation does not match.`);
  return password;
}

function utf8ToBase64(value) {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function updateCreationFields() {
  elements.fileCustomExpiryWrap.classList.toggle("hidden", elements.fileExpiryPreset.value !== "custom");
  elements.clipboardCustomExpiryWrap.classList.toggle("hidden", elements.clipboardExpiryPreset.value !== "custom");
  if (elements.filePasswordConfirmWrap && elements.filePassword) {
    elements.filePasswordConfirmWrap.classList.toggle("hidden", !elements.filePassword.value);
  }
  elements.clipboardPasswordConfirmWrap.classList.toggle("hidden", !elements.clipboardPassword.value);
}

function quickDropExpirySeconds() {
  return selectedExpirySeconds(
    elements.quickDropExpiryPreset,
    elements.quickDropCustomExpiry,
    "Drop",
    state.info?.drop_max_expiry_seconds || 365 * 86400,
  );
}

function fileUploadSettings() {
  return {
    expiresInSeconds: selectedExpirySeconds(elements.fileExpiryPreset, elements.fileCustomExpiry, "Drop", state.info?.drop_max_expiry_seconds || 365 * 86400),
    password: "",
  };
}

function clipboardShareSettings() {
  return {
    expiresInSeconds: selectedExpirySeconds(elements.clipboardExpiryPreset, elements.clipboardCustomExpiry, "Clipboard"),
    password: selectedCreationPassword(elements.clipboardPassword, elements.clipboardPasswordConfirm, "Clipboard"),
  };
}

function queueFiles(fileList) {
  const candidates = [...fileList];
  const files = candidates.slice(0, 1);
  if (!files.length) return;
  if (candidates.length > 1) toast("Create one Drop at a time; only the first file was selected.", "error");
  let settings;
  try { settings = fileUploadSettings(); } catch (error) { toast(error.message, "error"); elements.fileInput.value = ""; return; }
  files.forEach((file) => uploadFile(file, settings));
  elements.fileInput.value = "";
}

function uploadFile(file, settings) {
  const id = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const row = document.createElement("article");
  row.className = "transfer-item";
  const main = document.createElement("div");
  main.className = "transfer-main";
  const title = document.createElement("div");
  title.className = "transfer-title";
  const name = document.createElement("strong");
  name.textContent = file.name;
  const status = document.createElement("span");
  status.textContent = "Preparing…";
  title.append(name, status);
  const track = document.createElement("div");
  track.className = "progress-track";
  const bar = document.createElement("div");
  bar.className = "progress-bar";
  track.append(bar);
  main.append(title, track);
  const cancel = document.createElement("button");
  cancel.className = "transfer-cancel";
  cancel.type = "button";
  cancel.textContent = "Cancel";
  row.append(main, cancel);
  elements.transferList.prepend(row);
  elements.transferPanel.classList.remove("hidden");

  const xhr = new XMLHttpRequest();
  state.uploads.set(id, { xhr, row });
  updateQueueSummary();
  cancel.addEventListener("click", () => xhr.abort());
  xhr.open("PUT", `/api/drops/files?filename=${encodeURIComponent(file.name)}`);
  xhr.setRequestHeader("X-NightWire-Expires-In-Seconds", String(settings.expiresInSeconds));
  if (settings.password) xhr.setRequestHeader("X-NightWire-Password-B64", utf8ToBase64(settings.password));
  xhr.responseType = "json";
  xhr.upload.addEventListener("progress", (event) => {
    if (!event.lengthComputable) return;
    const percentage = Math.min(100, Math.round((event.loaded / event.total) * 100));
    bar.style.width = `${percentage}%`;
    status.textContent = `${percentage}% · ${formatBytes(event.loaded)} / ${formatBytes(event.total)}`;
  });
  xhr.addEventListener("load", () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      bar.style.width = "100%";
      status.textContent = "Complete";
      const uploaded = xhr.response?.file;
      if (uploaded) {
        rememberDropCredential(uploaded, xhr.response.access_key, xhr.response.share_url);
        const localUpload = withLocalCredential(uploaded);
        state.files = [localUpload, ...state.files.filter((item) => item.name !== uploaded.name)];
        if (state.currentRoute === "files") renderFiles();
        if (elements.fileCount) elements.fileCount.textContent = String(state.files.length);
        if (elements.protectedFileCount) elements.protectedFileCount.textContent = String(state.files.filter((item) => item.password_protected).length);
      }
      showShareUrl(xhr.response.share_url);
      toast(`${file.name} uploaded${settings.password ? " with permanent password protection" : ""}.`, "success");
    } else {
      status.textContent = "Failed";
      toast(xhr.response?.error || `Could not upload ${file.name}.`, "error");
    }
    finishUpload(id);
  });
  xhr.addEventListener("error", () => { status.textContent = "Failed"; toast(`Could not upload ${file.name}.`, "error"); finishUpload(id); });
  xhr.addEventListener("abort", () => { status.textContent = "Cancelled"; finishUpload(id); });
  xhr.send(file);
}

function acceptCreatedDrop(payload, successMessage) {
  const uploaded = payload?.file;
  if (uploaded) {
    rememberDropCredential(uploaded, payload.access_key, payload.share_url);
    const localUpload = withLocalCredential(uploaded);
    state.files = [localUpload, ...state.files.filter((item) => item.name !== uploaded.name)];
    if (state.currentRoute === "files" && state.info?.active_drop_browsing) renderFiles();
    if (state.info?.active_drop_browsing) {
      if (elements.fileCount) elements.fileCount.textContent = String(state.files.length);
      if (elements.protectedFileCount) elements.protectedFileCount.textContent = String(state.files.filter((item) => item.password_protected).length);
    }
  }
  showShareUrl(payload.share_url);
  toast(successMessage, "success");
}

function updateDropTextCharacterCount() {
  const maximum = elements.dropTextInput.maxLength || 32768;
  const length = elements.dropTextInput.value.length;
  elements.dropTextCharacterCount.textContent = `${length.toLocaleString()} / ${maximum.toLocaleString()}`;
  elements.shareTextDropButton.disabled = !elements.dropTextInput.value.trim();
}

async function shareDropText() {
  const text = elements.dropTextInput.value.trim();
  if (!text) return;
  elements.shareTextDropButton.disabled = true;
  try {
    const payload = await api("/api/drops/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        title: elements.dropTextTitle.value.trim() || "Shared Text",
        mode: elements.dropTextMode.value,
        language: elements.dropTextMode.value === "code" ? (elements.dropTextLanguage.value || null) : null,
        expires_in_seconds: quickDropExpirySeconds(),
      }),
    });
    elements.dropTextInput.value = "";
    updateDropTextCharacterCount();
    acceptCreatedDrop(payload, "Temporary text Drop created.");
  } catch (error) {
    toast(error.message, "error");
    updateDropTextCharacterCount();
  }
}

function voiceFilename(mimeType) {
  const extension = mimeType.includes("ogg")
    ? "ogg"
    : mimeType.includes("mp4")
      ? "m4a"
      : mimeType.includes("wav")
        ? "wav"
        : mimeType.includes("aac")
          ? "aac"
          : "webm";
  return `voice-${new Date().toISOString().replace(/[:.]/g, "-")}.${extension}`;
}

async function uploadVoiceBlob(blob) {
  const filename = voiceFilename(blob.type || "audio/webm");
  elements.voiceStatus.textContent = `Uploading ${formatBytes(blob.size)}…`;
  try {
    const response = await fetch(`/api/drops/files?filename=${encodeURIComponent(filename)}`, {
      method: "PUT",
      cache: "no-store",
      headers: {
        "Content-Type": blob.type || "audio/webm",
        "X-NightWire-Drop-Kind": "voice",
        "X-NightWire-Expires-In-Seconds": String(quickDropExpirySeconds()),
      },
      body: blob,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Voice upload failed (${response.status}).`);
    elements.voiceStatus.textContent = "Voice message uploaded through the Drop transfer pipeline.";
    acceptCreatedDrop(payload, "Voice-message Drop created.");
  } catch (error) {
    elements.voiceStatus.textContent = error.message;
    toast(error.message, "error");
  }
}

function recorderForStream(stream) {
  const candidates = [
    "audio/mp4;codecs=mp4a.40.2",
    "audio/mp4",
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
  ];
  for (const mimeType of candidates) {
    try {
      if (MediaRecorder.isTypeSupported?.(mimeType)) return new MediaRecorder(stream, { mimeType });
    } catch (_) {}
  }
  return new MediaRecorder(stream);
}

function drawVoiceMatrix() {
  const canvas = elements.voiceVisualizer;
  const context = canvas.getContext("2d");
  const analyser = state.voiceAnalyser;
  if (!context || !analyser) return;
  const values = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(values);
  const columns = 16;
  const rows = 4;
  const gap = 5;
  const cellWidth = (canvas.width - gap * (columns - 1)) / columns;
  const cellHeight = (canvas.height - gap * (rows - 1)) / rows;
  context.clearRect(0, 0, canvas.width, canvas.height);
  for (let column = 0; column < columns; column += 1) {
    const value = values[Math.floor((column / columns) * values.length)] / 255;
    const lit = Math.max(1, Math.ceil(value * rows));
    for (let row = 0; row < rows; row += 1) {
      const active = rows - row <= lit;
      context.fillStyle = active
        ? `rgba(104, 229, 238, ${0.38 + value * 0.62})`
        : "rgba(129, 160, 185, 0.12)";
      context.fillRect(column * (cellWidth + gap), row * (cellHeight + gap), cellWidth, cellHeight);
    }
  }
  const elapsed = Math.max(0, Math.floor((performance.now() - state.voiceStartedAt) / 1000));
  elements.voiceElapsed.textContent = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;
  state.voiceAnimationFrame = requestAnimationFrame(drawVoiceMatrix);
}

async function startVoiceVisualization(stream) {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return;
  try {
    state.voiceAudioContext = new AudioContextClass();
    await state.voiceAudioContext.resume();
    const source = state.voiceAudioContext.createMediaStreamSource(stream);
    state.voiceAnalyser = state.voiceAudioContext.createAnalyser();
    state.voiceAnalyser.fftSize = 64;
    source.connect(state.voiceAnalyser);
    state.voiceStartedAt = performance.now();
    elements.voiceVisualizer.classList.add("recording");
    drawVoiceMatrix();
  } catch (_) {
    // Recording remains functional when visual analysis is unavailable.
  }
}

function stopVoiceVisualization() {
  if (state.voiceAnimationFrame) cancelAnimationFrame(state.voiceAnimationFrame);
  state.voiceAnimationFrame = null;
  state.voiceAnalyser = null;
  state.voiceAudioContext?.close().catch(() => {});
  state.voiceAudioContext = null;
  state.voiceStartedAt = 0;
  elements.voiceVisualizer.classList.remove("recording");
}

function useVoiceCaptureFallback(message) {
  elements.voiceStatus.textContent = message;
  elements.voiceCaptureInput.click();
}

async function startVoiceRecording() {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    useVoiceCaptureFallback("Use your device recorder, then choose the audio message to share.");
    return;
  }
  try {
    state.voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.voiceChunks = [];
    const recorder = recorderForStream(state.voiceStream);
    state.voiceRecorder = recorder;
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data?.size) state.voiceChunks.push(event.data);
    });
    recorder.addEventListener("stop", () => {
      const type = recorder.mimeType || state.voiceChunks[0]?.type || "audio/webm";
      const blob = new Blob(state.voiceChunks, { type });
      state.voiceStream?.getTracks().forEach((track) => track.stop());
      stopVoiceVisualization();
      state.voiceRecorder = null;
      state.voiceStream = null;
      elements.recordVoiceButton.classList.remove("hidden");
      elements.stopVoiceButton.classList.add("hidden");
      if (blob.size) uploadVoiceBlob(blob);
      else elements.voiceStatus.textContent = "No audio was recorded.";
    }, { once: true });
    recorder.start(250);
    await startVoiceVisualization(state.voiceStream);
    elements.recordVoiceButton.classList.add("hidden");
    elements.stopVoiceButton.classList.remove("hidden");
    elements.voiceStatus.textContent = "Recording… stop when your message is ready.";
  } catch (error) {
    state.voiceStream?.getTracks().forEach((track) => track.stop());
    stopVoiceVisualization();
    state.voiceStream = null;
    state.voiceRecorder = null;
    if (!window.isSecureContext || error?.name === "NotSupportedError") {
      useVoiceCaptureFallback("Use your device recorder, then choose the audio message to share.");
    } else {
      elements.voiceStatus.textContent = "Microphone permission is required to record a voice message.";
      toast(error.message || "Microphone access was not granted.", "error");
    }
  }
}

function stopVoiceRecording() {
  if (state.voiceRecorder?.state === "recording") state.voiceRecorder.stop();
}

function finishUpload(id) {
  const upload = state.uploads.get(id);
  if (!upload) return;
  state.uploads.delete(id);
  upload.row.querySelector(".transfer-cancel")?.remove();
  setTimeout(() => {
    upload.row.remove();
    if (!state.uploads.size) elements.transferPanel.classList.add("hidden");
  }, 2400);
  updateQueueSummary();
  loadFiles().catch(() => {});
}

function updateQueueSummary() {
  const count = state.uploads.size;
  elements.queueSummary.textContent = `${count} ${count === 1 ? "transfer" : "transfers"}`;
}

function updateClipboardCharacterCount() {
  const maximum = elements.clipboardInput.maxLength > 0 ? elements.clipboardInput.maxLength : 32768;
  const length = elements.clipboardInput.value.length;
  elements.clipboardCharacterCount.textContent = `${length.toLocaleString()} / ${maximum.toLocaleString()}`;
  elements.shareClipboardButton.disabled = !elements.clipboardInput.value.trim();
}

function clipboardPreview(text, limit = 180) {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > limit ? `${normalized.slice(0, limit)}…` : normalized;
}

async function shareClipboardText(rawText) {
  const text = rawText.trim();
  if (!text) return;
  if (text.length > (state.info?.clipboard_max_text_length || 32768)) {
    toast("Copied text is too large for the shared clipboard.", "error");
    return;
  }
  let settings;
  try { settings = clipboardShareSettings(); } catch (error) { toast(error.message, "error"); return; }
  elements.shareClipboardButton.disabled = true;
  try {
    const payload = { client_id: state.clientId, text, expires_in_seconds: settings.expiresInSeconds };
    if (settings.password) payload.password = settings.password;
    const data = await api("/api/clipboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.clipboardEntries = [data.entry, ...state.clipboardEntries.filter((entry) => entry.id !== data.entry.id)].slice(0, state.info?.clipboard_history_limit || 40);
    state.clipboardRevision = data.revision;
    elements.clipboardInput.value = "";
    elements.clipboardPassword.value = "";
    elements.clipboardPasswordConfirm.value = "";
    updateCreationFields();
    updateClipboardCharacterCount();
    dismissClipboardRecommendation();
    if (state.currentRoute === "clipboard") renderClipboard();
    toast(`Text shared${settings.password ? " with permanent password protection" : ""}.`, "success");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    updateClipboardCharacterCount();
  }
}

async function loadClipboard() {
  try {
    const data = await api(`/api/clipboard?since_revision=${encodeURIComponent(state.clipboardRevision)}`);
    if (data.changed) {
      state.clipboardRevision = data.revision;
      state.clipboardEntries = data.entries || [];
      if (state.currentRoute === "clipboard") renderClipboard();
    }
    state.initialClipboardLoaded = true;
    setServerOnline(true);
  } catch (_) {
    setServerOnline(false);
  }
}

function renderClipboard() {
  const entries = state.clipboardEntries;
  elements.clipboardSummary.textContent = `${entries.length} ${entries.length === 1 ? "item" : "items"}`;
  elements.clipboardList.replaceChildren();
  elements.clipboardEmptyState.classList.toggle("hidden", entries.length > 0);

  for (const entry of entries) {
    const item = document.createElement("article");
    item.className = `clipboard-item${entry.client_id === state.clientId ? " own-item" : ""}`;
    const head = document.createElement("div");
    head.className = "clipboard-item-head";
    const meta = document.createElement("div");
    meta.className = "clipboard-item-meta";
    const source = document.createElement("strong");
    source.textContent = entry.client_id === state.clientId ? "Shared from this device" : (entry.source || "Connected device");
    const detail = document.createElement("small");
    detail.textContent = `${formatDate(entry.created_at)} · ${entry.ip_address || "Unknown IP"}`;
    meta.append(source, detail);
    const headBadges = document.createElement("div");
    headBadges.className = "clipboard-item-status";
    if (entry.password_protected) headBadges.append(createStatusBadge("Password protected", "locked"));
    head.append(meta, headBadges);

    let body;
    if (entry.password_protected) {
      body = document.createElement("div");
      body.className = "clipboard-locked";
      const icon = document.createElement("div");
      icon.className = "clipboard-lock-icon";
      icon.textContent = "●";
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = "Protected shared text";
      const hint = document.createElement("small");
      hint.textContent = `${entry.text_length.toLocaleString()} characters · enter the password to copy`;
      copy.append(title, hint);
      body.append(icon, copy);
    } else {
      body = document.createElement("pre");
      body.className = "clipboard-text";
      body.textContent = entry.text || "";
    }

    const footer = document.createElement("div");
    footer.className = "clipboard-item-footer";
    const statuses = document.createElement("div");
    statuses.className = "clipboard-item-status";
    const expiry = createStatusBadge(formatCountdown(entry.expires_at), entry.expires_at ? "expiring" : "unlimited");
    expiry.dataset.expiresAt = entry.expires_at || "";
    expiry.dataset.itemKind = "clipboard";
    statuses.append(expiry);
    const buttons = document.createElement("div");
    buttons.className = "clipboard-item-buttons";
    const copyButton = actionButton(entry.password_protected ? "Unlock & copy" : "Copy text", "primary-action");
    copyButton.addEventListener("click", () => copyClipboardEntry(entry));
    const manage = actionButton("Edit countdown");
    manage.addEventListener("click", () => openSettings("clipboard", entry));
    const remove = actionButton("Delete", "danger-action");
    remove.addEventListener("click", () => deleteClipboardEntry(entry));
    buttons.append(copyButton, manage, remove);
    footer.append(statuses, buttons);
    item.append(head, body, footer);
    elements.clipboardList.append(item);
  }
}

async function copyClipboardEntry(entry) {
  if (!entry.password_protected) {
    const copied = await copyText(entry.text || "");
    toast(copied ? "Shared text copied." : "Could not copy text.", copied ? "success" : "error");
    return;
  }
  askPassword("Unlock shared text", `${entry.text_length.toLocaleString()} protected characters`, "Copy text", async (password) => {
    const data = await api(`/api/clipboard/${encodeURIComponent(entry.id)}/unlock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const copied = await copyText(data.text);
    if (!copied) throw new Error("Could not copy text to this device.");
    toast("Protected text copied.", "success");
  });
}

async function performDeleteClipboard(entry, password = undefined) {
  const data = await api(`/api/clipboard/${encodeURIComponent(entry.id)}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(password === undefined ? {} : { password }),
  });
  state.clipboardEntries = state.clipboardEntries.filter((item) => item.id !== entry.id);
  state.clipboardRevision = data.revision;
  renderClipboard();
  toast("Shared text deleted.", "success");
}

function deleteClipboardEntry(entry) {
  if (!entry.password_protected) {
    if (!confirm("Delete this shared text for every connected client?")) return;
    performDeleteClipboard(entry).catch((error) => toast(error.message, "error"));
    return;
  }
  askPassword("Delete protected text", "The password is required before deletion.", "Delete", async (password) => {
    if (!confirm("Permanently delete this protected shared text?")) return;
    await performDeleteClipboard(entry, password);
  });
}

function recommendClipboardText(rawText) {
  const text = typeof rawText === "string" ? rawText.trim() : "";
  if (!text || text === state.lastDetectedClipboardText || text === elements.clipboardInput.value.trim()) return;
  if (text.length > (state.info?.clipboard_max_text_length || 32768)) return;
  state.detectedClipboardText = text;
  state.lastDetectedClipboardText = text;
  elements.clipboardRecommendationPreview.textContent = clipboardPreview(text);
  elements.clipboardRecommendation.classList.remove("hidden");
}

function dismissClipboardRecommendation() {
  state.detectedClipboardText = "";
  elements.clipboardRecommendation.classList.add("hidden");
}

function selectedTextFromTarget(target) {
  if (target instanceof HTMLTextAreaElement || (target instanceof HTMLInputElement && /^(text|search|url|tel|email)$/i.test(target.type))) {
    const start = target.selectionStart;
    const end = target.selectionEnd;
    if (Number.isInteger(start) && Number.isInteger(end) && end > start) return target.value.slice(start, end);
  }
  return window.getSelection()?.toString() || "";
}

async function readClipboardForRecommendation(showErrors = false) {
  if (!navigator.clipboard?.readText || !window.isSecureContext) {
    if (showErrors) {
      elements.clipboardWatchHint.textContent = "Automatic clipboard reading is unavailable on this browser/address. Paste anywhere on this page instead.";
      toast("Clipboard watching requires browser support and usually HTTPS or localhost.", "error");
    }
    return false;
  }
  if (state.clipboardWatchBusy || document.visibilityState !== "visible") return false;
  state.clipboardWatchBusy = true;
  try {
    recommendClipboardText(await navigator.clipboard.readText());
    return true;
  } catch (_) {
    if (showErrors) {
      elements.clipboardWatchHint.textContent = "Clipboard access was not granted. You can still paste anywhere on the page to share text.";
      toast("Clipboard permission was not granted.", "error");
    }
    return false;
  } finally {
    state.clipboardWatchBusy = false;
  }
}

async function toggleClipboardWatching() {
  if (state.clipboardWatching) {
    state.clipboardWatching = false;
    elements.watchClipboardButton.classList.remove("watching");
    elements.watchClipboardButton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5c5.5 0 9 7 9 7s-3.5 7-9 7-9-7-9-7 3.5-7 9-7Zm0 4a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"></path></svg>Watch my clipboard';
    elements.clipboardWatchHint.textContent = "Clipboard watching is off. Paste anywhere on this page and NightWire will still suggest sharing the text.";
    return;
  }
  if (!(await readClipboardForRecommendation(true))) return;
  state.clipboardWatching = true;
  elements.watchClipboardButton.classList.add("watching");
  elements.watchClipboardButton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"></path></svg>Watching clipboard';
  elements.clipboardWatchHint.textContent = "Clipboard watching is active while this tab is visible. New text is suggested, never shared without approval.";
  toast("Clipboard watching enabled.", "success");
}

function openSettings(kind, item) {
  state.settingsTarget = { kind, item };
  elements.settingsTitle.textContent = kind === "file" ? "Edit file countdown" : "Edit text countdown";
  elements.settingsSubtitle.textContent = kind === "file" ? item.name : `Shared text · ${item.text_length.toLocaleString()} characters`;
  elements.settingsExpiryPreset.value = "keep";
  elements.settingsUnlimitedOption.hidden = kind === "file";
  elements.settingsUnlimitedOption.disabled = kind === "file";
  const maximumSeconds = kind === "file"
    ? (state.info?.drop_max_expiry_seconds || 365 * 86400)
    : (state.info?.item_max_expiry_seconds || 365 * 86400);
  elements.settingsCustomExpiry.max = String(Math.floor(maximumSeconds / 60));
  elements.settingsCustomExpiry.value = kind === "file" ? "60" : "10";
  elements.settingsExpiryStatus.textContent = item.expires_at ? `Current setting: ${formatCountdown(item.expires_at)}.` : "Current setting: unlimited / never auto-delete.";
  updateSettingsFields();
  elements.settingsModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
  elements.settingsExpiryPreset.focus();
}

function updateSettingsFields() {
  elements.settingsCustomExpiryWrap.classList.toggle("hidden", elements.settingsExpiryPreset.value !== "custom");
}

function closeSettings() {
  state.settingsTarget = null;
  elements.settingsModal.classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function settingsExpirySeconds() {
  const value = elements.settingsExpiryPreset.value;
  if (value === "keep") return undefined;
  if (value !== "custom") return Number.parseInt(value, 10);
  const minutes = Number(elements.settingsCustomExpiry.value);
  const maximumSeconds = state.settingsTarget?.kind === "file" ? state.info?.drop_max_expiry_seconds : state.info?.item_max_expiry_seconds;
  const maximum = Math.floor((maximumSeconds || 365 * 86400) / 60);
  if (!Number.isFinite(minutes) || minutes < 1 || minutes > maximum) {
    throw new Error(`Custom countdown must be between 1 and ${maximum.toLocaleString()} minutes.`);
  }
  return Math.round(minutes * 60);
}

async function saveSettings(event) {
  event.preventDefault();
  const target = state.settingsTarget;
  if (!target) return;
  let expiry;
  try { expiry = settingsExpirySeconds(); } catch (error) { toast(error.message, "error"); return; }
  if (expiry === undefined) { closeSettings(); return; }
  elements.saveSettingsButton.disabled = true;
  try {
    if (target.kind === "file") {
      const data = await api(`/api/files/${encodeURIComponent(target.item.name)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expires_in_seconds: expiry }),
      });
      state.files = state.files.map((file) => file.name === data.file.name ? data.file : file);
      if (state.currentRoute === "files") renderFiles();
    } else {
      const data = await api(`/api/clipboard/${encodeURIComponent(target.item.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expires_in_seconds: expiry }),
      });
      state.clipboardEntries = state.clipboardEntries.map((entry) => entry.id === data.entry.id ? data.entry : entry);
      state.clipboardRevision = data.revision;
      if (state.currentRoute === "clipboard") renderClipboard();
    }
    closeSettings();
    toast("Auto-delete countdown updated.", "success");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    elements.saveSettingsButton.disabled = false;
  }
}

function askPassword(title, subtitle, submitLabel, action) {
  state.passwordAction = action;
  elements.passwordTitle.textContent = title;
  elements.passwordSubtitle.textContent = subtitle;
  elements.submitPasswordButton.textContent = submitLabel;
  elements.passwordInput.value = "";
  elements.passwordModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
  elements.passwordInput.focus();
}

function closePasswordModal() {
  state.passwordAction = null;
  elements.passwordModal.classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function showShareUrl(url) {
  if (!url) return;
  elements.shareUrlInput.value = url;
  elements.shareQrImage.src = `/api/qr?url=${encodeURIComponent(url)}&v=${Date.now()}`;
  elements.shareModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
  elements.shareUrlInput.select();
}

function closeShareModal() {
  elements.shareModal.classList.add("hidden");
  document.body.classList.remove("modal-open");
}

async function copyShareUrl() {
  const copied = await copyText(elements.shareUrlInput.value);
  toast(copied ? "Complete Drop link copied." : "Could not copy the Drop link.", copied ? "success" : "error");
}

async function submitPassword(event) {
  event.preventDefault();
  const action = state.passwordAction;
  if (!action) return;
  const password = elements.passwordInput.value;
  if (!password) return;
  elements.submitPasswordButton.disabled = true;
  try {
    await action(password);
    closePasswordModal();
  } catch (error) {
    toast(error.message, "error");
    elements.passwordInput.select();
  } finally {
    elements.submitPasswordButton.disabled = false;
  }
}

function refreshCountdowns() {
  let expiredKind = null;
  document.querySelectorAll(`[data-page="${state.currentRoute}"] [data-expires-at]`).forEach((node) => {
    const value = node.dataset.expiresAt;
    if (!value) return;
    const text = formatCountdown(value);
    node.textContent = text;
    if (text === "Deleting now") expiredKind = node.dataset.itemKind || expiredKind;
  });
  if (expiredKind && !state.expiryReloadPending) {
    state.expiryReloadPending = true;
    setTimeout(async () => {
      if (expiredKind === "file") await loadFiles().catch(() => {});
      else { state.clipboardRevision = -1; await loadClipboard(); }
      state.expiryReloadPending = false;
    }, 700);
  }
}

function deviceInitial(device) {
  if (device.role === "server") return "S";
  if (device.device_kind === "phone") return "P";
  if (device.device_kind === "tablet") return "T";
  if (device.device_kind === "computer") return "C";
  return "D";
}

function renderDevices(devices) {
  elements.deviceList.replaceChildren();
  elements.deviceSummary.textContent = `${devices.length} online`;
  elements.clientsOnlineBadge.textContent = `${devices.length} online`;
  for (const device of devices) {
    const card = document.createElement("article");
    card.className = `device-card${device.role === "server" ? " server-device" : ""}`;
    if (device.user_agent) card.title = device.user_agent;
    const icon = document.createElement("div");
    icon.className = "device-icon";
    icon.textContent = deviceInitial(device);
    const meta = document.createElement("div");
    meta.className = "device-meta";
    const title = document.createElement("div");
    title.className = "device-title";
    const name = document.createElement("strong");
    name.textContent = device.role === "server" ? `${device.name} · Server` : (device.agent_label || device.name || "Connected device");
    const status = document.createElement("span");
    status.textContent = device.id === state.clientId ? "This device" : "Online";
    if (device.id === state.clientId) status.className = "this-device";
    title.append(name, status);
    const ip = document.createElement("small");
    ip.textContent = device.primary_ip || device.ip_address || "Unknown IP";
    const agent = document.createElement("small");
    agent.dataset.lastSeen = device.last_seen;
    agent.dataset.server = device.role === "server" ? "true" : "false";
    agent.dataset.os = device.operating_system || "Unknown OS";
    agent.textContent = device.role === "server" ? "NightWire host" : `${agent.dataset.os} · ${relativeTime(device.last_seen)}`;
    meta.append(title, ip, agent);
    card.append(icon, meta);
    elements.deviceList.append(card);
  }
}

async function heartbeat() {
  const hints = navigator.userAgentData || {};
  try {
    const data = await api("/api/clients/heartbeat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: state.clientId, platform: hints.platform || navigator.platform || "", mobile: Boolean(hints.mobile) }),
    });
    state.devices = data.devices || [];
    if (state.currentRoute === "clients") renderDevices(state.devices);
    setServerOnline(true);
  } catch (_) {
    setServerOnline(false);
  }
}

async function copyAddress(button) {
  const copied = await copyText(button.dataset.address || state.info?.primary_network_url);
  toast(copied ? "Network address copied." : "Could not copy the address.", copied ? "success" : "error");
}

function bindEvents() {
  for (const item of elements.navItems) {
    item.addEventListener("click", (event) => {
      event.preventDefault();
      setRoute(item.dataset.route, true);
    });
  }
  for (const link of elements.routeLinks) {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      setRoute(link.dataset.routeLink, true);
    });
  }
  window.addEventListener("popstate", () => setRoute(routeFromPath(), false));

  elements.dropzone.addEventListener("click", () => elements.fileInput.click());
  elements.dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); elements.fileInput.click(); }
  });
  elements.fileInput.addEventListener("change", () => queueFiles(elements.fileInput.files));
  document.querySelector("[data-upload-control]")?.addEventListener("click", (event) => event.stopPropagation());
  document.querySelector("[data-upload-control]")?.addEventListener("keydown", (event) => event.stopPropagation());
  elements.fileExpiryPreset.addEventListener("change", updateCreationFields);
  elements.filePassword?.addEventListener("input", updateCreationFields);
  elements.dropTextInput.addEventListener("input", updateDropTextCharacterCount);
  elements.dropTextMode.addEventListener("change", () => { elements.dropTextLanguageWrap.classList.toggle("hidden", elements.dropTextMode.value !== "code"); });
  elements.dropTextInput.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); shareDropText(); }
  });
  elements.shareTextDropButton.addEventListener("click", shareDropText);
  elements.recordVoiceButton.addEventListener("click", startVoiceRecording);
  elements.stopVoiceButton.addEventListener("click", stopVoiceRecording);
  elements.voiceCaptureInput.addEventListener("change", () => {
    const recording = elements.voiceCaptureInput.files?.[0];
    if (recording) uploadVoiceBlob(recording);
    elements.voiceCaptureInput.value = "";
  });
  elements.searchInput?.addEventListener("input", renderFiles);
  elements.refreshButton.addEventListener("click", () => loadFiles({ quiet: false }).then(() => toast("Files refreshed.", "success")).catch(() => {}));
  elements.copyAddressButton.addEventListener("click", () => copyAddress(elements.copyAddressButton));
  elements.copyQrAddressButton.addEventListener("click", () => copyAddress(elements.copyQrAddressButton));

  elements.clipboardInput.addEventListener("input", updateClipboardCharacterCount);
  elements.clipboardInput.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); shareClipboardText(elements.clipboardInput.value); }
  });
  elements.shareClipboardButton.addEventListener("click", () => shareClipboardText(elements.clipboardInput.value));
  elements.shareDetectedClipboardButton.addEventListener("click", () => shareClipboardText(state.detectedClipboardText));
  elements.dismissClipboardButton.addEventListener("click", dismissClipboardRecommendation);
  elements.watchClipboardButton.addEventListener("click", toggleClipboardWatching);
  elements.clipboardExpiryPreset.addEventListener("change", updateCreationFields);
  elements.clipboardPassword.addEventListener("input", updateCreationFields);

  document.addEventListener("copy", (event) => {
    if (state.suppressCopyCapture) return;
    setTimeout(() => recommendClipboardText(selectedTextFromTarget(event.target)), 0);
  });
  document.addEventListener("paste", (event) => {
    if (event.target === elements.clipboardInput || event.target === elements.dropTextInput || event.target instanceof HTMLInputElement) return;
    recommendClipboardText(event.clipboardData?.getData("text/plain") || "");
  });

  for (const eventName of ["dragenter", "dragover"]) {
    elements.dropzone.addEventListener(eventName, (event) => { event.preventDefault(); elements.dropzone.classList.add("dragging"); });
  }
  for (const eventName of ["dragleave", "drop"]) {
    elements.dropzone.addEventListener(eventName, (event) => { event.preventDefault(); elements.dropzone.classList.remove("dragging"); });
  }
  elements.dropzone.addEventListener("drop", (event) => queueFiles(event.dataTransfer.files));

  elements.qrImage.addEventListener("load", () => { elements.qrImage.classList.add("loaded"); elements.qrLoading.classList.add("hidden"); });
  elements.qrImage.addEventListener("error", () => { elements.qrLoading.textContent = "Could not generate QR code."; });

  elements.settingsExpiryPreset.addEventListener("change", updateSettingsFields);
  elements.settingsForm.addEventListener("submit", saveSettings);
  elements.closeSettingsButton.addEventListener("click", closeSettings);
  elements.cancelSettingsButton.addEventListener("click", closeSettings);
  elements.settingsModal.addEventListener("click", (event) => { if (event.target === elements.settingsModal) closeSettings(); });

  elements.passwordForm.addEventListener("submit", submitPassword);
  elements.closePasswordButton.addEventListener("click", closePasswordModal);
  elements.cancelPasswordButton.addEventListener("click", closePasswordModal);
  elements.passwordModal.addEventListener("click", (event) => { if (event.target === elements.passwordModal) closePasswordModal(); });
  elements.closeShareButton.addEventListener("click", closeShareModal);
  elements.dismissShareButton.addEventListener("click", closeShareModal);
  elements.copyShareButton.addEventListener("click", copyShareUrl);
  elements.shareModal.addEventListener("click", (event) => { if (event.target === elements.shareModal) closeShareModal(); });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!elements.passwordModal.classList.contains("hidden")) closePasswordModal();
    else if (!elements.shareModal.classList.contains("hidden")) closeShareModal();
    else if (!elements.settingsModal.classList.contains("hidden")) closeSettings();
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      heartbeat();
      loadClipboard();
      loadFiles().catch(() => {});
      if (state.clipboardWatching) readClipboardForRecommendation(false);
    }
  });
  window.addEventListener("focus", () => { if (state.clipboardWatching) readClipboardForRecommendation(false); });
}

async function start() {
  bindEvents();
  setRoute(routeFromPath(), false);
  updateClipboardCharacterCount();
  updateDropTextCharacterCount();
  updateCreationFields();
  renderClipboard();
  try {
    await loadInfo();
    await Promise.all([loadFiles(), heartbeat(), loadClipboard()]);
    setServerOnline(true);
  } catch (error) {
    setServerOnline(false);
    toast(error.message, "error");
  }

  setInterval(heartbeat, 2500);
  setInterval(loadClipboard, 1200);
  setInterval(() => loadFiles().catch(() => {}), 4000);
  setInterval(refreshCountdowns, 1000);
  setInterval(() => { if (state.clipboardWatching) readClipboardForRecommendation(false); }, 1500);
  setInterval(() => {
    document.querySelectorAll("[data-last-seen]").forEach((node) => {
      if (node.dataset.server === "true") return;
      node.textContent = `${node.dataset.os || "Unknown OS"} · ${relativeTime(node.dataset.lastSeen)}`;
    });
  }, 1000);
}

export { start as startDrop };
