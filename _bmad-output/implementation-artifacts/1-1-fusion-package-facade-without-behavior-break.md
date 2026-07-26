# Story 1.1: Fusion package facade without behavior break

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a Zeus engineer,
I want `backend/app/fusion/` with a facade re-exporting `iter_fusion` / `run_fusion` (and the full brownfield import surface),
so that we can migrate Path logic into package modules without breaking Cursor/TG/API callers.

## Acceptance Criteria

1. **Given** existing `chat.py` and TG call `run_fusion` / `iter_fusion`  
   **When** the facade package is introduced and monolith `fusion.py` is moved behind the package  
   **Then** `backend/tests/test_fusion_routing.py` passes and `from app.fusion import …` works for all current callers  
   **And** `/v1/chat/completions` with `model: "zeus/fusion"` still returns a non-empty answer (smoke / manual if live)

2. **Given** any module under `backend/app/fusion/`  
   **When** imports are inspected (static grep / AST)  
   **Then** no `fusion/*` file imports `routers.*` (AD-6, AD-10)

3. **Given** aliases `zeus/fusion`, `zeus/fusion-fast`, `zeus/fusion-full` and prefs helpers  
   **When** facade ships  
   **Then** runtime behavior of routing/classifier/panel/think-frames is unchanged (no Path rewrite, no FusionResult, no scrub move)

## Tasks / Subtasks

- [ ] **T1 — Package skeleton (AC: #1, #2)**
  - [ ] Create `backend/app/fusion/` package (cannot coexist with `app/fusion.py` — remove/rename module)
  - [ ] Add inert stubs: `policy.py`, `panel.py`, `verify.py`, `judge.py`, `session.py`, `metrics.py` (empty or docstring-only; **not wired**)
  - [ ] Move monolith body unchanged into `backend/app/fusion/_monolith.py` (or equivalent private module name)

- [ ] **T2 — Public facade (AC: #1)**
  - [ ] `__init__.py` re-exports full brownfield surface (see Dev Notes → Public API)
  - [ ] Keep signatures of `iter_fusion` / `run_fusion` identical (kwargs + event/dict shape)
  - [ ] Prefer **zero edits** to `chat.py`, `telegram_bot.py`, `me.py`, `tg_miniapp.py`, `auth.py`

- [ ] **T3 — Patch-path honesty (AC: #1)**
  - [ ] Fix or preserve unittest patches that target `app.fusion.upstream` / `app.fusion._CLASSIFIER_TIMEOUT_S`
  - [ ] Either update patches to `app.fusion._monolith.*` **or** keep symbols bindable where tests expect (document choice in Completion Notes)

- [ ] **T4 — Guardrails (AC: #2, #3)**
  - [ ] Grep: no `from app.routers` / `import app.routers` under `fusion/`
  - [ ] Do not move billing/SSE/publish into fusion
  - [ ] Do not implement FusionResult / Path enum / scrub-once / sticky (Stories 1.2–1.4, Epic 2–4)

- [ ] **T5 — Verify (AC: #1)**
  - [ ] `PYTHONPATH=backend python -m pytest backend/tests/test_fusion_routing.py -q`
  - [ ] Import smoke of callers (`chat`, `me`, `tg_miniapp`, `auth`, `telegram_bot` symbols)
  - [ ] Optional: `backend/scripts/smoke_fusion_stack.py` if upstream available

## Dev Notes

### Goal / non-goal

| In scope | Out of scope |
|---|---|
| Package + facade + monolith move | FusionResult / billable states (1.2) |
| Stub module files for AD-6 tree | Onestack Path fields / `routed_by` rewrite (1.3) |
| Preserve all `from app.fusion import X` | Scrub-once + Brief contract (1.4) |
| Keep AD-6/10 import direction | Path policy, Mini-Verifier, Judge, sticky, Shadow |

### Architecture compliance (must follow)

- **AD-1:** One Policy→Execute→Bill pipeline; TG may call `iter_fusion`/`run_fusion` — no second Path stack.
- **AD-2:** Public id stays `zeus/fusion` (+ legacy aliases).
- **AD-6:** New Path logic under `backend/app/fusion/{policy,panel,verify,judge,session,metrics}`; chat wires only; **`fusion/*` ↛ `routers.*`**. Facade re-export OK during migration.
- **AD-10 `[ADOPTED]`:** `routers → fusion → {upstream, catalog, cost helpers}`; publish only post-answer from chat. Policy ↛ Judge.
- **AD-14/15/17:** Scaffold awareness only — **do not implement** FusionResult, Path-enum serving rewrite, or scrub re-home in this story.
- **AD-6′ (review end-state):** Sole import surface `app.fusion` package; monolith not a parallel module.

[Source: `_bmad-output/planning-artifacts/architecture/architecture-ZeusCode-2026-07-22/ARCHITECTURE-SPINE.md` AD-6/10]  
[Source: `_bmad-output/planning-artifacts/epics.md` Epic 1 / Story 1.1]

### Current state (brownfield)

- Monolith: `backend/app/fusion.py` (~1538 lines), **no classes**.
- Deps today: `upstream`, `catalog`, `model_policy`, `fastapi.HTTPException`. **Does not** import routers/publish/billing.
- Edge owns SSE (`_fusion_live_sse`), `_bill_and_enrich`, `publish.enrich_answer_with_publish` in `routers/chat.py` — **leave there**.

**Key signatures (preserve):**

```python
async def iter_fusion(
    *,
    messages: list[dict[str, Any]],
    user: Any | None = None,
    models: list[str] | None = None,
    judge: str | None = None,
    mode: str | None = None,
    model_id: str | None = None,
    zeus: dict[str, Any] | None = None,
    show_thinking: bool | None = None,
):
    """Yield events: {kind: think|answer|done, text?, data?}"""

async def run_fusion(...) -> dict[str, Any]:
    # drains iter_fusion; raises HTTPException(502) if empty
```

### Recommended file structure

```text
backend/app/fusion/
  __init__.py          # PUBLIC facade re-exports
  _monolith.py         # moved fusion.py body UNCHANGED
  policy.py            # stub (Epic 2)
  panel.py             # stub (Epic 2/3)
  verify.py            # stub
  judge.py             # stub
  session.py           # stub (Epic 4)
  metrics.py           # stub
# DELETE backend/app/fusion.py after move (package wins on import)
```

### Public API — must remain `from app.fusion import …`

**Minimum (arch):** `iter_fusion`, `run_fusion`

**Brownfield callers (must keep):**

| Symbol | Callers |
|---|---|
| `iter_fusion` | `routers/chat.py` |
| `run_fusion` | `chat.py`, `telegram_bot.py`, smoke |
| `is_fusion_model` | chat, telegram_bot, tg_miniapp |
| `apply_user_fusion_pref` | chat, telegram_bot |
| `sanitize_messages` | chat (solo path) |
| `DEFAULT_PRODUCT_MODE`, `PRODUCT_MODES` | me, tg_miniapp, telegram_bot, auth |
| `normalize_product_mode`, `parse_fusion_models_json` | same |
| `classify_query`, `resolve_routing`, `resolve_routing_ex`, `resolve_mode` | tests, smoke |
| `classify_smart`, `classify_task`, `classifier_features`, `apply_classifier_guardrails`, `regex_classify` | tests |
| `pick_leader`, `order_panel_leader_first` | tests |
| `_parse_classifier_json` | tests (private but imported) |
| `FUSION_IDS`, `_CLASSIFIER_TIMEOUT_S` | identity / patches |

Also re-export anything else tests patch or smoke needs so import graph stays stable.

### Forbidden / anti-patterns

- `fusion/*` → `routers.*`
- Moving bill/SSE/publish into fusion
- Wiring stub `policy/panel/...` into `iter_fusion` in this story
- Dual Path semantics (chat on new pipeline + TG on old) under same names
- Greenfield rewrite of classifier/panel logic “while moving files”
- Leaving both `app/fusion.py` and `app/fusion/` (broken/ambiguous imports)

### Testing requirements

```bash
cd /Users/money/Desktop/Projects/ultra-mode-mvp
PYTHONPATH=backend python -m pytest backend/tests/test_fusion_routing.py -q

PYTHONPATH=backend python -c "
from app.fusion import iter_fusion, run_fusion, is_fusion_model, apply_user_fusion_pref
from app.fusion import PRODUCT_MODES, DEFAULT_PRODUCT_MODE, sanitize_messages
assert is_fusion_model('zeus/fusion')
print('import ok')
"
```

Optional live: `backend/scripts/smoke_fusion_stack.py`.

**Done lies to avoid:** “package created” without deleting monolith module; stubs that change routing; tests green only because tests were deleted.

### Project Structure Notes

- Run path: `PYTHONPATH=backend`, `uvicorn app.main:app --app-dir backend` (see `scripts/run_api.sh`).
- Absolute imports only: `from app.fusion import …` — no relative caller imports today.
- Root `requirements.txt`; no installed package for `app`.

### References

- Epics: `_bmad-output/planning-artifacts/epics.md` — Epic 1, Story 1.1
- Arch spine: `…/architecture-ZeusCode-2026-07-22/ARCHITECTURE-SPINE.md` — AD-6, AD-10, package tree
- Arch companion: `…/ARCHITECTURE.md` — module map § fusion/
- PRD: `…/prds/prd-zeuscode-fusion-2026-07-22/prd.md` — FR-1, FR-37, public `zeus/fusion`
- Code: `backend/app/fusion.py`, `backend/app/routers/chat.py`, `backend/app/telegram_bot.py`
- Tests: `backend/tests/test_fusion_routing.py`

### Git intelligence

Recent commits are product/infra merges, not fusion Path work. Treat brownfield `fusion.py` + `test_fusion_routing.py` as the source of truth for behavior.

### Previous story intelligence

N/A — first story in Epic 1.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
