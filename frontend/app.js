const state = {
  token: localStorage.getItem("os_token") || "",
  projectId: Number(localStorage.getItem("os_studio_project") || 0) || null,
  chatId: Number(localStorage.getItem("os_studio_chat") || 0) || null,
  models: [],
  selectedModels: (() => {
    try {
      return new Set(JSON.parse(localStorage.getItem("os_pick_models") || "[]"));
    } catch {
      return new Set();
    }
  })(),
  teamModels: (() => {
    try {
      return JSON.parse(localStorage.getItem("os_team_models") || "[]");
    } catch {
      return [];
    }
  })(),
  judgeModel: localStorage.getItem("os_judge_model") || "",
  rawApiKey: sessionStorage.getItem("os_raw_key") || "",
  clientGuideId: localStorage.getItem("zeus_client_guide") || "cursor",
  fusionPref: localStorage.getItem("zeus_fusion_pref") || "power",
  balanceRub: 0,
  modelFamily: "",
  keysCount: 0,
  intent: "feature",
  mode: "standard",
  agentsN: 2,
  studioMeta: null,
  projectBrief: "",
  projectsCache: [],
  chatsCache: [],
  chatTitle: "",
  runKind: "team", // team | solo | fork
  openFile: null,
  github: null,
  termWs: null,
  previewRunning: false,
  // Single-chat studio (Lovable/Bolt pattern)
  openPanes: [], // [{id, chatId, title, model, agentsN, running}]
  activePaneId: null,
  previewOpen: localStorage.getItem("os_studio_preview") !== "0",
  mobilePaneIdx: 0,
  mobileView: "chat", // chat | preview | chats
  _streamPaneId: null,
  statusStrip: "Готов к задаче",
};

const STUDIO_HOME_TITLE = "Моя студия";
const MAX_PANES = 1;

const STUDIO_TEMPLATES = {
  landing: "Сделай красивый одностраничный лендинг: герой-блок, преимущества, отзыв и кнопка «Оставить заявку». Современный дизайн, адаптив.",
  login: "Сделай страницу входа: email, пароль, кнопка «Войти», ссылка «Забыли пароль?». Аккуратный минималистичный UI.",
  todo: "Сделай Todo-приложение: добавить задачу, отметить выполненной, удалить. Всё в одном HTML+CSS+JS без бэкенда.",
  dashboard: "Сделай простую панель: заголовок, 3 карточки-метрики и таблица последних событий. Чистый современный UI.",
  form: "Сделай форму заявки: имя, телефон, комментарий, кнопка отправить. После отправки покажи сообщение «Спасибо».",
};

function persistStudioSelection() {
  if (state.projectId) localStorage.setItem("os_studio_project", String(state.projectId));
  else localStorage.removeItem("os_studio_project");
  if (state.chatId) localStorage.setItem("os_studio_chat", String(state.chatId));
  else localStorage.removeItem("os_studio_chat");
  persistOpenPanes();
}

function panesStorageKey() {
  return `os_studio_panes_${state.projectId || 0}`;
}

function persistOpenPanes() {
  if (!state.projectId) return;
  const slim = state.openPanes.map((p) => ({
    id: p.id,
    chatId: p.chatId,
    title: p.title,
    model: p.model || "",
    agentsN: p.agentsN || 2,
  }));
  localStorage.setItem(panesStorageKey(), JSON.stringify(slim));
  localStorage.setItem("os_studio_preview", state.previewOpen ? "1" : "0");
}

function loadOpenPanesFromStorage() {
  if (!state.projectId) return [];
  try {
    const raw = JSON.parse(localStorage.getItem(panesStorageKey()) || "[]");
    if (!Array.isArray(raw)) return [];
    return raw.slice(0, 1).map((p, i) => ({
      id: p.id || `pane-${i}-${Date.now()}`,
      chatId: p.chatId || null,
      title: p.title || "",
      model: p.model || "",
      agentsN: Number(p.agentsN) || state.agentsN || 2,
      running: false,
    }));
  } catch {
    return [];
  }
}

function newPaneId() {
  return `pane-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function getPane(paneId) {
  return state.openPanes.find((p) => p.id === paneId) || null;
}

function getActivePane() {
  return getPane(state.activePaneId) || state.openPanes[0] || null;
}

function syncActiveChatFromPane(pane) {
  if (!pane?.chatId) return;
  state.chatId = pane.chatId;
  state.chatTitle = pane.title || state.chatTitle;
  state.agentsN = pane.agentsN || state.agentsN;
  persistStudioSelection();
}


const $ = (id) => document.getElementById(id);

function publicBaseUrl() {
  const base = resolveApiBase();
  return `${base || window.location.origin}/v1`;
}

function saveRawKey(raw) {
  const k = String(raw || "").trim();
  if (!k) return;
  state.rawApiKey = k;
  sessionStorage.setItem("os_raw_key", k);
  syncKeyFields();
  renderMySetup();
}

function syncKeyFields() {
  const url = publicBaseUrl();
  ["dash-base-url", "keys-base-url"].forEach((id) => {
    if ($(id)) $(id).textContent = url;
  });
  const key = state.rawApiKey || "нажми «создать / показать ключ»";
  ["dash-api-key", "keys-api-key"].forEach((id) => {
    if ($(id)) $(id).textContent = key;
  });
}

function syncBaseUrlFields() {
  syncKeyFields();
}

function selectedModelObjs() {
  return [...state.selectedModels]
    .map((id) => state.models.find((m) => m.id === id))
    .filter(Boolean);
}

function per1kRub(per1m) {
  return Number(per1m || 0) / 1000;
}

function estimateDialogRub(m) {
  // короткий диалог ~1k токенов: 700 вход + 300 выход
  const inn = Number(m?.pricing?.input_per_1m || 0);
  const out = Number(m?.pricing?.output_per_1m || m?.pricing?.from_rub || 0);
  return (700 / 1e6) * inn + (300 / 1e6) * out;
}

function setupCostSummary() {
  const rows = selectedModelObjs();
  if (!rows.length) {
    return { html: "", mini: "—", lines: [] };
  }
  const costs = rows.map((m) => ({
    m,
    rub: estimateDialogRub(m),
    inn: Number(m.pricing?.input_per_1m || 0),
    out: Number(m.pricing?.output_per_1m || 0),
  }));
  costs.sort((a, b) => a.rub - b.rub);
  const min = costs[0];
  const max = costs[costs.length - 1];
  const bal = Number(state.balanceRub || 0);
  const cheapN = min.rub > 0 ? Math.floor(bal / min.rub) : "∞";
  const html = `
    <div class="cost-hero">${fmtRub(min.rub, 4)} – ${fmtRub(max.rub, 4)}</div>
    <div class="cost-sub">за 1 короткий диалог (~700 вх + 300 вых токенов)</div>
    <ul class="cost-list">
      ${costs
        .map(
          (c) =>
            `<li><span>${escapeHtml(c.m.title || c.m.id)}</span><b>~${fmtRub(c.rub, 4)}</b></li>`
        )
        .join("")}
    </ul>
    <div class="cost-note">На балансе ${fmtRub(bal)} ≈ ${cheapN} таких диалогов на самой дешёвой из набора.</div>`;
  return {
    html,
    mini: `диалог ${fmtRub(min.rub, 3)}–${fmtRub(max.rub, 3)} ₽`,
    lines: costs.map((c) => `${c.m.id}: ~${fmtRub(c.rub, 4)}/диалог`),
  };
}

function setupModelsHtml() {
  const rows = selectedModelObjs();
  if (!rows.length) {
    return `<div class="setup-empty">Нет моделей — нажми «модели» и отметь нужные.</div>`;
  }
  return `<div class="setup-chips">${rows
    .map((m) => {
      const inn = fmtRub(m.pricing?.input_per_1m || 0, 2);
      const out = fmtRub(m.pricing?.output_per_1m || 0, 2);
      const dlg = fmtRub(estimateDialogRub(m), 4);
      return `<div class="setup-chip" data-mid="${escapeHtml(m.id)}">
        <div class="setup-chip-t">${escapeHtml(m.title || m.id)}</div>
        <div class="setup-chip-id">${escapeHtml(m.id)}</div>
        <div class="setup-chip-p">вход ${inn} · выход ${out} ₽/1M</div>
        <div class="setup-chip-dlg">~${dlg} за диалог</div>
        <button type="button" class="setup-chip-x" data-unpick="${escapeHtml(m.id)}" title="убрать">×</button>
      </div>`;
    })
    .join("")}</div>`;
}

function modelStrength(m) {
  return Number(m?.pricing?.input_per_1m || 0) + Number(m?.pricing?.output_per_1m || 0);
}

function rankPackModels(rows) {
  const list = (rows || selectedModelObjs()).slice().sort((a, b) => modelStrength(b) - modelStrength(a));
  return { judge: list[0] || null, workers: list.slice(1) };
}

function launchStudioFromPack() {
  const rows = selectedModelObjs();
  if (!rows.length) {
    alert("Сначала выбери 2–5 моделей в каталоге");
    setTab("models");
    return;
  }
  const ranked = rankPackModels(rows);
  state.teamModels = rows.map((m) => m.id);
  state.judgeModel = ranked.judge?.id || rows[0].id;
  state.agentsN = Math.min(4, Math.max(2, rows.length));
  localStorage.setItem("os_team_models", JSON.stringify(state.teamModels));
  localStorage.setItem("os_judge_model", state.judgeModel || "");
  setTab("projects");
  flashSetup(
    `Студия: оркестратор ${state.judgeModel} · воркеры ${state.teamModels.filter((id) => id !== state.judgeModel).join(", ") || "—"}`
  );
  startNewStudioChat().catch((e) => alert(e.message || String(e)));
}

function flashSetup(msg) {
  document.querySelectorAll('[data-setup="flash"]').forEach((el) => {
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.add("hidden"), 4000);
  });
}

function renderMySetup() {
  syncKeyFields();
  const n = state.selectedModels.size;
  if ($("pick-n")) $("pick-n").textContent = String(n);
  if ($("pick-n-dash")) $("pick-n-dash").textContent = String(n);
  const bar = $("models-pick-bar");
  if (bar) bar.classList.toggle("on", n > 0);

  const hasRaw = !!state.rawApiKey;
  const keyCount = Number(state.keysCount || 0);
  let status = "";
  if (!hasRaw && keyCount > 0) status = "Ключ скрыт — нажми «создать ключ», чтобы показать новый.";
  else if (!hasRaw) status = "Создай ключ — потом вставь Base URL + ключ в любой OpenAI-compatible клиент.";

  document.querySelectorAll('[data-setup="status"]').forEach((el) => {
    el.textContent = status;
    el.classList.toggle("ok", hasRaw);
    el.classList.toggle("warn", !hasRaw);
    el.classList.toggle("hidden", !status);
  });

  const modelsHtml = setupModelsHtml();
  document.querySelectorAll('[data-setup="models"]').forEach((el) => {
    el.innerHTML = modelsHtml;
  });
  document.querySelectorAll("[data-unpick]").forEach((btn) => {
    btn.onclick = (e) => {
      e.preventDefault();
      toggleModelPick(btn.dataset.unpick);
      renderModels();
    };
  });

  const cost = setupCostSummary();
  document.querySelectorAll('[data-setup="cost"]').forEach((el) => {
    el.innerHTML = cost.html;
    el.classList.toggle("hidden", !cost.html);
  });
  if ($("pick-cost-mini")) $("pick-cost-mini").textContent = cost.mini || "—";

  const bal = Number(state.balanceRub || 0);
  document.querySelectorAll('[data-setup="balance"]').forEach((el) => {
    el.textContent = `Баланс: ${fmtRub(bal)} · платишь только за токены выбранной модели`;
  });
  renderClientGuides();
}

function persistSelectedModels() {
  localStorage.setItem("os_pick_models", JSON.stringify([...state.selectedModels]));
  renderMySetup();
  // One key → server remembers panel when mode is «свой набор»
  if (state.token && (state.fusionPref || "") === "custom") {
    void syncFusionModelsToServer();
  }
}

async function syncFusionModelsToServer() {
  try {
    const models = selectedModelIds().slice(0, 3);
    if (!models.length) return;
    await api("/me/fusion", { method: "PUT", body: { mode: "custom", models } });
  } catch {
    /* non-blocking */
  }
}

function toggleModelPick(id) {
  if (!id) return;
  if (state.selectedModels.has(id)) state.selectedModels.delete(id);
  else {
    if (state.selectedModels.size >= 3) {
      flashSetup("Максимум 3 модели в наборе", true);
      return;
    }
    state.selectedModels.add(id);
  }
  persistSelectedModels();
  document.querySelectorAll(`.model-card[data-mid="${CSS.escape(id)}"]`).forEach((el) => {
    el.classList.toggle("picked", state.selectedModels.has(id));
    const cb = el.querySelector(".m-pick");
    if (cb) cb.checked = state.selectedModels.has(id);
  });
}

function defaultPickModels() {
  if (state.selectedModels.size) {
    persistSelectedModels();
    return;
  }
  const prefer = ["gemini-2.5-flash", "claude-sonnet-4-5", "gpt-4o", "grok-3", "gpt-5"];
  const ready = state.models.filter(
    (m) => m.ready && (m.modality || "chat") === "chat" && !String(m.id).startsWith("studio-")
  );
  for (const id of prefer) {
    if (ready.some((m) => m.id === id)) state.selectedModels.add(id);
    if (state.selectedModels.size >= 3) break;
  }
  if (state.selectedModels.size < 2) {
    ready.slice(0, 3).forEach((m) => state.selectedModels.add(m.id));
  }
  persistSelectedModels();
}

const CLIENT_GUIDES = [
  {
    id: "fusion",
    title: "Fusion",
    steps: [
      "model = zeuscode — режим из Mini App / выбора ниже",
      "Простой: flash+gemini-3-pro+haiku · Мощный: opus-4-8+v4-pro+3.1-pro (умный 1↔3)",
      "Свой набор: отметь до 3 моделей во вкладке «модели»",
      "Cursor: только zeuscode — режим с аккаунта",
    ],
    configKind: "fusion",
  },
  {
    id: "cursor",
    title: "Cursor",
    steps: [
      "Settings → Models → OpenAI API Key — ключ ZeusCode",
      "Override OpenAI Base URL → …/v1",
      "Add model → zeuscode + нужные id из каталога",
      "В чате выбери модель ZeusCode",
    ],
    configKind: "cursor",
  },
  {
    id: "opencode",
    title: "OpenCode",
    steps: [
      "Windows: C:\\Users\\<имя ПК>\\.config\\opencode\\opencode.json",
      "Mac/Linux: ~/.config/opencode/opencode.json — вставь весь JSON",
      "В пикере только ZeusCode (zeuscode) — один id",
      "Режим Пользовательский / Продвинутый / Набор — только в Telegram «Модели»",
    ],
    configKind: "opencode",
  },
  {
    id: "kilo",
    title: "Kilo Code",
    steps: [
      "VS Code / JetBrains → Extensions → Kilo Code",
      "Settings → Providers → Custom → OpenAI Compatible",
      "Base URL = Zeus …/v1 · API Key = zeus_…",
      "Модели подтянутся сами с /v1/models",
    ],
    configKind: "kilo",
  },
  {
    id: "continue",
    title: "Continue",
    steps: [
      "Открой ~/.continue/config.yaml (или config.json)",
      "Добавь provider openai с apiBase и apiKey",
      "model: zeuscode (режим) или любой id — весь каталог в yaml",
      "Перезапусти Continue",
    ],
    configKind: "continue",
  },
  {
    id: "cline",
    title: "Cline",
    steps: [
      "Панель Cline → ⚙️ → API Provider = OpenAI Compatible",
      "Base URL = Zeus …/v1 (без /chat/completions)",
      "API Key = zeus_… · Model ID = zeuscode (весь каталог на ключе)",
      "Verify / Save → задача в панели Cline",
    ],
    configKind: "cline",
  },
  {
    id: "goose",
    title: "Goose",
    steps: [
      "Установи Goose (block.github.io/goose)",
      "OPENAI_HOST=https://zeuscode.ru (без /v1) · OPENAI_BASE_PATH=v1/chat/completions",
      "OPENAI_API_KEY + GOOSE_PROVIDER=openai + GOOSE_MODEL=zeuscode",
      "goose info -v · goose session · сменить модель: GOOSE_MODEL=<id>",
    ],
    configKind: "goose",
  },
  {
    id: "crush",
    title: "Crush",
    steps: [
      "Установи Crush (charmbracelet/crush)",
      "~/.config/crush/crush.json — type openai-compat",
      "export ZEUSCODE_API_KEY=…",
      "crush → выбери модель Zeus",
    ],
    configKind: "crush",
  },
  {
    id: "openhands",
    title: "OpenHands",
    steps: [
      "Settings → LLM → Advanced",
      "Custom Model = openai/<id> (префикс openai/ обязателен)",
      "Base URL = Zeus …/v1 · API Key = zeus_…",
      "Issue→PR / задача в UI или CLI",
    ],
    configKind: "openhands",
  },
  {
    id: "windsurf",
    title: "Windsurf",
    steps: [
      "Скачай Windsurf IDE",
      "Marketplace → Cline или Kilo Code (нативный BYOK слабый)",
      "В расширении: OpenAI Compatible → Base URL + ключ Zeus",
      "Агент Zeus — в панели Cline/Kilo, не в Cascade",
    ],
    configKind: "kilo",
  },
  {
    id: "zed",
    title: "Zed",
    steps: [
      "settings.json → language_models.openai_compatible.ZeusCode",
      "api_url = Zeus …/v1 · available_models с capabilities",
      "Ключ: ZEUSCODE_API_KEY в env или agent: open settings (не в JSON)",
      "Agent panel → модель Zeus",
    ],
    configKind: "zed",
  },
  {
    id: "librechat",
    title: "LibreChat",
    steps: [
      "librechat.yaml → endpoints.custom ZeusCode",
      ".env → ZEUSCODE_API_KEY=…",
      "models.fetch: true тянет /v1/models",
      "Restart → выбери ZeusCode в чате",
    ],
    configKind: "librechat",
  },
  {
    id: "openwebui",
    title: "Open WebUI",
    steps: [
      "Admin → Connections → OpenAI",
      "Base URL = Zeus …/v1 · API Key = zeus_…",
      "Или env OPENAI_API_BASE_URL + OPENAI_API_KEY",
      "Модели с /v1/models",
    ],
    configKind: "openwebui",
  },
  {
    id: "omniroute",
    title: "OmniRoute",
    steps: [
      "Providers → OpenAI Compatible · Chat Completions (не Responses)",
      "Base URL …/v1 · API Key zeus_… · model zeuscode",
      "502 UND_ERR_SOCKET → OmniRoute ≥3.8.36 + FETCH_KEEPALIVE_TIMEOUT_MS=1",
      "Тест: gemini-2.5-flash → потом fusion · omniroute setup-codex",
    ],
    configKind: "omniroute",
  },
  {
    id: "codex",
    title: "Codex",
    steps: [
      "~/.codex/config.toml → model_providers.zeuscode",
      "wire_api = responses · requires_openai_auth = false",
      "export ZEUSCODE_API_KEY=zeus_… (не в toml)",
      "model = zeuscode · или любой id · через OmniRoute localhost:20128/v1",
    ],
    configKind: "codex",
  },
  {
    id: "claude",
    title: "Claude Code",
    steps: [
      "~/.claude/settings.json → env блок (Claude Code ≥ 2.1.129)",
      "ANTHROPIC_BASE_URL = https://zeuscode.ru (без /v1) · AUTH_TOKEN = zeus_…",
      "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1 → /model = весь каталог ZeusCode",
      "Дефолт zeuscode · не-Claude в пикере: anthropic.zeuscode/<id>",
    ],
    configKind: "claude",
  },
  {
    id: "aider",
    title: "Aider",
    steps: [
      "export OPENAI_API_BASE=…/v1 · OPENAI_API_KEY=zeus_…",
      "aider --model openai/zeuscode",
      "Другая модель: openai/<id> из каталога ZeusCode",
    ],
    configKind: "aider",
  },
  {
    id: "python",
    title: "Python SDK",
    steps: [
      "pip install openai",
      "OpenAI(base_url=…, api_key=…)",
      "model = \"zeuscode\" или id нейросети",
    ],
    configKind: "python",
  },
  {
    id: "js",
    title: "JS / Node",
    steps: [
      "npm i openai",
      "new OpenAI({ baseURL, apiKey })",
      "model: \"zeuscode\" или id нейросети",
    ],
    configKind: "js",
  },
  {
    id: "curl",
    title: "curl / HTTP",
    steps: [
      "POST {Base URL}/chat/completions",
      "Header: Authorization: Bearer {API Key}",
      "Body: model zeuscode + messages (+ опционально models)",
    ],
    configKind: "curl",
  },
  {
    id: "any",
    title: "Любой OpenAI-compatible",
    steps: [
      "Найди «OpenAI Compatible» / «Custom provider» / «Base URL»",
      "Вставь Base URL (…/v1) и API Key",
      "Одна нейронка: её id · кооператив: zeuscode",
      "Проверка: GET /v1/models · POST /v1/chat/completions",
    ],
    configKind: "openai_any",
  },
];

function selectedModelIds() {
  let models = [...state.selectedModels];
  if (!models.length) {
    defaultPickModels();
    models = [...state.selectedModels];
  }
  if (!models.length) models = ["gemini-2.5-flash"];
  return models;
}

function primaryModelId() {
  return selectedModelIds()[0] || "gemini-2.5-flash";
}

/** One key unlocks the full ready chat catalog; default client model is zeuscode. */
function readyChatModelIds() {
  const fusion = "zeuscode";
  const fromCat = (state.models || state.catalog || [])
    .filter((m) => m && m.id && m.ready !== false && (m.modality || "chat") === "chat")
    .map((m) => String(m.id));
  const ids = [fusion, ...fromCat.filter((id) => id !== fusion)];
  if (ids.length <= 1) {
    for (const id of [
      "gemini-3.1-pro",
      "gemini-3-pro",
      "gemini-3-flash",
      "gemini-2.5-pro",
      "gemini-2.5-flash",
      "deepseek-v4-pro",
      "deepseek-v4-flash",
      "claude-opus-4-8",
      "claude-sonnet-4-6",
      "claude-haiku-4-5",
      "gpt-5.4",
      "gpt-5.6-sol",
      "gpt-5.6-terra",
      "grok-4-5",
    ]) {
      if (!ids.includes(id)) ids.push(id);
    }
  }
  return ids;
}

function catalogCommentLines(ids, limit = 80) {
  const slice = ids.slice(0, limit);
  const more = ids.length > limit ? ` … +${ids.length - limit}` : "";
  return [
    `# ZeusCode · весь каталог (${ids.length}) на этом ключе — GET …/models`,
    `# ${slice.join(" · ")}${more}`,
  ];
}

function catalogDisplayName(id) {
  const row = (state.models || state.catalog || []).find((m) => m && String(m.id) === String(id));
  const title = (row && (row.title || row.name)) || id;
  if (id === "zeuscode") return "ZeusCode";
  return String(title).startsWith("ZeusCode") ? String(title) : `ZeusCode · ${title}`;
}

function buildClientConfig(kind) {
  const base = publicBaseUrl();
  const key = state.rawApiKey || "<создай ключ>";
  const fusion = "zeuscode";
  const model = fusion; // дефолт везде: режим из Mini App / кабинета
  const catalogIds = readyChatModelIds();
  const catNote = catalogCommentLines(catalogIds);
  const panel = selectedModelIds().slice(0, 3);
  const pref = state.fusionPref || "power";
  if (kind === "fusion") {
    const modelsJson = JSON.stringify(panel);
    const zeusBody =
      pref === "custom"
        ? `"zeus":{"mode":"custom"},"models":${modelsJson}`
        : `"zeus":{"mode":"${pref}"}`;
    return [
      `# Режим: ${pref} (сохрани в кабинете / TG /mode)`,
      `curl ${base}/chat/completions \\`,
      '  -H "Content-Type: application/json" \\',
      `  -H "Authorization: Bearer ${key}" \\`,
      `  -d '{"model":"zeuscode",${zeusBody},"messages":[{"role":"user","content":"Сравни плюсы и минусы"}]}'`,
      "",
      "# Python:",
      "from openai import OpenAI",
      `c = OpenAI(base_url="${base}", api_key="${key}")`,
      "r = c.chat.completions.create(",
      '  model="zeuscode",',
      pref === "custom"
        ? `  extra_body={"zeus": {"mode": "custom"}, "models": ${modelsJson}},`
        : `  extra_body={"zeus": {"mode": "${pref}"}},`,
      '  messages=[{"role":"user","content":"Сравни плюсы и минусы"}],',
      ")",
      "print(r.choices[0].message.content)",
    ].join("\n");
  }
  if (kind === "continue") {
    const extra = catalogIds
      .filter((id) => id !== fusion)
      .map(
        (id) =>
          `  - name: ${catalogDisplayName(id)}\n    provider: openai\n    model: ${id}\n` +
          `    apiBase: ${base}\n    apiKey: ${key}\n` +
          `    useResponsesApi: false\n` +
          `    roles:\n      - chat\n      - edit\n      - apply`
      )
      .join("\n");
    return [
      "# ~/.continue/config.yaml · zeuscode = режим Mini App",
      "name: ZeusCode",
      "version: 1.0.0",
      "schema: v1",
      "models:",
      `  - name: ZeusCode`,
      "    provider: openai",
      `    model: ${fusion}`,
      `    apiBase: ${base}`,
      `    apiKey: ${key}`,
      "    useResponsesApi: false",
      "    capabilities:",
      "      - tool_use",
      "    roles:",
      "      - chat",
      "      - edit",
      "      - apply",
      extra,
      ...catNote,
    ].join("\n");
  }
  if (kind === "opencode") {
    const simple = ["deepseek-v4-flash", "gemini-3-pro", "claude-haiku-4-5"];
    const power = ["claude-opus-4-8", "deepseek-v4-pro", "gemini-3.1-pro"];
    const pref = state.fusionPref || "power";
    const custom = selectedModelIds().slice(0, 3);
    const titles = {
      simple: "Пользовательский",
      power: "Продвинутый",
      custom: "Набор",
    };
    const hints = {
      simple: "Три лёгкие нейронки · сами переключаются",
      power: "Три сильные нейронки · сами переключаются",
      custom: "Собери до трёх нейронок сам",
    };
    const curTitle = titles[pref] || "Продвинутый";
    // Один id в пикере. Режим — только TG / кабинет, не отдельные Zeus Simple/Power/Custom.
    const models = {
      zeuscode: {
        name: `ZeusCode · режим «${curTitle}» из Telegram`,
        tools: true,
      },
    };
    const rows = (state.models || state.catalog || []).filter(
      (m) => m && m.id && m.ready !== false && (m.modality || "chat") === "chat"
    );
    for (const m of rows) {
      const id = String(m.id);
      if (id === "zeuscode" || id.startsWith("zeuscode")) continue;
      if (id.startsWith("studio-") || id === "ultra-mode") continue;
      const title = String(m.title || id).replace(/^ZeusCode( ·)?\s*/i, "");
      models[id] = {
        name: title,
        tools: id !== "claude-fable-5" && m.adapter !== "pending",
      };
    }
    return JSON.stringify(
      {
        $schema: "https://opencode.ai/config.json",
        model: "zeuscode/zeuscode",
        provider: {
          zeuscode: {
            npm: "@ai-sdk/openai-compatible",
            name: "ZeusCode",
            options: {
              baseURL: String(base || "").replace(/\/+$/, ""),
              apiKey: key,
            },
            models,
          },
        },
      },
      null,
      2
    );
  }
  const root = String(base || "").replace(/\/+$/, "");
  const host = root.replace(/\/v1$/, "");
  if (kind === "cline") {
    return [
      `# Cline → панель слева → ⚙️ Settings`,
      `# Один ключ = весь каталог. Дефолт zeuscode = режим из Mini App.`,
      `API Provider: OpenAI Compatible`,
      `Base URL:     ${root}`,
      `API Key:      ${key}`,
      `Model ID:     ${fusion}`,
      ``,
      ...catNote,
      `# В клиенте можно выбрать любой id из /v1/models`,
      `# Base URL только до /v1 — без /chat/completions`,
    ].join("\n");
  }
  if (kind === "kilo") {
    return [
      `# Kilo Code → Settings → Providers → Custom`,
      `# Один ключ = весь каталог (Kilo тянет /models сам)`,
      `# Provider API: OpenAI Compatible`,
      `Base URL: ${root}`,
      `API Key: ${key}`,
      `Model: ${fusion}`,
      ...catNote,
    ].join("\n");
  }
  if (kind === "goose") {
    return [
      `# Goose — путь A (built-in openai)`,
      `export GOOSE_PROVIDER=openai`,
      `export OPENAI_API_KEY="${key}"`,
      `export OPENAI_HOST="${root}"`,
      `export GOOSE_MODEL="${fusion}"`,
      ``,
      `# Путь B: ~/.config/goose/custom_providers/zeuscode.json`,
      `# base_url=${root}/chat/completions · api_key_env=ZEUSCODE_API_KEY`,
      ``,
      ...catNote,
      `# goose info -v && goose session`,
    ].join("\n");
  }
  if (kind === "crush") {
    const models = catalogIds.map((id) => ({
      id,
      name: catalogDisplayName(id),
      context_window: 200000,
      default_max_tokens: 8192,
    }));
    return (
      JSON.stringify(
        {
          $schema: "https://charm.land/crush.json",
          providers: {
            zeuscode: {
              name: "ZeusCode",
              type: "openai-compat",
              base_url: root,
              api_key: "$ZEUSCODE_API_KEY",
              discover_models: true,
              models,
            },
          },
        },
        null,
        2
      ) +
      `\n\n# export ZEUSCODE_API_KEY="${key}"\n# ~/.config/crush/crush.json\n` +
      catNote.join("\n")
    );
  }
  if (kind === "openhands") {
    return [
      `# Один ключ = все модели. Дефолт = режим Mini App.`,
      `LLM_MODEL=openai/${fusion}`,
      `LLM_BASE_URL=${root}`,
      `LLM_API_KEY=${key}`,
      ``,
      `# Любая другая: openai/<id>  (префикс openai/ обязателен)`,
      ...catNote,
    ].join("\n");
  }
  if (kind === "zed") {
    const zedCaps = {
      tools: true,
      images: false,
      parallel_tool_calls: false,
      prompt_cache_key: false,
    };
    const available_models = catalogIds.map((id) => ({
      name: id,
      display_name: catalogDisplayName(id),
      max_tokens: 200000,
      capabilities: zedCaps,
    }));
    return (
      JSON.stringify(
        {
          language_models: {
            openai_compatible: {
              zeuscode: {
                api_url: root,
                available_models,
              },
            },
          },
        },
        null,
        2
      ) +
      `\n\n# export ZEUSCODE_API_KEY="${key}"\n` +
      catNote.join("\n")
    );
  }
  if (kind === "librechat") {
    const defaults = catalogIds.slice(0, 12);
    return [
      `# Один ключ · fetch: true тянет ВЕСЬ каталог`,
      `endpoints:`,
      `  custom:`,
      `    - name: "ZeusCode"`,
      `      apiKey: "\${ZEUSCODE_API_KEY}"`,
      `      baseURL: "${root}"`,
      `      models:`,
      `        default: ${JSON.stringify(defaults)}`,
      `        fetch: true`,
      `      titleConvo: true`,
      `      titleModel: "${fusion}"`,
      `      modelDisplayLabel: "ZeusCode"`,
      ``,
      `ZEUSCODE_API_KEY=${key}`,
      ...catNote,
    ].join("\n");
  }
  if (kind === "openwebui") {
    return [
      `# Один ключ Zeus — модели подтянутся все с /v1/models`,
      `OPENAI_API_BASE_URL=${root}`,
      `OPENAI_API_KEY=${key}`,
      `# Admin → Connections → OpenAI — те же значения`,
      `# В чате: любая модель · zeuscode = режим Mini App`,
      ...catNote,
    ].join("\n");
  }
  if (kind === "openai_any") {
    return [
      `# Любой OpenAI-compatible · один ключ = весь каталог`,
      `Base URL: ${root}`,
      `API Key:  ${key}`,
      `Model:    ${fusion}   # режим Mini App · или любой id`,
      ``,
      `curl ${root}/models -H "Authorization: Bearer ${key}"`,
      ``,
      `curl ${root}/chat/completions \\`,
      `  -H "Content-Type: application/json" \\`,
      `  -H "Authorization: Bearer ${key}" \\`,
      `  -d '{"model":"${fusion}","messages":[{"role":"user","content":"ping"}]}'`,
      ...catNote,
    ].join("\n");
  }
  if (kind === "omniroute") {
    return [
      `# OmniRoute → Providers → OpenAI Compatible`,
      `# Протокол: Chat Completions (НЕ Responses)`,
      `Base URL: ${root}`,
      `API Key:  ${key}`,
      `Model:    ${fusion}   # со слэшем · тест: gemini-2.5-flash`,
      ``,
      `# 502 UND_ERR_SOCKET → OmniRoute ≥3.8.36 + FETCH_KEEPALIVE_TIMEOUT_MS=1`,
      `# omniroute setup-codex  → профили на все модели`,
      ...catNote,
    ].join("\n");
  }
  if (kind === "codex") {
    return [
      `# ~/.codex/config.toml`,
      `# Один ключ = все модели. Дефолт zeuscode = режим Mini App.`,
      `model = "${fusion}"`,
      `model_provider = "zeuscode"`,
      ``,
      `[model_providers.zeuscode]`,
      `name = "ZeusCode"`,
      `base_url = "${root}"`,
      `env_key = "ZEUSCODE_API_KEY"`,
      `requires_openai_auth = false`,
      `wire_api = "responses"`,
      ``,
      `# export ZEUSCODE_API_KEY="${key}"`,
      `# Сменить модель: codex -m <id>  или /model в сессии`,
      `# Через OmniRoute: base_url = "http://localhost:20128/v1"`,
      ...catNote,
    ].join("\n");
  }
  if (kind === "claude") {
    const hostOnly = root.replace(/\/v1$/, "");
    return (
      JSON.stringify(
        {
          env: {
            ANTHROPIC_BASE_URL: hostOnly,
            ANTHROPIC_AUTH_TOKEN: key,
            ANTHROPIC_MODEL: fusion,
            CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY: "1",
            ANTHROPIC_CUSTOM_MODEL_OPTION: fusion,
            ANTHROPIC_CUSTOM_MODEL_OPTION_NAME: "ZeusCode",
            ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION:
              "Режим из Mini App «Модели» · весь каталог ZeusCode на ключе",
            ANTHROPIC_DEFAULT_SONNET_MODEL: "claude-sonnet-4-6",
            ANTHROPIC_DEFAULT_OPUS_MODEL: "claude-opus-4-8",
            ANTHROPIC_DEFAULT_HAIKU_MODEL: "claude-haiku-4-5",
          },
        },
        null,
        2
      ) +
      `\n\n# ~/.claude/settings.json · Claude Code ≥ 2.1.129\n` +
      `# без /v1 в BASE_URL · unset ANTHROPIC_API_KEY\n` +
      `# /model → весь каталог ZeusCode (gateway discovery)\n` +
      `# Не-Claude: anthropic.zeuscode/<id> · или claude --model <id>\n` +
      catNote.join("\n")
    );
  }
  if (kind === "aider") {
    const menu = catalogIds.map((id) => `#   aider --model openai/${id}`).join("\n");
    return [
      `# Aider · ZeusCode · один ключ = весь каталог`,
      `export OPENAI_API_BASE="${root}"`,
      `export OPENAI_API_KEY="${key}"`,
      `aider --model openai/${fusion}`,
      ``,
      `# Другая модель:`,
      menu,
      ...catNote,
    ].join("\n");
  }
  if (kind === "cursor") {
    return [
      `# Cursor Override часто ломает Agent (Responses → /chat/completions).`,
      `# Надёжнее: Cline/Kilo → OpenAI Compatible.`,
      ``,
      `# Нативно (на свой риск):`,
      `# Settings → Models → OpenAI API Key + Override Base URL = ${root}`,
      `# Add model → ${fusion}  (не gpt-*, не zeuscode-simple)`,
      ``,
      `# Cline/Kilo:`,
      `# Base URL: ${root}`,
      `# API Key:  ${key}`,
      `# Model:    ${fusion}`,
      ...catNote,
    ].join("\n");
  }
  if (kind === "python") {
    return [
      "from openai import OpenAI",
      "",
      "client = OpenAI(",
      `    base_url="${base}",`,
      `    api_key="${key}",`,
      ")",
      "",
      "r = client.chat.completions.create(",
      `    model="${fusion}",  # или любой id из /v1/models`,
      '    messages=[{"role": "user", "content": "ping"}],',
      ")",
      "print(r.choices[0].message.content)",
      "",
      ...catNote,
    ].join("\n");
  }
  if (kind === "js") {
    return [
      'import OpenAI from "openai";',
      "",
      "const client = new OpenAI({",
      `  baseURL: "${base}",`,
      `  apiKey: "${key}",`,
      "});",
      "",
      "const r = await client.chat.completions.create({",
      `  model: "${fusion}", // или любой id из /v1/models`,
      '  messages: [{ role: "user", content: "ping" }],',
      "});",
      "console.log(r.choices[0].message.content);",
      "",
      ...catNote,
    ].join("\n");
  }
  if (kind === "curl") {
    return [
      `curl ${base}/chat/completions \\`,
      '  -H "Content-Type: application/json" \\',
      `  -H "Authorization: Bearer ${key}" \\`,
      `  -d '{"model":"${fusion}","messages":[{"role":"user","content":"ping"}]}'`,
      "",
      ...catNote,
    ].join("\n");
  }
  return buildConnectionPack();
}

function buildConnectionPack() {
  const base = publicBaseUrl();
  const key = state.rawApiKey || "<сначала создай ключ кнопкой>";
  const models = readyChatModelIds();
  const lines = [
    "ZeusCode · OpenAI-compatible API",
    "",
    `Base URL: ${base}`,
    `API Key:  ${key}`,
    "",
    "Один ключ = весь каталог. Дефолт в клиенте: zeuscode",
    "(режим из Mini App «Модели» / кабинета).",
    "",
    "Models (GET /v1/models):",
    ...models.slice(0, 24).map((id, i) => `  ${i + 1}. ${id}`),
    models.length > 24 ? `  … +${models.length - 24}` : "",
    "",
    "Клиенты: OpenCode, Kilo, Goose, Crush, OpenHands, Windsurf, Zed,",
    "LibreChat, Open WebUI, Cursor, Continue, Cline, Codex, Claude, SDK.",
    "Кооператив / режим: model=zeuscode.",
  ].filter((x) => x !== "");
  return lines.join("\n");
}

function renderClientGuides() {
  const tabsNodes = document.querySelectorAll('[data-setup="client-tabs"]');
  const panelNodes = document.querySelectorAll('[data-setup="client-panel"]');
  if (!tabsNodes.length) return;

  const active = state.clientGuideId || CLIENT_GUIDES[0].id;
  state.clientGuideId = active;
  const guide = CLIENT_GUIDES.find((g) => g.id === active) || CLIENT_GUIDES[0];

  const tabsHtml = CLIENT_GUIDES.map(
    (g) =>
      `<button type="button" class="client-tab${g.id === guide.id ? " on" : ""}" data-client="${g.id}" role="tab" aria-selected="${g.id === guide.id}">${g.title}</button>`
  ).join("");

  const steps = guide.steps.map((s) => `<li>${s}</li>`).join("");
  const config = guide.configKind ? buildClientConfig(guide.configKind) : null;
  const fusionModes =
    guide.id === "fusion"
      ? `<div class="fusion-mode-pick" role="group" aria-label="Режим Fusion">
          ${["simple", "power", "custom"]
            .map((m) => {
              const titles = { simple: "Простой", power: "Мощный", custom: "Свой набор" };
              const hints = {
                simple: "всегда 1 модель",
                power: "умный 1↔3",
                custom: "модели ниже + 1↔3",
              };
              const on = (state.fusionPref || "power") === m ? " on" : "";
              return `<button type="button" class="client-tab fusion-mode-btn${on}" data-fusion-mode="${m}" title="${hints[m]}">${titles[m]}</button>`;
            })
            .join("")}
         </div>
         <p class="muted sm" style="margin:.4rem 0 .8rem">TG: /mode · Cursor подхватит pref с аккаунта</p>`
      : "";
  const panelHtml = [
    fusionModes,
    `<ol class="client-steps">${steps}</ol>`,
    config
      ? `<pre class="polza-code client-config">${escapeHtml(config)}</pre>
         <button type="button" class="btn btn-s sm" data-action="copy-client-config">скопировать конфиг</button>`
      : `<button type="button" class="btn btn-s sm" data-action="copy-pack">скопировать Base URL + ключ</button>`,
  ].join("");

  tabsNodes.forEach((el) => {
    el.innerHTML = tabsHtml;
  });
  panelNodes.forEach((el) => {
    el.innerHTML = panelHtml;
  });

  document.querySelectorAll("[data-client]").forEach((btn) => {
    btn.onclick = () => {
      state.clientGuideId = btn.dataset.client;
      localStorage.setItem("zeus_client_guide", state.clientGuideId);
      renderClientGuides();
    };
  });
  document.querySelectorAll("[data-fusion-mode]").forEach((btn) => {
    btn.onclick = () => {
      void setFusionPref(btn.dataset.fusionMode);
    };
  });
}

async function setFusionPref(mode) {
  if (!mode || !["simple", "power", "custom"].includes(mode)) return;
  state.fusionPref = mode;
  localStorage.setItem("zeus_fusion_pref", mode);
  if (state.token) {
    try {
      const body = { mode };
      if (mode === "custom") body.models = selectedModelIds().slice(0, 3);
      await api("/me/fusion", { method: "PUT", body });
      flashSetup(
        mode === "simple"
          ? "Режим: простой (1 модель)"
          : mode === "power"
            ? "Режим: мощный (умный 1↔3)"
            : "Режим: свой набор"
      );
    } catch (e) {
      flashSetup(e.message || "Не удалось сохранить режим", true);
    }
  }
  renderClientGuides();
  renderMySetup();
}

async function generateConnectionPack(targetId) {
  if (!state.rawApiKey) {
    await createVisibleKey();
  } else {
    await ensureApiKey();
  }
  const pack = buildConnectionPack();
  const targets = [targetId, "dash-pack-out", "keys-pack-out", "models-pack-out"].filter(Boolean);
  const seen = new Set();
  targets.forEach((id) => {
    if (seen.has(id)) return;
    seen.add(id);
    const out = $(id);
    if (!out) return;
    out.textContent = pack;
    out.classList.remove("hidden");
  });
  await copyText(pack);
  flashSetup("Подключение скопировано в буфер");
  renderMySetup();
  return pack;
}

async function ensureApiKey() {
  if (!state.token) return null;
  if (state.rawApiKey) {
    syncKeyFields();
    return state.rawApiKey;
  }
  const data = await api("/keys/ensure", { method: "POST", body: {} });
  if (data.raw_key) {
    saveRawKey(data.raw_key);
    state.keysCount = Math.max(1, Number(state.keysCount || 0));
    flashSetup("Ключ создан автоматически");
  } else {
    syncKeyFields();
  }
  renderMySetup();
  return state.rawApiKey || null;
}

async function createVisibleKey() {
  if (!state.token) throw new Error("Сначала войди в кабинет");
  const name = ($("key-name")?.value || "").trim() || "default";
  const budget_rub = Math.max(0, Number($("key-budget")?.value || 0));
  const data = await api("/keys", { method: "POST", body: { name, budget_rub } });
  if (!data.raw_key) throw new Error("Сервер не вернул ключ");
  saveRawKey(data.raw_key);
  state.keysCount = Number(state.keysCount || 0) + 1;
  flashSetup("Ключ создан — скопируй его сейчас, полный текст больше не покажем");
  const box = $("new-key-box");
  if (box) {
    box.classList.remove("hidden");
    box.innerHTML = `<div class="setup-flash">✓ Ключ создан: <code>${escapeHtml(data.raw_key)}</code></div>`;
  }
  try {
    await refreshKeys();
  } catch {
    /* */
  }
  try {
    await refreshSummary();
  } catch {
    /* */
  }
  renderMySetup();
  return data.raw_key;
}

async function copyText(text) {
  const t = String(text || "").trim();
  if (!t) return;
  try {
    await navigator.clipboard.writeText(t);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = t;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}

function bindCopyButtons(root = document) {
  root.querySelectorAll("[data-copy], [data-copy-text]").forEach((btn) => {
    if (btn.dataset.copyBound) return;
    btn.dataset.copyBound = "1";
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const sel = btn.getAttribute("data-copy");
      const el = sel ? document.querySelector(sel) : null;
      const text = (el?.textContent || btn.getAttribute("data-copy-text") || btn.dataset.copyText || "").trim();
      await copyText(text);
      const prev = btn.textContent;
      btn.textContent = "ok";
      setTimeout(() => {
        btn.textContent = prev;
      }, 1000);
    });
  });
}

function updatePolzaSteps(s) {
  state.balanceRub = Number(s.balance_rub || 0);
  state.kieCredits =
    s.credits != null
      ? Number(s.credits)
      : s.kie_credits != null
        ? Number(s.kie_credits)
        : state.balanceRub;
  state.keysCount = Number(s.api_keys || 0);
  const balTxt = fmtRub(state.balanceRub);
  if ($("polza-bal")) {
    const kie = s.credits != null ? Number(s.credits) : (s.kie_credits != null ? Number(s.kie_credits) : null);
    $("polza-bal").textContent =
      kie != null ? fmtRub(kie) : balTxt;
  }
  if ($("keys-n-vis")) $("keys-n-vis").textContent = String(s.api_keys ?? 0);
  if ($("models-total-vis")) $("models-total-vis").textContent = String(s.models_total ?? state.models.length ?? 0);
  renderMySetup();
}


function setAuthCookie() {
  if (state.token) {
    document.cookie = `zc_token=${state.token}; path=/; SameSite=Lax`;
  }
}

const BADGE_RU = {
  killer: "фишка",
  cheap: "дёшево",
  fusion: "fusion",
  benchmark: "эталон",
  cache: "кэш",
  ready: "доступно",
  soon: "скоро",
};

const MODE_RU = {
  ultra: "ультра",
  premium: "premium",
  light: "лайт",
  standard: "стандарт",
  solo: "обычный",
};

const ROLE_LABEL = {
  frontend: "фронт",
  backend: "бэк",
  design: "дизайн",
  tests: "тесты",
  docs: "доки",
  general: "ассистент",
  synth: "сборка",
  reviewer: "ревью",
};

/** Live artifacts streamed during a Studio run: path → {path, content, role, ...} */
state.liveArts = state.liveArts || {};
state.liveEvidence = null;
state.liveTab = "files";

function resetLiveWork() {
  state.liveArts = {};
  state.liveEvidence = null;
  state.liveTab = "files";
  const lw = $("live-work");
  const files = $("live-files");
  const prev = $("live-preview-wrap");
  if (lw) lw.classList.add("hidden");
  if (files) files.innerHTML = "";
  if (prev) {
    prev.classList.add("hidden");
    const iframe = $("live-preview");
    if (iframe) iframe.srcdoc = "";
  }
  document.querySelectorAll(".live-tab").forEach((t) => {
    t.classList.toggle("on", t.dataset.liveTab === "files");
  });
  // visible run panels
  ["zc-contract", "zc-gate", "zc-run-bill"].forEach((id) => {
    const el = $(id);
    if (el) {
      el.classList.add("hidden");
      el.innerHTML = "";
    }
  });
}

function renderContractPanel(ev) {
  const box = $("zc-contract");
  if (!box) return;
  box.classList.add("hidden");
  void ev;
}

function renderGatePanel(ev) {
  const box = $("zc-gate");
  if (!box) return;
  box.classList.add("hidden");
  if (ev?.gate) {
    setStatusStrip(`Gate · ${ev.gate} · score ${ev.score ?? "—"}`);
  }
}

function showRunBilling(data) {
  const box = $("zc-run-bill");
  if (!data) return;
  const bill = data.billing || {};
  const msg = data.message || {};
  const agents = msg.agents || data.onestack?.agents || [];
  const models = {};
  for (const a of agents) {
    const m = a.model || "?";
    models[m] = (models[m] || 0) + 1;
  }
  const modelLine = Object.entries(models)
    .map(([m, n]) => `${m}×${n}`)
    .join(" · ");
  const charged = bill.charged_rub ?? msg.cost_user_rub;
  const left = bill.balance_left_rub;
  const chargeTxt = charged != null ? `${Number(charged).toFixed(2)} ₽` : "—";
  setStatusStrip(
    `Готово · списано ${chargeTxt}${left != null ? ` · баланс ${Number(left).toFixed(2)} ₽` : ""}`
  );
  if (!box) return;
  // keep legacy panel filled but stay hidden (details live in status strip)
  box.classList.add("hidden");
  box.innerHTML = `
    <div class="zc-panel-h">Списание за прогон</div>
    <div class="zc-panel-b">
      <strong>${chargeTxt}</strong>
      ${left != null ? `<span class="muted"> · баланс ${Number(left).toFixed(2)} ₽</span>` : ""}
      ${modelLine ? `<div class="muted">${escapeHtml(modelLine)}</div>` : ""}
    </div>`;
}

function mergeLiveArts(arts) {
  if (!arts || !arts.length) return;
  for (const a of arts) {
    if (!a?.path) continue;
    state.liveArts[a.path] = a;
  }
  renderLiveFiles();
  maybeUpdatePreview();
}

function renderLiveFiles() {
  const lw = $("live-work");
  const box = $("live-files");
  if (!lw || !box) return;
  const paths = Object.keys(state.liveArts).sort();
  if (!paths.length) {
    lw.classList.add("hidden");
    return;
  }
  lw.classList.remove("hidden");
  box.innerHTML = paths
    .map((p) => {
      const a = state.liveArts[p];
      const role = a.role || "";
      const n = a.bytes || (a.content || "").length;
      return `<div class="live-file" data-path="${escapeHtml(p)}"><span>${escapeHtml(p)}</span><span class="lf-role">${escapeHtml(role)} · ${n}b</span></div>`;
    })
    .join("");
  box.querySelectorAll(".live-file").forEach((el) => {
    el.onclick = () => {
      const a = state.liveArts[el.dataset.path];
      if (!a) return;
      // show file in preview tab as text via srcdoc pre
      setLiveTab("preview");
      const iframe = $("live-preview");
      if (!iframe) return;
      if ((a.path || "").endsWith(".html") || a.language === "html") {
        iframe.srcdoc = buildFrontendSrcdoc();
      } else {
        iframe.srcdoc = `<pre style="margin:12px;font:12px/1.4 ui-monospace,monospace;white-space:pre-wrap">${escapeHtml(a.content || "")}</pre>`;
      }
    };
  });
}

function buildFrontendSrcdoc() {
  const arts = state.liveArts;
  let html =
    arts["/src/frontend/index.html"]?.content ||
    Object.values(arts).find((a) => (a.path || "").endsWith(".html"))?.content ||
    "";
  if (!html) {
    return `<p style="font:14px system-ui;padding:16px;color:#444">Нет HTML артефакта для preview</p>`;
  }
  let css = Object.values(arts)
    .filter(
      (a) =>
        ((a.path || "").startsWith("/src/frontend/") &&
          ((a.path || "").endsWith(".css") || a.language === "css")) ||
        ((a.path || "").endsWith(".css") && a.role === "frontend")
    )
    .map((a) => a.content || "")
    .join("\n");
  // Flatten @import of workspace CSS (design tokens) — mirrors evidence.flatten_css_for_preview
  css = flattenCssImports(css, arts);
  const tok = arts["/src/design/tokens.css"]?.content || "";
  if (!css.trim() && tok) css = tok;
  const js = Object.values(arts)
    .filter((a) => (a.path || "").endsWith(".js") || a.language === "js" || a.language === "javascript")
    .map((a) => a.content || "")
    .join("\n");
  // Inline linked assets so iframe works without network
  html = html.replace(/<link[^>]+href=["']\.\/[^"']+\.css["'][^>]*>/gi, "");
  html = html.replace(/<script[^>]+src=["']\.\/[^"']+\.js["'][^>]*>\s*<\/script>/gi, "");
  if (css) {
    if (/<\/head>/i.test(html)) {
      html = html.replace(/<\/head>/i, `<style>\n${css}\n</style></head>`);
    } else {
      html = `<style>${css}</style>` + html;
    }
  }
  if (js) {
    if (/<\/body>/i.test(html)) {
      html = html.replace(/<\/body>/i, `<script type="module">\n${js}\n</script></body>`);
    } else {
      html += `<script type="module">\n${js}\n</script>`;
    }
  }
  return html;
}

function resolveFeRel(ref, fromPath) {
  const r = String(ref || "").trim();
  if (!r || /^(data:|https?:|blob:|#|mailto:|tel:|\/\/)/i.test(r)) return null;
  if (r.startsWith("/src/")) return r.split(/[?#]/)[0];
  if (r.startsWith("/") && !r.startsWith("/src/")) {
    return `/src/frontend/${r.replace(/^\//, "")}`.split(/[?#]/)[0];
  }
  const baseDir = (fromPath || "/src/frontend/styles.css").replace(/\/[^/]*$/, "");
  const parts = [...baseDir.replace(/^\//, "").split("/"), ...r.split("/")];
  const out = [];
  for (const p of parts) {
    if (!p || p === ".") continue;
    if (p === "..") {
      out.pop();
      continue;
    }
    out.push(p);
  }
  return ("/" + out.join("/")).split(/[?#]/)[0];
}

function flattenCssImports(cssText, arts, fromPath, depth) {
  const seen = flattenCssImports._seen || (flattenCssImports._seen = new Set());
  if (depth === 0) seen.clear();
  depth = depth || 0;
  fromPath = fromPath || "/src/frontend/styles.css";
  if (depth > 6) return cssText || "";
  return String(cssText || "").replace(
    /@import\s+(?:url\(\s*['"]?([^'")\s]+)['"]?\s*\)|['"]([^'"]+)['"])\s*;?/gi,
    (full, g1, g2) => {
      const ref = (g1 || g2 || "").trim();
      if (!ref || /^(https?:|data:)/i.test(ref)) return full;
      let resolved = resolveFeRel(ref, fromPath);
      if (!resolved || seen.has(resolved)) return "/* skipped import */\n";
      let body = arts[resolved]?.content;
      if (!body) {
        const base = resolved.split("/").pop();
        const hit = Object.keys(arts).find((p) => p.endsWith("/" + base) && p.startsWith("/src/"));
        if (hit) {
          resolved = hit;
          body = arts[hit]?.content;
        }
      }
      if (!body) return full;
      seen.add(resolved);
      return `/* inlined ${resolved} */\n` + flattenCssImports(body, arts, resolved, depth + 1) + "\n";
    }
  );
}

function maybeUpdatePreview() {
  const hasHtml = Object.keys(state.liveArts).some(
    (p) => p.endsWith(".html") || state.liveArts[p]?.language === "html"
  );
  if (!hasHtml) return;
  if (state.liveTab !== "preview") return;
  const iframe = $("live-preview");
  if (iframe) iframe.srcdoc = buildFrontendSrcdoc();
}

function setLiveTab(tab) {
  state.liveTab = tab;
  document.querySelectorAll(".live-tab").forEach((t) => {
    t.classList.toggle("on", t.dataset.liveTab === tab);
  });
  const files = $("live-files");
  const prev = $("live-preview-wrap");
  if (tab === "files") {
    files?.classList.remove("hidden");
    prev?.classList.add("hidden");
  } else {
    files?.classList.add("hidden");
    prev?.classList.remove("hidden");
    const iframe = $("live-preview");
    if (iframe) iframe.srcdoc = buildFrontendSrcdoc();
  }
}

document.addEventListener("click", (e) => {
  const t = e.target.closest?.(".live-tab");
  if (t?.dataset.liveTab) setLiveTab(t.dataset.liveTab);
});


function fmtRub(n, digits = 2) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "0,00 ₽";
  return (
    v.toLocaleString("ru-RU", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }) + " ₽"
  );
}

function formatErr(detail) {
  if (!detail) return "Ошибка";
  if (typeof detail === "string") {
    const map = {
      "Email already registered": "Этот email уже зарегистрирован",
      "Invalid email or password": "Неверный email или пароль",
      "Insufficient balance": "Недостаточно средств на балансе",
    };
    return map[detail] || detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (typeof d === "string") return d;
        const loc = (d.loc || []).filter((x) => x !== "body").join(".");
        if (d.type === "value_error" && loc === "email") return "Введи нормальный email (с @)";
        if (loc === "password") return "Пароль слишком короткий (минимум 6 символов)";
        return d.msg || JSON.stringify(d);
      })
      .join("; ");
  }
  if (typeof detail === "object" && detail.msg) return detail.msg;
  return JSON.stringify(detail);
}

function resolveApiBase() {
  let base = String(window.ZEUS_API_BASE || localStorage.getItem("zeus_api_base") || "")
    .trim()
    .replace(/\/$/, "");
  const host = location.hostname || "";
  const onLocal = host === "127.0.0.1" || host === "localhost";
  const looksLocalApi = /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(base);
  // Stale local API from localStorage breaks production (HTTPS page → HTTP localhost).
  if (!onLocal && looksLocalApi) {
    localStorage.removeItem("zeus_api_base");
    window.ZEUS_API_BASE = "";
    base = "";
  }
  return base;
}

async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const base = resolveApiBase();
  const url = path.startsWith("http") ? path : `${base}${path}`;
  let res;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    const onPages = /github\.io$/i.test(location.hostname);
    const onProd = /zeuscode\.ru$/i.test(location.hostname);
    throw new Error(
      onPages
        ? "Нет связи с API. На GitHub Pages бэкенда нет — впиши адрес API выше (живой сервер) и войди снова."
        : onProd
          ? "Нет связи с сервером. Обнови страницу (Ctrl+Shift+R). Если не помогло — напиши в поддержку."
          : "Сервер не отвечает. Запусти API на http://127.0.0.1:8080 и обнови страницу."
    );
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // GitHub Pages / tunnel interstitial often returns HTML → empty detail
    if (onGithubPages() && (res.status === 404 || res.status === 405 || !data.detail)) {
      throw new Error(
        "API не найден по этому адресу. Укажи живой бэкенд в поле API (не github.io)."
      );
    }
    throw new Error(formatErr(data.detail) || res.statusText || "Ошибка");
  }
  return data;
}

function onGithubPages() {
  return /github\.io$/i.test(location.hostname);
}

function syncApiBaseFromField() {
  const inp = $("api-base");
  if (!inp) return;
  const v = inp.value.trim().replace(/\/$/, "");
  if (v) {
    localStorage.setItem("zeus_api_base", v);
    window.ZEUS_API_BASE = v;
  } else {
    localStorage.removeItem("zeus_api_base");
    window.ZEUS_API_BASE = "";
  }
}

function initApiBaseField() {
  const inp = $("api-base");
  const field = $("api-base-field");
  if (!inp) return;
  resolveApiBase(); // drop stale localhost override on prod
  const saved = localStorage.getItem("zeus_api_base") || window.ZEUS_API_BASE || "";
  inp.value = saved;
  window.ZEUS_API_BASE = saved;
  // Always show on GitHub Pages; hide on same-origin cabinet
  if (field && !onGithubPages() && !saved) {
    field.classList.add("hidden");
  }
  inp.addEventListener("change", syncApiBaseFromField);
  inp.addEventListener("blur", syncApiBaseFromField);
}

function showApp(on) {
  $("view-auth").classList.toggle("hidden", on);
  $("view-app").classList.toggle("hidden", !on);
  $("nav-bal")?.classList.toggle("hidden", !on);
  $("nav-logout")?.classList.toggle("hidden", !on);
  if (!on) {
    $("nav-cabinet")?.classList.add("hidden");
    $("view-app")?.classList.remove("studio-focus");
    document.body.classList.remove("studio-focus");
  }
}

function setTab(name) {
  document.querySelectorAll(".nav a[data-tab]").forEach((a) => {
    a.classList.toggle("on", a.dataset.tab === name);
  });
  ["dash", "models", "projects", "keys", "usage", "billing"].forEach((t) => {
    $(`tab-${t}`).classList.toggle("hidden", t !== name);
  });
  const studioFocus = name === "projects";
  $("view-app")?.classList.toggle("studio-focus", studioFocus);
  document.body.classList.toggle("studio-focus", studioFocus);
  const appVisible = $("view-app") && !$("view-app").classList.contains("hidden");
  // Exit lives inside studio canvas (#btn-studio-exit); hide duplicate top chip
  $("nav-cabinet")?.classList.add("hidden");
  $("nav-bal")?.classList.toggle("hidden", studioFocus || !appVisible);
  $("nav-logout")?.classList.toggle("hidden", studioFocus || !appVisible);
  $("nav-logo")?.classList.toggle("hidden", studioFocus);
  if (name === "projects") {
    loadStudioMeta();
    enterStudioShell();
  }
  if (name === "keys") {
    syncBaseUrlFields();
    ensureApiKey().then(() => refreshKeys()).catch(() => refreshKeys());
  }
  if (name === "dash") {
    refreshSummary();
    ensureApiKey().catch(() => {});
  }
  if (name === "usage") loadUsage();
  if (name === "models") {
    loadModelsCatalog()
      .then(() => renderModels())
      .catch((e) => {
        const box = $("models-grid");
        if (box) {
          box.innerHTML = `<div class="empty-state"><div class="empty-t">Не удалось загрузить каталог</div><div class="empty-d">${escapeHtml(e.message || String(e))}</div></div>`;
        }
      });
  }
  if (name === "billing") loadBillingSettings();
}

function setAgents(mode, team, agentsDetail) {
  // legacy no-op kept for callers — coop board is the live UI
  updateChatSub();
  if (mode === "run" && team) initCoopBoard(team);
}

function updateChatSub() {
  const el = $("chat-sub");
  if (!el) return;
  if (state.runKind === "fork") {
    el.textContent = "3 нейросети делают параллельно — потом выберешь лучший вариант";
    return;
  }
  if (state.runKind === "solo" || ($("model")?.value || "").trim()) {
    el.textContent = "одна нейросеть отвечает на задачу";
    return;
  }
  const hints = {
    light: "быстро · 1 нейросеть",
    standard: "обычно · 2 нейросети думают вместе",
    ultra: "мощно · 4 нейросети + сборка ответа",
    premium: "максимум · 4 топ-нейросети + сборка",
  };
  const intent = state.studioMeta?.intents?.find((i) => i.id === state.intent);
  el.textContent = `${hints[state.mode] || state.mode}${intent ? ` · ${intent.title}` : ""}`;
}

function initCoopBoard(team) {
  const board = $("coop-board");
  const grid = $("coop-grid");
  const synth = $("coop-synth");
  if (!board || !grid) return;
  board.classList.remove("hidden");
  resetLiveWork();
  if (synth) {
    synth.classList.add("hidden");
    synth.innerHTML = "";
  }
  const review = $("coop-review");
  if (review) {
    review.classList.add("hidden");
    review.classList.remove("pass", "fail", "risk");
    review.innerHTML = "";
  }
  const roles = team && team.length ? team : ["design", "frontend", "backend", "tests"];
  grid.innerHTML = roles
    .map(
      (r) => `
    <div class="coop-card" id="coop-${r}" data-role="${r}">
      <div class="coop-card-h">
        <span class="coop-role">${ROLE_LABEL[r] || r}</span>
        <span class="coop-status" data-st>ждёт</span>
      </div>
      <div class="coop-model" data-model></div>
      <div class="coop-think" data-think></div>
      <div class="coop-out" data-out></div>
      <div class="coop-files" data-files></div>
    </div>`
    )
    .join("");
}

function coopUpdate(ev) {
  const board = $("coop-board");
  if (!board) return;
  board.classList.remove("hidden");

  if (ev.type === "meta") {
    initCoopBoard(ev.team || []);
    return;
  }
  if (ev.type === "agent_start") {
    let card = $(`coop-${ev.role}`);
    if (!card) {
      initCoopBoard([...(state._coopTeam || []), ev.role]);
      card = $(`coop-${ev.role}`);
    }
    if (!card) return;
    card.classList.add("running");
    const st = card.querySelector("[data-st]");
    const md = card.querySelector("[data-model]");
    if (st) st.textContent = "думает…";
    if (md) md.textContent = `${ev.skill || ""} · ${ev.model || ""}`;
    return;
  }
  if (ev.type === "agent_think") {
    const card = $(`coop-${ev.role}`);
    if (!card) return;
    const th = card.querySelector("[data-think]");
    const st = card.querySelector("[data-st]");
    if (st) st.textContent = "размышляет";
    if (th) th.textContent = ev.thinking || "";
    card.classList.add("thinking");
    return;
  }
  if (ev.type === "agent_done") {
    const card = $(`coop-${ev.role}`);
    if (!card) return;
    card.classList.remove("running", "thinking");
    card.classList.add("done");
    const st = card.querySelector("[data-st]");
    const th = card.querySelector("[data-think]");
    const out = card.querySelector("[data-out]");
    const md = card.querySelector("[data-model]");
    const files = card.querySelector("[data-files]");
    if (st) st.textContent = `готово · ${ev.latency_s || "?"}с`;
    if (md) md.textContent = ev.model || "";
    if (th && ev.thinking) th.textContent = ev.thinking;
    if (out) out.textContent = ev.preview || "";
    const arts = ev.artifacts || [];
    if (files && arts.length) {
      files.textContent = arts.map((a) => a.path).filter(Boolean).join("\n");
    }
    mergeLiveArts(arts);
    return;
  }
  if (ev.type === "synth_start") {
    const synth = $("coop-synth");
    if (!synth) return;
    synth.classList.remove("hidden");
    synth.innerHTML = `<div class="coop-synth-h">Собираем общий ответ · ${escapeHtml(ev.model || "")}</div><div class="coop-synth-b">Склеиваю работу нейросетей…</div>`;
    return;
  }
  if (ev.type === "synth_done") {
    const synth = $("coop-synth");
    if (!synth) return;
    synth.classList.remove("hidden");
    synth.innerHTML = `<div class="coop-synth-h">Ответ собран</div><div class="coop-synth-b">${escapeHtml((ev.preview || "").slice(0, 400))}</div>`;
    return;
  }
  if (ev.type === "review_start") {
    const box = $("coop-review");
    if (!box) return;
    box.classList.remove("hidden");
    box.classList.remove("pass", "fail", "risk");
    box.innerHTML = `<div class="coop-synth-h">Проверяем результат · ${escapeHtml(ev.model || "")}</div><div class="coop-synth-b">${ev.llm ? "Нейросеть смотрит код…" : "Автопроверка…"}</div>`;
    return;
  }
  if (ev.type === "review_done") {
    const box = $("coop-review");
    if (!box) return;
    box.classList.remove("hidden");
    const v = (ev.verdict || ev.gate || "").toUpperCase();
    box.classList.remove("pass", "fail", "risk");
    if (v === "FAIL") box.classList.add("fail");
    else if (v === "PASS_WITH_RISKS") box.classList.add("risk");
    else box.classList.add("pass");
    const verdictRu =
      v === "FAIL" ? "есть проблемы" : v === "PASS_WITH_RISKS" ? "ок, но с рисками" : "всё ок";
    const findings = (ev.evidence && ev.evidence.findings) || [];
    const fl = findings
      .slice(0, 8)
      .map((f) => `• [${f.severity}] ${f.code}: ${f.message}`)
      .join("\n");
    const notProved = ((ev.evidence && ev.evidence.not_proved) || [])
      .slice(0, 2)
      .map((x) => `· ${x}`)
      .join("\n");
    box.innerHTML = `<div class="coop-synth-h">Проверка · ${escapeHtml(verdictRu)} · оценка ${escapeHtml(String(ev.score ?? "—"))}</div><div class="coop-synth-b">${escapeHtml(fl || ev.preview || "")}${notProved ? "\n\nНе доказано:\n" + escapeHtml(notProved) : ""}</div>`;
    state.liveEvidence = ev.evidence || {
      verdict: ev.verdict,
      gate: ev.gate,
      score: ev.score,
      grade: ev.grade,
      findings,
    };
    mergeLiveArts(ev.artifacts || []);
    // Auto-open preview when frontend HTML landed and gate finished
    if (Object.keys(state.liveArts).some((p) => p.endsWith(".html"))) {
      setLiveTab("preview");
    }
  }
}

function relativeTime(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "";
  const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (sec < 60) return `${sec}с`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}м`;
  const h = Math.round(min / 60);
  if (h < 48) return `${h}ч`;
  return `${Math.round(h / 24)}д`;
}

function applyWorkShellAttrs() {
  const shell = $("zc-work-shell");
  if (!shell) return;
  shell.dataset.panes = "1";
  shell.dataset.preview = "0";
  state.previewOpen = false;
  shell.classList.remove("is-preview-focus", "is-chats-focus");
}

function setStatusStrip(_text) {
  // status chrome removed from studio UI
}

function syncAgentsFromAdv() {
  const sel = $("studio-agents-n");
  if (sel) {
    const n = Number(sel.value) || 2;
    state.agentsN = n;
    state.mode = { 1: "light", 2: "standard", 3: "ultra", 4: "ultra" }[n] || state.mode || "standard";
  }
  const modelSel = $("studio-adv-model");
  const pane = getActivePane();
  if (pane && modelSel) pane.model = modelSel.value || "";
}

function fillAdvModelSelect() {
  const sel = $("studio-adv-model");
  if (!sel) return;
  const pane = getActivePane();
  sel.innerHTML = modelOptionsHtml(pane?.model || "");
}

function ensureDefaultPanes() {
  if (state.openPanes.length > 1) {
    state.openPanes = state.openPanes.slice(0, 1);
  }
  if (state.openPanes.length) {
    if (!state.activePaneId || !getPane(state.activePaneId)) {
      state.activePaneId = state.openPanes[0].id;
    }
    return;
  }
  const stored = loadOpenPanesFromStorage();
  if (stored.length) {
    state.openPanes = stored.slice(0, 1);
  } else {
    state.openPanes = [
      {
        id: newPaneId(),
        chatId: state.chatId || null,
        title: state.chatTitle || "",
        model: "",
        agentsN: state.agentsN || 2,
        running: false,
      },
    ];
  }
  if (!state.activePaneId || !getPane(state.activePaneId)) {
    state.activePaneId = state.openPanes[0].id;
  }
  persistOpenPanes();
}

function setActivePane(paneId) {
  if (!getPane(paneId)) return;
  state.activePaneId = paneId;
  const pane = getPane(paneId);
  syncActiveChatFromPane(pane);
  document.querySelectorAll(".agent-pane").forEach((el) => {
    el.classList.toggle("is-active", el.dataset.paneId === paneId);
  });
  renderStudioRail();
  renderMobilePaneTabs();
}

function addEmptyPane() {
  // Multi-pane removed: new task = new chat in the single pane
  const pane = getActivePane();
  if (pane) createChatForPane(pane.id);
}

function closePane(_paneId) {
  // no-op: single chat layout
}

function openChatInPane(chatId, title, { newPane: _newPane = false } = {}) {
  const chat = (state.chatsCache || []).find((c) => c.id === chatId);
  const t = title || chat?.title || `Чат #${chatId}`;
  ensureDefaultPanes();
  let pane = getActivePane() || state.openPanes[0];
  if (!pane) {
    ensureDefaultPanes();
    pane = state.openPanes[0];
  }
  if (pane.running) {
    alert("Сейчас идёт генерация — подожди или открой другой чат после");
    return;
  }
  pane.chatId = chatId;
  pane.title = t;
  state.activePaneId = pane.id;
  syncActiveChatFromPane(pane);
  persistOpenPanes();
  showStudioWork(t);
  renderAllPanes();
  loadPaneHistory(pane.id).catch(() => {});
  renderStudioRail();
}

function modelOptionsHtml(selected) {
  const ready = (state.models || []).filter(
    (m) =>
      m.ready &&
      (m.modality || "chat") === "chat" &&
      !String(m.id).startsWith("studio-") &&
      m.id !== "ultra-mode"
  );
  const autoLabel = autoModelsShortLabel();
  const opts = [`<option value="">авто · ${escapeHtml(autoLabel)}</option>`].concat(
    ready.map(
      (m) =>
        `<option value="${escapeHtml(m.id)}" ${m.id === selected ? "selected" : ""}>${escapeHtml(m.title)}</option>`
    )
  );
  return opts.join("");
}

function studioPackModels() {
  if (state.teamModels && state.teamModels.length) return state.teamModels.slice(0, 5);
  if (state.selectedModels && state.selectedModels.size) return [...state.selectedModels].slice(0, 5);
  return [];
}

function autoModelsShortLabel() {
  const pack = studioPackModels();
  if (pack.length) {
    return pack
      .map((id) => (state.models || []).find((m) => m.id === id)?.title || id)
      .join(", ");
  }
  return "Flash + Pro";
}

function autoModelsHintHtml(agentsN) {
  const n = Number(agentsN) || state.agentsN || 2;
  const pack = studioPackModels();
  let text;
  if (pack.length) {
    const titles = pack.map((id) => (state.models || []).find((m) => m.id === id)?.title || id);
    text = `При «авто» возьму из твоего набора: ${titles.join(" · ")} (${n} агент${n === 1 ? "" : n < 5 ? "а" : "ов"})`;
  } else if (n === 1) {
    text = "При «авто»: Gemini 2.5 Flash (1 агент, режим быстро)";
  } else if (n === 2) {
    text = "При «авто»: Gemini 2.5 Flash ×2 + ревью Gemini 2.5 Pro";
  } else if (n === 3) {
    text = "При «авто»: Gemini 2.5 Flash ×3 + synth/review Gemini 2.5 Pro";
  } else {
    text = "При «авто»: Gemini 2.5 Flash ×4 + synth/review Gemini 2.5 Pro (ультра)";
  }
  return `<div class="ap-auto-hint" data-ap-auto-hint>${escapeHtml(text)}</div>`;
}

function modeSelectHtml(agentsN) {
  const n = Number(agentsN) || state.agentsN || 2;
  const opts = [
    [1, "1 · быстро"],
    [2, "2 · обычно"],
    [3, "3 · сильнее"],
    [4, "4 · ультра"],
  ];
  return `<select data-ap-mode class="ap-mode-select" title="Режим">${opts
    .map(([v, label]) => `<option value="${v}" ${n === v ? "selected" : ""}>${label}</option>`)
    .join("")}</select>`;
}

function updateAutoHint(paneEl) {
  const hint = paneEl?.querySelector("[data-ap-auto-hint]");
  if (!hint) return;
  const modeSel = paneEl.querySelector("[data-ap-mode]");
  const modelSel = paneEl.querySelector("[data-ap-model]");
  const n = Number(modeSel?.value) || state.agentsN || 2;
  if (modelSel && modelSel.value) {
    const title =
      (state.models || []).find((m) => m.id === modelSel.value)?.title || modelSel.value;
    hint.textContent = `Фикс: одна модель «${title}» на всех агентах`;
    return;
  }
  hint.innerHTML = autoModelsHintHtml(n).replace(/^<div[^>]*>/, "").replace(/<\/div>$/, "");
  // simpler: just set text via temporary parse
  const tmp = document.createElement("div");
  tmp.innerHTML = autoModelsHintHtml(n);
  hint.textContent = tmp.textContent || "";
}

function renderAgentPane(pane, idx) {
  const empty = !pane.chatId;
  const agents = pane.agentsN || state.agentsN || 2;
  const modelSel = `<select data-ap-model class="ap-model-select" title="Модель">${modelOptionsHtml(pane.model || "")}</select>`;
  const modeSel = modeSelectHtml(agents);
  const hint = autoModelsHintHtml(agents);
  if (empty) {
    return `
      <div class="agent-pane zc-chat is-empty is-active mobile-on" data-pane-id="${pane.id}" data-pane-idx="${idx}">
        <div class="ap-scroll ap-hero-scroll">
          <div class="ap-hero">
            <strong class="ap-hero-title">Что сделать?</strong>
            <p class="ap-hero-sub">Опиши сайт или задачу — команда соберёт это за тебя.</p>
            <textarea data-ap-input class="ap-hero-input" placeholder="Сделай лендинг кофейни…" rows="4"></textarea>
            <div class="ap-hero-actions">
              ${modeSel}
              ${modelSel}
              <button type="button" class="btn primary ap-send" data-ap-send>Сделать</button>
            </div>
            ${hint}
          </div>
        </div>
      </div>`;
  }
  return `
    <div class="agent-pane zc-chat is-active mobile-on" data-pane-id="${pane.id}" data-pane-idx="${idx}">
      <div class="ap-scroll" data-ap-scroll></div>
      <div class="ap-foot">
        <textarea data-ap-input placeholder="Что доработать?" rows="2"></textarea>
        <div class="ap-foot-row">
          ${modeSel}
          ${modelSel}
          <button type="button" class="btn primary sm ap-send" data-ap-send ${pane.running ? "disabled" : ""}>Отправить</button>
        </div>
        ${hint}
      </div>
    </div>`;
}

function renderAllPanes() {
  ensureDefaultPanes();
  applyWorkShellAttrs();
  const host = $("zc-panes");
  if (!host) return;
  host.innerHTML = state.openPanes.slice(0, 1).map((p, i) => renderAgentPane(p, i)).join("");
  bindPaneDom();
  renderStudioRail();
  state.openPanes.slice(0, 1).forEach((p) => {
    if (p.chatId) loadPaneHistory(p.id).catch(() => {});
  });
}

function renderMobilePaneTabs() {
  const tabs = $("zc-mobile-tabs");
  if (!tabs) return;
  tabs.classList.add("hidden");
  tabs.innerHTML = "";
}

function bindPaneDom() {
  document.querySelectorAll(".agent-pane").forEach((el) => {
    const paneId = el.dataset.paneId;
    el.addEventListener("mousedown", () => setActivePane(paneId));
    const modelSel = el.querySelector("[data-ap-model]");
    modelSel?.addEventListener("change", () => {
      const pane = getPane(paneId);
      if (!pane) return;
      pane.model = modelSel.value || "";
      persistOpenPanes();
      const adv = $("studio-adv-model");
      if (adv) adv.value = pane.model;
      updateAutoHint(el);
    });
    const modeSel = el.querySelector("[data-ap-mode]");
    modeSel?.addEventListener("change", () => {
      const pane = getPane(paneId);
      const n = Number(modeSel.value) || 2;
      state.agentsN = n;
      state.mode = { 1: "light", 2: "standard", 3: "ultra", 4: "ultra" }[n] || "standard";
      if (pane) {
        pane.agentsN = n;
        persistOpenPanes();
      }
      if ($("studio-agents-n")) $("studio-agents-n").value = String(n);
      if ($("studio-mode")) $("studio-mode").value = state.mode;
      // refresh auto option label + hint
      if (modelSel && !modelSel.value) {
        const opt0 = modelSel.options[0];
        if (opt0 && opt0.value === "") opt0.textContent = `авто · ${autoModelsShortLabel()}`;
      }
      updateAutoHint(el);
    });
    updateAutoHint(el);
    el.querySelector("[data-ap-send]")?.addEventListener("click", () => sendPaneFollowUp(paneId));
    const ta = el.querySelector("[data-ap-input]");
    ta?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        sendPaneFollowUp(paneId);
      }
    });
  });
}

async function createChatForPane(paneId) {
  const pane = getPane(paneId);
  if (!pane) return;
  if (pane.running) {
    alert("Дождись окончания генерации");
    return;
  }
  await ensureStudioHome();
  pane.chatId = null;
  pane.title = "";
  state.chatId = null;
  state.chatTitle = "";
  persistStudioSelection();
  persistOpenPanes();
  setStatusStrip("Готов к задаче");
  showStudioWork("Новый чат");
  renderAllPanes();
  renderStudioRail();
}

function paneScrollEl(paneId) {
  return document.querySelector(`.agent-pane[data-pane-id="${paneId}"] [data-ap-scroll]`);
}

function isNearBottom(el) {
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight < 48;
}

function appendPaneBubble(paneId, { role, text, files }) {
  const scroll = paneScrollEl(paneId);
  if (!scroll || !text) return;
  const stick = isNearBottom(scroll);
  const empty = scroll.querySelector(".ap-empty");
  if (empty) empty.remove();
  const div = document.createElement("div");
  div.className = `ap-msg ${role === "user" ? "user" : role === "status" ? "status" : "assistant"}`;
  const who = role === "user" ? "Ты" : role === "status" ? "Статус" : "Студия";
  const filesHtml =
    files && files.length
      ? `<div class="ap-files">${files.map((f) => escapeHtml(f)).join(" · ")}</div>`
      : "";
  div.innerHTML = `<div class="ap-msg-role">${who}</div><div class="ap-msg-body">${escapeHtml(text)}</div>${filesHtml}`;
  scroll.appendChild(div);
  if (stick) scroll.scrollTop = scroll.scrollHeight;
}

function setPaneRunning(paneId, running, statusText) {
  const pane = getPane(paneId);
  if (pane) pane.running = !!running;
  const el = document.querySelector(`.agent-pane[data-pane-id="${paneId}"]`);
  if (!el) return;
  const st = el.querySelector("[data-ap-status]");
  if (st) {
    st.textContent = running ? statusText || "работает…" : "";
    st.classList.toggle("run", !!running);
  }
  const send = el.querySelector("[data-ap-send]");
  if (send) send.disabled = !!running;
  if (running) setStatusStrip(statusText || "Работаю…");
}

async function loadPaneHistory(paneId) {
  const pane = getPane(paneId);
  const scroll = paneScrollEl(paneId);
  if (!pane?.chatId || !scroll || !state.projectId) return;
  const msgs = await api(`/projects/${state.projectId}/chats/${pane.chatId}/messages`);
  if (!msgs.length) {
    scroll.innerHTML = `<div class="ap-empty">Чат пустой — напиши задачу внизу.</div>`;
    return;
  }
  scroll.innerHTML = msgs
    .map((m) => {
      const role = m.role === "user" ? "user" : "assistant";
      const who = role === "user" ? "Ты" : "Студия";
      return `<div class="ap-msg ${role}"><div class="ap-msg-role">${who}</div><div class="ap-msg-body">${escapeHtml(String(m.content || "").slice(0, 8000))}</div></div>`;
    })
    .join("");
  scroll.scrollTop = scroll.scrollHeight;
}

async function renderStudioRail() {
  const box = $("zc-rail-list");
  const foot = $("zc-rail-foot");
  if (!box) return;
  let chats = [];
  try {
    chats = await api("/projects/chats/recent");
    state.chatsCache = chats;
  } catch {
    chats = state.chatsCache || [];
  }
  if (!chats.length) {
    box.innerHTML = `<div class="zc-rail-empty">
      <p>Пока нет чатов</p>
      <button type="button" class="btn primary sm" id="btn-rail-empty-chat">Создать чат</button>
    </div>`;
    if (foot) foot.textContent = "";
    box.querySelector("#btn-rail-empty-chat")?.addEventListener("click", () => {
      $("btn-rail-new-chat")?.click();
    });
    return;
  }
  const byProj = {};
  for (const c of chats) {
    const pid = c.project_id;
    (byProj[pid] ||= []).push(c);
  }
  const projIds = Object.keys(byProj);
  box.innerHTML = projIds
    .map((pid) => {
      const list = byProj[pid];
      const pname =
        (state.projectsCache || []).find((p) => p.id === Number(pid))?.title ||
        (Number(pid) === state.projectId ? STUDIO_HOME_TITLE : `Папка #${pid}`);
      return `<div class="zc-rail-proj-row" data-proj-id="${pid}">
        <div class="zc-rail-proj" title="${escapeHtml(pname)}">${escapeHtml(pname)}</div>
        <button type="button" class="zc-rail-del" data-del-proj="${pid}" title="Удалить папку">×</button>
      </div>${list
        .map((c) => {
          const on = state.chatId === c.id;
          return `<div class="zc-rail-chat ${on ? "on" : ""}" data-cid="${c.id}">
            <button type="button" class="zc-rail-chat-btn" data-rail-open="${c.id}" data-pid="${c.project_id}" title="${escapeHtml(c.title || "")}">${escapeHtml(c.title || "Чат")}</button>
            <span class="zc-rail-chat-meta">${relativeTime(c.updated_at)}</span>
            <button type="button" class="zc-rail-del" data-del-chat="${c.id}" data-pid="${c.project_id}" title="Удалить чат">×</button>
          </div>`;
        })
        .join("")}`;
    })
    .join("");
  if (foot) foot.textContent = `${chats.length} чат(ов)`;

  box.querySelectorAll("[data-rail-open]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const pid = Number(btn.dataset.pid);
      const cid = Number(btn.dataset.railOpen);
      if (pid !== state.projectId) {
        await openProject(pid, false);
      }
      openChatInPane(cid, btn.title || btn.textContent, { newPane: false });
    });
  });

  box.querySelectorAll("[data-del-chat]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const pid = Number(btn.dataset.pid);
      const cid = Number(btn.dataset.delChat);
      if (!confirm("Удалить этот чат?")) return;
      try {
        await api(`/projects/${pid}/chats/${cid}`, { method: "DELETE" });
        if (state.chatId === cid) {
          state.chatId = null;
          state.chatTitle = "";
          state.openPanes = [];
          persistStudioSelection();
          showStudioWork("");
        }
        await loadProjects();
        await renderStudioRail();
      } catch (err) {
        alert(err.message || err);
      }
    });
  });

  box.querySelectorAll("[data-del-proj]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const pid = Number(btn.dataset.delProj);
      const title =
        (state.projectsCache || []).find((p) => p.id === pid)?.title || `папку #${pid}`;
      if (!confirm(`Удалить папку «${title}» и все её чаты?`)) return;
      try {
        await api(`/projects/${pid}`, { method: "DELETE" });
        if (state.projectId === pid) {
          state.projectId = null;
          state.chatId = null;
          state.chatTitle = "";
          state.openPanes = [];
          persistStudioSelection();
          await ensureStudioHome();
          showStudioWork("");
        }
        await loadProjects();
        await renderStudioRail();
      } catch (err) {
        alert(err.message || err);
      }
    });
  });
}

async function createStudioProjectFolder() {
  const title = (prompt("Название папки / проекта", "Новый проект") || "").trim();
  if (!title) return;
  const p = await api("/projects", { method: "POST", body: { title } });
  state.projectId = p.id;
  state.chatId = null;
  state.chatTitle = "";
  state.openPanes = [];
  persistStudioSelection();
  await loadProjects();
  showStudioWork("");
  renderStudioRail();
}

function leaveStudioToCabinet() {
  setTab("dash");
  try {
    history.replaceState(null, "", location.pathname);
  } catch {
    /* */
  }
}

function routePaneLiveEvent(paneId, ev) {
  const t = ev.type;
  if (t === "status" && ev.text) {
    appendPaneBubble(paneId, { role: "status", text: ev.text });
    setPaneRunning(paneId, true, ev.text.slice(0, 40));
    setStatusStrip(ev.text.slice(0, 80));
  } else if (t === "meta") {
    const team = (ev.team || []).map((r) => ROLE_LABEL[r] || r).join(", ");
    const line = `Команда: ${team} · ${ev.agents_n || "?"} сети`;
    appendPaneBubble(paneId, { role: "status", text: line });
    setStatusStrip(line);
  } else if (t === "agent_think" && ev.thinking) {
    const think = String(ev.thinking).replace(/\s+/g, " ").trim().slice(0, 140);
    appendPaneBubble(paneId, {
      role: "status",
      text: `${ROLE_LABEL[ev.role] || ev.role}: ${think || "думает…"}`,
    });
  } else if (t === "agent_done") {
    const files = (ev.files || []).map((f) => f.path || f).filter(Boolean);
    appendPaneBubble(paneId, {
      role: "status",
      text: `${ROLE_LABEL[ev.role] || ev.role}: ${ev.summary || "готово"}`,
      files: files.slice(0, 6),
    });
  } else if (t === "review_done" || t === "gate_done") {
    const line = `Проверка: ${ev.verdict || ev.gate || "—"} · score ${ev.score ?? "—"}`;
    appendPaneBubble(paneId, { role: "status", text: line });
    setStatusStrip(line);
  } else if (t === "synth_start") {
    appendPaneBubble(paneId, { role: "status", text: "Склеиваю ответы…" });
    setStatusStrip("Склеиваю ответы…");
  }
}

async function runStudioStream(body, opts = {}) {
  const paneId = opts.paneId || state.activePaneId;
  const projectId = opts.projectId || state.projectId;
  const chatId = opts.chatId || getPane(paneId)?.chatId || state.chatId;
  if (!projectId || !chatId) throw new Error("Нет проекта или чата");

  state._streamPaneId = paneId;
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const streamBase = resolveApiBase();
  const res = await fetch(
    `${streamBase}/projects/${projectId}/chats/${chatId}/complete/stream`,
    { method: "POST", headers, body: JSON.stringify(body) }
  );
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(formatErr(data.detail) || res.statusText);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let finalPayload = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      let ev;
      try {
        ev = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      if (ev.type === "error") throw new Error(ev.message || "Ошибка студии");
      if (ev.type === "final") {
        finalPayload = ev;
        continue;
      }
      if (ev.type === "file_changed") {
        mergeLiveArts(ev.files || []);
        if (state.projectId) loadFsTree(state.projectId);
        setAlgoNow("Файлы обновились — можно смотреть превью");
        refreshPreviewFrame().catch(() => {});
        continue;
      }
      if (paneId) routePaneLiveEvent(paneId, ev);
      handleStudioLiveEvent(ev);
      coopUpdate(ev);
    }
  }
  state._streamPaneId = null;
  if (!finalPayload) throw new Error("Стрим оборвался без результата");
  return finalPayload;
}

async function sendPaneFollowUp(paneId) {
  const pane = getPane(paneId);
  const el = document.querySelector(`.agent-pane[data-pane-id="${paneId}"]`);
  const ta = el?.querySelector("[data-ap-input]");
  const content = (ta?.value || "").trim();
  if (!content) return;
  if (pane?.running) return;
  setActivePane(paneId);
  if (!pane.chatId) {
    await ensureStudioHome();
    const title = content.slice(0, 48) + (content.length > 48 ? "…" : "");
    const c = await api(`/projects/${state.projectId}/chats`, {
      method: "POST",
      body: { title },
    });
    pane.chatId = c.id;
    pane.title = title;
    syncActiveChatFromPane(pane);
    persistOpenPanes();
    await loadProjects();
    // re-render so pane gets scroll history chrome, then inject user bubble
    renderAllPanes();
    appendPaneBubble(paneId, { role: "user", text: content });
    await runPaneStudio(paneId, content);
    return;
  }
  if (ta) ta.value = "";
  appendPaneBubble(paneId, { role: "user", text: content });
  await runPaneStudio(paneId, content);
}

async function runPaneStudio(paneId, content) {
  const pane = getPane(paneId);
  if (!pane?.chatId) throw new Error("Нет чата");
  syncActiveChatFromPane(pane);
  const modeEl = document.querySelector(`.agent-pane[data-pane-id="${paneId}"] [data-ap-mode]`);
  if (modeEl) {
    const n = Number(modeEl.value) || 2;
    state.agentsN = n;
    pane.agentsN = n;
    state.mode = { 1: "light", 2: "standard", 3: "ultra", 4: "ultra" }[n] || "standard";
  } else {
    syncAgentsFromAdv();
  }
  const n = state.agentsN || pane.agentsN || 2;
  pane.agentsN = n;
  state.mode = { 1: "light", 2: "standard", 3: "ultra", 4: "ultra" }[n] || state.mode || "standard";
  if ($("studio-mode")) $("studio-mode").value = state.mode;
  if ($("studio-agents-n")) $("studio-agents-n").value = String(n);
  const advModel =
    document.querySelector(`.agent-pane[data-pane-id="${paneId}"] [data-ap-model]`)?.value ||
    $("studio-adv-model")?.value ||
    pane.model ||
    "";
  if (advModel) pane.model = advModel;
  const body = {
    content,
    intent: state.intent || "feature",
    mode: state.mode,
    agents: n,
    run_kind: "team",
  };
  if (pane.model) body.model = pane.model;
  const pack =
    (state.teamModels && state.teamModels.length
      ? state.teamModels
      : [...state.selectedModels]) || [];
  if (pack.length) {
    body.team_models = pack.slice(0, 5);
    body.agents = Math.min(4, Math.max(body.agents || 2, Math.min(4, pack.length)));
  }
  setPaneRunning(paneId, true, "старт…");
  setStatusStrip("Стартую…");
  resetLiveSteps();
  try {
    let data;
    try {
      data = await runStudioStream(body, {
        paneId,
        projectId: state.projectId,
        chatId: pane.chatId,
      });
    } catch (e) {
      if (!/Chat not found|404/i.test(String(e.message || e))) throw e;
      await ensureStudioProject();
      pane.chatId = state.chatId;
      persistOpenPanes();
      data = await runStudioStream(body, {
        paneId,
        projectId: state.projectId,
        chatId: pane.chatId,
      });
    }
    const text =
      (data.message && data.message.content) ||
      data.assistant_text ||
      data.content ||
      data.reply ||
      "";
    if (text) appendPaneBubble(paneId, { role: "assistant", text: String(text).slice(0, 8000) });
    else appendPaneBubble(paneId, { role: "status", text: "Готово — смотри превью справа" });
    if (data.message?.content && pane.title && /Новый топик|Новый чат|Чат #/i.test(pane.title)) {
      pane.title = String(content).slice(0, 48) + (content.length > 48 ? "…" : "");
      const titleEl = document.querySelector(`.agent-pane[data-pane-id="${paneId}"] .ap-title`);
      if (titleEl) titleEl.textContent = pane.title;
      if ($("zc-work-title")) $("zc-work-title").textContent = pane.title;
      state.chatTitle = pane.title;
      persistOpenPanes();
    }
    try {
      showRunBilling(data);
    } catch {
      /* optional */
    }
    setLiveStep("show", "done");
    setAlgoNow("Готово", { done: true });
    setStatusStrip("Готово — смотри превью");
    $("preview-empty")?.classList.add("hidden");
    await refreshPreviewFrame().catch(() => {});
    await loadProjects();
    renderStudioRail();
    refreshMe().catch(() => {});
  } catch (e) {
    appendPaneBubble(paneId, { role: "status", text: "Ошибка: " + (e.message || e) });
    setStatusStrip("Ошибка: " + (e.message || e));
    throw e;
  } finally {
    setPaneRunning(paneId, false);
  }
}

function setAlgoNow(text, { done = false } = {}) {
  const el = $("zc-now-text");
  const box = $("zc-now");
  if (el) el.textContent = text;
  if (box) box.classList.toggle("done", !!done);
}

function pushTimeline(text, kind = "plan", role = "") {
  const box = $("zc-timeline");
  if (!box || !text) return;
  const row = document.createElement("div");
  row.className = `zc-tl-item ${kind}`;
  const roleHtml = role
    ? `<span class="zc-tl-role">${escapeHtml(ROLE_LABEL[role] || role)}</span>`
    : "";
  row.innerHTML = `${roleHtml}${escapeHtml(text)}`;
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
  // keep last ~40
  while (box.children.length > 40) box.removeChild(box.firstChild);
}

function handleStudioLiveEvent(ev) {
  const t = ev.type;
  if (t === "meta") {
    state._coopTeam = ev.team || [];
    setLiveStep("understand", "active");
    setAlgoNow("Понял задачу — дроблю на волны для нейросетей");
    const models = ev.models || {};
    const modelHint = models.code
      ? ` · code ${models.code}${models.judge ? " · judge " + models.judge : ""}`
      : "";
    pushTimeline(
      `Команда: ${(ev.team || []).map((r) => ROLE_LABEL[r] || r).join(", ")} · ${ev.agents_n || "?"} сети${modelHint}`,
      "plan"
    );
    if (ev.pipeline) pushTimeline(`пайплайн: ${ev.pipeline}`, "plan");
    (ev.plan || []).forEach((p) => pushTimeline(p, "plan"));
    setLiveStep("understand", "done");
    setLiveStep("build", "active");
    return;
  }
  if (t === "status") {
    const phase = ev.phase || "plan";
    setAlgoNow(ev.text || "…");
    pushTimeline(ev.text || "", phase, ev.role || "");
    if (phase === "think" || phase === "build") setLiveStep("build", "active");
    if (phase === "check") setLiveStep("check", "active");
    if (phase === "synth") setLiveStep("check", "active");
    return;
  }
  if (t === "wave_start") {
    const roles = (ev.roles || []).map((r) => ROLE_LABEL[r] || r).join(" + ");
    setAlgoNow(`Волна ${(ev.wave ?? 0) + 1}: ${roles}`);
    pushTimeline(`Старт волны: ${roles}`, "build");
    setLiveStep("build", "active");
    return;
  }
  if (t === "agent_start") {
    setAlgoNow(`${ROLE_LABEL[ev.role] || ev.role} подключается (${ev.model || "модель"})`);
    pushTimeline(`старт · ${ev.model || ""}`, "build", ev.role);
    return;
  }
  if (t === "agent_think") {
    const think = String(ev.thinking || "").replace(/\s+/g, " ").trim().slice(0, 160);
    setAlgoNow(`${ROLE_LABEL[ev.role] || ev.role} думает: ${think || "…"}`);
    pushTimeline(think || "думает…", "think", ev.role);
    setLiveStep("build", "active");
    return;
  }
  if (t === "agent_done") {
    const summary = ev.summary || "готово";
    const files = (ev.files || []).map((f) => (f.path || "").split("/").pop()).filter(Boolean);
    setAlgoNow(`${ROLE_LABEL[ev.role] || ev.role}: ${summary}`);
    pushTimeline(summary, "build", ev.role);
    if (files.length) pushTimeline(`файлы: ${files.join(", ")}`, "build", ev.role);
    if (ev.thinking_short) pushTimeline(ev.thinking_short, "think", ev.role);
    return;
  }
  if (t === "wave_done") {
    pushTimeline(
      `Волна ${(ev.wave ?? 0) + 1} закрыта · артефактов: ${ev.artifacts_n ?? "—"}`,
      "build"
    );
    return;
  }
  if (t === "brief_expand") {
    const title = ev.title || "Бриф";
    setAlgoNow(`Распаковка: ${title}`);
    pushTimeline(
      `оркестратор: ${title} · допущений ${(ev.assumptions || []).length} · вопросов ${(ev.questions || []).length}`,
      "plan"
    );
    const qs = (ev.questions || []).slice(0, 3);
    qs.forEach((q) => pushTimeline(`уточнение: ${q}`, "plan"));
    return;
  }
  if (t === "contract_lock") {
    const c = ev.contract || {};
    const paths = (c.paths || []).slice(0, 4).join(", ") || "fields";
    const src = ev.source || c.source || "";
    setAlgoNow(
      src === "task_prelock" || src === "brief_expand"
        ? `Pre-lock: ${paths}`
        : `Контракт API: ${paths}`
    );
    pushTimeline(
      src === "task_prelock" || src === "brief_expand"
        ? `pre-lock: ${paths}`
        : `контракт: ${paths}${c.auth_required ? " · auth" : ""}`,
      "build"
    );
    renderContractPanel(ev);
    return;
  }
  if (t === "synth_start") {
    setLiveStep("check", "active");
    setAlgoNow("Склеиваю ответы всех нейросетей…");
    pushTimeline("сборка ответа", "check");
    return;
  }
  if (t === "synth_done") {
    setAlgoNow("Сборка готова — проверяю качество");
    pushTimeline("сборка готова", "check");
    return;
  }
  if (t === "gate_done") {
    setLiveStep("check", "active");
    setAlgoNow(`Автопроверка: ${ev.gate || "—"} · оценка ${ev.score ?? "—"}`);
    pushTimeline(
      `гейт ${ev.gate || "—"} · score ${ev.score ?? "—"} · находок ${ev.findings_n ?? 0}`,
      "check"
    );
    renderGatePanel(ev);
    return;
  }
  if (t === "review_start") {
    setAlgoNow(ev.llm ? "Ревьюер ищет баги и AI-look…" : "Только автогейт…");
    pushTimeline("ревью стартовало", "check");
    return;
  }
  if (t === "review_done") {
    setLiveStep("check", "done");
    setLiveStep("show", "active");
    const v = (ev.verdict || ev.gate || "").toUpperCase();
    const label =
      v === "FAIL" ? "нашёл проблемы" : v === "PASS_WITH_RISKS" ? "ок, но с рисками" : "всё ок";
    setAlgoNow(`Проверка: ${label}`);
    pushTimeline(`проверка: ${label} · score ${ev.score ?? "—"}`, "check");
    return;
  }
}

function setLiveStep(step, status) {
  const items = document.querySelectorAll("#zc-live-steps li");
  items.forEach((li) => {
    if (li.dataset.step !== step) return;
    li.classList.remove("pending", "active", "done");
    li.classList.add(status === "active" ? "active" : status === "done" ? "done" : "pending");
  });
  if (status === "active") {
    const order = ["understand", "build", "check", "show"];
    const idx = order.indexOf(step);
    items.forEach((li) => {
      const i = order.indexOf(li.dataset.step);
      if (i >= 0 && i < idx) {
        li.classList.remove("pending", "active");
        li.classList.add("done");
      }
    });
  }
}

function resetLiveSteps() {
  document.querySelectorAll("#zc-live-steps li").forEach((li) => {
    li.classList.remove("active", "done");
    li.classList.add("pending");
  });
  setLiveStep("understand", "active");
  setAlgoNow("Стартую…");
  const tl = $("zc-timeline");
  if (tl) tl.innerHTML = "";
  const log = $("studio-log");
  if (log) log.textContent = "";
  resetLiveWork();
  const board = $("coop-board");
  if (board) board.classList.add("hidden");
}

function appendStudioLog(line) {
  const log = $("studio-log");
  if (!log) return;
  log.textContent += (log.textContent ? "\n" : "") + line;
  log.scrollTop = log.scrollHeight;
}

function showStudioWork(_title) {
  $("zc-home")?.classList.add("hidden");
  $("zc-work")?.classList.remove("hidden");
  ensureDefaultPanes();
  if (state.openPanes.length > 1) state.openPanes = state.openPanes.slice(0, 1);
  persistOpenPanes();
  renderAllPanes();
}

function showStudioHome() {
  showStudioWork("");
}

async function enterStudioShell() {
  try {
    await ensureStudioHome();
    await loadProjects();
    try {
      await loadModelsCatalog();
    } catch {
      /* models optional for UI */
    }
    // Always open blank prompt — no chat list / old titles
    state.chatId = null;
    state.chatTitle = "";
    state.openPanes = [];
    persistStudioSelection();
    localStorage.removeItem(panesStorageKey());
    showStudioWork("");
  } catch (e) {
    console.error(e);
    state.chatId = null;
    state.openPanes = [];
    showStudioWork("");
  }
}

function setAdvOpen(open) {
  $("zc-adv")?.classList.toggle("hidden", !open);
}

const AGENT_HINTS = {
  1: "1 нейросеть: быстро и дёшево. Подходит для простых правок.",
  2: "2 нейросети: одна пишет, вторая проверяет. Обычно хватает.",
  3: "3 нейросети: сильнее спорят и чинят. Для сложных экранов.",
  4: "4 нейросети: как команда. Дольше и дороже, но мощнее.",
};

async function ensureStudioProject() {
  // Reuse current chat only if it really exists under current project.
  // Stale localStorage (project/chat mismatch) was causing "Chat not found".
  if (state.projectId && state.chatId) {
    try {
      await api(`/projects/${state.projectId}/chats/${state.chatId}/messages`);
      persistStudioSelection();
      return;
    } catch {
      state.chatId = null;
      try {
        await api(`/projects/${state.projectId}`);
      } catch {
        state.projectId = null;
      }
      persistStudioSelection();
    }
  }

  if (!state.projectId) {
    await ensureStudioHome();
  }

  const full = await api(`/projects/${state.projectId}`);
  const chats = full.chats || [];
  const reusable =
    chats.find((c) => !["Основной чат", "Чат", "Новый топик"].includes(c.title)) ||
    chats[0];
  if (reusable) {
    state.chatId = reusable.id;
    state.chatTitle = reusable.title;
    persistStudioSelection();
    await loadProjects();
    return;
  }
  const c = await api(`/projects/${state.projectId}/chats`, {
    method: "POST",
    body: { title: "Новый топик" },
  });
  state.chatId = c.id;
  state.chatTitle = c.title;
  persistStudioSelection();
  await loadProjects();
}

async function ensureStudioHome() {
  const list = await api("/projects");
  state.projectsCache = list;
  let home = list.find((p) => p.title === STUDIO_HOME_TITLE);
  if (!home) {
    home = list.find((p) => {
      const t = (p.title || "").toLowerCase();
      return !t.startsWith("trap-") && !t.startsWith("glue-") && !t.startsWith("skill-");
    });
  }
  if (!home) {
    home = await api("/projects", { method: "POST", body: { title: STUDIO_HOME_TITLE } });
  }
  state.projectId = home.id;
  persistStudioSelection();
  return home;
}

async function startNewStudioChat() {
  const home = await ensureStudioHome();
  const c = await api(`/projects/${home.id}/chats`, {
    method: "POST",
    body: { title: "Новый топик" },
  });
  state.projectId = home.id;
  state.chatId = c.id;
  state.chatTitle = c.title;
  persistStudioSelection();
  openChatInPane(c.id, c.title, { newPane: false });
  await loadProjects();
}

async function runBeginnerStudio(content) {
  await ensureStudioProject();
  ensureDefaultPanes();
  let pane = getActivePane() || state.openPanes[0];
  if (!pane) {
    ensureDefaultPanes();
    pane = state.openPanes[0];
  }
  pane.chatId = state.chatId;
  pane.title = content.slice(0, 48) + (content.length > 48 ? "…" : "");
  pane.agentsN = state.agentsN || pane.agentsN || 2;
  state.activePaneId = pane.id;
  state.chatTitle = pane.title;
  persistOpenPanes();
  showStudioWork(pane.title);
  appendPaneBubble(pane.id, { role: "user", text: content });
  try {
    await runPaneStudio(pane.id, content);
  } catch (e) {
    const msg = String(e.message || e);
    if (/chat not found|project not found/i.test(msg)) {
      state.chatId = null;
      persistStudioSelection();
      await ensureStudioProject();
      pane.chatId = state.chatId;
      persistOpenPanes();
      await runPaneStudio(pane.id, content);
    } else {
      throw e;
    }
  }
  return null;
}

async function refreshPreviewFrame() {
  if (!state.projectId) return;
  try {
    const info = await api(`/projects/${state.projectId}/preview/start`, { method: "POST", body: {} });
    state.previewRunning = true;
    const entry = info.entry || "";
    const url = `${info.url}${entry}`;
    if ($("preview-url")) $("preview-url").value = url;
    // Cookie so iframe can load CSS/JS relative to the page (srcdoc breaks assets)
    setAuthCookie();
    const iframe = $("studio-preview");
    if (iframe) {
      iframe.removeAttribute("srcdoc");
      iframe.src = url;
    }
    $("preview-empty")?.classList.add("hidden");
  } catch (e) {
    appendStudioLog("Превью: " + e.message);
  }
}

async function loadStudioMeta() {
  if (state.studioMeta) {
    renderIntentChips();
    renderModeRow();
    return state.studioMeta;
  }
  try {
    state.studioMeta = await api("/projects/meta/studio");
  } catch {
    state.studioMeta = {
      intents: [
        { id: "feature", title: "Фича", hint: "собрать кусок" },
        { id: "bug", title: "Баг", hint: "починить" },
        { id: "ui", title: "UI", hint: "экран" },
        { id: "api", title: "API", hint: "эндпоинты" },
        { id: "tests", title: "Тесты", hint: "покрытие" },
        { id: "refactor", title: "Рефактор", hint: "упростить" },
        { id: "ask", title: "Спросить", hint: "ответ" },
      ],
      modes: [
        { id: "light", title: "Лайт", hint: "дёшево" },
        { id: "standard", title: "Стандарт", hint: "повседневка" },
        { id: "ultra", title: "Ultra", hint: "команда" },
        { id: "premium", title: "Premium", hint: "макс" },
      ],
      teams: {
        feature: ["design", "frontend", "backend", "tests"],
        bug: ["backend", "frontend", "tests"],
        ui: ["design", "frontend"],
        api: ["backend", "tests"],
        tests: ["tests", "backend"],
        refactor: ["backend", "frontend", "tests"],
        ask: ["general"],
      },
    };
  }
  renderIntentChips();
  renderModeRow();
  setAgents("");
  return state.studioMeta;
}

function renderIntentChips() {
  const box = $("intent-chips");
  if (!box || !state.studioMeta) return;
  box.innerHTML = state.studioMeta.intents
    .map(
      (i) => `
    <button type="button" class="chip ${state.intent === i.id ? "on" : ""}" data-intent="${i.id}" title="${i.hint || ""}">
      ${i.title}
    </button>`
    )
    .join("");
  box.querySelectorAll("[data-intent]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.intent = btn.dataset.intent;
      renderIntentChips();
      setAgents("");
    });
  });
}

function renderModeRow() {
  const box = $("mode-row");
  if (!box || !state.studioMeta) return;
  const extra = {
    light: "1 нейросеть",
    standard: "2 нейросети",
    ultra: "4 + сборка",
    premium: "4 топ + сборка",
  };
  box.innerHTML = state.studioMeta.modes
    .map(
      (m) => `
    <button type="button" class="mode-btn ${state.mode === m.id ? "on" : ""}" data-mode="${m.id}">
      <span class="mode-t">${m.title}</span>
      <span class="mode-h">${extra[m.id] || m.hint || ""}</span>
    </button>`
    )
    .join("");
  box.querySelectorAll("[data-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.mode = btn.dataset.mode;
      renderModeRow();
      setAgents("");
      updateChatSub();
    });
  });
}

async function loadModelsCatalog() {
  const data = await api("/v1/models");
  state.models = data.data || [];
  if (data.model_family) state.modelFamily = data.model_family;
  fillModelSelect();
  fillProviderFilter();
  defaultPickModels();
  const pick =
    state.models.find((m) => m.id === "gemini-2.5-flash" && m.ready) ||
    state.models.find((m) => m.ready && (m.modality || "chat") === "chat" && !String(m.id).startsWith("studio-"));
  if (pick && $("dash-model-id")) $("dash-model-id").textContent = pick.id;
  syncBaseUrlFields();
  return state.models;
}

function fillProviderFilter() {
  const sel = $("models-provider");
  if (!sel) return;
  const cur = sel.value;
  const providers = [...new Set(state.models.map((m) => m.provider).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, "ru")
  );
  sel.innerHTML =
    `<option value="">все компании</option>` +
    providers.map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join("");
  if ([...sel.options].some((o) => o.value === cur)) sel.value = cur;
}

function fillModelSelect() {
  const targets = ["model", "studio-solo-model"].map((id) => $(id)).filter(Boolean);
  if (!targets.length) return;
  const chat = state.models.filter(
    (m) =>
      (m.modality || "chat") === "chat" &&
      !String(m.id).startsWith("studio-") &&
      m.id !== "ultra-mode"
  );
  const ready = chat.filter((m) => m.ready);
  const soon = chat.filter((m) => !m.ready);
  targets.forEach((sel) => {
    const cur = sel.value;
    sel.innerHTML = "";
    const auto = document.createElement("option");
    auto.value = "";
    auto.textContent = "авто — команда по режиму";
    sel.appendChild(auto);
    const ogReady = document.createElement("optgroup");
    ogReady.label = `Доступно сейчас (${ready.length})`;
    ready.forEach((m) => {
      const o = document.createElement("option");
      o.value = m.id;
      o.textContent = m.title;
      ogReady.appendChild(o);
    });
    sel.appendChild(ogReady);
    if (soon.length) {
      const ogSoon = document.createElement("optgroup");
      ogSoon.label = `В каталоге · скоро (${soon.length})`;
      soon.forEach((m) => {
        const o = document.createElement("option");
        o.value = m.id;
        o.textContent = `${m.title} · скоро`;
        o.disabled = true;
        ogSoon.appendChild(o);
      });
      sel.appendChild(ogSoon);
    }
    if ([...sel.options].some((o) => o.value === cur && !o.disabled)) sel.value = cur;
  });
}

function catalogChatModels() {
  return state.models.filter((m) => {
    const mod = m.modality || "chat";
    if (mod !== "chat") return false;
    if (m.family === "studio" || m.family === "ultra") return false;
    if (String(m.id).startsWith("studio-") || m.id === "ultra-mode") return false;
    return true;
  });
}

function renderModels() {
  const q = ($("models-q")?.value || "").trim().toLowerCase();
  const sort = $("models-sort")?.value || "cheap";
  let rows = catalogChatModels().filter((m) => m.ready);
  if (q) {
    rows = rows.filter(
      (m) =>
        m.id.toLowerCase().includes(q) ||
        m.title.toLowerCase().includes(q) ||
        m.provider.toLowerCase().includes(q) ||
        (m.description || "").toLowerCase().includes(q)
    );
  }
  rows.sort((a, b) => {
    const da = estimateDialogRub(a);
    const db = estimateDialogRub(b);
    return sort === "expensive" ? db - da : da - db;
  });
  // убрать из набора всё, чего больше нет в каталоге чата
  let pruned = false;
  [...state.selectedModels].forEach((id) => {
    if (!catalogChatModels().some((m) => m.id === id)) {
      state.selectedModels.delete(id);
      pruned = true;
    }
  });
  if (pruned) persistSelectedModels();

  const box = $("models-grid");
  if (!box) return;
  if (!catalogChatModels().length) {
    box.innerHTML = `<div class="empty-state"><div class="empty-t">Каталог пуст</div><div class="empty-d">Нажми «↻ обновить».</div></div>`;
    return;
  }
  if (!rows.length) {
    box.innerHTML = `<div class="empty-state"><div class="empty-t">Ничего не найдено</div><div class="empty-d">Попробуй другой поиск.</div></div>`;
    return;
  }

  const cardHtml = (m) => {
    const badge = `<span class="m-badge ready">доступно</span>`;
    const prices = `<div class="m-price">вход ${fmtRub(m.pricing?.input_per_1m || 0, 2)} ₽/1M</div>
         <div class="m-price">выход ${fmtRub(m.pricing?.output_per_1m || 0, 2)} ₽/1M</div>`;
    const picked = state.selectedModels.has(m.id);
    const btnLabel = picked ? "✓ выбрано" : "выбрать";
    return `
      <div class="model-card ${picked ? "picked" : ""}" data-mid="${m.id}">
        <div class="m-top">
          <label class="m-pick-wrap">
            <input type="checkbox" class="m-pick" ${picked ? "checked" : ""} data-pick="${escapeHtml(m.id)}" />
            <span class="m-pick-label">выбрать</span>
          </label>
          ${badge}
        </div>
        <div class="m-title">${escapeHtml(m.title)}</div>
        <div class="m-id">${escapeHtml(m.id)}</div>
        <div class="m-prices">${prices}</div>
        <div class="m-actions">
          <button type="button" class="btn ghost sm m-copy-id" data-copy-text="${escapeHtml(m.id)}" title="Скопировать Model ID">ID</button>
          <button type="button" class="btn btn-s m-use" data-use="${escapeHtml(m.id)}" data-studio="0">
            ${btnLabel}
          </button>
        </div>
      </div>`;
  };

  box.innerHTML = `<div class="models-grid">${rows.map(cardHtml).join("")}</div>`;

  box.querySelectorAll("[data-use]").forEach((btn) => {
    btn.addEventListener("click", () => {
      toggleModelPick(btn.dataset.use);
      renderModels();
    });
  });
  box.querySelectorAll("[data-pick]").forEach((cb) => {
    cb.addEventListener("change", (e) => {
      e.stopPropagation();
      toggleModelPick(cb.dataset.pick);
      renderModels();
    });
  });
  bindCopyButtons(box);
  persistSelectedModels();
}

async function refreshSummary() {
  const s = await api("/billing/dashboard");
  const balNum = Number(s.balance_rub || 0);
  const kieNum = s.credits != null ? Number(s.credits) : (s.kie_credits != null ? Number(s.kie_credits) : balNum);
  // Live balance (₽)
  const bal = fmtRub(kieNum);
  $("bal").textContent = bal;
  if ($("side-bal")) $("side-bal").textContent = bal;
  if ($("nav-bal")) $("nav-bal").textContent = bal;
  $("spent").textContent = fmtRub(s.spent_rub);
  $("req-n").textContent = String(s.requests);
  if ($("spent-today")) $("spent-today").textContent = fmtRub(s.limits?.spent_today_rub ?? 0);
  if ($("spent-week")) {
    const week = (s.spend_chart || []).reduce((sum, d) => sum + Number(d.spent_rub || 0), 0);
    $("spent-week").textContent = fmtRub(week);
  }
  if ($("daily-limit")) $("daily-limit").textContent = fmtRub(s.limits?.daily_soft_rub ?? 300, 0);
  if ($("month-spent")) {
    const mSpent = s.limits?.month_spent_rub ?? 0;
    const mBud = s.limits?.monthly_budget_rub ?? 0;
    $("month-spent").textContent = mBud > 0 ? `${fmtRub(mSpent, 0)} / ${fmtRub(mBud, 0)}` : fmtRub(mSpent, 0);
  }
  if ($("proj-n")) $("proj-n").textContent = String(s.projects);
  if ($("keys-n")) $("keys-n").textContent = String(s.api_keys);
  if ($("models-ready")) $("models-ready").textContent = String(s.models_ready ?? "—");
  if ($("models-total")) $("models-total").textContent = String(s.models_total ?? "—");
  syncBaseUrlFields();
  updatePolzaSteps(s);
  renderDashAlerts(s.alerts || {});
  renderDashBoard(s);
}

function renderDashAlerts(a) {
  const box = $("dash-alerts");
  if (!box) return;
  const notes = [];
  if (a.low_balance_triggered) {
    notes.push(
      `Баланс ниже ${fmtRub(a.low_balance_threshold_rub, 0)} — пополни счёт, чтобы IDE не остановилась.`
    );
  }
  if (a.monthly_budget_triggered) {
    notes.push(
      `Мягкий месячный бюджет ${fmtRub(a.monthly_budget_rub, 0)} исчерпан (потрачено ${fmtRub(a.month_spent_rub, 0)}). Запросы пока идут.`
    );
  } else if (a.monthly_budget_warning) {
    notes.push(
      `Уже ${fmtRub(a.month_spent_rub, 0)} из месячного бюджета ${fmtRub(a.monthly_budget_rub, 0)}.`
    );
  }
  if (!notes.length) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  box.innerHTML = notes.map((n) => `<div class="dash-alert">${n}</div>`).join("");
}

function shortDay(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(5, 10);
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}

function shortTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderDashBoard(s) {
  const projBox = $("dash-projects");
  const modelBox = $("dash-models");
  const histBox = $("dash-history");
  const chartBox = $("dash-chart");
  if (!projBox || !modelBox || !histBox || !chartBox) return;

  const projects = s.projects_active || [];
  projBox.innerHTML = projects.length
    ? projects
        .map(
          (p) => `
      <div class="kcard" data-goto="projects" data-open-project="${p.id}">
        <div class="kcard-t">${escapeHtml(p.title)}</div>
        <div class="kcard-m">${p.chats_count} ${plural(p.chats_count, "чат", "чата", "чатов")} · ${shortTime(p.updated_at)}</div>
      </div>`
        )
        .join("")
    : `<div class="kempty">Пока нет проектов.<br/>Открой студию и создай первый.</div>`;

  const models = s.models_used || [];
  if (models.length) {
    modelBox.innerHTML = models
      .map(
        (m) => `
      <div class="kcard" data-goto="models">
        <div class="kcard-t">${escapeHtml(m.model)}</div>
        <div class="kcard-m">${m.calls} ${plural(m.calls, "вызов", "вызова", "вызовов")} · <span class="hi">${fmtRub(m.spent_rub, 2)}</span></div>
      </div>`
      )
      .join("");
  } else {
    const ready = state.models
      .filter((m) => m.ready && (m.modality || "chat") === "chat" && !String(m.id).startsWith("studio-"))
      .slice(0, 6);
    modelBox.innerHTML = ready.length
      ? ready
          .map(
            (m) => `
      <div class="kcard" data-goto="models">
        <div class="kcard-t">${escapeHtml(m.title)}</div>
        <div class="kcard-m">вход ${fmtRub(m.pricing?.input_per_1m || 0, 2)} · выход ${fmtRub(m.pricing?.output_per_1m || 0, 2)} ₽/1M</div>
      </div>`
          )
          .join("") +
        `<div class="empty-mini">Всего в каталоге ${state.models.length} · открой «модели»</div>`
      : `<div class="kempty">Каталог: ${state.models.length || 0} моделей.<br/>Открой вкладку «модели».</div>`;
  }

  const recent = s.recent || [];
  histBox.innerHTML = recent.length
    ? recent
        .map(
          (r) => `
      <div class="kcard" data-goto="usage">
        <div class="kcard-t">${escapeHtml(r.model)}</div>
        <div class="kcard-m"><span class="hi">${fmtRub(r.cost_user_rub, 4)}</span> · ${MODE_RU[r.mode] || r.mode} · ${shortTime(r.created_at)}</div>
      </div>`
        )
        .join("")
    : `<div class="kempty">История пустая.</div>`;

  const chart = s.spend_chart || [];
  const max = Math.max(...chart.map((c) => c.spent_rub), 0.01);
  chartBox.innerHTML = chart
    .map((c) => {
      const h = Math.max(3, Math.round((c.spent_rub / max) * 100));
      return `
      <div class="chart-bar" title="${fmtRub(c.spent_rub, 2)}">
        <div class="chart-val">${c.spent_rub > 0 ? fmtRub(c.spent_rub, 0) : ""}</div>
        <div class="chart-fill" style="height:${h}%"></div>
        <div class="chart-label">${shortDay(c.day)}</div>
      </div>`;
    })
    .join("");
}

async function refreshMe() {
  const me = await api("/auth/me");
  state.modelFamily = me.model_family || "";
  if (me.fusion_pref) {
    state.fusionPref = me.fusion_pref;
    localStorage.setItem("zeus_fusion_pref", me.fusion_pref);
  }
  if (Array.isArray(me.fusion_models) && me.fusion_models.length) {
    state.selectedModels = new Set(me.fusion_models);
    persistSelectedModels();
  }
  await loadModelsCatalog();
  await refreshSummary();
  await ensureApiKey().catch(() => {});
  renderMySetup();
}

async function refreshKeys() {
  await ensureApiKey().catch(() => {});
  const keys = await api("/keys");
  const box = $("keys-list");
  if (!keys.length) {
    box.innerHTML = `
      <div class="empty-state keys-empty">
        <div class="empty-t">Ключа пока нет</div>
        <div class="empty-d">Нажми кнопку — ключ появится сразу на экране.</div>
        <button type="button" class="btn btn-p" id="btn-empty-key">создать ключ</button>
      </div>`;
    $("btn-empty-key")?.addEventListener("click", () => {
      createVisibleKey().catch((e) => alert(e.message || String(e)));
    });
    return;
  }
  box.innerHTML = keys
    .map((k) => {
      const budget = Number(k.budget_rub || 0);
      const spent = Number(k.spent_rub || 0);
      const lim =
        budget > 0
          ? `${fmtRub(spent, 2)} / ${fmtRub(budget, 0)}`
          : `${fmtRub(spent, 2)} · без лимита`;
      const pct = budget > 0 ? Math.min(100, Math.round((spent / budget) * 100)) : 0;
      const bar =
        budget > 0
          ? `<div class="key-bar"><div class="key-bar-fill" style="width:${pct}%"></div></div>`
          : "";
      const name = k.name === "default" ? "Основной ключ" : k.name;
      return `
    <div class="list-item key-item" style="cursor:default">
      <div class="key-main">
        <div class="t">${escapeHtml(name)}</div>
        <div class="m">${k.key_prefix}… · ${shortTime(k.created_at)}</div>
        <div class="key-spend">${lim}</div>
        ${bar}
      </div>
      <div class="key-actions">
        <button class="btn btn-s" data-budget="${k.id}" data-cur="${budget}">лимит</button>
        <button class="btn btn-s" data-revoke="${k.id}">отозвать</button>
      </div>
    </div>`;
    })
    .join("");
  box.querySelectorAll("[data-revoke]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Отозвать этот ключ? IDE перестанет работать с ним.")) return;
      await api(`/keys/${btn.dataset.revoke}`, { method: "DELETE" });
      refreshKeys();
      refreshSummary();
    });
  });
  box.querySelectorAll("[data-budget]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const cur = Number(btn.dataset.cur || 0);
      const raw = prompt("Лимит ключа в ₽ (0 = без лимита)", String(cur));
      if (raw === null) return;
      const budget_rub = Math.max(0, Number(raw) || 0);
      await api(`/keys/${btn.dataset.budget}`, {
        method: "PATCH",
        body: { budget_rub },
      });
      refreshKeys();
    });
  });
}

async function loadBillingSettings() {
  try {
    const s = await api("/billing/settings");
    if ($("alert-on")) $("alert-on").checked = !!s.low_balance_alert;
    if ($("alert-threshold")) $("alert-threshold").value = s.low_balance_threshold_rub ?? 50;
    if ($("month-budget")) $("month-budget").value = s.monthly_budget_rub ?? 0;
    if ($("alerts-note")) $("alerts-note").textContent = s.email_note || "";
  } catch {
    /* ignore */
  }
}

async function loadProjects() {
  const box = $("projects-list");
  let chats = [];
  try {
    chats = await api("/projects/chats/recent");
  } catch {
    // fallback: flatten from projects
    const list = await api("/projects");
    state.projectsCache = list;
    for (const p of list) {
      const t = (p.title || "").toLowerCase();
      if (t.startsWith("trap-") || t.startsWith("glue-")) continue;
      try {
        const full = await api(`/projects/${p.id}`);
        for (const c of full.chats || []) {
          chats.push({
            id: c.id,
            title: c.title,
            project_id: p.id,
            updated_at: c.updated_at || c.created_at,
          });
        }
      } catch {
        /* */
      }
    }
  }
  try {
    const list = await api("/projects");
    state.projectsCache = list;
  } catch {
    /* */
  }
  state.chatsCache = chats;
  // home list
  if (box) {
  if (!chats.length) {
    box.innerHTML = `<div class="cs-empty-tree">Пока нет чатов.<br/>Напиши задачу и жми «Сделать» — появится топик.</div>`;
  } else {
  box.innerHTML = chats
    .map(
      (c) => `
    <div class="zc-chat-row ${state.chatId === c.id ? "on" : ""}" data-cid="${c.id}" data-pid="${c.project_id}">
      <button type="button" class="zc-chat-btn" data-open-chat="${c.id}" data-pid="${c.project_id}">
        <span class="zc-chat-title">${escapeHtml(c.title || "Чат")}</span>
      </button>
      <button type="button" class="cs-icon-btn sm danger" data-del-chat="${c.id}" data-pid="${c.project_id}" title="Удалить чат">×</button>
    </div>`
    )
    .join("");

  box.querySelectorAll("[data-open-chat]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const pid = Number(btn.dataset.pid);
      const cid = Number(btn.dataset.openChat);
      await openProject(pid, false);
      await openChat(cid);
      await loadProjects();
    });
  });
  box.querySelectorAll("[data-del-chat]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Удалить этот чат?")) return;
      const pid = Number(btn.dataset.pid);
      const cid = Number(btn.dataset.delChat);
      await api(`/projects/${pid}/chats/${cid}`, { method: "DELETE" });
      if (state.chatId === cid) {
        state.chatId = null;
        state.chatTitle = "";
        persistStudioSelection();
        showStudioHome();
      }
      state.openPanes.forEach((p) => {
        if (p.chatId === cid) {
          p.chatId = null;
          p.title = "";
        }
      });
      persistOpenPanes();
      await loadProjects();
    });
  });
  }
  }
  renderStudioRail();
}

async function createChatInProject(projectId) {
  state.projectId = projectId;
  const title = prompt("Название чата", "Новый чат") || "Новый чат";
  const c = await api(`/projects/${projectId}/chats`, {
    method: "POST",
    body: { title },
  });
  await openProject(projectId, false);
  await openChat(c.id);
  await loadProjects();
}

async function openProject(id, autoOpenChat = true) {
  state.projectId = id;
  persistStudioSelection();
  const p = await api(`/projects/${id}`);
  state.projectBrief = p.brief || "";
  if ($("project-brief")) $("project-brief").value = state.projectBrief;
  $("brief-wrap")?.classList.remove("hidden");
  await loadFsTree(id);
  await refreshGitStatus();
  await refreshGithubStatus();
  await loadProjects();
  if (autoOpenChat) {
    if (p.chats && p.chats.length) {
      const keep = p.chats.find((c) => c.id === state.chatId);
      await openChat((keep || p.chats[0]).id);
    } else {
      state.chatId = null;
      persistStudioSelection();
      $("play-empty")?.classList.remove("hidden");
      $("play-active")?.classList.add("hidden");
    }
  }
}

async function loadArtifactTree(projectId) {
  // legacy name — now loads real workspace FS tree
  await loadFsTree(projectId);
}

async function loadFsTree(projectId) {
  const box = $("fs-tree");
  if (!box || !projectId) return;
  try {
    const data = await api(`/projects/${projectId}/fs/tree`);
    const files = data.files || [];
    if (!files.length) {
      box.innerHTML = `<div class="cs-empty-tree">Пока пусто — напиши задачу справа, появятся файлы</div>`;
      return;
    }
    box.innerHTML = files
      .map(
        (f) =>
          `<button type="button" class="cs-fs-file ${state.openFile === f.path ? "on" : ""}" data-path="${escapeHtml(f.path)}" title="${escapeHtml(f.path)}">${escapeHtml(f.path)}</button>`
      )
      .join("");
    box.querySelectorAll("[data-path]").forEach((btn) => {
      btn.onclick = () => openWorkspaceFile(btn.dataset.path);
    });
  } catch {
    box.innerHTML = `<div class="cs-empty-tree">Не удалось загрузить</div>`;
  }
}

async function openWorkspaceFile(path) {
  if (!state.projectId || !path) return;
  try {
    const data = await api(`/projects/${state.projectId}/fs/file?path=${encodeURIComponent(path)}`);
    state.openFile = data.path;
    if ($("open-file-path")) $("open-file-path").textContent = data.path;
    if ($("code-editor")) $("code-editor").value = data.binary ? "/* binary file */" : data.content || "";
    if ($("btn-save-file")) $("btn-save-file").disabled = !!data.binary;
    setCenterTab("code");
    document.querySelectorAll(".cs-fs-file").forEach((el) => {
      el.classList.toggle("on", el.dataset.path === data.path);
    });
  } catch (e) {
    if ($("play-err")) $("play-err").textContent = e.message;
  }
}

function setCenterTab(name) {
  document.querySelectorAll("#center-tabs .cs-tab").forEach((t) => {
    t.classList.toggle("on", t.dataset.ctab === name);
  });
  ["code", "diff", "changes"].forEach((n) => {
    const el = $(`pane-${n}`);
    if (el) el.classList.toggle("hidden", n !== name);
  });
  if (name === "diff") refreshDiff();
  if (name === "changes") refreshGitStatus();
}

function setBottomTab(name) {
  document.querySelectorAll(".cs-bottom-tabs .cs-tab").forEach((t) => {
    t.classList.toggle("on", t.dataset.btab === name);
  });
  if ($("bottom-terminal")) $("bottom-terminal").classList.toggle("hidden", name !== "terminal");
  if ($("bottom-preview")) $("bottom-preview").classList.toggle("hidden", name !== "preview");
}

async function refreshGitStatus() {
  if (!state.projectId) return;
  try {
    const st = await api(`/projects/${state.projectId}/git/status`);
    const branch = st.branch || "—";
    const dirty = st.dirty ? " · есть правки" : " · чисто";
    const repo = st.github_repo ? ` · ${st.github_repo}` : "";
    if ($("git-branch")) $("git-branch").textContent = `ветка ${branch}${dirty}${repo}`;
    const box = $("changes-list");
    if (box) {
      const files = st.files || [];
      box.innerHTML = files.length
        ? files.map((f) => `<div class="cs-change-row">${escapeHtml(f.status)} ${escapeHtml(f.path)}</div>`).join("")
        : `<div class="cs-empty-tree">Нет правок — всё уже сохранено</div>`;
    }
  } catch {
    if ($("git-branch")) $("git-branch").textContent = "git не готов";
  }
}

async function refreshDiff() {
  if (!state.projectId) return;
  try {
    const data = await api(`/projects/${state.projectId}/git/diff`);
    if ($("diff-view")) $("diff-view").textContent = data.diff || "Пока нет изменений. Напиши задачу справа — здесь появится разница в коде.";
  } catch (e) {
    if ($("diff-view")) $("diff-view").textContent = e.message;
  }
}

async function refreshGithubStatus() {
  try {
    state.github = await api("/github/status");
  } catch {
    state.github = { connected: false };
  }
  const st = state.github;
  if ($("gh-status")) {
    $("gh-status").textContent = st.connected ? `@${st.login}` : "не подключён";
  }
  if ($("gh-actions")) $("gh-actions").classList.toggle("hidden", !!st.connected);
  if ($("gh-connected")) $("gh-connected").classList.toggle("hidden", !st.connected);
  if ($("gh-user") && st.connected) $("gh-user").textContent = `аккаунт: @${st.login}`;
}

function setRunKind(kind) {
  state.runKind = kind;
  document.querySelectorAll("#run-kinds .rk").forEach((b) => {
    b.classList.toggle("on", b.dataset.rk === kind);
  });
  const solo = $("solo-model-wrap");
  if (solo) solo.style.display = kind === "solo" ? "block" : kind === "fork" ? "none" : "block";
  updateChatSub();
}

async function runForkStream(content) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const streamBase = resolveApiBase();
  const res = await fetch(`${streamBase}/projects/${state.projectId}/fork/run`, {
    method: "POST",
    headers,
    body: JSON.stringify({ content, intent: state.intent }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(formatErr(data.detail) || res.statusText);
  }
  const board = $("fork-board");
  const grid = $("fork-grid");
  if (board) board.classList.remove("hidden");
  if (grid) grid.innerHTML = "";
  const forks = {};
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let final = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      let ev;
      try {
        ev = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      if (ev.type === "error") throw new Error(ev.message || "Fork error");
      if (ev.type === "fork_start" && grid) {
        forks[ev.fork_id] = ev;
        grid.insertAdjacentHTML(
          "beforeend",
          `<div class="fork-card running" id="fork-${ev.fork_id}">
            <div class="fork-card-h"><span>${escapeHtml(ev.model)}</span><span>…</span></div>
            <div class="fork-preview">думает…</div>
          </div>`
        );
      }
      if (ev.type === "fork_done") {
        const card = $(`fork-${ev.fork_id}`);
        if (card) {
          card.className = "fork-card done";
          card.innerHTML = `
            <div class="fork-card-h"><span>${escapeHtml(ev.model)}</span><span>готово</span></div>
            <div class="fork-preview">${escapeHtml(ev.preview || "")}</div>
            <button type="button" class="btn btn-p cs-btn-sm" data-pick="${escapeHtml(ev.fork_id)}">Взять этот вариант</button>`;
          card.querySelector("[data-pick]").onclick = async () => {
            await api(`/projects/${state.projectId}/fork/pick`, {
              method: "POST",
              body: { fork_id: ev.fork_id },
            });
            board.classList.add("hidden");
            await loadFsTree(state.projectId);
            await refreshDiff();
            await refreshGitStatus();
            if ($("messages")) {
              $("messages").insertAdjacentHTML(
                "beforeend",
                `<div class="msg assistant"><div class="msg-role">выбран вариант</div><div class="msg-body">Взяли ответ ${escapeHtml(ev.model)} — файлы уже в проекте. Можно «Показать сайт» или «Сохранить и на GitHub».</div></div>`
              );
            }
          };
        }
      }
      if (ev.type === "fork_final") final = ev;
    }
  }
  return final;
}

async function openChat(chatId) {
  state.chatId = chatId;
  persistStudioSelection();
  $("play-empty")?.classList.add("hidden");
  $("play-active")?.classList.remove("hidden");
  await loadStudioMeta();
  fillModelSelect();
  setAgents("");
  const fromCache = (state.chatsCache || []).find((c) => c.id === chatId);
  state.chatTitle = fromCache?.title || `Чат #${chatId}`;
  const titleEl = $("chat-title");
  if (titleEl) titleEl.textContent = state.chatTitle;
  openChatInPane(chatId, state.chatTitle, { newPane: false });
  try {
    const msgs = await api(`/projects/${state.projectId}/chats/${chatId}/messages`);
    renderMessages(msgs);
    if (msgs.some((m) => m.role === "assistant")) {
      refreshPreviewFrame().catch(() => {});
    }
  } catch {
    /* */
  }
}

function renderStudioTranscript(msgs) {
  const log = $("studio-log");
  if (!log) return;
  if (!msgs.length) {
    log.textContent = "Чат пустой — напиши задачу.";
    return;
  }
  log.textContent = msgs
    .map((m) => {
      const who = m.role === "user" ? "Ты" : "Студия";
      return `${who}: ${String(m.content || "").slice(0, 600)}`;
    })
    .join("\n\n");
  log.scrollTop = log.scrollHeight;
}

function plural(n, one, few, many) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

function renderMessages(msgs) {
  const box = $("messages");
  if (!box) return;
  if (!msgs.length) {
    box.innerHTML = `<div class="empty-state compact"><div class="empty-t">Чат пока пустой</div><div class="empty-d">Напиши задачу и жми «Сделать».</div></div>`;
    return;
  }
  box.innerHTML = msgs
    .map((m) => {
      const modeLabel = MODE_RU[m.mode] || m.mode || "";
      const intentLabel = m.intent ? ` · ${m.intent}` : "";
      const agents = m.agents || [];
      const agentStrip = agents.length
        ? `<div class="msg-agents">${agents
            .map((a) => `<span class="msg-agent">${escapeHtml(a.label || a.role)} · ${escapeHtml(a.model || "")}</span>`)
            .join("")}</div>`
        : "";
      const arts = m.artifacts || [];
      const artStrip = arts.length
        ? `<div class="msg-arts">${arts
            .slice(0, 8)
            .map((a) => `<span class="msg-art">${escapeHtml(a.path || a.title || "")}</span>`)
            .join("")}</div>`
        : "";
      return `
    <div class="msg ${m.role}">
      <div class="msg-role">${m.role === "user" ? "ты" : "ответ"}${modeLabel ? ` · ${modeLabel}` : ""}${intentLabel}</div>
      <div class="msg-body">${escapeHtml(m.content)}</div>
      ${agentStrip}
      ${artStrip}
      ${
        m.role === "assistant"
          ? `<div class="msg-meta">${m.model || ""} · ${fmtRub(m.cost_user_rub ?? m.cost_user_usd, 4)} · вход ${m.prompt_tokens} / выход ${m.completion_tokens}</div>`
          : ""
      }
    </div>`;
    })
    .join("");
  box.scrollTop = box.scrollHeight;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function loadUsage() {
  const rows = await api("/me/usage?limit=100");
  const tbody = $("usage-rows");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="5" style="color:var(--muted)">Запросов пока нет — сначала что-нибудь запусти в студии</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(
      (r) => `
    <tr>
      <td>${(r.created_at || "").replace("T", " ").slice(0, 19)}</td>
      <td>${r.model}</td>
      <td><span class="badge">${MODE_RU[r.mode] || r.mode}</span></td>
      <td>${r.prompt_tokens} / ${r.completion_tokens}</td>
      <td>${fmtRub(r.cost_user_rub ?? r.cost_user_usd, 4)}</td>
    </tr>`
    )
    .join("");
}

$("btn-login").onclick = async () => {
  $("auth-err").textContent = "";
  syncApiBaseFromField();
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: { email: $("email").value.trim(), password: $("password").value },
    });
    state.token = data.access_token;
    localStorage.setItem("os_token", state.token);
    setAuthCookie();
    showApp(true);
    await refreshMe();
    await ensureApiKey();
    setTab("dash");
  } catch (e) {
    $("auth-err").textContent = e.message;
  }
};

$("btn-register").onclick = async () => {
  $("auth-err").textContent = "";
  syncApiBaseFromField();
  try {
    const data = await api("/auth/register", {
      method: "POST",
      body: { email: $("email").value.trim(), password: $("password").value },
    });
    state.token = data.access_token;
    localStorage.setItem("os_token", state.token);
    setAuthCookie();
    if (data.api_key) saveRawKey(data.api_key);
    showApp(true);
    await refreshMe();
    await loadModelsCatalog().catch(() => {});
    defaultPickModels();
    setTab("dash");
    flashSetup("Аккаунт готов: ключ создан — можно копировать Base URL + ключ");
    await generateConnectionPack("dash-pack-out");
  } catch (e) {
    $("auth-err").textContent = e.message;
  }
};

function doLogout() {
  if (!confirm("Выйти из кабинета?")) return;
  state.token = "";
  state.projectId = null;
  state.chatId = null;
  localStorage.removeItem("os_token");
  showApp(false);
}

$("nav-logout").onclick = () => {
  if (state.token) doLogout();
};

$("nav-bal").onclick = () => {
  if (state.token) setTab("billing");
};

// все data-goto / data-action — делегирование, чтобы всё тыкалось
document.addEventListener("click", async (e) => {
  const openProj = e.target.closest("[data-open-project]");
  if (openProj) {
    e.preventDefault();
    const id = Number(openProj.dataset.openProject);
    setTab("projects");
    if (id) openProject(id);
    return;
  }
  const goto = e.target.closest("[data-goto]");
  if (goto) {
    e.preventDefault();
    const tab = goto.dataset.goto;
    setTab(tab);
    return;
  }
  const act = e.target.closest("[data-action]");
  if (act) {
    e.preventDefault();
    const a = act.dataset.action;
    if (a === "create-key") {
      createVisibleKey().catch((err) => alert(err.message || String(err)));
      return;
    }
    if (a === "copy-pack") {
      generateConnectionPack("dash-pack-out").catch((err) => alert(err.message || String(err)));
      return;
    }
    if (a === "copy-client-config") {
      (async () => {
        if (!state.rawApiKey) await createVisibleKey();
        const guide = CLIENT_GUIDES.find((g) => g.id === state.clientGuideId) || CLIENT_GUIDES[0];
        const text = guide.configKind ? buildClientConfig(guide.configKind) : buildConnectionPack();
        await copyText(text);
        flashSetup("Конфиг для клиента скопирован");
      })().catch((err) => alert(err.message || String(err)));
      return;
    }
    if (a === "launch-studio") {
      launchStudioFromPack();
      return;
    }
  }
  const tabLink = e.target.closest(".nav a[data-tab]");
  if (tabLink) {
    e.preventDefault();
    setTab(tabLink.dataset.tab);
  }
});

document.querySelectorAll(".nav a[data-tab]").forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    setTab(a.dataset.tab);
  });
});

document.querySelectorAll(".pkg[data-amt]").forEach((el) => {
  el.addEventListener("click", () => {
    $("topup-amount").value = el.dataset.amt;
    document.querySelectorAll(".pkg").forEach((p) => p.classList.remove("selected"));
    el.classList.add("selected");
  });
});

["models-q", "models-sort"].forEach((id) => {
  $(id)?.addEventListener("input", renderModels);
  $(id)?.addEventListener("change", renderModels);
});
$("btn-models-sync")?.addEventListener("click", async () => {
  const btn = $("btn-models-sync");
  if (btn) btn.disabled = true;
  try {
    await api("/v1/models/sync", { method: "POST", body: {} });
    await loadModelsCatalog();
    renderModels();
  } catch (e) {
    alert(e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
});

$("btn-new-project") && ($("btn-new-project").onclick = async () => {
  await startNewStudioChat();
});
$("btn-new-chat-home")?.addEventListener("click", () => startNewStudioChat());

$("btn-new-key").onclick = async () => {
  try {
    await createVisibleKey();
    await generateConnectionPack("keys-pack-out");
  } catch (e) {
    alert(e.message || String(e));
  }
};

$("btn-create-key-dash")?.addEventListener("click", () => {
  createVisibleKey().catch((e) => alert(e.message || String(e)));
});

$("btn-gen-pack")?.addEventListener("click", async () => {
  try {
    await generateConnectionPack("models-pack-out");
  } catch (e) {
    alert(e.message || String(e));
  }
});
$("btn-gen-pack-dash")?.addEventListener("click", () =>
  generateConnectionPack("dash-pack-out").catch((e) => alert(e.message || String(e)))
);
$("btn-gen-pack-keys")?.addEventListener("click", () =>
  generateConnectionPack("keys-pack-out").catch((e) => alert(e.message || String(e)))
);
$("btn-pick-clear")?.addEventListener("click", () => {
  state.selectedModels.clear();
  persistSelectedModels();
  renderModels();
});
$("btn-reissue-key")?.addEventListener("click", async () => {
  try {
    await createVisibleKey();
  } catch (e) {
    alert(e.message || String(e));
  }
});

$("btn-save-alerts")?.addEventListener("click", async () => {
  const body = {
    low_balance_alert: !!$("alert-on")?.checked,
    low_balance_threshold_rub: Math.max(0, Number($("alert-threshold")?.value || 50)),
    monthly_budget_rub: Math.max(0, Number($("month-budget")?.value || 0)),
  };
  await api("/billing/settings", { method: "PATCH", body });
  const ok = $("alerts-saved");
  if (ok) {
    ok.classList.remove("hidden");
    setTimeout(() => ok.classList.add("hidden"), 2000);
  }
  refreshSummary();
});

$("btn-run").onclick = async () => {
  if ($("play-err")) $("play-err").textContent = "";
  const content =
    ($("studio-prompt")?.value || "").trim() ||
    ($("prompt")?.value || "").trim() ||
    ($("studio-iterate")?.value || "").trim();
  if (!content) {
    if ($("play-err")) $("play-err").textContent = "Напиши задачу обычными словами";
    alert("Напиши задачу обычными словами");
    return;
  }
  $("btn-run").disabled = true;
  $("btn-studio-go") && ($("btn-studio-go").disabled = true);
  try {
    await runBeginnerStudio(content);
    if ($("studio-prompt")) $("studio-prompt").value = "";
    if ($("prompt")) $("prompt").value = "";
    if ($("studio-iterate")) $("studio-iterate").value = "";
  } catch (e) {
    if ($("play-err")) $("play-err").textContent = e.message;
    appendStudioLog("Ошибка: " + e.message);
    alert(e.message);
  } finally {
    $("btn-run").disabled = false;
    $("btn-studio-go") && ($("btn-studio-go").disabled = false);
  }
};

$("btn-save-brief")?.addEventListener("click", async () => {
  if (!state.projectId) return;
  const brief = $("project-brief")?.value || "";
  await api(`/projects/${state.projectId}`, { method: "PATCH", body: { brief } });
  state.projectBrief = brief;
});

$("btn-topup").onclick = async () => {
  const amount = Number($("topup-amount").value || 500);
  const method = $("topup-method").value;
  const data = await api("/billing/topup", {
    method: "POST",
    body: { amount_rub: amount, method },
  });
  const methodRu = method === "card" ? "карта РФ" : "USDT CryptoBot";
  const out = $("topup-out");
  out.classList.remove("hidden");
  out.textContent = `${data.instructions}\n\nTelegram: ${data.telegram}\nСумма: ${fmtRub(data.amount_rub, 0)} · ${methodRu}`;
};

(async function boot() {
  bindCopyButtons();
  initApiBaseField();
  syncBaseUrlFields();
  // studio UI bindings
  document.querySelectorAll("#center-tabs .cs-tab").forEach((t) => {
    t.onclick = () => setCenterTab(t.dataset.ctab);
  });
  document.querySelectorAll(".cs-bottom-tabs .cs-tab").forEach((t) => {
    t.onclick = () => setBottomTab(t.dataset.btab);
  });
  document.querySelectorAll("#run-kinds .rk").forEach((b) => {
    b.onclick = () => setRunKind(b.dataset.rk);
  });
  $("btn-save-file")?.addEventListener("click", async () => {
    if (!state.projectId || !state.openFile) return;
    await api(`/projects/${state.projectId}/fs/file`, {
      method: "PUT",
      body: { path: state.openFile, content: $("code-editor").value },
    });
    await refreshGitStatus();
  });
  $("btn-file-revert")?.addEventListener("click", async () => {
    if (!state.projectId || !state.openFile) return;
    await openWorkspaceFile(state.openFile);
  });
  $("btn-git-commit")?.addEventListener("click", async () => {
    if (!state.projectId) return;
    const message = prompt("Кратко опиши, что сохраняем", "обновление из студии") || "обновление из студии";
    await api(`/projects/${state.projectId}/git/commit`, { method: "POST", body: { message } });
    await refreshGitStatus();
    await refreshDiff();
  });
  $("btn-git-push")?.addEventListener("click", async () => {
    if (!state.projectId) return;
    try {
      await api(`/projects/${state.projectId}/git/push`, { method: "POST", body: {} });
      alert("Готово: код отправлен на GitHub");
      await refreshGitStatus();
    } catch (e) {
      alert("Не удалось отправить на GitHub.\n\n" + e.message + "\n\nСначала подключи GitHub слева и привяжи репозиторий.");
    }
  });
  $("btn-commit-push")?.addEventListener("click", async () => {
    if (!state.projectId) return;
    const message = ($("commit-msg")?.value || "").trim() || "обновление из студии";
    try {
      await api(`/projects/${state.projectId}/git/commit`, { method: "POST", body: { message } });
      await api(`/projects/${state.projectId}/git/push`, { method: "POST", body: {} });
      if ($("commit-msg")) $("commit-msg").value = "";
      await refreshGitStatus();
      await refreshDiff();
      alert("Готово: снимок сохранён и отправлен на GitHub");
    } catch (e) {
      alert("Ошибка.\n\n" + e.message + "\n\nЕсли push не прошёл — подключи GitHub и привяжи репозиторий.");
    }
  });
  async function startPreview() {
    if (!state.projectId) return;
    await refreshPreviewFrame();
    setBottomTab("preview");
  }
  $("btn-preview-toggle")?.addEventListener("click", () => {
    setBottomTab("preview");
    if (!state.previewRunning) startPreview().catch((e) => alert(e.message));
  });
  $("btn-preview-start")?.addEventListener("click", () => startPreview().catch((e) => alert(e.message)));
  $("btn-preview-stop")?.addEventListener("click", async () => {
    if (!state.projectId) return;
    await api(`/projects/${state.projectId}/preview/stop`, { method: "POST", body: {} });
    state.previewRunning = false;
    if ($("preview-url")) $("preview-url").value = "";
    const iframe = $("studio-preview");
    if (iframe) {
      iframe.removeAttribute("srcdoc");
      iframe.src = "about:blank";
    }
    $("preview-empty")?.classList.remove("hidden");
  });
  $("btn-preview-reload")?.addEventListener("click", () => startPreview().catch((e) => alert(e.message)));

  function connectTerm() {
    if (!state.projectId || !state.token) return;
    if (state.termWs) {
      try {
        state.termWs.close();
      } catch {
        /* */
      }
    }
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(
      `${proto}://${location.host}/projects/${state.projectId}/term?token=${encodeURIComponent(state.token)}`
    );
    state.termWs = ws;
    const out = $("term-out");
    if (out) out.textContent = "Подключаем консоль…\n";
    ws.onmessage = (ev) => {
      if (typeof ev.data === "string" && ev.data.startsWith("{")) {
        try {
          const j = JSON.parse(ev.data);
          if (j.type === "error") {
            if (out) out.textContent += `\n[ошибка] ${j.message}\n`;
            return;
          }
          if (j.type === "ready") {
            if (out) out.textContent += `Готово. Папка проекта: ${j.cwd}\n`;
            return;
          }
        } catch {
          /* plain */
        }
      }
      if (out) {
        out.textContent += ev.data;
        out.scrollTop = out.scrollHeight;
      }
    };
    ws.onclose = () => {
      if (out) out.textContent += "\n[консоль отключена]\n";
    };
  }
  $("btn-term-connect")?.addEventListener("click", connectTerm);
  $("term-in")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const line = $("term-in").value;
    if (state.termWs && state.termWs.readyState === 1) {
      state.termWs.send(line + "\n");
      $("term-in").value = "";
    } else {
      connectTerm();
    }
  });

  $("btn-gh-connect")?.addEventListener("click", async () => {
    try {
      const data = await api("/github/connect");
      if (data.url) location.href = data.url;
    } catch (e) {
      alert(e.message + "\n\nПроще: нажми «Вставить токен» и вставь Personal Access Token из GitHub.");
    }
  });
  $("btn-gh-pat")?.addEventListener("click", async () => {
    const token = prompt(
      "Вставь токен GitHub (Settings → Developer settings → Personal access tokens).\nНужны права на репозитории (repo)."
    );
    if (!token) return;
    await api("/github/pat", { method: "POST", body: { token } });
    await refreshGithubStatus();
    alert("GitHub подключён. Теперь нажми «Привязать репозиторий».");
  });
  $("btn-gh-disconnect")?.addEventListener("click", async () => {
    await api("/github/disconnect", { method: "DELETE" });
    await refreshGithubStatus();
  });
  $("btn-gh-link")?.addEventListener("click", async () => {
    if (!state.projectId) {
      alert("Сначала открой проект слева");
      return;
    }
    let repos = [];
    try {
      repos = await api("/github/repos");
    } catch (e) {
      alert(e.message);
      return;
    }
    const names = repos.map((r) => r.full_name).slice(0, 30);
    const pick = prompt(
      "Укажи репозиторий в формате имя/проект\n(можно новый — создадим)\n\nТвои репозитории:\n" +
        (names.join("\n") || "пока пусто"),
      names[0] || "username/my-app"
    );
    if (!pick) return;
    await api(`/github/projects/${state.projectId}/link`, {
      method: "POST",
      body: { repo: pick.trim(), clone: true, create_if_missing: true },
    });
    await openProject(state.projectId);
    alert("Репозиторий привязан. После правок жми «Сохранить и на GitHub».");
  });
  $("btn-onboard-project")?.addEventListener("click", () => $("btn-new-project")?.click());
  $("btn-onboard-github")?.addEventListener("click", () => $("btn-gh-pat")?.click());

  // Beginner Studio bindings
  document.querySelectorAll("#zc-agents .zc-agent-btn").forEach((btn) => {
    btn.onclick = () => {
      const n = Number(btn.dataset.n) || 2;
      state.agentsN = n;
      state.mode = { 1: "light", 2: "standard", 3: "ultra", 4: "ultra" }[n] || "standard";
      document.querySelectorAll("#zc-agents .zc-agent-btn").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      if ($("zc-agents-hint")) $("zc-agents-hint").textContent = AGENT_HINTS[n] || "";
      if ($("studio-mode")) $("studio-mode").value = state.mode;
    };
  });
  document.querySelectorAll("#zc-templates .zc-chip").forEach((btn) => {
    btn.onclick = () => {
      const text = STUDIO_TEMPLATES[btn.dataset.tpl];
      if (text && $("studio-prompt")) $("studio-prompt").value = text;
    };
  });
  $("btn-studio-go")?.addEventListener("click", () => $("btn-run")?.click());
  $("btn-studio-iterate")?.addEventListener("click", () => {
    const t = ($("studio-iterate")?.value || "").trim();
    if (!t) return;
    if ($("studio-prompt")) $("studio-prompt").value = t;
    $("btn-run")?.click();
  });
  $("btn-studio-advanced-toggle")?.addEventListener("click", () => setAdvOpen(false));
  $("btn-adv-close")?.addEventListener("click", () => setAdvOpen(false));
  $("nav-cabinet")?.addEventListener("click", () => leaveStudioToCabinet());
  $("btn-studio-exit")?.addEventListener("click", () => leaveStudioToCabinet());
  $("btn-rail-new-chat")?.addEventListener("click", async () => {
    ensureDefaultPanes();
    const pane = getActivePane() || state.openPanes[0];
    if (!pane) return;
    await createChatForPane(pane.id);
  });
  $("btn-rail-new-project")?.addEventListener("click", () => {
    createStudioProjectFolder().catch((e) => alert(e.message || e));
  });
  $("studio-agents-n")?.addEventListener("change", () => {
    syncAgentsFromAdv();
    const pane = getActivePane();
    if (pane) {
      pane.agentsN = state.agentsN;
      persistOpenPanes();
    }
  });
  $("studio-adv-model")?.addEventListener("change", () => {
    const pane = getActivePane();
    if (pane) {
      pane.model = $("studio-adv-model").value || "";
      persistOpenPanes();
    }
  });
  void $("btn-preview-toggle");
  void $("btn-studio-adv2");
  $("btn-preview-refresh")?.addEventListener("click", () => refreshPreviewFrame().catch((e) => alert(e.message)));
  $("btn-preview-open")?.addEventListener("click", () => {
    const url = ($("preview-url")?.value || "").trim();
    if (url) window.open(url.startsWith("http") ? url : url, "_blank");
    else refreshPreviewFrame().catch((e) => alert(e.message));
  });
  $("btn-fs-refresh")?.addEventListener("click", () => state.projectId && loadFsTree(state.projectId));
  $("btn-commit")?.addEventListener("click", async () => {
    if (!state.projectId) return;
    const message = prompt("Кратко опиши, что сохраняем", "обновление из студии") || "обновление из студии";
    await api(`/projects/${state.projectId}/git/commit`, { method: "POST", body: { message } });
    await refreshGitStatus();
  });
  $("btn-push")?.addEventListener("click", async () => {
    if (!state.projectId) return;
    try {
      await api(`/projects/${state.projectId}/git/push`, { method: "POST", body: {} });
      alert("Отправлено на GitHub");
    } catch (e) {
      alert(e.message);
    }
  });
  $("btn-pull")?.addEventListener("click", async () => {
    if (!state.projectId) return;
    try {
      await api(`/projects/${state.projectId}/git/pull`, { method: "POST", body: {} });
      await loadFsTree(state.projectId);
      alert("Стянули с GitHub");
    } catch (e) {
      alert(e.message);
    }
  });
  $("btn-diff")?.addEventListener("click", async () => {
    await refreshDiff();
    const d = $("diff-view")?.textContent || "";
    alert(d.slice(0, 1500) || "Нет изменений");
  });
  $("btn-gh-save")?.addEventListener("click", async () => {
    const token = ($("gh-pat")?.value || "").trim();
    if (!token) {
      alert("Вставь Personal Access Token");
      return;
    }
    await api("/github/pat", { method: "POST", body: { token } });
    if ($("gh-pat")) $("gh-pat").value = "";
    await refreshGithubStatus();
    alert("GitHub подключён");
  });
  $("btn-gh-clear")?.addEventListener("click", async () => {
    await api("/github/disconnect", { method: "DELETE" });
    await refreshGithubStatus();
  });
  $("btn-new-chat")?.addEventListener("click", async () => {
    await startNewStudioChat();
  });
  $("studio-mode")?.addEventListener("change", () => {
    state.mode = $("studio-mode").value || "standard";
  });
  $("btn-runtime-start")?.addEventListener("click", () => refreshPreviewFrame().catch((e) => alert(e.message)));
  $("btn-runtime-stop")?.addEventListener("click", async () => {
    if (!state.projectId) return;
    await api(`/projects/${state.projectId}/preview/stop`, { method: "POST", body: {} });
    state.previewRunning = false;
    if ($("studio-preview")) {
      $("studio-preview").removeAttribute("srcdoc");
      $("studio-preview").src = "about:blank";
    }
    $("preview-empty")?.classList.remove("hidden");
  });
  $("btn-term-run")?.addEventListener("click", () => {
    const line = $("term-in")?.value || "";
    if (state.termWs && state.termWs.readyState === 1) {
      state.termWs.send(line + "\n");
      if ($("term-in")) $("term-in").value = "";
    } else {
      connectTerm();
    }
  });
  $("btn-fork")?.addEventListener("click", async () => {
    const content = ($("studio-prompt")?.value || $("studio-iterate")?.value || "").trim();
    if (!content) {
      alert("Сначала напиши задачу");
      return;
    }
    await ensureStudioProject();
    showStudioWork("×3 варианта");
    appendStudioLog("Запуск 3 вариантов…");
    try {
      await runForkStream(content);
      appendStudioLog("Варианты готовы — смотри продвинутый режим / fork-panel");
    } catch (e) {
      alert(e.message);
    }
  });
  // improve gh-link to use input
  const oldGhLink = $("btn-gh-link");
  if (oldGhLink) {
    oldGhLink.onclick = async () => {
      if (!state.projectId) {
        alert("Сначала открой проект");
        return;
      }
      const pick =
        ($("gh-repo")?.value || "").trim() ||
        prompt("Укажи репозиторий owner/repo", "username/my-app");
      if (!pick) return;
      await api(`/github/projects/${state.projectId}/link`, {
        method: "POST",
        body: { repo: pick.trim(), clone: true, create_if_missing: true },
      });
      await openProject(state.projectId);
      alert("Репозиторий привязан");
    };
  }
  $("btn-gh-clone")?.addEventListener("click", () => $("btn-gh-link")?.click());
  $("btn-gh-create")?.addEventListener("click", () => $("btn-gh-link")?.click());

  // Only open studio from URL when linking GitHub — don't dump users into studio on #projects
  if (new URLSearchParams(location.search).get("github")) {
    setTab("projects");
  } else if (location.hash.includes("projects")) {
    try {
      history.replaceState(null, "", location.pathname);
    } catch {
      /* */
    }
  }

  if (state.token) {
    try {
      setAuthCookie();
      showApp(true);
      await refreshMe();
      await refreshGithubStatus();
    } catch (e) {
      const msg = e?.message || String(e);
      const serverDown = /не отвечает|Failed to fetch|NetworkError|Load failed/i.test(msg);
      if (serverDown) {
        showApp(false);
        if ($("auth-err")) {
          $("auth-err").textContent = msg;
        }
      } else {
        state.token = "";
        localStorage.removeItem("os_token");
        showApp(false);
      }
    }
  } else {
    showApp(false);
  }
})();
