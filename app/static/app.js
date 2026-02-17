function readCollapsedPanels() {
  try {
    const raw = localStorage.getItem("collapsed_panels");
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

const COLLAPSIBLE_PANELS = ["admin-panel", "create-panel", "filter-panel", "reports-panel", "map-panel", "kanban-panel", "notifications-panel"];

const state = {
  token: localStorage.getItem("token") || "",
  me: null,
  orders: [],
  workers: [],
  notifications: [],
  residents: [],
  subsets: [],
  map: null,
  mapMarkers: null,
  residentSearchPerformed: false,
  collapsedPanels: new Set(readCollapsedPanels()),
};

const statusLabel = {
  backlog: "Backlog",
  fazendo: "Fazendo",
  pendentes: "Pendentes",
  concluido: "Concluído",
};

const categoryLabel = {
  eletrica: "Elétrica",
  hidraulica: "Hidráulica",
  limpeza: "Limpeza",
  pintura: "Pintura",
  seguranca: "Segurança",
  outros: "Outros",
};

const priorityLabel = {
  baixa: "Baixa",
  media: "Média",
  alta: "Alta",
  urgente: "Urgente",
};

const roleLabel = {
  administrador: "Administrador",
  sindico: "Síndico",
  funcionario: "Funcionário",
  morador: "Morador",
};

const $ = (sel) => document.querySelector(sel);
const toast = $("#toast");
const loginErrorEl = $("#login-error");

function persistCollapsedPanels() {
  localStorage.setItem("collapsed_panels", JSON.stringify([...state.collapsedPanels]));
}

function syncPanelCollapse(panelId) {
  const panel = document.getElementById(panelId);
  if (!panel) {
    return;
  }

  const collapsed = state.collapsedPanels.has(panelId);
  panel.classList.toggle("collapsed", collapsed);

  const btn = panel.querySelector(`[data-action='toggle-panel'][data-panel-id='${panelId}']`);
  if (btn) {
    btn.textContent = collapsed ? "Ampliar" : "Reduzir";
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }
}

function applyPanelCollapseStates() {
  COLLAPSIBLE_PANELS.forEach(syncPanelCollapse);
}

function togglePanelCollapse(panelId) {
  if (state.collapsedPanels.has(panelId)) {
    state.collapsedPanels.delete(panelId);
  } else {
    state.collapsedPanels.add(panelId);
  }
  persistCollapsedPanels();
  syncPanelCollapse(panelId);
  if (panelId === "map-panel" && state.map && !state.collapsedPanels.has(panelId)) {
    setTimeout(() => state.map.invalidateSize(), 180);
  }
}

function notify(message) {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2200);
}

function headers(extra = {}) {
  const base = { ...extra };
  if (state.token) {
    base.Authorization = `Bearer ${state.token}`;
  }
  return base;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: headers(opts.headers || {}),
  });

  if (res.status === 401) {
    // Evita derrubar o usuário para tela de login por qualquer endpoint auxiliar.
    // Faz logout automático apenas quando o endpoint de sessão falha.
    if (path === "/api/auth/me") {
      logout();
      throw new Error("Sessão expirada");
    }
    throw new Error("Não autorizado para esta ação");
  }

  if (!res.ok) {
    let msg = "Erro na requisição";
    try {
      const data = await res.json();
      msg = data.detail || JSON.stringify(data);
    } catch {
      msg = await res.text();
    }
    throw new Error(msg);
  }

  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  return null;
}

function clearLoginError() {
  loginErrorEl.textContent = "";
  loginErrorEl.classList.add("hidden");
}

function showLoginError(message) {
  loginErrorEl.textContent = message;
  loginErrorEl.classList.remove("hidden");
}

function firstName(fullName) {
  const value = String(fullName || "").trim();
  if (!value) {
    return "";
  }
  return value.split(/\s+/)[0];
}

function logout() {
  state.token = "";
  state.me = null;
  state.orders = [];
  state.workers = [];
  state.notifications = [];
  state.residents = [];
  state.subsets = [];
  if (state.map) {
    state.map.remove();
  }
  state.map = null;
  state.mapMarkers = null;
  state.residentSearchPerformed = false;
  localStorage.removeItem("token");

  COLLAPSIBLE_PANELS.forEach((id) => {
    const panel = document.getElementById(id);
    if (panel) {
      panel.classList.add("hidden");
    }
  });

  $("#auth-panel").classList.remove("hidden");
  $("#user-info").textContent = "";
  $("#logout-btn").classList.add("hidden");
  clearLoginError();
}

async function login(username, password) {
  clearLoginError();
  const body = new URLSearchParams();
  body.set("username", username);
  body.set("password", password);

  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!res.ok) {
    if (res.status === 401) {
      throw new Error("Usuário ou senha incorreto");
    }

    let msg = "Erro ao efetuar login";
    try {
      const data = await res.json();
      msg = data.detail || msg;
    } catch {
      msg = await res.text();
    }
    throw new Error(msg);
  }

  const data = await res.json();
  state.token = data.access_token;
  localStorage.setItem("token", state.token);
  await bootstrapAuthenticated();
}

async function register(formData) {
  const payload = Object.fromEntries(formData.entries());
  payload.apartment = payload.apartment || null;

  await api("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  notify("Conta criada. Faça login.");
}

function prettyStatus(status) {
  return statusLabel[status] || status;
}

function badge(value) {
  return `<span class="badge b-${value}">${priorityLabel[value] || value}</span>`;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function canManageWorkOrders() {
  return state.me && ["sindico", "funcionario", "administrador"].includes(state.me.role);
}

function canManageWorkers() {
  return state.me && ["sindico", "administrador"].includes(state.me.role);
}

function renderHistory(history = []) {
  if (!history.length) {
    return '<div class="history-empty">Sem atualizações ainda.</div>';
  }

  return history
    .slice(0, 4)
    .map((entry) => {
      const fromText = entry.from_status ? prettyStatus(entry.from_status) : "Início";
      const toText = prettyStatus(entry.to_status);
      return `
        <div class="history-item">
          <div class="history-head">
            <strong>${escapeHtml(entry.actor_name)}</strong>
            <span>${new Date(entry.created_at).toLocaleString()}</span>
          </div>
          <div class="history-status">${fromText} -> ${toText}</div>
          <div class="history-note">${escapeHtml(entry.note)}</div>
        </div>
      `;
    })
    .join("");
}

function managerControls(order) {
  if (!canManageWorkOrders()) {
    return "";
  }

  let workerSelect = "";
  if (canManageWorkers()) {
    const options = ['<option value="">Sem atribuição</option>']
      .concat(
        state.workers.map((w) => {
          const selected = w.id === order.assigned_to_id ? "selected" : "";
          return `<option value="${w.id}" ${selected}>${escapeHtml(w.full_name)}</option>`;
        })
      )
      .join("");

    workerSelect = `
      <select data-action="assign" data-id="${order.id}">
        ${options}
      </select>
    `;
  }

  return `
    <div class="stack">
      <select data-status-select="${order.id}">
        ${["backlog", "fazendo", "pendentes", "concluido"]
          .map((s) => `<option value="${s}" ${order.status === s ? "selected" : ""}>${prettyStatus(s)}</option>`)
          .join("")}
      </select>
      <textarea rows="2" data-note-input="${order.id}" placeholder="Atualização do histórico (ex.: pendente compra de item específico)"></textarea>
      <button type="button" data-action="status-save" data-id="${order.id}">Salvar atualização</button>
      ${workerSelect}
    </div>
  `;
}

function renderBoard() {
  const cols = ["backlog", "fazendo", "pendentes", "concluido"];
  cols.forEach((status) => {
    const body = document.querySelector(`.column[data-status="${status}"] .column-body`);
    const cards = state.orders
      .filter((o) => o.status === status)
      .map((o) => {
        const img = o.image_path ? `<img src="${o.image_path}" alt="Anexo da OS" />` : "";
        const historyHtml = renderHistory(o.history || []);
        return `
          <article class="os-card">
            <strong>#${o.id} - ${escapeHtml(o.title)}</strong>
            <p>${escapeHtml(o.description)}</p>
            ${img}
            <div class="os-meta">
              ${badge(o.priority)}
              <span>${categoryLabel[o.category] || o.category}</span>
              <span>criador: ${o.created_by_id}</span>
              <span>atribuído: ${o.assigned_to_id || "-"}</span>
            </div>
            <div class="history-box">
              <div class="history-title">Histórico de Atualizações</div>
              ${historyHtml}
            </div>
            ${managerControls(o)}
          </article>
        `;
      })
      .join("");

    body.innerHTML = cards || "<p>Sem itens</p>";
  });
}

function renderReports(data) {
  const root = $("#reports-content");
  const blocks = [];

  blocks.push(`
    <article class="metric">
      <div class="metric-title">Total de Ordens</div>
      <div class="metric-value">${data.total_ordens || 0}</div>
    </article>
  `);

  blocks.push(`
    <article class="metric">
      <div class="metric-title">Tempo Médio de Resolução (h)</div>
      <div class="metric-value">${data.tempo_medio_resolucao_horas || 0}</div>
    </article>
  `);

  const listMetric = (title, items, mapper) => {
    const rows = Object.entries(items || {}).map(
      ([key, value]) => `<div class="metric-row"><span>${mapper[key] || key}</span><strong>${value}</strong></div>`
    );

    return `
      <article class="metric">
        <div class="metric-title">${title}</div>
        <div class="metric-list">
          ${rows.length ? rows.join("") : '<div class="metric-empty">Sem dados</div>'}
        </div>
      </article>
    `;
  };

  blocks.push(listMetric("Status", data.por_status, statusLabel));
  blocks.push(listMetric("Categoria", data.por_categoria, categoryLabel));
  blocks.push(listMetric("Prioridade", data.por_prioridade, priorityLabel));

  root.innerHTML = blocks.join("");
}

function subsetNameById(subsetId) {
  const found = state.subsets.find((s) => s.id === subsetId);
  return found ? found.name : "-";
}

function renderSubsetOptions() {
  const createSelect = $("#resident-subset-select");
  const searchSelect = $("#resident-search-subset-select");
  const managerSelect = $("#manager-subset-select");
  if (!createSelect || !searchSelect || !managerSelect) {
    return;
  }

  const createOptions = ['<option value="">Selecione o subconjunto</option>']
    .concat(state.subsets.map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`))
    .join("");
  const managerOptions = ['<option value="">Selecione o subconjunto</option>']
    .concat(state.subsets.map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`))
    .join("");
  const searchOptions = ['<option value="">Todos os subconjuntos</option>']
    .concat(state.subsets.map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`))
    .join("");
  createSelect.innerHTML = createOptions;
  managerSelect.innerHTML = managerOptions;
  searchSelect.innerHTML = searchOptions;

  const isSindico = state.me && state.me.role === "sindico";
  if (isSindico && state.subsets.length === 1) {
    createSelect.value = String(state.subsets[0].id);
    searchSelect.value = String(state.subsets[0].id);
    managerSelect.value = String(state.subsets[0].id);
    createSelect.disabled = true;
    searchSelect.disabled = true;
    managerSelect.disabled = true;
  } else {
    createSelect.disabled = false;
    searchSelect.disabled = false;
    managerSelect.disabled = false;
  }
}

function renderSubsetList() {
  const root = $("#subset-list");
  if (!root) {
    return;
  }

  if (!state.me || state.me.role !== "administrador") {
    root.innerHTML = "";
    return;
  }

  root.innerHTML = state.subsets.length
    ? state.subsets
        .map(
          (s) => `
      <article class="resident-item">
        <strong>${escapeHtml(s.name)}</strong>
        <span>ID ${s.id}</span>
      </article>
    `
        )
        .join("")
    : '<div class="resident-item">Nenhum subconjunto cadastrado.</div>';
}

function renderResidents() {
  const list = $("#resident-list");
  const select = $("#resident-select");
  if (!list || !select) {
    return;
  }

  const options = ['<option value="">Pesquise e selecione um morador</option>']
    .concat(
      state.residents.map((r) => {
        const loc = `${r.unit_number || r.apartment || "-"} • ${r.subset_name || subsetNameById(r.subset_id)}`;
        return `<option value="${r.id}">${escapeHtml(r.full_name)} - ${escapeHtml(loc)}</option>`;
      })
    )
    .join("");
  select.innerHTML = options;

  list.innerHTML = state.residents.length
    ? state.residents
        .map(
          (r) => `
      <article class="resident-item">
        <strong>${escapeHtml(r.full_name)}</strong>
        <span>
          ${escapeHtml(r.subset_name || subsetNameById(r.subset_id) || "-")} • Moradia ${escapeHtml(r.unit_number || r.apartment || "-")}
          • Lat ${r.latitude ?? "-"} • Lon ${r.longitude ?? "-"} • @${escapeHtml(r.username)}
        </span>
      </article>
    `
        )
        .join("")
    : state.residentSearchPerformed
      ? '<div class="resident-item">Nenhum resultado para a pesquisa.</div>'
      : '<div class="resident-item">Use a pesquisa para encontrar moradores por nome, usuário ou moradia.</div>';
}

function initOpenMap() {
  if (!window.L) {
    $("#map-info").textContent = "Mapa indisponível no momento.";
    return false;
  }
  if (state.map) {
    return true;
  }

  state.map = window.L.map("open-os-map");
  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(state.map);
  state.mapMarkers = window.L.layerGroup().addTo(state.map);
  state.map.setView([-22.892, -47.204], 15);
  return true;
}

async function loadOpenMapPoints() {
  const hasAccess = state.me && ["sindico", "administrador"].includes(state.me.role);
  if (!hasAccess) {
    $("#map-panel").classList.add("hidden");
    return;
  }

  $("#map-panel").classList.remove("hidden");
  syncPanelCollapse("map-panel");
  $("#map-info").textContent = "Carregando pontos...";

  if (!initOpenMap()) {
    return;
  }

  const points = await api("/api/map/open-work-orders");
  state.mapMarkers.clearLayers();

  if (!points.length) {
    $("#map-info").textContent = "Sem OS abertas com coordenadas no seu escopo.";
    state.map.setView([-22.892, -47.204], 15);
    return;
  }

  $("#map-info").textContent = `${points.length} OS aberta(s) com localização.`;
  const bounds = [];
  points.forEach((p) => {
    if (p.latitude == null || p.longitude == null) {
      return;
    }
    const latlng = [p.latitude, p.longitude];
    const marker = window.L.circleMarker(latlng, {
      radius: 8,
      color: "#073b4c",
      weight: 2,
      fillColor: "#ef476f",
      fillOpacity: 0.8,
    });
    marker.bindPopup(
      `<strong>#${p.work_order_id} - ${escapeHtml(p.title)}</strong><br/>` +
        `Status: ${escapeHtml(prettyStatus(p.status))}<br/>` +
        `Prioridade: ${escapeHtml(priorityLabel[p.priority] || p.priority)}<br/>` +
        `Subconjunto: ${escapeHtml(p.subset_name)}<br/>` +
        `Moradia: ${escapeHtml(p.unit_number)}`
    );
    marker.addTo(state.mapMarkers);
    bounds.push(latlng);
  });

  if (!bounds.length) {
    $("#map-info").textContent = "Sem OS abertas com coordenadas válidas no seu escopo.";
    return;
  }

  if (bounds.length === 1) {
    state.map.setView(bounds[0], 17);
  } else {
    state.map.fitBounds(bounds, { padding: [25, 25] });
  }
}

async function loadSubsets() {
  if (!state.me || !["administrador", "sindico"].includes(state.me.role)) {
    state.subsets = [];
    renderSubsetOptions();
    renderSubsetList();
    return;
  }

  state.subsets = await api("/api/admin/subsets");
  renderSubsetOptions();
  renderSubsetList();
}

async function loadResidents({ q = "", subsetId = "", limit = 50 } = {}) {
  if (!state.me || !["administrador", "sindico"].includes(state.me.role)) {
    state.residents = [];
    state.residentSearchPerformed = false;
    renderResidents();
    return;
  }

  const params = new URLSearchParams();
  const text = String(q || "").trim();
  const subset = String(subsetId || "").trim();
  if (text) {
    params.set("q", text);
  }
  if (subset) {
    params.set("subset_id", subset);
  }
  params.set("limit", String(limit));

  state.residents = await api(`/api/admin/residents?${params.toString()}`);
  state.residentSearchPerformed = true;
  renderResidents();
}

async function loadOrders() {
  const params = new URLSearchParams(new FormData($("#filter-form")));
  const data = await api(`/api/work-orders?${params.toString()}`);
  state.orders = data;
  renderBoard();
}

async function loadNotifications() {
  state.notifications = await api("/api/notifications");
  const root = $("#notifications-list");
  root.innerHTML = state.notifications
    .map(
      (n) => `
      <article class="note-item ${n.is_read ? "" : "unread"}">
        <strong>${escapeHtml(n.title)}</strong>
        <div>${escapeHtml(n.message)}</div>
        <small>${new Date(n.created_at).toLocaleString()}</small>
      </article>
    `
    )
    .join("");
}

async function loadReports() {
  if (!state.me || !["administrador", "sindico", "funcionario"].includes(state.me.role)) {
    $("#reports-panel").classList.add("hidden");
    return;
  }

  const data = await api("/api/reports/summary");
  renderReports(data);
  $("#reports-panel").classList.remove("hidden");
  syncPanelCollapse("reports-panel");
}

async function loadWorkers() {
  if (!state.me || !canManageWorkers()) {
    state.workers = [];
    return;
  }
  state.workers = await api("/api/workers");
}

function enablePanels() {
  $("#auth-panel").classList.add("hidden");
  ["#create-panel", "#filter-panel", "#kanban-panel", "#notifications-panel"].forEach((id) => {
    $(id).classList.remove("hidden");
  });

  if (state.me && ["administrador", "sindico"].includes(state.me.role)) {
    $("#admin-panel").classList.remove("hidden");
  } else {
    $("#admin-panel").classList.add("hidden");
  }

  const subsetAdminBlock = $("#subset-admin-block");
  if (subsetAdminBlock) {
    if (state.me && state.me.role === "administrador") {
      subsetAdminBlock.classList.remove("hidden");
    } else {
      subsetAdminBlock.classList.add("hidden");
    }
  }

  $("#logout-btn").classList.remove("hidden");
  const role = roleLabel[state.me.role] || state.me.role;
  $("#user-info").textContent = `${firstName(state.me.full_name)} (${role})`;
  applyPanelCollapseStates();
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
}

async function setupPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    return;
  }

  try {
    const cfg = await api("/api/push/public-key");
    if (!cfg.publicKey) {
      return;
    }

    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      return;
    }

    const registration = await navigator.serviceWorker.register("/sw.js");
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(cfg.publicKey),
    });

    await api("/api/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(subscription.toJSON()),
    });
  } catch {
    // Push é opcional no MVP.
  }
}

async function bootstrapAuthenticated() {
  state.me = await api("/api/auth/me");
  enablePanels();
  state.residents = [];
  state.residentSearchPerformed = false;
  renderResidents();
  await Promise.all([loadSubsets(), loadWorkers(), loadOrders(), loadNotifications(), loadReports(), loadOpenMapPoints()]);
  setupPush();
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  try {
    await login(form.get("username"), form.get("password"));
    notify("Login efetuado");
  } catch (err) {
    if (err.message === "Usuário ou senha incorreto") {
      showLoginError(err.message);
      return;
    }
    notify(err.message);
  }
});

$("#login-form").addEventListener("input", () => {
  clearLoginError();
});

$("#register-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  try {
    await register(form);
    e.target.reset();
  } catch (err) {
    notify(err.message);
  }
});

$("#subset-create-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const payload = { name: String(form.get("name") || "").trim() };

  try {
    await api("/api/admin/subsets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    e.target.reset();
    await loadSubsets();
    notify("Subconjunto cadastrado");
  } catch (err) {
    notify(err.message);
  }
});

$("#manager-create-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const payload = {
    username: String(form.get("username") || "").trim(),
    full_name: String(form.get("full_name") || "").trim(),
    subset_id: Number(form.get("subset_id")),
    password: String(form.get("password") || ""),
  };

  if (!payload.subset_id) {
    notify("Selecione um subconjunto para o síndico");
    return;
  }

  try {
    await api("/api/admin/managers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    e.target.reset();
    notify("Síndico cadastrado com sucesso");
  } catch (err) {
    notify(err.message);
  }
});

$("#resident-create-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const subsetRaw = String(form.get("subset_id") || "").trim();
  const latitudeRaw = String(form.get("latitude") || "").trim();
  const longitudeRaw = String(form.get("longitude") || "").trim();

  const payload = {
    username: String(form.get("username") || "").trim(),
    full_name: String(form.get("full_name") || "").trim(),
    subset_id: subsetRaw ? Number(subsetRaw) : null,
    unit_number: String(form.get("unit_number") || "").trim(),
    latitude: latitudeRaw ? Number(latitudeRaw) : null,
    longitude: longitudeRaw ? Number(longitudeRaw) : null,
    password: String(form.get("password") || ""),
  };

  if (state.me?.role === "administrador" && !payload.subset_id) {
    notify("Selecione um subconjunto para o morador");
    return;
  }

  try {
    await api("/api/admin/residents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    e.target.reset();
    const searchInput = $("#resident-search-form input[name='q']");
    if (searchInput) {
      searchInput.value = payload.username;
    }
    const searchSubset = $("#resident-search-subset-select");
    if (searchSubset && payload.subset_id) {
      searchSubset.value = String(payload.subset_id);
    }
    await loadResidents({ q: payload.username, subsetId: payload.subset_id || "" });
    notify("Morador cadastrado");
  } catch (err) {
    notify(err.message);
  }
});

$("#resident-search-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const q = String(form.get("q") || "").trim();
  const subsetId = String(form.get("subset_id") || "").trim();

  if (q.length < 1) {
    notify("Digite um termo para pesquisar");
    return;
  }

  try {
    await loadResidents({ q, subsetId });
    notify(`${state.residents.length} resultado(s) encontrado(s)`);
  } catch (err) {
    notify(err.message);
  }
});

$("#resident-reset-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const residentId = Number(form.get("resident_id"));
  const password = String(form.get("password") || "");
  if (!residentId) {
    notify("Selecione um morador");
    return;
  }

  try {
    await api(`/api/admin/residents/${residentId}/reset-password`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    e.target.reset();
    notify("Senha resetada com sucesso");
  } catch (err) {
    notify(err.message);
  }
});

$("#os-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  try {
    await api("/api/work-orders", {
      method: "POST",
      body: form,
    });
    e.target.reset();
    notify("OS criada com sucesso");
    await loadOrders();
  } catch (err) {
    notify(err.message);
  }
});

$("#filter-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await loadOrders();
  } catch (err) {
    notify(err.message);
  }
});

$("#refresh-btn").addEventListener("click", async () => {
  try {
    await Promise.all([loadSubsets(), loadOrders(), loadNotifications(), loadReports(), loadOpenMapPoints()]);
    notify("Atualizado");
  } catch (err) {
    notify(err.message);
  }
});

$("#logout-btn").addEventListener("click", () => {
  logout();
  notify("Logout realizado");
});

document.addEventListener("click", (e) => {
  const toggleBtn = e.target.closest("[data-action='toggle-panel']");
  if (!toggleBtn) {
    return;
  }

  const panelId = toggleBtn.dataset.panelId;
  if (!panelId) {
    return;
  }

  togglePanelCollapse(panelId);
});

$("#kanban-board").addEventListener("change", async (e) => {
  const target = e.target;
  const action = target.dataset.action;
  const id = target.dataset.id;
  if (!action || !id) {
    return;
  }

  try {
    if (action === "assign") {
      await api(`/api/work-orders/${id}/assign`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assigned_to_id: target.value ? Number(target.value) : null }),
      });
    }

    await loadOrders();
  } catch (err) {
    notify(err.message);
  }
});

$("#kanban-board").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-action='status-save']");
  if (!btn) {
    return;
  }

  const id = btn.dataset.id;
  const statusEl = document.querySelector(`[data-status-select="${id}"]`);
  const noteEl = document.querySelector(`[data-note-input="${id}"]`);
  if (!statusEl) {
    return;
  }

  try {
    await api(`/api/work-orders/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: statusEl.value,
        note: noteEl ? noteEl.value.trim() : "",
      }),
    });
    notify("Histórico atualizado");
    await Promise.all([loadOrders(), loadNotifications()]);
  } catch (err) {
    notify(err.message);
  }
});

if (state.token) {
  bootstrapAuthenticated().catch((err) => {
    notify(err.message);
    logout();
  });
}

setInterval(() => {
  if (!state.token) {
    return;
  }
  loadNotifications().catch(() => {});
}, 20000);
