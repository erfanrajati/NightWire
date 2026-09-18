"use strict";

import { renderText } from "/library/assets/text-ui.js";

const token = decodeURIComponent(window.location.pathname.slice(3));
const accessKey = new URLSearchParams(window.location.search).get("key") || "";
const elements = {
  title: document.querySelector("#shareTitle"), status: document.querySelector("#shareStatus"),
  warning: document.querySelector("#shareSecurityWarning"), details: document.querySelector("#shareDetails"),
  size: document.querySelector("#shareSize"), created: document.querySelector("#shareCreated"),
  expires: document.querySelector("#shareExpires"), security: document.querySelector("#shareSecurity"),
  form: document.querySelector("#shareDownloadForm"), button: document.querySelector("#shareDownloadButton"),
  textPreview: document.querySelector("#shareTextPreview"), copyText: document.querySelector("#copyShareTextButton"),
};
const securityStates = {
  clean: ["Clean", ""], suspicious: ["Suspicious", "Warning: this file has suspicious security evidence."],
  malicious: ["Malicious", "Danger: this file was reported as malicious. Hold the download button to retrieve it deliberately."],
  scan_failed: ["Scan failed", "Warning: malware scanning failed."],
  unscanned: ["Unscanned", "Warning: no malware scanner result is available."],
};
const HOLD_MS = 1800;
let share = null, holdTimer = null, holdStart = 0, holdFrame = null, maliciousConfirmed = false;

function formatSize(bytes) { const units = ["B", "KB", "MB", "GB", "TB"]; let value = bytes, i = 0; while (value >= 1024 && i < units.length - 1) { value /= 1024; i += 1; } return `${value.toFixed(i ? 1 : 0)} ${units[i]}`; }
function formatDate(value) { if (!value) return "No expiry"; const date = new Date(value); return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString(); }
function verdict() { return share?.security?.verdict || share?.security_verdict || "unscanned"; }
function keyQuery(includeConfirmation = false) { const query = new URLSearchParams(); if (accessKey) query.set("key", accessKey); if (includeConfirmation) query.set("confirm_malicious", "true"); const value = query.toString(); return value ? `?${value}` : ""; }

function resetHold(message = null) { if (holdTimer) clearTimeout(holdTimer); if (holdFrame) cancelAnimationFrame(holdFrame); holdTimer = null; holdFrame = null; holdStart = 0; elements.button.classList.remove("hold-confirming"); if (verdict() === "malicious") elements.button.textContent = "Hold to download malicious file"; if (message) elements.status.textContent = message; }
function updateHold() { if (!holdStart) return; const percent = Math.min(100, Math.round((performance.now() - holdStart) / HOLD_MS * 100)); elements.button.textContent = `Keep holding… ${percent}%`; if (percent < 100) holdFrame = requestAnimationFrame(updateHold); }
function beginHold(event) { if (verdict() !== "malicious" || holdTimer) return; event.preventDefault(); maliciousConfirmed = false; holdStart = performance.now(); elements.button.classList.add("hold-confirming"); elements.status.textContent = "Keep holding to confirm this malicious download."; updateHold(); holdTimer = setTimeout(() => { holdTimer = null; maliciousConfirmed = true; elements.form.requestSubmit(); }, HOLD_MS); }
function cancelHold(event) { if (verdict() !== "malicious" || maliciousConfirmed) return; event?.preventDefault(); if (holdTimer) resetHold("Download not confirmed. Hold continuously to proceed."); }

async function renderFilePreview() {
  const preview = share.preview;
  if (!preview) return;
  elements.textPreview.classList.remove("hidden");
  if (!preview.available) {
    const message = document.createElement("p"); message.className = "share-preview-fallback";
    message.textContent = preview.reason || "No safe inline preview is available. Download the original to inspect it locally.";
    elements.textPreview.replaceChildren(message); return;
  }
  const url = share.preview_url;
  if (preview.kind === "image") { const image = document.createElement("img"); image.src = url; image.alt = `Preview of ${share.name}`; elements.textPreview.replaceChildren(image); return; }
  if (preview.kind === "pdf") { const frame = document.createElement("iframe"); frame.src = url; frame.title = `Preview of ${share.name}`; frame.setAttribute("sandbox", ""); elements.textPreview.replaceChildren(frame); return; }
  if (["audio", "video"].includes(preview.kind)) { const media = document.createElement(preview.kind); media.src = url; media.controls = true; media.preload = "metadata"; elements.textPreview.replaceChildren(media); return; }
  if (["text", "code", "markdown"].includes(preview.kind)) { const response = await fetch(url, { cache: "no-store" }); if (!response.ok) throw new Error("The preview could not be loaded safely."); renderText(elements.textPreview, { content: await response.text(), mode: preview.kind === "text" ? "plain" : preview.kind, language: preview.language }, { lineNumbers: true }); }
}

async function loadShare() {
  const response = await fetch(`/api/public/shares/${encodeURIComponent(token)}${keyQuery()}`, { cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "This share is unavailable.");
  share = data.share; document.title = `${share.name} — NightWire Share`; elements.title.textContent = share.name;
  elements.status.textContent = share.access_key_required ? "The reusable Access Key is valid." : "This share does not require an Access Key.";
  elements.size.textContent = formatSize(share.size); elements.created.textContent = formatDate(share.created_at); elements.expires.textContent = formatDate(share.expires_at);
  const state = securityStates[verdict()] || securityStates.unscanned; elements.security.textContent = state[0]; elements.warning.textContent = state[1]; elements.warning.classList.toggle("hidden", !state[1]); elements.warning.classList.toggle("malicious", verdict() === "malicious");
  if (verdict() === "malicious") elements.button.textContent = "Hold to download malicious file";
  if (share.item_type === "text") {
    renderText(elements.textPreview, share, { lineNumbers: true }); elements.textPreview.classList.remove("hidden"); elements.copyText.classList.remove("hidden"); elements.button.textContent = "Download Text";
  } else await renderFilePreview();
  elements.details.classList.remove("hidden"); elements.form.classList.remove("hidden");
}

function save(blob, name) { const url = URL.createObjectURL(blob), anchor = document.createElement("a"); anchor.href = url; anchor.download = name; document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000); }
async function download(event) { event.preventDefault(); if (!share) return; if (verdict() === "malicious" && !maliciousConfirmed) { elements.status.textContent = "Hold continuously to confirm this malicious download."; return; } elements.button.disabled = true; try { const response = await fetch(`/api/public/shares/${encodeURIComponent(token)}/download${keyQuery(maliciousConfirmed)}`, { cache: "no-store" }); const data = response.ok ? null : await response.json().catch(() => ({})); if (!response.ok) throw new Error(data?.error || `Download failed (${response.status}).`); save(await response.blob(), share.name); elements.status.textContent = "Download started."; } catch (error) { elements.status.textContent = error.message; } finally { elements.button.disabled = false; maliciousConfirmed = false; resetHold(); } }

elements.form.addEventListener("submit", download); elements.button.addEventListener("pointerdown", beginHold);
elements.copyText.addEventListener("click", async () => { try { await navigator.clipboard.writeText(share?.content || ""); elements.status.textContent = "Shared Text copied."; } catch (_) { elements.status.textContent = "Could not copy automatically; select the Text above instead."; } });
for (const eventName of ["pointerup", "pointercancel", "pointerleave"]) elements.button.addEventListener(eventName, cancelHold);
elements.button.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) beginHold(event); });
elements.button.addEventListener("keyup", (event) => { if (["Enter", " "].includes(event.key)) cancelHold(event); });
loadShare().catch((error) => { elements.title.textContent = "Share unavailable"; elements.status.textContent = error.message; });
