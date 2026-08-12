/* ZeusCode Telegram Mini App — простой старт + выбор моделей */
(() => {
  const tg = window.Telegram?.WebApp;
  const LS_STEP = "zc_learn_step";
  const LS_TRACK = "zc_learn_track";
  const LS_DONE = "zc_onboarding_done";
  const SS_KEY = "zc_raw_key";

  const MODEL_SHOW = "ZeusCode";
  const MODEL_TECH = "gpt-5.5";

  /** Model id as the client expects (Aider needs openai/ prefix via LiteLLM). */
  function clientModelHint(platform) {
    const kind = (platform && platform.configKind) || "";
    if (kind === "aider") return "openai/gpt-5.5";
    return MODEL_TECH;
  }

  const FIRST_PROMPT =
    "Сделай лендинг автосервиса: витрина 3 фото, 6 услуг с ценами, " +
    "форма записи POST /api/booking, отзывы и FAQ. Асфальт/янтарь, без indigo.";

  /* Standard ZeusCode stack; manual picks 1–3 */
  const PRESET = {
    standard: ["claude-opus-4-6", "gpt-5.5", "gpt-5.6-sol"],
  };

  const ROLE_BY_ARCH = {
    solo: ["Solo"],
    combo3: ["Architect", "Builder", "Finalizer"],
  };

  const state = {
    route: "learn",
    mode: "standard",
    selected: new Set(),
    catalog: [],
    modes: [],
    architecture: "combo3",
    me: null,
    learnStep: 0,
    track: "unknown",
    visualIdx: 0,
    rawKey: null,
    advHistory: [],
    advBusy: false,
  };

  function platform() {
    const cat = window.ZC_PLATFORMS || {};
    return cat[state.track] || cat.unknown || { id: "unknown", title: "Не знаю", steps: [] };
  }

  function continueYaml(base, key) {
    return (
      `name: ZeusCode\nversion: 1.0.0\nschema: v1\nmodels:\n` +
      `  - name: ZeusCode\n    provider: openai\n    model: ${MODEL_TECH}\n` +
      `    apiBase: ${base}\n    apiKey: ${key || "zeus_ВАШ_КЛЮЧ"}\n` +
      `    useResponsesApi: false\n` +
      `    capabilities:\n      - tool_use\n` +
      `    roles:\n      - chat\n      - edit\n      - apply\n`
    );
  }

  /** Same product modes as Mini App tab «Модели». */
  function botFusionModes() {
    const modes =
      state.modes && state.modes.length
        ? state.modes
        : [
            {
              id: "standard",
              title: "ZeusCode",
              hint: "Стандартный стек · роли по силе моделей",
            },
            {
              id: "manual",
              title: "Ручной",
              hint: "Свой выбор: 1 модель (соло) или 3 модели (Combo-3)",
            },
          ];
    const byId = Object.fromEntries(modes.map((m) => [m.id, m]));
    const selectedIds = [...(state.selected || [])].slice(0, 3);
    const stackHint =
      selectedIds.length > 0
        ? selectedIds.join(" + ")
        : "отметь 1–3 во вкладке «Модели»";
    return {
      standard: byId.standard || modes[0],
      manual: byId.manual || modes[1],
      standardStack: PRESET.standard,
      selectedStack: selectedIds,
      stackHint,
      // legacy keys for older advisor prompts
      simple: byId.manual || modes[1],
      power: byId.standard || modes[0],
      custom: byId.manual || modes[1],
      simpleStack: selectedIds,
      powerStack: PRESET.standard,
      customStack: selectedIds,
      customHint: stackHint,
    };
  }

  /**
   * OpenCode: в пикере id «zeuscode/zeuscode» (provider/model) = связка нейронок.
   * Режим (Пользовательский / Продвинутый / Набор) настраивается ТОЛЬКО в TG «Модели».
   * Отдельных Zeus Simple/Power/Custom в пикере больше нет.
   */
  function opencodeModelsFromCatalog(catalog) {
    const f = botFusionModes();
    const modeTitle = f[state.mode]?.title || "Продвинутый";
    const models = {
      zeuscode: {
        name: `ZeusCode · режим «${modeTitle}» из Telegram`,
        tools: true,
      },
    };

    const rows = (catalog || []).filter(
      (m) => m && m.id && m.ready !== false && (m.modality || "chat") === "chat"
    );
    for (const m of rows) {
      const id = String(m.id);
      if (id === "gpt-5.5" || id.startsWith("zeuscode")) continue;
      if (id.startsWith("studio-") || id === "ultra-mode") continue;
      const noTools =
        id === "claude-fable-5" ||
        m.adapter === "pending" ||
        (m.modality && m.modality !== "chat");
      const title = String(m.title || id).replace(/^ZeusCode( ·)?\s*/i, "");
      models[id] = {
        name: title,
        tools: !noTools,
      };
    }
    return models;
  }

  /** OpenCode: ключ один раз · дефолт = режим из Telegram. */
  function opencodeJson(base, key) {
    const root = String(base || "").replace(/\/+$/, "");
    const models = opencodeModelsFromCatalog(state.catalog);
    const cfg = {
      $schema: "https://opencode.ai/config.json",
      model: "zeuscode/zeuscode",
      provider: {
        zeuscode: {
          npm: "@ai-sdk/openai-compatible",
          name: "ZeusCode",
          options: {
            baseURL: root,
            apiKey: key || "zeus_ВАШ_КЛЮЧ",
          },
          models,
        },
      },
    };
    // Чистый JSON — как ждёт OpenCode (без #комментов в файле)
    return JSON.stringify(cfg, null, 2);
  }

  /** Ready chat model ids from Mini App catalog (one key unlocks all). */
  function readyChatIds() {
    const fromCat = (state.catalog || [])
      .filter((m) => m && m.id && m.ready !== false && (m.modality || "chat") === "chat")
      .map((m) => String(m.id));
    const ids = [MODEL_TECH, ...fromCat.filter((id) => id !== MODEL_TECH)];
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

  function catalogComment(ids, limit = 80) {
    const slice = ids.slice(0, limit);
    const more = ids.length > limit ? ` … +${ids.length - limit}` : "";
    return `# ZeusCode · весь каталог (${ids.length}) на этом ключе — GET …/models\n# ${slice.join(" · ")}${more}`;
  }

  function catalogTitle(id) {
    const row = (state.catalog || []).find((m) => m && String(m.id) === String(id));
    const title = (row && row.title) || id;
    if (id === MODEL_TECH) return "ZeusCode";
    return String(title).startsWith("ZeusCode") ? String(title) : `ZeusCode · ${title}`;
  }

  function clientConfig(base, key, platform) {
    const root = String(base || "").replace(/\/+$/, "");
    const host = root.replace(/\/v1$/, "");
    const k = key || "zeus_ВАШ_КЛЮЧ";
    const kind = (platform && platform.configKind) || "continue";
    const ids = readyChatIds();
    const fusion = MODEL_TECH; // режим из вкладки «Модели» Mini App
    const catNote = catalogComment(ids);

    if (kind === "opencode") return opencodeJson(base, key);

    if (kind === "cline" || kind === "kilo") {
      const who = kind === "cline" ? "Cline → ⚙️ Settings" : "Kilo → Providers → Custom";
      return [
        `# ${who}`,
        `# Один ключ = весь каталог. Дефолт zeuscode = режим из Mini App.`,
        `API Provider: OpenAI Compatible`,
        `Base URL:     ${root}`,
        `API Key:      ${k}`,
        `Model ID:     ${fusion}`,
        ``,
        catNote,
        `# В окне разработки можно выбрать любой id из /v1/models`,
        `# Base URL только до /v1 — без /chat/completions`,
      ].join("\n");
    }
    if (kind === "goose") {
      return [
        `# Goose — путь A (built-in openai, проще)`,
        `# OPENAI_HOST = origin БЕЗ /v1 — Goose сам добавляет /v1/chat/completions`,
        `export GOOSE_PROVIDER=openai`,
        `export OPENAI_API_KEY="${k}"`,
        `export OPENAI_HOST="${host}"`,
        `export GOOSE_MODEL="${fusion}"`,
        ``,
        `# Путь B — ~/.config/goose/custom_providers/zeuscode.json`,
        `# {`,
        `#   "name": "zeuscode", "engine": "openai", "display_name": "ZeusCode",`,
        `#   "api_key_env": "ZEUSCODE_API_KEY",`,
        `#   "base_url": "${root}",`,
        `#   "models": [{"name": "${fusion}", "context_limit": 128000}],`,
        `#   "supports_streaming": true, "requires_auth": true`,
        `# }`,
        `# export ZEUSCODE_API_KEY="${k}"`,
        `# export GOOSE_PROVIDER=zeuscode`,
        ``,
        catNote,
        `# goose info -v && goose session`,
      ].join("\n");
    }
    if (kind === "crush") {
      const models = ids.map((id) => ({
        id,
        name: catalogTitle(id),
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
        `\n\n# export ZEUSCODE_API_KEY="${k}"\n# ~/.config/crush/crush.json\n${catNote}`
      );
    }
    if (kind === "openhands") {
      return [
        `# OpenHands → LLM → Advanced`,
        `# Один ключ = все модели. Дефолт = режим Mini App.`,
        `LLM_MODEL=openai/${fusion}`,
        `LLM_BASE_URL=${root}`,
        `LLM_API_KEY=${k}`,
        ``,
        `# Любая другая: openai/<id>  (префикс openai/ обязателен)`,
        catNote,
      ].join("\n");
    }
    if (kind === "zed") {
      // provider id `zeuscode` → env ZEUSCODE_API_KEY (UPPER_SNAKE per Zed docs)
      const zedCaps = {
        tools: true,
        images: false,
        parallel_tool_calls: false,
        prompt_cache_key: false,
      };
      const available_models = ids.map((id) => ({
        name: id,
        display_name: catalogTitle(id),
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
        `\n\n# export ZEUSCODE_API_KEY="${k}"\n# agent: open settings → ключ, если без env\n${catNote}`
      );
    }
    if (kind === "librechat") {
      const defaults = ids.slice(0, 12);
      return [
        `# librechat.yaml — один ключ, fetch тянет ВЕСЬ каталог`,
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
        `ZEUSCODE_API_KEY=${k}`,
        catNote,
      ].join("\n");
    }
    if (kind === "openwebui") {
      return [
        `# Admin → Connections → OpenAI`,
        `# Один ключ Zeus — модели подтянутся все с /v1/models`,
        `OPENAI_API_BASE_URL=${root}`,
        `OPENAI_API_KEY=${k}`,
        ``,
        `# В чате выбери любую модель · zeuscode = режим Mini App`,
        catNote,
      ].join("\n");
    }
    if (kind === "omniroute") {
      return [
        `# OmniRoute → Providers → OpenAI Compatible`,
        `# Протокол: Chat Completions (НЕ Responses)`,
        `# Base URL / Key / Model:`,
        `Base URL: ${root}`,
        `API Key:  ${k}`,
        `Model:    ${fusion}   # id со слэшем · или gemini-2.5-flash для теста`,
        ``,
        `# Если 502 UND_ERR_SOCKET / other side closed:`,
        `#   1) OmniRoute ≥ 3.8.36`,
        `#   2) export FETCH_KEEPALIVE_TIMEOUT_MS=1`,
        `#   3) перезапусти OmniRoute · Test Connection заново`,
        ``,
        `# omniroute setup-codex  → профили на все модели`,
        catNote,
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
        `# export ZEUSCODE_API_KEY="${k}"`,
        `# Сменить модель: codex -m <id>  или /model в сессии`,
        catNote,
      ].join("\n");
    }
    if (kind === "claude") {
      // Claude Code /model picker only accepts ids starting with claude|anthropic.
      // Zeus enables CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY → GET /v1/models?limit=1000
      // returns anthropic.zeuscode/<id> for Gemini/DeepSeek/GPT/Fusion (+ real claude-* ids).
      return (
        JSON.stringify(
          {
            env: {
              ANTHROPIC_BASE_URL: host,
              ANTHROPIC_AUTH_TOKEN: k,
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
        `\n\n# ~/.claude/settings.json  ·  Claude Code ≥ 2.1.129\n` +
        `# BASE_URL без /v1 · unset ANTHROPIC_API_KEY\n` +
        `# /model → весь каталог ZeusCode (discovery + Fusion)\n` +
        `# Не-Claude в пикере: anthropic.zeuscode/<id>  (бэкенд сам снимет префикс)\n` +
        `# Или: claude --model gemini-3.1-pro\n${catNote}`
      );
    }
    if (kind === "openai_any") {
      return [
        `# Любой OpenAI-compatible · один ключ = весь каталог`,
        `Base URL: ${root}`,
        `API Key:  ${k}`,
        `Model:    ${fusion}   # режим Mini App · или любой id`,
        ``,
        `curl ${root}/models -H "Authorization: Bearer ${k}"`,
        ``,
        `curl ${root}/chat/completions \\`,
        `  -H "Content-Type: application/json" \\`,
        `  -H "Authorization: Bearer ${k}" \\`,
        `  -d '{"model":"${fusion}","messages":[{"role":"user","content":"ping"}]}'`,
        catNote,
      ].join("\n");
    }
    if (kind === "aider") {
      const menu = ids.map((id) => `#   aider --model openai/${id}`).join("\n");
      return [
        `# Aider · ZeusCode · один ключ = весь каталог`,
        `export OPENAI_API_BASE="${root}"`,
        `export OPENAI_API_KEY="${k}"`,
        `aider --model openai/${fusion}`,
        ``,
        `# Другая модель:`,
        menu,
        catNote,
      ].join("\n");
    }
    if (kind === "cursor") {
      return [
        `# Cursor — нативный Override часто ломает Agent (Responses → /chat/completions).`,
        `# Надёжнее: Cline/Kilo в Cursor → OpenAI Compatible → поля ниже.`,
        ``,
        `# Нативный путь (на свой риск):`,
        `# Cursor Settings → Models`,
        `# OpenAI API Key = ${k}`,
        `# Override OpenAI Base URL = ${root}`,
        `# Add model → ${fusion}   ← только этот id, не gpt-* и не zeuscode-simple`,
        ``,
        `# Cline/Kilo (рекомендуем):`,
        `# API Provider: OpenAI Compatible`,
        `# Base URL:     ${root}`,
        `# API Key:      ${k}`,
        `# Model ID:     ${fusion}`,
        catNote,
      ].join("\n");
    }
    // Continue / unknown — fusion + весь список в yaml (без обрезания)
    const extra = ids
      .filter((id) => id !== fusion)
      .map(
        (id) =>
          `  - name: ${catalogTitle(id)}\n    provider: openai\n    model: ${id}\n` +
          `    apiBase: ${root}\n    apiKey: ${k}\n` +
          `    roles:\n      - chat\n      - edit\n      - apply\n`
      )
      .join("");
    return (
      `name: ZeusCode\nversion: 1.0.0\nschema: v1\nmodels:\n` +
      `  - name: ZeusCode\n    provider: openai\n    model: ${fusion}\n` +
      `    apiBase: ${root}\n    apiKey: ${k}\n` +
      `    useResponsesApi: false\n` +
      `    capabilities:\n      - tool_use\n` +
      `    roles:\n      - chat\n      - edit\n      - apply\n` +
      extra +
      `\n# zeuscode = режим Mini App · остальные id — соло\n` +
      `# ~/.continue/config.yaml · apiBase обязан заканчиваться на /v1\n${catNote}\n`
    );
  }

  const $ = (id) => document.getElementById(id);

  function initData() {
    return (tg?.initData || "").trim();
  }

  async function api(path, { method = "GET", body } = {}) {
    const headers = {
      Accept: "application/json",
      "X-Tg-Init-Data": initData(),
    };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.detail || data.message || res.statusText || "Ошибка";
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  }

  /** Batched UI analytics — avoids /tg/events storm on every tap. */
  const _eventQ = [];
  let _eventFlushTimer = null;
  let _eventFlushing = false;

  function track(event, meta, promptPreview) {
    try {
      const body = { event: String(event || "").slice(0, 40), meta: meta || {} };
      if (promptPreview) body.prompt_preview = String(promptPreview).slice(0, 500);
      const last = _eventQ[_eventQ.length - 1];
      // collapse back-to-back duplicates (view toggles, viz dots)
      if (
        last &&
        last.event === body.event &&
        JSON.stringify(last.meta || {}) === JSON.stringify(body.meta || {})
      ) {
        return;
      }
      _eventQ.push(body);
      if (_eventQ.length > 12) {
        void flushEvents();
        return;
      }
      if (_eventFlushTimer) clearTimeout(_eventFlushTimer);
      _eventFlushTimer = setTimeout(() => {
        void flushEvents();
      }, 1800);
    } catch {
      /* ignore */
    }
  }

  async function flushEvents() {
    if (_eventFlushTimer) {
      clearTimeout(_eventFlushTimer);
      _eventFlushTimer = null;
    }
    if (_eventFlushing || !_eventQ.length) return;
    _eventFlushing = true;
    const batch = _eventQ.splice(0, 20);
    try {
      for (const body of batch) {
        await api("/tg/events", { method: "POST", body }).catch(() => {});
      }
    } finally {
      _eventFlushing = false;
      if (_eventQ.length) {
        _eventFlushTimer = setTimeout(() => {
          void flushEvents();
        }, 400);
      }
    }
  }

  // flush leftover analytics when Mini App is closed / hidden
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") void flushEvents();
  });
  window.addEventListener("pagehide", () => {
    void flushEvents();
  });

  function showErr(msg) {
    const el = $("err");
    el.textContent = msg || "";
    el.classList.toggle("hidden", !msg);
    $("ok").classList.add("hidden");
  }

  function showOk(msg) {
    const el = $("ok");
    el.textContent = msg || "";
    el.classList.toggle("hidden", !msg);
    $("err").classList.add("hidden");
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /** Elegant advisor text: safe HTML, **bold**, lists, no raw tags on screen. */
  function formatAdvisorHtml(raw) {
    let s = escapeHtml(String(raw || "").trim());
    s = s.replace(/&lt;b&gt;([\s\S]*?)&lt;\/b&gt;/gi, "<b>$1</b>");
    s = s.replace(/&lt;i&gt;([\s\S]*?)&lt;\/i&gt;/gi, "<i>$1</i>");
    s = s.replace(/&lt;code&gt;([\s\S]*?)&lt;\/code&gt;/gi, "<code>$1</code>");
    s = s.replace(/&lt;br\s*\/?&gt;/gi, "\n");
    s = s.replace(/\*\*([\s\S]+?)\*\*/g, "<b>$1</b>");
    const lines = s.split(/\n/);
    const out = lines.map((line) => {
      const step = line.match(/^(\d{1,2})[.)]\s+(.+)$/);
      if (step) {
        return `<div class="adv-step"><span class="adv-n">${step[1]}</span><span class="adv-t">${step[2]}</span></div>`;
      }
      const bullet = line.match(/^[•·\-]\s+(.+)$/);
      if (bullet) {
        return `<span class="adv-li">${bullet[1]}</span>`;
      }
      return line;
    });
    return out
      .join("<br>")
      .replace(/(?:<br>\s*){3,}/g, "<br><br>")
      .replace(/<br>(<div class="adv-step">)/g, "$1")
      .replace(/(<\/div>)<br>/g, "$1");
  }

  function friendlyTitle(id) {
    const row = state.catalog.find((m) => m.id === id);
    if (row?.title) return row.title;
    const tail = String(id || "").split("/").pop() || id;
    return String(tail)
      .replace(/-/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function parseRoute() {
    const params = new URLSearchParams(location.search);
    const view = (params.get("view") || "").toLowerCase();
    const start =
      (tg?.initDataUnsafe?.start_param || "").toLowerCase() ||
      (params.get("startapp") || "").toLowerCase();
    const hash = (location.hash || "").replace(/^#\/?/, "").toLowerCase();

    if (view === "fusion" || view === "models" || view === "mode") return "fusion";
    if (view === "advisor" || view === "help" || view === "ask") return "advisor";
    if (view === "learn" || view === "onboarding") return "learn";
    if (start === "fusion" || start === "models" || start === "mode") return "fusion";
    if (start === "advisor" || start === "help") return "advisor";
    if (start === "learn" || start === "onboarding") return "learn";
    if (hash.startsWith("fusion") || hash.startsWith("models") || hash === "mode") {
      return "fusion";
    }
    if (hash.startsWith("advisor") || hash.startsWith("help")) return "advisor";
    if (hash.startsWith("learn")) return "learn";

    const done =
      localStorage.getItem(LS_DONE) === "1" ||
      Boolean(state.me?.onboarding_done);
    return done ? "fusion" : "learn";
  }

  function setRoute(route, { push = true } = {}) {
    const prev = state.route;
    if (route === "fusion") state.route = "fusion";
    else if (route === "subscription") state.route = "subscription";
    else state.route = "learn";
    if (push) {
      const url = new URL(location.href);
      url.searchParams.set("view", state.route);
      url.hash = `/${state.route}`;
      const next = url.pathname + url.search + url.hash;
      if (location.pathname + location.search + location.hash !== next) {
        history.replaceState(null, "", next);
      }
    }
    if (prev !== state.route) {
      track("miniapp_view", { view: state.route, from: prev || null });
    }
    $("view-learn")?.classList.toggle("hidden", state.route !== "learn");
    $("view-fusion")?.classList.toggle("hidden", state.route !== "fusion");
    $("view-subscription")?.classList.toggle("hidden", state.route !== "subscription");
    document.querySelectorAll(".seg-btn").forEach((btn) => {
      btn.classList.toggle("on", btn.dataset.route === state.route);
      btn.setAttribute("aria-selected", btn.dataset.route === state.route ? "true" : "false");
    });
    const again = $("btn-learn-again");
    if (again) {
      const showHelp =
        state.route === "fusion" &&
        (localStorage.getItem(LS_DONE) === "1" || state.me?.onboarding_done);
      again.classList.toggle("hidden", !showHelp);
    }
    showErr("");
    showOk("");
    if (state.route === "learn") {
      renderLearn();
      syncLearnMainButton();
    } else if (state.route === "advisor") {
      renderAdvisor();
      if (tg?.MainButton) tg.MainButton.hide();
    } else {
      renderModes();
      renderModels();
      syncKeyUi();
      syncFusionMainButton();
    }
    syncBackUi();
  }

  function syncBackUi() {
    const canBack = state.route === "learn" && state.learnStep > 0;
    $("learn-back")?.classList.toggle("hidden", !canBack);
    if (!tg?.BackButton) return;
    if (canBack) tg.BackButton.show();
    else tg.BackButton.hide();
  }

  function goLearnBack() {
    if (state.route !== "learn" || state.learnStep <= 0) return;
    state.learnStep -= 1;
    localStorage.setItem(LS_STEP, String(state.learnStep));
    renderLearn();
    syncLearnMainButton();
    syncBackUi();
    tg?.HapticFeedback?.impactOccurred?.("light");
  }

  /* —— Models —— */
  function architectureForCount(n) {
    if (n === 1) return "solo";
    if (n === 3) return "combo3";
    return n === 2 ? "invalid" : "combo3";
  }

  function normalizeUiMode(mode) {
    if (mode === "standard" || mode === "manual") return mode;
    if (mode === "power" || mode === "combo3") return "standard";
    return "manual";
  }

  function renderModes() {
    const box = $("modes");
    if (!box) return;
    const fallback = [
      {
        id: "standard",
        title: "ZeusCode",
        hint: "Стандартный стек · роли по силе моделей",
      },
      {
        id: "manual",
        title: "Ручной",
        hint: "Свой выбор: 1 модель (соло) или 3 модели (Combo-3)",
      },
    ];
    const modes = (state.modes.length ? state.modes : fallback).filter((m) =>
      ["standard", "manual"].includes(m.id)
    );
    box.innerHTML = modes
      .map(
        (m) => `<button type="button" class="mode${state.mode === m.id ? " on" : ""}" data-mode="${m.id}">
          <span class="mode-t">${escapeHtml(m.title)}</span>
          <span class="mode-h">${escapeHtml(m.hint || "")}</span>
        </button>`
      )
      .join("");
    box.querySelectorAll("[data-mode]").forEach((btn) => {
      btn.onclick = () => {
        state.mode = btn.dataset.mode;
        if (state.mode === "standard") {
          state.selected = new Set(PRESET.standard);
          state.architecture = "combo3";
        }
        renderModes();
        renderModels();
        syncFusionMainButton();
        tg?.HapticFeedback?.selectionChanged?.();
      };
    });
    $("models-block")?.classList.toggle("dim", false);
  }

  function renderModels() {
    const box = $("models");
    const hint = $("models-hint");
    const search = $("search-wrap");
    if (!box) return;

    state.mode = normalizeUiMode(state.mode);
    state.architecture = architectureForCount(state.selected.size || PRESET.standard.length);

    if (state.mode === "standard") {
      search?.classList.add("hidden");
      const ids = [...state.selected].length ? [...state.selected] : PRESET.standard;
      const roles = ROLE_BY_ARCH.combo3;
      if (hint) {
        hint.textContent =
          "Стандартный ZeusCode: роли (Architect / Builder / Finalizer) назначает сервер по силе моделей.";
      }
      if ($("pick-n")) $("pick-n").textContent = String(ids.length);
      box.innerHTML = ids
        .map(
          (id, i) => `<div class="model locked">
          <span class="check on-dot">${i + 1}</span>
          <span>
            <div class="model-t">${escapeHtml(friendlyTitle(id))}${roles[i] ? ` · ${escapeHtml(roles[i])}` : ""}</div>
            <div class="model-id">в стеке ZeusCode</div>
          </span>
        </div>`
        )
        .join("");
      return;
    }

    search?.classList.remove("hidden");
    const arch = architectureForCount(state.selected.size);
    const roles = ROLE_BY_ARCH[arch] || [];
    if (hint) {
      hint.textContent =
        "Отметь 1 или 3 модели. 1 = соло, 3 = Combo-3. Роли по силе моделей.";
    }
    if ($("pick-n")) $("pick-n").textContent = `${state.selected.size}/3`;

    const q = ($("q")?.value || "").trim().toLowerCase();
    let rows = state.catalog.filter((m) => m.id !== MODEL_TECH && !String(m.id).startsWith("gpt-5.5") && !String(m.id).startsWith("zeuscode"));
    if (q) {
      rows = rows.filter(
        (m) =>
          m.id.toLowerCase().includes(q) ||
          (m.title || "").toLowerCase().includes(q) ||
          (m.provider || "").toLowerCase().includes(q)
      );
    }
    if (!rows.length) {
      box.innerHTML = `<div class="hint">Ничего не найдено</div>`;
      return;
    }
    const selectedOrder = [...state.selected];
    box.innerHTML = rows
      .map((m) => {
        const on = state.selected.has(m.id);
        const idx = selectedOrder.indexOf(m.id);
        const role = idx >= 0 ? roles[idx] || "" : "";
        const inn = m.pricing?.input_per_1m;
        const out = m.pricing?.output_per_1m;
        const price =
          inn != null
            ? `${Number(inn).toFixed(2)} / ${Number(out || 0).toFixed(2)} ₽ за миллион`
            : "";
        return `<button type="button" class="model${on ? " on" : ""}" data-mid="${escapeHtml(m.id)}">
          <span class="check">${on ? String(idx + 1) : ""}</span>
          <span>
            <div class="model-t">${escapeHtml(m.title || m.id)}${role ? ` · ${escapeHtml(role)}` : ""}</div>
            ${price ? `<div class="model-p">${escapeHtml(price)}</div>` : ""}
          </span>
        </button>`;
      })
      .join("");
    box.querySelectorAll("[data-mid]").forEach((btn) => {
      btn.onclick = () => {
        const id = btn.dataset.mid;
        if (state.selected.has(id)) state.selected.delete(id);
        else {
          if (state.selected.size >= 3) {
            showErr("Максимум три модели");
            tg?.HapticFeedback?.notificationOccurred?.("error");
            return;
          }
          if (state.selected.size === 1) {
            // Jumping 1→2 is invalid product; keep allowing selection to 3.
          }
          state.selected.add(id);
        }
        state.architecture = architectureForCount(state.selected.size);
        showErr("");
        renderModels();
        syncFusionMainButton();
        tg?.HapticFeedback?.selectionChanged?.();
      };
    });
  }

  function syncFusionMainButton() {
    if (!tg?.MainButton) return;
    tg.MainButton.setText("Сохранить");
    tg.MainButton.show();
    tg.MainButton.enable();
  }

  function modeLabel(mode, architecture) {
    if (mode === "standard") return "ZeusCode";
    if (architecture === "solo") return "ручной · соло";
    if (architecture === "combo3") return "ручной · Combo-3";
    return "ручной";
  }

  async function saveFusion() {
    showErr("");
    try {
      state.mode = normalizeUiMode(state.mode);
      if (state.mode === "manual" && state.selected.size !== 1 && state.selected.size !== 3) {
        throw new Error("Выбери 1 модель (соло) или ровно 3 (Combo-3)");
      }
      tg?.MainButton?.showProgress?.();
      const body =
        state.mode === "standard"
          ? { mode: "standard", models: PRESET.standard }
          : { mode: "manual", models: [...state.selected].slice(0, 3) };
      const data = await api("/tg/fusion", {
        method: "PUT",
        body,
      });
      state.mode = data.mode || state.mode;
      state.architecture = data.architecture || architectureForCount((data.models || []).length);
      if (Array.isArray(data.models)) state.selected = new Set(data.models);
      showOk(`Сохранено: ${modeLabel(data.mode, data.architecture)}`);
      tg?.HapticFeedback?.notificationOccurred?.("success");
      tg?.MainButton?.hideProgress?.();
    } catch (e) {
      tg?.MainButton?.hideProgress?.();
      showErr(e.message || String(e));
      tg?.HapticFeedback?.notificationOccurred?.("error");
    }
  }

  /* —— Learn —— */
  const LEARN_COUNT = 7;

  function learnDots() {
    const box = $("learn-dots");
    if (!box) return;
    box.innerHTML = Array.from({ length: LEARN_COUNT }, (_, i) => {
      const cls =
        i < state.learnStep ? "learn-dot done" : i === state.learnStep ? "learn-dot on" : "learn-dot";
      return `<span class="${cls}"></span>`;
    }).join("");
  }

  async function copyText(text, okMsg, what) {
    try {
      await navigator.clipboard.writeText(text);
      if (okMsg) showOk(okMsg);
      else {
        showOk("");
        $("ok").classList.add("hidden");
      }
      tg?.HapticFeedback?.notificationOccurred?.("success");
      track("ui_copy", { what: what || "text", ok: true });
    } catch {
      showErr("Не вышло скопировать — выдели текст вручную");
      track("ui_copy", { what: what || "text", ok: false });
    }
  }

  function rememberKey(raw, prefix) {
    state.rawKey = raw;
    if (prefix && state.me) state.me.key_prefix = prefix;
    try {
      sessionStorage.setItem(SS_KEY, raw);
    } catch {
      /* ignore */
    }
    syncKeyUi();
  }

  function syncKeyUi() {
    const el = $("key-val");
    if (!el) return;
    if (state.rawKey) el.textContent = state.rawKey;
    else el.textContent = (state.me?.key_prefix || "zeus_") + "…";
  }

  async function ensureKey() {
    if (state.rawKey) return state.rawKey;
    try {
      const cached = sessionStorage.getItem(SS_KEY);
      if (cached && cached.startsWith("zeus_")) {
        state.rawKey = cached;
        syncKeyUi();
        return cached;
      }
    } catch {
      /* ignore */
    }
    try {
      const data = await api("/tg/key/rotate", { method: "POST", body: {} });
      rememberKey(data.api_key, data.key_prefix);
      return state.rawKey;
    } catch (e) {
      showErr(e.message || String(e));
      return null;
    }
  }

  async function reissueKey() {
    showErr("");
    const ok = window.confirm(
      "Старый ключ перестанет работать. Выпустить новый?"
    );
    if (!ok) return;
    try {
      tg?.MainButton?.showProgress?.();
      const data = await api("/tg/key/rotate", { method: "POST", body: {} });
      rememberKey(data.api_key, data.key_prefix);
      tg?.MainButton?.hideProgress?.();
      await copyText(data.api_key, "Новый ключ скопирован");
      if (state.route === "learn") renderLearn();
    } catch (e) {
      tg?.MainButton?.hideProgress?.();
      showErr(e.message || String(e));
    }
  }

  function renderLearn() {
    learnDots();
    syncBackUi();
    const root = $("learn-step");
    if (!root) return;
    // На шаге настроек ключ должен уже быть на экране — без кнопки «получить»
    if (state.learnStep === 2 && !state.rawKey && !state._keyLoading) {
      state._keyLoading = true;
      ensureKey().finally(() => {
        state._keyLoading = false;
        if (state.route === "learn" && state.learnStep === 2) renderLearn();
      });
    }
    const me = state.me || {};
    const base = me.base_url || "https://zeuscode.ru/v1";
    const prefix = me.key_prefix || "zeus_…";
    const bal = me.balance_rub ?? "—";
    const keyShow = state.rawKey || (state._keyLoading ? "загрузка…" : `${prefix}…`);
    const p = platform();
    const order = window.ZC_PLATFORM_ORDER || Object.keys(window.ZC_PLATFORMS || {});
    const yaml = clientConfig(base, state.rawKey || "zeus_ВАШ_КЛЮЧ", p);

    const platformPicker = () => {
      const mk = (id) => {
        const x = (window.ZC_PLATFORMS || {})[id];
        if (!x) return "";
        return `<button type="button" class="choice${
          state.track === id ? " on" : ""
        }" data-track="${escapeHtml(id)}">
            <span class="choice-t">${escapeHtml(x.title)}</span>
          </button>`;
      };
      return `<div class="choice-grid platforms">${order.map(mk).join("")}</div>`;
    };

    const visualDeck = () => {
      const visuals = p.visuals || [];
      if (!visuals.length) return "";
      const idx = Math.max(0, Math.min(state.visualIdx, visuals.length - 1));
      state.visualIdx = idx;
      const v = visuals[idx];
      const dots = visuals
        .map(
          (_, i) =>
            `<button type="button" class="viz-dot${i === idx ? " on" : ""}" data-viz="${i}" aria-label="Шаг ${
              i + 1
            }"></button>`
        )
        .join("");
      return `
        <div class="viz">
          <div class="viz-head">
            <span class="viz-k">Куда нажимать</span>
            <span class="viz-n">${idx + 1}/${visuals.length}</span>
          </div>
          <div class="viz-frame">
            <img class="viz-img" src="${escapeHtml(v.src)}?v=2" alt="${escapeHtml(v.caption || "")}" loading="eager" />
          </div>
          <p class="viz-cap">${escapeHtml(v.caption || "")}</p>
          <div class="viz-nav">
            <button type="button" class="btn-soft" data-act="viz-prev" ${idx === 0 ? "disabled" : ""}>←</button>
            <div class="viz-dots">${dots}</div>
            <button type="button" class="btn-soft" data-act="viz-next" ${
              idx >= visuals.length - 1 ? "disabled" : ""
            }>→</button>
          </div>
        </div>`;
    };

    const actionPlan = () => {
      const plan = p.plan || [];
      if (!plan.length) return "";
      const rows = plan
        .map(
          (row, i) => `<li class="plan-item">
            <span class="plan-n">${i + 1}</span>
            <span class="plan-body">
              <span class="plan-t">${escapeHtml(row.t)}</span>
              <span class="plan-d">${escapeHtml(row.d)}</span>
            </span>
          </li>`
        )
        .join("");
      return `
        <div class="plan">
          <div class="plan-h">План действий</div>
          <ol class="plan-list">${rows}</ol>
        </div>`;
    };

    const setupGuide = () => {
      const lis = (p.steps || []).map((s) => `<li>${s}</li>`).join("");
      const links = [];
      if (p.installUrl) {
        const labelById = {
          opencode: "Документация OpenCode",
          cline: "Скачать VS Code",
          kilo: "Скачать VS Code",
          goose: "Документация Goose",
          crush: "Crush на GitHub",
          openhands: "Документация OpenHands",
          windsurf: "Скачать Windsurf",
          zed: "Скачать Zed",
          librechat: "Документация LibreChat",
          openwebui: "Документация Open WebUI",
          openai_any: "zeuscode.ru",
          omniroute: "OmniRoute на GitHub",
          codex: "Документация Codex",
          claude: "Документация Claude Code",
          aider: "Как установить Aider",
          cursor: "Скачать Cursor",
        };
        const label =
          labelById[p.id] ||
          (p.kind === "cli" || p.kind === "web"
            ? "Документация"
            : p.kind === "ide"
              ? "Скачать IDE"
              : "Скачать VS Code");
        links.push(
          `<button type="button" class="btn-soft primary" data-act="open-url" data-url="${escapeHtml(
            p.installUrl
          )}">${label}</button>`
        );
      }
      if (p.extUrl) {
        links.push(
          `<button type="button" class="btn-soft" data-act="open-url" data-url="${escapeHtml(
            p.extUrl
          )}">Страница расширения</button>`
        );
      }
      const keyReady = Boolean(state.rawKey);
      const isOpenCode = p.id === "opencode";
      const isAider = p.configKind === "aider";
      const modelHint = clientModelHint(p);
      const lead = isOpenCode
        ? "Скопируй JSON ниже → файл <b>opencode.json</b>. Windows: <code>C:\\Users\\&lt;имя ПК&gt;\\.config\\opencode\\</code> · Mac/Linux: <code>~/.config/opencode/</code>. В пикере выбери <b>ZeusCode</b> (<code>zeuscode/zeuscode</code>). Режим (Пользовательский / Продвинутый / Набор) — только во вкладке «Модели»."
        : isAider
          ? "Скопируй <b>весь блок</b> ниже в терминал (export + команда). Aider не GUI: модель только как <code>--model openai/zeuscode</code> — просто <code>zeuscode</code> не работает. Без <code>--model</code> Aider уйдёт в gpt-4o."
          : "Один ключ · одна модель <b>zeuscode</b>. Zeus сам вызывает сколько нужно нейронок. Режим — только во вкладке «Модели». Соло-id из каталога — по желанию.";
      const pathWin = "C:\\Users\\<имя ПК>\\.config\\opencode\\opencode.json";
      return `
        <h1>${escapeHtml(p.setupTitle || p.title)}</h1>
        <p class="lead">${lead}</p>
        ${
          isOpenCode
            ? `<button type="button" class="cred-btn" data-act="copy-oc-path">
          <span class="cred-btn-k">Куда сохранить (Windows)</span>
          <span class="cred-btn-v">${escapeHtml(pathWin)}</span>
          <span class="cred-btn-h">нажми — скопировать путь</span>
        </button>`
            : ""
        }
        ${
          isOpenCode
            ? ""
            : `<button type="button" class="cred-btn" data-act="copy-base">
          <span class="cred-btn-k">Адрес</span>
          <span class="cred-btn-v">${escapeHtml(base)}</span>
          <span class="cred-btn-h">нажми — скопировать</span>
        </button>
        <button type="button" class="cred-btn" data-act="copy-key">
          <span class="cred-btn-k">Ключ</span>
          <span class="cred-btn-v">${escapeHtml(keyShow)}</span>
          <span class="cred-btn-h">${
            keyReady ? "нажми — скопировать (один раз · все модели)" : "загружается…"
          }</span>
        </button>
        <button type="button" class="cred-btn" data-act="copy-model">
          <span class="cred-btn-k">${isAider ? "Модель (флаг --model)" : "Модель в настройках"}</span>
          <span class="cred-btn-v">${escapeHtml(modelHint)}</span>
          <span class="cred-btn-h">${
            isAider
              ? "префикс openai/ обязателен · режим из вкладки «Модели»"
              : "один id · режим из вкладки «Модели»"
          }</span>
        </button>`
        }
        ${
          p.yaml
            ? `<div class="yaml-box">${escapeHtml(yaml)}</div>
               <div class="cred-actions">
                 <button type="button" class="btn-soft primary" data-act="copy-yaml">${
                   isOpenCode ? "Скопировать opencode.json" : "Скопировать весь config"
                 }</button>
               </div>`
            : ""
        }
        ${actionPlan()}
        ${visualDeck()}
        <details class="steps-more">
          <summary>Ещё раз текстом</summary>
          <div class="body"><ol style="padding-left:1.2rem;margin:8px 0 0;color:var(--hint)">${lis}</ol></div>
        </details>
        ${p.note ? `<p class="hint">${escapeHtml(p.note)}</p>` : ""}
        <div class="cred-actions">${links.join("")}</div>`;
    };

    const promptLead = () => {
      const leads = {
        opencode: "В OpenCode модель <b>zeuscode/zeuscode</b> · пиши задачу (режим уже из вкладки «Модели» в TG):",
        kilo: "В панели Kilo Code отправь задачу:",
        goose: "В goose session напиши задачу:",
        crush: "В Crush выбери модель Zeus и напиши задачу:",
        openhands: "В OpenHands поставь задачу / открой issue:",
        windsurf: "В панели Cline/Kilo внутри Windsurf отправь задачу:",
        zed: "В Agent panel Zed отправь задачу:",
        librechat: "В LibreChat выбери ZeusCode и отправь:",
        openwebui: "В Open WebUI выбери модель Zeus и отправь:",
        openai_any: "В своём окне разработки отправь задачу на Zeus:",
        omniroute: "В OmniRoute / подключённом CLI отправь задачу:",
        codex: "В Codex напиши задачу:",
        claude: "В Claude Code напиши задачу:",
        aider: "В терминале после запуска aider напиши задачу:",
        cursor: "В чате Cursor выбери модель и отправь:",
        cline: "В панели Cline отправь задачу:",
        roo: "Лучше открой Kilo/Cline — или в старом Roo отправь задачу:",
      };
      return leads[p.id] || "В чате Continue выбери ZeusCode и отправь:";
    };

    const steps = [
      () => `
        <h1>Привет. Это ZeusCode</h1>
        <p class="lead">Работает там, куда можно вставить ключ и адрес. Мы покажем куда — просто и по шагам.</p>
        <div class="body">
          <ul>
            <li>Один ключ · в окне разработки модель всегда <b>gpt-5.5</b></li>
            <li>Выберешь окно — покажем куда вставить ключ</li>
            <li>Пользовательский / Продвинутый / Набор — только во вкладке «Модели», не в Cursor/OpenCode</li>
          </ul>
        </div>`,
      () => `
        <h1>Окно разработки</h1>
        ${platformPicker()}`,
      () => setupGuide(),
      () => `
        <h1>Первая задача</h1>
        <p class="lead">${escapeHtml(promptLead())}</p>
        <div class="prompt-box">${escapeHtml(FIRST_PROMPT)}</div>
        <div class="cred-actions">
          <button type="button" class="btn-soft primary" data-act="copy-prompt">Скопировать задачу</button>
        </div>
        <p class="hint">Можно своей задачей — эта просто для проверки.</p>`,
      () => `
        <h1>Три режима</h1>
        <p class="lead">Это не отдельные модели в Cursor/OpenCode. Везде один id <b>gpt-5.5</b> — режим меняешь здесь.</p>
        <div class="body">
          <ul>
            <li><b>Пользовательский</b> — три лёгкие, для обычных дел</li>
            <li><b>Продвинутый</b> — три сильные, для сложных</li>
            <li><b>ZeusCode</b> — стандартный стек из 3 моделей</li>
            <li><b>Ручной</b> — 1 соло или 3 Combo-3</li>
          </ul>
        </div>
        <button type="button" class="btn-soft primary" data-act="open-fusion">Открыть модели</button>`,
      () => `
        <h1>Баланс</h1>
        <p class="lead">Старт с нуля. За ответы списывается с баланса — пополни, когда будешь готов.</p>
        <div class="stat-row">
          <div class="stat"><div class="stat-k">Сейчас</div><div class="stat-v">${escapeHtml(
            String(bal)
          )} ₽</div></div>
          <div class="stat"><div class="stat-k">Старт</div><div class="stat-v">0 ₽</div></div>
        </div>
        <p class="hint">В боте: /balance · пополнить можно в кабинете.</p>`,
      () => `
        <h1>Готово</h1>
        <p class="lead">Твоё окно: <b>${escapeHtml(p.title)}</b>. Модель: <b>ZeusCode</b>.</p>
        <div class="cred-actions">
          <button type="button" class="btn-soft primary" data-act="copy-prompt">Скопировать задачу</button>
          <button type="button" class="btn-soft" data-act="open-fusion">К моделям</button>
        </div>
        <p class="hint">Пройти снова — вкладка «Старт» или кнопка ?</p>`,
    ];

    root.innerHTML = steps[state.learnStep]();

    root.querySelectorAll("[data-track]").forEach((btn) => {
      btn.onclick = () => {
        const next = btn.dataset.track;
        if (state.track === next) return;
        state.track = next;
        state.visualIdx = 0;
        localStorage.setItem(LS_TRACK, state.track);
        track("ui_platform", { platform: state.track });
        // Picker step: toggle classes only (no full DOM rebuild).
        if (state.learnStep === 1) {
          root.querySelectorAll("[data-track]").forEach((b) => {
            b.classList.toggle("on", b.dataset.track === state.track);
          });
        } else {
          renderLearn();
        }
        tg?.HapticFeedback?.selectionChanged?.();
      };
    });
    root.querySelectorAll("[data-viz]").forEach((btn) => {
      btn.onclick = () => {
        state.visualIdx = parseInt(btn.dataset.viz, 10) || 0;
        track("ui_learn_step", {
          action: "visual",
          step: state.learnStep,
          visual: state.visualIdx,
          platform: state.track,
        });
        renderLearn();
        tg?.HapticFeedback?.selectionChanged?.();
      };
    });
    root.querySelectorAll("[data-act]").forEach((btn) => {
      btn.onclick = async () => {
        const act = btn.dataset.act;
        const visuals = platform().visuals || [];
        if (act === "viz-prev") {
          state.visualIdx = Math.max(0, state.visualIdx - 1);
          track("ui_learn_step", {
            action: "viz_prev",
            step: state.learnStep,
            visual: state.visualIdx,
          });
          renderLearn();
          tg?.HapticFeedback?.impactOccurred?.("light");
          return;
        }
        if (act === "viz-next") {
          state.visualIdx = Math.min(visuals.length - 1, state.visualIdx + 1);
          track("ui_learn_step", {
            action: "viz_next",
            step: state.learnStep,
            visual: state.visualIdx,
          });
          renderLearn();
          tg?.HapticFeedback?.impactOccurred?.("light");
          return;
        }
        if (act === "copy-base") return copyText(base, "Адрес скопирован", "base_url");
        if (act === "copy-oc-path") {
          return copyText(
            "C:\\Users\\<имя ПК>\\.config\\opencode\\opencode.json",
            "Путь скопирован — подставь своё имя ПК",
            "oc_path"
          );
        }
        if (act === "copy-model") {
          if (state.track === "opencode") {
            return copyText(
              clientConfig(base, state.rawKey || "zeus_ВАШ_КЛЮЧ", platform()),
              "opencode.json скопирован",
              "yaml"
            );
          }
          const p = platform();
          const hint = clientModelHint(p);
          const msg =
            p.configKind === "aider"
              ? "Скопировано — aider --model …"
              : "Скопировано — вставь в настройки";
          return copyText(hint, msg, "model");
        }
        if (act === "copy-prompt") return copyText(FIRST_PROMPT, "Задача скопирована", "prompt");
        if (act === "copy-yaml") {
          return copyText(
            yaml,
            state.track === "opencode" ? "opencode.json скопирован — вставь в файл" : "Config скопирован",
            "yaml"
          );
        }
        if (act === "copy-key") {
          const key = state.rawKey || (await ensureKey());
          if (!key) return;
          if (!state.rawKey) {
            state.rawKey = key;
            renderLearn();
          }
          return copyText(key, "Ключ скопирован — этого хватит один раз", "api_key");
        }
        if (act === "open-fusion") {
          setRoute("fusion");
          return;
        }
        if (act === "open-url") {
          const url = btn.dataset.url;
          track("ui_open_url", { url: String(url || "").slice(0, 200) });
          if (!url) return;
          if (tg?.openLink) tg.openLink(url);
          else window.open(url, "_blank");
        }
      };
    });
  }

  function syncLearnMainButton() {
    if (!tg?.MainButton) return;
    const last = state.learnStep >= LEARN_COUNT - 1;
    tg.MainButton.setText(last ? "Готово" : "Дальше");
    tg.MainButton.show();
    tg.MainButton.enable();
  }

  async function finishOnboarding() {
    localStorage.setItem(LS_DONE, "1");
    localStorage.setItem(LS_STEP, String(LEARN_COUNT - 1));
    try {
      await api("/tg/onboarding", {
        method: "POST",
        body: { done: true, track: state.track },
      });
      if (state.me) state.me.onboarding_done = true;
    } catch {
      /* local progress still kept */
    }
    showOk("Готово — можно работать");
    tg?.HapticFeedback?.notificationOccurred?.("success");
    setRoute("fusion");
  }

  function renderAdvisor() {
    const log = $("adv-log");
    if (!log) return;
    if (!state.advHistory.length) {
      log.innerHTML =
        `<div class="adv-bubble bot">Привет! Я советник ZeusCode. Спроси, какой режим взять или куда вставить ключ.</div>`;
      return;
    }
    log.innerHTML = state.advHistory
      .map((m) => {
        const pending = m.pending ? " pending" : "";
        const cls =
          m.role === "user" ? "adv-bubble me" : `adv-bubble bot${pending}`;
        const body =
          m.role === "user" ? escapeHtml(m.content) : formatAdvisorHtml(m.content);
        return `<div class="${cls}">${body}</div>`;
      })
      .join("");
    log.scrollTop = log.scrollHeight;
  }

  async function askAdvisor(text) {
    const q = (text || "").trim();
    if (!q || state.advBusy) return;
    state.advBusy = true;
    state.advHistory.push({ role: "user", content: q });
    state.advHistory.push({
      role: "assistant",
      content: "Секунду, думаю…",
      pending: true,
    });
    renderAdvisor();
    showErr("");

    // If the request takes longer, soft-upgrade status to research copy
    const thinkIdx = state.advHistory.length - 1;
    const researchTimer = setTimeout(() => {
      const row = state.advHistory[thinkIdx];
      if (row && row.pending) {
        row.content = "Подождите, делаю исследование…";
        renderAdvisor();
      }
    }, 2200);

    try {
      const prior = state.advHistory
        .slice(0, -2)
        .filter((m) => !m.pending)
        .slice(-8);
      const data = await api("/tg/advisor", {
        method: "POST",
        body: {
          message: q,
          history: prior,
        },
      });
      clearTimeout(researchTimer);
      const answer = data.answer || "На связи. Спроси ещё.";
      if (data.researched) {
        const row = state.advHistory[thinkIdx];
        if (row) {
          row.content = "Подождите, делаю исследование…";
          row.pending = true;
          renderAdvisor();
          await new Promise((r) => setTimeout(r, 350));
        }
      }
      state.advHistory[thinkIdx] = {
        role: "assistant",
        content: answer,
      };
      renderAdvisor();
      tg?.HapticFeedback?.notificationOccurred?.("success");
    } catch (e) {
      clearTimeout(researchTimer);
      showErr(e.message || String(e));
      state.advHistory.splice(thinkIdx, 1);
      state.advHistory.pop();
      renderAdvisor();
    } finally {
      clearTimeout(researchTimer);
      state.advBusy = false;
    }
  }

  async function onMainClick() {
    if (state.route === "advisor") return;
    if (state.route === "fusion") {
      await saveFusion();
      return;
    }
    if (state.learnStep < LEARN_COUNT - 1) {
      state.learnStep += 1;
      if (state.learnStep === 2) {
        state.visualIdx = 0;
        await ensureKey();
      }
      localStorage.setItem(LS_STEP, String(state.learnStep));
      track("ui_learn_step", {
        action: "next",
        step: state.learnStep,
        platform: state.track,
      });
      track("ui_main_button", { action: "learn_next", step: state.learnStep });
      renderLearn();
      syncLearnMainButton();
      syncBackUi();
      tg?.HapticFeedback?.impactOccurred?.("light");
      return;
    }
    track("ui_main_button", { action: "onboarding_finish", platform: state.track });
    tg?.MainButton?.showProgress?.();
    await finishOnboarding();
    tg?.MainButton?.hideProgress?.();
  }

  function bindTabs() {
    document.querySelectorAll(".seg-btn").forEach((btn) => {
      btn.onclick = () => setRoute(btn.dataset.route);
    });
    $("banner-learn") &&
      ($("banner-learn").onclick = () => {
        state.learnStep = 0;
        localStorage.setItem(LS_STEP, "0");
        setRoute("learn");
      });
    $("btn-learn-again") &&
      ($("btn-learn-again").onclick = () => {
        state.learnStep = 0;
        localStorage.setItem(LS_STEP, "0");
        setRoute("learn");
      });
    $("btn-copy-key") &&
      ($("btn-copy-key").onclick = async () => {
        const key = state.rawKey || (await ensureKey());
        if (key) await copyText(key, "Ключ скопирован", "api_key");
      });
    $("btn-rekey") &&
      ($("btn-rekey").onclick = () => {
        track("ui_rekey", { where: "models" });
        reissueKey();
      });
    $("adv-send") &&
      ($("adv-send").onclick = () => {
        const v = $("adv-input")?.value || "";
        if ($("adv-input")) $("adv-input").value = "";
        askAdvisor(v);
      });
    $("adv-input") &&
      ($("adv-input").onkeydown = (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          $("adv-send")?.click();
        }
      });
    document.querySelectorAll("[data-ask]").forEach((btn) => {
      btn.onclick = () => {
        track("ui_chip", { ask: String(btn.dataset.ask || "").slice(0, 120) });
        askAdvisor(btn.dataset.ask || "");
      };
    });
    $("learn-back") && ($("learn-back").onclick = goLearnBack);
    tg?.BackButton?.onClick?.(goLearnBack);
    window.addEventListener("hashchange", () => {
      setRoute(parseRoute(), { push: false });
    });
    window.addEventListener("popstate", () => {
      setRoute(parseRoute(), { push: false });
    });
  }

  async function boot() {
    try {
      tg?.ready?.();
      tg?.expand?.();
      tg?.enableClosingConfirmation?.();
      document.body.style.background = tg?.themeParams?.bg_color || "";

      bindTabs();

      if (!initData()) {
        $("hello").textContent = "Открой из Telegram-бота ZeusCode";
        showErr("Открой Mini App из бота, не в обычном браузере");
        state.route = "learn";
        setRoute("learn", { push: true });
        return;
      }

      const me = await api("/tg/me");
      state.me = me;
      const name = me.telegram?.first_name || me.telegram?.username || "друг";
      $("hello").textContent = `${name} · ${me.balance_rub ?? "—"} ₽`;
      state.modes = me.fusion?.modes || [];
      state.mode = normalizeUiMode(me.fusion?.mode || "standard");
      state.catalog = me.catalog || [];
      state.architecture = me.fusion?.architecture || architectureForCount((me.fusion?.models || []).length);
      if (Array.isArray(me.fusion?.models) && me.fusion.models.length) {
        state.selected = new Set(me.fusion.models);
      } else {
        state.selected = new Set(PRESET.standard);
      }
      {
        const migrate = {
          vscode: "continue",
          vscode_continue: "continue",
          vscode_cline: "cline",
          vscode_roo: "roo",
          studio: "unknown",
        };
        let t = localStorage.getItem(LS_TRACK) || "unknown";
        t = migrate[t] || t;
        state.track = (window.ZC_PLATFORMS || {})[t] ? t : "unknown";
        localStorage.setItem(LS_TRACK, state.track);
      }
      try {
        const cached = sessionStorage.getItem(SS_KEY);
        if (cached && cached.startsWith("zeus_")) state.rawKey = cached;
      } catch {
        /* ignore */
      }
      const savedStep = parseInt(localStorage.getItem(LS_STEP) || "0", 10);
      state.learnStep = Number.isFinite(savedStep)
        ? Math.max(0, Math.min(LEARN_COUNT - 1, savedStep))
        : 0;
      if (me.onboarding_done) localStorage.setItem(LS_DONE, "1");

      if ($("q")) {
        let searchTimer = null;
        $("q").oninput = () => {
          if (searchTimer) clearTimeout(searchTimer);
          searchTimer = setTimeout(() => renderModels(), 160);
        };
      }
      tg?.MainButton?.onClick?.(onMainClick);
      syncKeyUi();

      setRoute(parseRoute(), { push: true });
    } catch (e) {
      $("hello").textContent = "Ошибка";
      showErr(e.message || String(e));
    }
  }

  boot();
})();
