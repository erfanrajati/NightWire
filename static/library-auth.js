"use strict";

const authView = document.querySelector("#authView");
const libraryView = document.querySelector("#libraryView");
const loginPanel = document.querySelector("#loginPanel");
const signupPanel = document.querySelector("#signupPanel");
const loginForm = document.querySelector("#loginForm");
const signupForm = document.querySelector("#signupForm");
const loginError = document.querySelector("#loginError");
const signupMessage = document.querySelector("#signupMessage");
const invitationField = document.querySelector("#invitationField");

async function request(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return { response, data };
}

function showMessage(element, message, error = false) {
  element.textContent = message;
  element.classList.toggle("error-message", error);
  element.hidden = false;
}

async function start() {
  const path = window.location.pathname;
  if (path === "/library") {
    try {
      const { data } = await request("/api/library/auth/me");
      document.querySelector("#currentName").textContent = data.user.display_name;
      document.querySelector("#currentEmail").textContent = data.user.email + (data.user.is_administrator ? " · Administrator" : "");
      libraryView.hidden = false;
    } catch (_) { window.location.replace("/library/login"); }
    return;
  }

  authView.hidden = false;
  const signup = path.endsWith("/signup");
  loginPanel.hidden = signup;
  signupPanel.hidden = !signup;
  if (!signup) return;

  try {
    const { data } = await request("/api/library/auth/config");
    document.querySelector("#signupPassword").minLength = data.password_min_characters;
    document.querySelector("#passwordHint").textContent = `Use at least ${data.password_min_characters} characters.`;
    if (data.first_account) {
      document.querySelector("#policyMessage").textContent = "Create the first account to become this Library’s administrator.";
    } else if (data.registration_policy === "invitation-only") {
      document.querySelector("#policyMessage").textContent = "An invitation from a Library administrator is required.";
      invitationField.hidden = false;
      invitationField.querySelector("input").required = true;
    } else if (data.registration_policy === "administrator-approved") {
      document.querySelector("#policyMessage").textContent = "Your account will need administrator approval before you can sign in.";
    } else {
      document.querySelector("#policyMessage").textContent = "Registration is open for this Community Library.";
    }
  } catch (error) {
    showMessage(signupMessage, error.message, true);
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.hidden = true;
  const values = Object.fromEntries(new FormData(loginForm));
  try {
    await request("/api/library/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) });
    window.location.assign("/library");
  } catch (error) { showMessage(loginError, error.message, true); }
});

signupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  signupMessage.hidden = true;
  const values = Object.fromEntries(new FormData(signupForm));
  try {
    const { data } = await request("/api/library/auth/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) });
    if (data.authenticated) window.location.assign("/library");
    else { signupForm.hidden = true; showMessage(signupMessage, "Account created. An administrator must approve it before you can sign in."); }
  } catch (error) { showMessage(signupMessage, error.message, true); }
});

document.querySelector("#logoutButton").addEventListener("click", async () => {
  await request("/api/library/auth/logout", { method: "POST" });
  window.location.assign("/library/login");
});

start();
