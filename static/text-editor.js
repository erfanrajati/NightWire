"use strict";

import { detectLanguage, renderText } from "/library/assets/text-ui.js";

const path = window.location.pathname.split("/").filter(Boolean);
const workspaceMode = path[0] === "workspaces";
const workspaceId = workspaceMode ? path[1] : null;
const textId = workspaceMode ? path[3] : path[2];
const apiBase = workspaceMode ? `/api/workspaces/${encodeURIComponent(workspaceId)}` : "/api/library";
const elements = Object.fromEntries(["backLink","textTitle","saveStatus","saveTextButton","textMode","languageField","textLanguage","detectedLanguage","sourceTab","previewTab","findText","findNextButton","copyTextButton","textError","sourcePane","lineNumbers","textContent","previewPane","textStats"].map((id) => [id, document.querySelector(`#${id}`)]));
let current = null, cleanSnapshot = "", findCursor = 0;

async function api(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { window.location.replace("/library/login"); throw new Error("Sign in required."); }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function value() {
  const mode = elements.textMode.value;
  const chosen = mode === "code" ? elements.textLanguage.value : "";
  return { title: elements.textTitle.value.trim(), content: elements.textContent.value, mode, language: mode === "code" ? (chosen || detectLanguage(elements.textContent.value)) : null };
}
function snapshot() { return JSON.stringify(value()); }
function updateDirty() { const dirty = snapshot() !== cleanSnapshot; elements.saveStatus.textContent = dirty ? "Unsaved changes" : "Saved"; document.title = `${dirty ? "• " : ""}${elements.textTitle.value || "Untitled"} — NightWire Text`; }
function renderLines() { const count = elements.textContent.value.split("\n").length; elements.lineNumbers.replaceChildren(...Array.from({ length: count }, (_, i) => { const line = document.createElement("span"); line.textContent = String(i + 1); return line; })); elements.textStats.textContent = `${elements.textContent.value.length.toLocaleString()} characters · ${count.toLocaleString()} line${count === 1 ? "" : "s"}`; }
function refreshPreview() { const text = value(); const detected = renderText(elements.previewPane, text, { lineNumbers: true }); elements.detectedLanguage.textContent = text.mode === "code" ? `${elements.textLanguage.value ? "Language" : "Detected"}: ${detected}` : ""; elements.detectedLanguage.hidden = text.mode !== "code"; }
function updateMode() { const code = elements.textMode.value === "code", markdown = elements.textMode.value === "markdown"; elements.languageField.hidden = !code; elements.previewTab.hidden = !(code || markdown); if (!code && !markdown && !elements.previewPane.hidden) showSource(); refreshPreview(); updateDirty(); }
function showSource() { elements.sourcePane.hidden = false; elements.previewPane.hidden = true; elements.sourceTab.classList.add("active"); elements.previewTab.classList.remove("active"); elements.textContent.focus(); }
function showPreview() { refreshPreview(); elements.sourcePane.hidden = true; elements.previewPane.hidden = false; elements.sourceTab.classList.remove("active"); elements.previewTab.classList.add("active"); }
function showError(message = "") { elements.textError.textContent = message; elements.textError.hidden = !message; }

async function load() {
  const data = await api(`${apiBase}/texts/${encodeURIComponent(textId)}`); current = data.text;
  elements.textTitle.value = current.title; elements.textContent.value = current.content; elements.textMode.value = current.mode; elements.textLanguage.value = current.language || "";
  elements.backLink.href = workspaceMode ? "/workspaces" : "/library"; elements.backLink.textContent = workspaceMode ? "← Workspace" : "← My Library";
  renderLines(); updateMode(); cleanSnapshot = snapshot(); updateDirty(); elements.saveStatus.textContent = "Saved";
}
async function save() {
  showError(); const payload = value(); if (!payload.title) { showError("A title is required."); elements.textTitle.focus(); return; }
  elements.saveTextButton.disabled = true; elements.saveStatus.textContent = "Saving…";
  try { const data = await api(`${apiBase}/texts/${encodeURIComponent(textId)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); current = data.text; cleanSnapshot = snapshot(); updateDirty(); }
  catch (error) { showError(error.message); elements.saveStatus.textContent = "Save failed"; }
  finally { elements.saveTextButton.disabled = false; }
}
function findNext() { const query = elements.findText.value; if (!query) return; const haystack = elements.textContent.value.toLocaleLowerCase(), needle = query.toLocaleLowerCase(); let index = haystack.indexOf(needle, findCursor); if (index < 0) index = haystack.indexOf(needle); if (index < 0) { elements.saveStatus.textContent = "No match"; return; } showSource(); elements.textContent.setSelectionRange(index, index + query.length); findCursor = index + query.length; const before = elements.textContent.value.slice(0, index).split("\n").length; elements.textContent.scrollTop = Math.max(0, (before - 3) * 21); elements.lineNumbers.scrollTop = elements.textContent.scrollTop; elements.saveStatus.textContent = `Match on line ${before}`; }

elements.textContent.addEventListener("input", () => { renderLines(); refreshPreview(); updateDirty(); });
elements.textContent.addEventListener("scroll", () => { elements.lineNumbers.scrollTop = elements.textContent.scrollTop; });
elements.textTitle.addEventListener("input", updateDirty); elements.textMode.addEventListener("change", updateMode); elements.textLanguage.addEventListener("change", () => { refreshPreview(); updateDirty(); });
elements.sourceTab.addEventListener("click", showSource); elements.previewTab.addEventListener("click", showPreview); elements.saveTextButton.addEventListener("click", save); elements.findNextButton.addEventListener("click", findNext); elements.findText.addEventListener("search", () => { findCursor = 0; findNext(); });
elements.copyTextButton.addEventListener("click", async () => { try { await navigator.clipboard.writeText(elements.textContent.value); elements.saveStatus.textContent = "Copied"; } catch (_) { showSource(); elements.textContent.select(); elements.saveStatus.textContent = "Selected for copying"; } });
document.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); save(); } if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") { event.preventDefault(); elements.findText.focus(); } });
window.addEventListener("beforeunload", (event) => { if (snapshot() !== cleanSnapshot) event.preventDefault(); });
load().catch((error) => { showError(error.message); elements.saveStatus.textContent = "Unavailable"; });
