---
title: Zeus Fusion — Architecture Doc
status: final
created: 2026-07-22
updated: 2026-07-22
spine: ARCHITECTURE-SPINE.md
prd: _bmad-output/planning-artifacts/prds/prd-zeuscode-fusion-2026-07-22/prd.md
author: BMAD Architect (Winston) / Fast path
document_output_language: Russian
---

# Zeus Fusion — Architecture Doc

Companion к `ARCHITECTURE-SPINE.md`. Spine = инварианты для CE; этот документ = карта внедрения на brownfield ZeusCode.

## 1. Цель и границы

Собрать **coding compound brain** под стабильным id `zeus/fusion`: classify → Path → verify/Judge → честный billing → Onestack, без marketplace и без server-side RAG.

**In:** FR-1…FR-26, FR-28…FR-37 (PRD MVP + §6.4 canary).  
**Out:** DUAL/Tradeoff/Presets, Elo writeback, TOOL-FULL, Redis (пока).

## 2. Brownfield baseline (не ломаем)

Сегодня: `POST /v1/chat/completions` → `is_fusion_model` → `iter_fusion` / `run_fusion` → `upstream.chat_completions` → bill + optional publish.

| Есть | Становится |
| --- | --- |
| `fusion_mode` fast\|full (1↔3) | Path `FAST\|CASCADE\|RACE\|FULL` |
| `classify_smart` + regex | + complexity band, design_lexicon, Effort +1 |
| Panel 3 + Judge | + Mini/Aspect verify, rank-then-fuse, RACE |
| `users.fusion_pref` | + Effort, Kill-Switch, Tradeoff later |
| Onestack agents/tokens | + billable states, `policy_path`, closed `routed_by` |
| Нет session store | sticky table (AD-7) |

## 3. Целевой runtime (логический)

```text
Edge: auth → balance → alias → prefs merge
  → Policy: scrub → classify → Effort+1 → Path table → MoR tip → mode clamp
       ↳ Shadow: log candidate vs baseline_id; serve flag path
  → Execute Path:
       FAST | CASCADE(+escalate map) | RACE(+both-fail) | FULL(panel→aspect→τ→rank→judge)
  → Bill states + Onestack (path=final)
  → Publish hook (HTML) if applicable
```

Детали предикатов Path / fixtures / Soft-Stop — **PRD FR-28/8/9/14** (не дублируем таблицы здесь).

## 4. Модули

| Module | Responsibility |
| --- | --- |
| `fusion/policy.py` | classify, lexicon_v1, Effort, Path first-match, MoR local scores, clamps, shadow compare |
| `fusion/panel.py` | Path executors, Brief, cancel/Soft-Stop coordination |
| `fusion/verify.py` | Mini-Verifier JSON, Aspect correctness/completeness |
| `fusion/judge.py` | rank-then-fuse, structured Judge, anti-bias checks |
| `fusion/session.py` | sticky CRUD by session_id |
| `fusion/metrics.py` | routed_by helpers, path rates |
| `fusion/__init__.py` | `iter_fusion` / `run_fusion` facade (compat) |
| `routers/chat.py` | wire, SSE, `_bill_and_enrich`, publish |
| `upstream.py` | adapters unchanged |

Миграция: вынести из монолита `fusion.py` без смены публичного поведения aliases.

## 4.1 FusionResult (Execute → Bill)

Обязательный handoff (AD-14):

```text
FusionResult
  path, policy_path, escalate_from?, routed_by
  phase, complexity, leader, trace_id
  branches[]: model, role, usage, billable_state
  answer
```

Внутри `fusion/*` только Path enum (AD-15). `fast|full` — только Edge/Shadow adapter.

Leader: один pick на запрос; sticky пишется в конце фактическим Leader (AD-16).

## 5. Данные

### 5.1 Sticky session (new)

| Field | Type |
| --- | --- |
| session_id | PK string |
| user_id | FK |
| leader_model | string |
| stack_json | text |
| phase_meta | string |
| expires_at | datetime |

TTL 5–15 мин inactivity (PRD). Path **игнорирует** phase_meta.

### 5.2 Flags / baseline (new or config)

- `fusion_flag`: shadow \| canary_pct \| kill  
- `baseline_id`: hash(policy code + lexicon_v1 + panel constants)

### 5.3 Usage / Onestack (extend)

Per-agent: tokens, latency, billable_state, role.  
Top-level: `path`, `policy_path`, `escalate_from?`, `phase`, `complexity`, `routed_by`, `product_mode`.

## 6. Path execution notes (eng)

| Path | Sketch |
| --- | --- |
| FAST | 1 Leader + failover list |
| CASCADE | cheap → Mini-Verify → escalate map (PRD FR-8) |
| RACE | parallel cheap+strong; first годный; both-fail → FULL/Soft-Stop/disaster |
| FULL | A/B/C roles → Aspects → τ early-exit? → rank top-K → Judge |

MoR: local `s_quality/s_cost/s_latency` (PRD formulas); tip escalate one step max.

## 7. Billing

- Charge all billable states except `cancelled_no_tokens`.  
- Include verifier/Judge/cascade attempts; classify/MoR LLM only if separate call.  
- Drift: token ledger exact; ₽ ≤ 1 minor unit.

## 8. Observability & rollout

- `trace_id` на запрос; histogram `routed_by` / Path by Phase.  
- Alerts min: verifier always-OK, billing drift, dead models.  
- Rollout: Shadow → 10% → 50% → 100%; exit = PRD §6.4 + Eval fixtures.  
- Publish regression на prompt/Judge/Brief/sanitize/adapt releases.

## 9. Security

- Scrub keys/bearer/private-key/email-like before upstream (FR-21).  
- Opt-out raw prompt retention at key/account (existing policy extend).  
- No new auth; API keys as today.

## 10. Deployment / ops envelope

- Same VPS/process as ZeusCode API (uvicorn).  
- Sticky on SQLite OK for single-node MVP; multi-node → Deferred Redis.  
- Budgets (timeout/concurrency/rate) in Settings — numbers ops before canary.  
- Eval suite: repo scripts + CI/nightly; baseline snapshot artifact.

## 11. FR → module checklist

| FR cluster | Module |
| --- | --- |
| FR-28/3/4/5/37 | policy |
| FR-7/8/9/10/14 | panel |
| FR-12/31 | verify |
| FR-13/10 rank | judge |
| FR-16 | session |
| FR-19/20 | chat bill + Onestack builder |
| FR-18/25 | flags + eval |
| FR-26 | publish |
| FR-29/15/17 | policy+panel+Settings |

## 12. Open (не блокер spine)

1. Конкретные ms/concurrency numbers.  
2. Judge model id + SM-V frontier id в `eval_baseline.json`.  
3. Когда выносить panel lists в Settings.

## 13. Next

1. `bmad-create-epics-and-stories` (CE) от PRD + этого spine.  
2. Incremental refactor: `fusion/` package behind facade.  
3. Shadow flag + Path enum в Onestack до включения RACE/FULL policy.

---

*Invariants: see `ARCHITECTURE-SPINE.md` (AD-1…AD-13). Product rules: PRD.*
