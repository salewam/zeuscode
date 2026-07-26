# FR-17 Connect Coherence Review

**Scope:** FR-17 + FR-4 + UJ-3 vs `addendum.md` §G2, `docs/CLIENT_API_CONNECT_RESEARCH.md`, spot-check `frontend/tg-platforms.js` + `frontend/tg-miniapp.js` (2026-07-25).

## Verdict

**Mostly coherent — FR-17 intent is implemented in TG onboarding code.** Spot-checks for fake Simple/Power/Custom model ids, Cursor BYOK caveats, Claude base without `/v1`, and OpenCode `zeuscode/zeuscode` match PRD/G2/research. Residual gaps: research matrix does not cover every `ZC_PLATFORM_ORDER` id; one Goose generator path still embeds `/chat/completions` in `base_url`; OpenCode *copy* in `tg-platforms.js` understates the qualified model id. No evidence that client pickers still advertise `zeuscode-simple|power|custom`.

## Findings

- **[low]** **OpenCode plan copy vs canon** — `tg-platforms.js` plan step says «model = zeuscode (один id)»; FR-17/research require default `model: "zeuscode/zeuscode"`. Generated JSON in `tg-miniapp.js` (`opencodeJson`) is correct; UI text is slightly imprecise for SM-8 literal readers.

- **[medium]** **Goose path B in generated config** — `clientConfig` comments for Goose path B set `"base_url": "${root}/chat/completions"`, while research invariant #2 forbids `/chat/completions` in Base URL for OpenAI-compat clients (Cline/Kilo/OpenCode called out). Path A (`OPENAI_HOST=${root}`) aligns. Medium-confidence Goose drift is acknowledged in research, but path B teaches a pitfall the matrix warns against.

- **[medium]** **Research matrix ⊂ onboarding list** — `ZC_PLATFORM_ORDER` includes `windsurf`, `roo`, `unknown` (onramp) with no dedicated rows in `CLIENT_API_CONNECT_RESEARCH.md`. Guides exist (`windsurf` → Cline/Kilo `configKind`; `roo` → redirect); process rule «research doc first» is not closed for these ids if official client docs change.

- **[low]** **`frontend/app.js` parity** — G2 names `app.js` generators alongside Mini App; Cursor comment warns against `zeuscode-simple`; OpenCode emits `zeuscode/zeuscode`. Dead local arrays `simple`/`power` in OpenCode block are prefs labels only (not emitted model ids) — harmless but noisy for reviewers.

- **[low]** **Negative mentions of legacy ids** — `tg-miniapp.js` / `app.js` Cursor snippets say «не … zeuscode-simple» (anti-pattern), not advertising separate products. Consistent with FR-4 consequence «UI/гайды — нет».

- **Pass (spot-check)** **No Simple/Power/Custom in pickers** — OpenCode builds a single `zeuscode` provider entry; fusion mode comes from TG prefs naming only. No grep hits advertising `zeuscode-power|custom` as connect models.

- **Pass (spot-check)** **Cursor** — `tg-platforms.js` note/steps + `tg-miniapp.js` `configKind: cursor`: Cline/Kilo first; native Override low confidence; Responses→`/chat/completions`; Add model → `zeuscode` only (not `gpt-*`). Matches research critical finding #1.

- **Pass (spot-check)** **Claude Code** — `ANTHROPIC_BASE_URL` uses host without `/v1` (`host = root.replace(/\/v1$/, "")`); discovery env documented. Matches FR-17 exception and research #3.

- **Pass (spot-check)** **OpenCode** — `model: "zeuscode/zeuscode"`, `@ai-sdk/openai-compatible`, `options.baseURL` to `…/v1`, comments state TG-only mode. Matches FR-17 exception and research row.

## Gaps vs research matrix

| Platform / id | Research row | TG guides today | Divergence |
|---------------|--------------|-----------------|------------|
| OpenCode | high · `zeuscode/zeuscode` | JSON correct; plan text says plain `zeuscode` | Copy only |
| Cline, Kilo, Continue, Aider, Zed, Crush, OpenHands, LibreChat, Open WebUI, Claude, Cursor, Codex, OmniRoute, Goose | in matrix | Matching `configKind`, URL/key/model exceptions, pitfalls where noted | **Goose path B** `/chat/completions` in commented JSON |
| **Windsurf** | *absent* | Cline/Kilo inside IDE (`configKind: kilo`) | Not in matrix; pragmatic fallback |
| **Roo Code (legacy)** | *absent* | Redirect to Kilo/Cline | Intentional deprecation, not researched |
| **unknown** (onramp) | *absent* (Continue implied) | Continue `configKind` | OK if Continue row is proxy |
| **openai_any** | *absent* (generic) | Universal OpenAI-compat curl/SDK | Acceptable escape hatch |

**FR-4 / UJ-3 alignment:** Product modes `simple|power|custom` remain TG-only; client surface messaging («режим только в TG «Модели»») is repeated across OpenCode/Cursor/unknown leads in `tg-miniapp.js` — consistent with FR-4 and UJ-3 edge case.

**SM-8:** Per-id guides include Base URL + key + model (`zeuscode` or FR-17 exceptions) and do not promote legacy fusion model ids; only Goose path B and OpenCode plan wording weaken strict «matches research verbatim» interpretation.
