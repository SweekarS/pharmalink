// static/app.js
const API = ""; // relative (served from same Flask backend)
const $ = (id) => document.getElementById(id);
let token = localStorage.getItem("pl_token");
let me = null;

function authHeader() {
  return token ? { "Authorization": "Bearer " + token } : {};
}

async function api(path, opts = {}) {
  opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  const res = await fetch(API + path, opts);
  return res.json().then(data => ({ ok: res.ok, status: res.status, data }));
}

async function showMe() {
  if (!token) return;
  const r = await api("/api/me", { headers: authHeader() });
  if (r.ok) {
    me = r.data.user;
    $("me-info").innerHTML = `<div style="text-align:right">
      <div><strong>${me.name}</strong></div>
      <div class="muted">${me.role}</div>
      <div><button onclick="logout()" class="secondary small">Logout</button></div>
    </div>`;
    $("auth-panel").classList.add("hidden");
    $("app").classList.remove("hidden");
    loadPharmacies();
    loadTransfers();
  } else {
    logout();
  }
}

function showAuthArea() {
  const area = $("auth-area");
  if (!token) {
    area.innerHTML = `<button onclick="scrollToAuth()">Sign in / Register</button>`;
  } else {
    area.innerHTML = `<button onclick="toggleApp()">Open Dashboard</button>`;
  }
}

function scrollToAuth() {
  document.querySelector(".auth-panel").scrollIntoView({ behavior: "smooth" });
}

function toggleApp() {
  const a = $("app");
  a.classList.toggle("hidden");
}

async function login() {
  const email = $("login-email").value;
  const password = $("login-password").value;
  const r = await api("/api/login", { method: "POST", body: JSON.stringify({ email, password }) });
  if (!r.ok) return alert(r.data?.error || "Login failed");
  token = r.data.token;
  localStorage.setItem("pl_token", token);
  showAuthArea();
  showMe();
}

async function registerUser() {
  const name = $("reg-name").value;
  const email = $("reg-email").value;
  const password = $("reg-password").value;
  const role = $("reg-role").value;
  const r = await api("/api/register", { method: "POST", body: JSON.stringify({ name, email, password, role }) });
  if (!r.ok) return alert(r.data?.error || "Register failed");
  token = r.data.token;
  localStorage.setItem("pl_token", token);
  showAuthArea();
  showMe();
}

function logout() {
  token = null;
  me = null;
  localStorage.removeItem("pl_token");
  $("app").classList.add("hidden");
  $("auth-panel").classList.remove("hidden");
  $("me-info").innerHTML = "";
  showAuthArea();
}

async function loadPharmacies() {
  const r = await api("/api/pharmacies", { headers: authHeader() });
  if (!r.ok) return console.error("failed to load pharmacies", r);
  const ph = r.data.pharmacies || [];
  const from = $("from-pharm");
  const to = $("to-pharm");
  from.innerHTML = "";
  to.innerHTML = "";
  ph.forEach(p => {
    const opt = `<option value="${p.id}">${p.name}</option>`;
    from.insertAdjacentHTML("beforeend", opt);
    to.insertAdjacentHTML("beforeend", opt);
  });
}

async function loadTransfers() {
  const r = await api("/api/transfers", { headers: authHeader() });
  if (!r.ok) return console.error("failed to load transfers", r);
  const container = $("transfers");
  container.innerHTML = "";
  const arr = r.data.transfers || [];
  arr.forEach(t => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center">
        <h4>${t.medication}</h4>
        <div class="badge ${t.status}">${t.status}</div>
      </div>
      <div class="meta">Patient: ${t.patient_name} • From: ${t.from_pharmacy?.name || "-"} • To: ${t.to_pharmacy?.name || "-"}</div>
      <div class="meta">Created by: ${t.created_by?.name || "-" } • ${new Date(t.created_at).toLocaleString()}</div>
      <div class="actions"></div>
    `;
    const actions = card.querySelector(".actions");
    if (t.status === "pending") {
      const btnApprove = document.createElement("button");
      btnApprove.className = "btn-small btn-approve";
      btnApprove.innerText = "Approve";
      btnApprove.onclick = () => updateStatus(t.id, "approved");
      actions.appendChild(btnApprove);
    }
    if (t.status !== "completed") {
      const btnComplete = document.createElement("button");
      btnComplete.className = "btn-small btn-complete";
      btnComplete.innerText = "Complete";
      btnComplete.onclick = () => updateStatus(t.id, "completed");
      actions.appendChild(btnComplete);
    }
    container.appendChild(card);
  });
}

async function createTransfer() {
  const patient_name = $("patient-name").value;
  const medication = $("medication").value;
  const from_pharmacy_id = Number($("from-pharm").value);
  const to_pharmacy_id = Number($("to-pharm").value);
  if (!patient_name || !medication) return alert("Patient and medication required");
  const r = await api("/api/transfers", { method: "POST", headers: authHeader(), body: JSON.stringify({ patient_name, medication, from_pharmacy_id, to_pharmacy_id }) });
  if (!r.ok) return alert(r.data?.error || "Failed");
  $("patient-name").value = "";
  $("medication").value = "";
  loadTransfers();
}

async function updateStatus(id, status) {
  const r = await api(`/api/transfers/${id}/status`, { method: "PUT", headers: authHeader(), body: JSON.stringify({ status }) });
  if (!r.ok) return alert(r.data?.error || "Failed to update");
  loadTransfers();
}

// Bind UI
document.addEventListener("DOMContentLoaded", () => {
  $("btn-login").addEventListener("click", login);
  $("btn-register").addEventListener("click", registerUser);
  $("create-transfer").addEventListener("click", createTransfer);
  showAuthArea();
  if (token) showMe();
});
