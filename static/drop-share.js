"use strict";

import { renderText } from "/static/text-ui.js";

const elements = {
  title: document.querySelector("#dropTitle"),
  status: document.querySelector("#dropStatus"),
  details: document.querySelector("#dropDetails"),
  size: document.querySelector("#dropSize"),
  created: document.querySelector("#dropCreated"),
  expires: document.querySelector("#dropExpires"),
  security: document.querySelector("#dropSecurity"),
  securityWarning: document.querySelector("#dropSecurityWarning"),
  form: document.querySelector("#downloadForm"),
  passwordWrap: document.querySelector("#sharePasswordWrap"),
  password: document.querySelector("#sharePassword"),
  button: document.querySelector("#downloadDropButton"),
  textPreview: document.querySelector("#dropTextPreview"),
  copyTextButton: document.querySelector("#copyDropTextButton"),
  imageFrame: document.querySelector("#dropImageFrame"),
  image: document.querySelector("#dropImagePreview"),
  audioPlayer: document.querySelector("#dropAudioPlayer"),
  audio: document.querySelector("#dropAudio"),
  audioPlayButton: document.querySelector("#audioPlayButton"),
  audioSeek: document.querySelector("#audioSeek"),
  audioCurrentTime: document.querySelector("#audioCurrentTime"),
  audioDuration: document.querySelector("#audioDuration"),
  footnote: document.querySelector("#shareFootnote"),
};

const filename = decodeURIComponent(window.location.pathname.slice("/drop/".length));
const accessKey = new URLSearchParams(window.location.search).get("key") || "";
let currentDrop = null;
let sharedTextContent = "";
let mediaObjectUrl = null;
let maliciousConfirmed = false;
let holdTimer = null;
let holdStartedAt = 0;
let holdAnimation = null;
const MALICIOUS_HOLD_MS = 1800;

const securityStates = {
  clean: { label: "Clean", warning: "" },
  suspicious: { label: "Suspicious", warning: "Warning: this Drop has conflicting or suspicious security evidence. Treat it cautiously." },
  malicious: { label: "Malicious", warning: "Danger: the configured scanner reported this Drop as malicious. NightWire will not preview or process it. Hold the download button to deliberately retrieve the original bytes." },
  scan_failed: { label: "Scan failed", warning: "Warning: malware scanning failed, so this Drop must not be treated as clean." },
  unscanned: { label: "Unscanned", warning: "Warning: no malware scanner result is available for this Drop." },
};

function securityVerdict() {
  return currentDrop?.security?.verdict || currentDrop?.security_verdict || "unscanned";
}

function renderSecurityState() {
  const verdict = securityVerdict();
  const state = securityStates[verdict] || securityStates.unscanned;
  elements.security.textContent = state.label;
  elements.securityWarning.textContent = state.warning;
  elements.securityWarning.classList.toggle("hidden", !state.warning);
  elements.securityWarning.classList.toggle("malicious", verdict === "malicious");
  if (verdict === "malicious") elements.button.textContent = "Hold to download malicious Drop";
}

function resetMaliciousHold(message = null) {
  if (holdTimer) clearTimeout(holdTimer);
  if (holdAnimation) cancelAnimationFrame(holdAnimation);
  holdTimer = null;
  holdAnimation = null;
  holdStartedAt = 0;
  elements.button.classList.remove("hold-confirming");
  if (securityVerdict() === "malicious") elements.button.textContent = "Hold to download malicious Drop";
  if (message) elements.status.textContent = message;
}

function updateMaliciousHold() {
  if (!holdStartedAt) return;
  const percent = Math.min(100, Math.round(((performance.now() - holdStartedAt) / MALICIOUS_HOLD_MS) * 100));
  elements.button.textContent = `Keep holding… ${percent}%`;
  if (percent < 100) holdAnimation = requestAnimationFrame(updateMaliciousHold);
}

function beginMaliciousHold(event) {
  if (securityVerdict() !== "malicious" || elements.button.disabled || holdTimer) return;
  event.preventDefault();
  maliciousConfirmed = false;
  holdStartedAt = performance.now();
  elements.button.classList.add("hold-confirming");
  elements.status.textContent = "Keep holding to confirm this malicious download.";
  updateMaliciousHold();
  holdTimer = setTimeout(() => {
    holdTimer = null;
    maliciousConfirmed = true;
    elements.button.classList.remove("hold-confirming");
    elements.button.textContent = "Confirmed — preparing download…";
    elements.form.requestSubmit();
  }, MALICIOUS_HOLD_MS);
}

function cancelMaliciousHold(event) {
  if (securityVerdict() !== "malicious" || maliciousConfirmed) return;
  if (event) event.preventDefault();
  if (holdTimer) resetMaliciousHold("Download not confirmed. Hold continuously to proceed.");
}

function formatBytes(value) {
  if (!Number.isFinite(value)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
  return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function mediaMimeType() {
  const detected = currentDrop?.security?.detected_mime || currentDrop?.detected_mime || "";
  const extension = currentDrop?.name.split(".").pop()?.toLowerCase();
  if (currentDrop?.content_kind === "voice") {
    if (extension === "m4a" || extension === "mp4") return "audio/mp4";
    if (extension === "ogg" || extension === "oga") return "audio/ogg";
    if (extension === "wav") return "audio/wav";
    if (extension === "aac") return "audio/aac";
    return detected.startsWith("audio/") ? detected : "audio/webm";
  }
  return detected;
}

function replaceMediaObjectUrl(blob, mimeType) {
  if (mediaObjectUrl) URL.revokeObjectURL(mediaObjectUrl);
  mediaObjectUrl = URL.createObjectURL(new Blob([blob], { type: mimeType || blob.type }));
  return mediaObjectUrl;
}

async function loadInlinePreview() {
  const response = await fetch(currentDrop.download_url, { cache: "no-store" });
  if (!response.ok) return false;
  const blob = await response.blob();
  if (currentDrop.content_kind === "text") {
    sharedTextContent = await blob.text();
    renderText(elements.textPreview, { content: sharedTextContent, mode: currentDrop.text?.mode || "plain", language: currentDrop.text?.language }, { lineNumbers: true });
    elements.textPreview.classList.remove("hidden");
    elements.copyTextButton.classList.remove("hidden");
    elements.button.textContent = "Download text file";
    elements.status.textContent = "Shared text is ready.";
    return true;
  }
  if (currentDrop.content_kind === "voice") {
    elements.audio.src = replaceMediaObjectUrl(blob, mediaMimeType());
    elements.audio.load();
    elements.audioPlayer.classList.remove("hidden");
    elements.button.textContent = "Download voice message";
    elements.status.textContent = "Voice message is ready to play.";
    return true;
  }
  if (mediaMimeType().startsWith("image/")) {
    elements.image.src = replaceMediaObjectUrl(blob, mediaMimeType());
    elements.image.alt = `Preview of ${currentDrop.name}`;
    elements.imageFrame.classList.remove("hidden");
    elements.status.textContent = "Image preview is ready. Press and hold it on mobile to save it.";
    return true;
  }
  return false;
}

function updateExpiry() {
  if (!currentDrop?.expires_at) return;
  const remaining = Math.max(0, Math.ceil((new Date(currentDrop.expires_at).getTime() - Date.now()) / 1000));
  if (!remaining) {
    elements.expires.textContent = "Expired";
    elements.button.disabled = true;
    elements.status.textContent = "This Drop has expired.";
    return;
  }
  const hours = Math.floor(remaining / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  const seconds = remaining % 60;
  elements.expires.textContent = `${formatDate(currentDrop.expires_at)} · ${hours ? `${hours}h ` : ""}${minutes}m ${seconds}s remaining`;
}

async function loadDrop() {
  if (!filename) throw new Error("This share URL is incomplete.");
  const keyQuery = accessKey ? `?key=${encodeURIComponent(accessKey)}` : "";
  const response = await fetch(`/api/drops/${encodeURIComponent(filename)}${keyQuery}`, { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "This Drop is unavailable or the Access Key is invalid.");
  currentDrop = payload.drop;
  document.title = `${currentDrop.name} — NightWire Drop`;
  elements.title.textContent = currentDrop.name;
  const accessMessage = currentDrop.access_key_required ? "The Access Key is valid." : "This Drop does not require an Access Key.";
  elements.status.textContent = currentDrop.password_protected
    ? `${accessMessage} Enter the additional password to download.`
    : `${accessMessage} This Drop is ready to download.`;
  if (!currentDrop.access_key_required) {
    elements.footnote.textContent = "This Drop can be accessed without an Access Key until it expires or is deleted.";
  }
  elements.size.textContent = formatBytes(currentDrop.size);
  elements.created.textContent = formatDate(currentDrop.created_at);
  elements.passwordWrap.classList.toggle("hidden", !currentDrop.password_protected);
  elements.password.required = currentDrop.password_protected;
  renderSecurityState();
  const previewable = currentDrop.content_kind === "text"
    || currentDrop.content_kind === "voice"
    || mediaMimeType().startsWith("image/");
  if (previewable && !currentDrop.password_protected && securityVerdict() !== "malicious") {
    await loadInlinePreview();
  }
  elements.details.classList.remove("hidden");
  elements.form.classList.remove("hidden");
  updateExpiry();
}

function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

async function downloadDrop(event) {
  event.preventDefault();
  if (!currentDrop) return;
  if (securityVerdict() === "malicious" && !maliciousConfirmed) {
    elements.status.textContent = "Hold the download button continuously to confirm this malicious download.";
    return;
  }
  elements.button.disabled = true;
  elements.status.textContent = "Preparing download…";
  const query = new URLSearchParams();
  if (accessKey) query.set("key", accessKey);
  if (maliciousConfirmed) query.set("confirm_malicious", "true");
  const queryString = query.toString();
  const keyQuery = queryString ? `?${queryString}` : "";
  const options = currentDrop.password_protected
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: elements.password.value, confirm_malicious: maliciousConfirmed }) }
    : { method: "GET" };
  try {
    const endpoint = currentDrop.password_protected
      ? `/api/files/${encodeURIComponent(filename)}/download${keyQuery}`
      : `/download/${encodeURIComponent(filename)}${keyQuery}`;
    const response = await fetch(endpoint, { cache: "no-store", ...options });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `Download failed (${response.status}).`);
    }
    saveBlob(await response.blob(), currentDrop.name);
    elements.status.textContent = securityVerdict() === "malicious"
      ? "Confirmed malicious download started without previewing the content."
      : "Download started.";
  } catch (error) {
    elements.status.textContent = error.message;
    elements.password.select();
  } finally {
    elements.button.disabled = false;
    maliciousConfirmed = false;
    resetMaliciousHold();
  }
}

elements.form.addEventListener("submit", downloadDrop);
elements.button.addEventListener("pointerdown", beginMaliciousHold);
for (const eventName of ["pointerup", "pointercancel", "pointerleave"]) {
  elements.button.addEventListener(eventName, cancelMaliciousHold);
}
elements.button.addEventListener("keydown", (event) => {
  if (["Enter", " "].includes(event.key)) beginMaliciousHold(event);
});
elements.button.addEventListener("keyup", (event) => {
  if (["Enter", " "].includes(event.key)) cancelMaliciousHold(event);
});
elements.copyTextButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(sharedTextContent);
    elements.status.textContent = "Shared text copied.";
  } catch (_) {
    elements.status.textContent = "Could not copy automatically; select the text above instead.";
  }
});
function formatPlaybackTime(value) {
  if (!Number.isFinite(value) || value < 0) return "0:00";
  const seconds = Math.floor(value);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function syncAudioPlayer() {
  const duration = Number.isFinite(elements.audio.duration) ? elements.audio.duration : 0;
  elements.audioCurrentTime.textContent = formatPlaybackTime(elements.audio.currentTime);
  elements.audioDuration.textContent = formatPlaybackTime(duration);
  elements.audioSeek.value = duration ? String(Math.round((elements.audio.currentTime / duration) * 1000)) : "0";
  elements.audioPlayButton.classList.toggle("playing", !elements.audio.paused);
  elements.audioPlayButton.setAttribute("aria-label", elements.audio.paused ? "Play voice message" : "Pause voice message");
}

elements.audioPlayButton.addEventListener("click", async () => {
  try {
    if (elements.audio.paused) await elements.audio.play();
    else elements.audio.pause();
  } catch (_) {
    elements.status.textContent = "This browser could not play the recording. Use Download voice message instead.";
  }
  syncAudioPlayer();
});
elements.audioSeek.addEventListener("input", () => {
  if (Number.isFinite(elements.audio.duration) && elements.audio.duration > 0) {
    elements.audio.currentTime = (Number(elements.audioSeek.value) / 1000) * elements.audio.duration;
  }
});
for (const eventName of ["loadedmetadata", "durationchange", "timeupdate", "play", "pause", "ended"]) {
  elements.audio.addEventListener(eventName, syncAudioPlayer);
}
loadDrop().catch((error) => {
  elements.title.textContent = "Drop unavailable";
  elements.status.textContent = error.message;
});
setInterval(updateExpiry, 1000);
window.addEventListener("pagehide", () => { if (mediaObjectUrl) URL.revokeObjectURL(mediaObjectUrl); });
