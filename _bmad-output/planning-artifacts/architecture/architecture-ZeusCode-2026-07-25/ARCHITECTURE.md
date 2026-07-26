---
title: ZeusCode — Role Routing Architecture Doc
status: final
created: 2026-07-25
updated: 2026-07-25
spine: ARCHITECTURE-SPINE.md
prd: _bmad-output/planning-artifacts/prds/prd-zeuscode-role-routing-verify-2026-07-24/prd.md
parent_spine: _bmad-output/planning-artifacts/architecture/architecture-ZeusCode-2026-07-22/ARCHITECTURE-SPINE.md
author: BMAD Architect (Winston) / Fast path
document_output_language: Russian
---

# ZeusCode — Role Routing Architecture Doc

Companion к `ARCHITECTURE-SPINE.md`. Spine = инварианты для CE; этот документ = карта внедрения на brownfield.

## 1. Цель и границы

Собрать **Role Routing + Verify/Escalate** поверх уже существующего Fusion gateway: один ключ, model id **`zeuscode`**, режимы только в TG, внутри — дешёвый small-path и редкий Pipeline v1.

**In:** FR-1…15, FR-17, FR-18, NFR-1…9, SM-1…6/8/9.  
**Out:** FR-16 e2e клиентов, Combo Studio, Path-кнопки, RACE-as-large, автодобавление моделей в custom.

Родительский Fusion spine (AD-1…18) **не выбрасываем** — расширяем AD-19…30.

## 2. Brownfield baseline (не ломаем)

Сегодня: `POST /v1/chat/completions` → fusion facade → Path/panel/verify → bill + Onestack.  
Уже есть: `power_score` (`model_power.py`), Mini-Verifier, sticky, Path enum, публичный id `zeuscode` в монолите.

| Есть | Становится |
| --- | --- |
| Path FAST/CASCADE/RACE/FULL | + `pipeline` = `small` \| `v1` \| `fallback_single` |
| Panel / Brief ad-hoc | Brief ≤3 + score-gated Architect/Test Author |
| Verify Mini | + Gate aggregate + Log Analyst JSON + Soft-Stop |
| Prefs simple/power/custom | без новых кнопок; Role table поверх стека |
| Onestack path/agents | + roles, pipeline, curator_model, gate, soft_stop |

## 3. Целевой runtime

```text
Edge: auth → balance → alias→zeuscode → prefs
  → Policy: scrub → classify(size, task_kind, confidence, 2nd signal) → Path lattice K → kill/mode clamp
  → Roles: resolve stack → curator → Role→Model table → pick pipeline
  → Execute:
       small:            1–2 Doers → Mini → Log? → Gate → Escalate≤2?
       fallback_single:  curator full answer → Mini → Log? → Gate → Escalate≤2?
       v1:               Architect Brief≤3 → Test Author → mid Doers (parallel)
                         → 1× test-fix → file-aware merge → Log? → Gate → Escalate≤2?
  → Bill FusionResult + Onestack
```

Нормативные таблицы: PRD addendum §J–N (не дублируем здесь).

## 4. Модули

| Module | Responsibility |
| --- | --- |
| `fusion/policy.py` | size/task_kind/2nd signal, Path lattice, kill, mode clamp |
| `fusion/roles.py` **target** | Role→Model v1, curator≡Leader (AD-32), score gates |
| `fusion/pipeline.py` **target** | sole final writer `small`/`v1`/`fallback_single` (AD-20) |
| `fusion/brief.py` | validate Brief ≤3 components |
| `fusion/merge.py` **target** | file-aware merge; conflict → strong |
| `fusion/log_analyst.py` **target** | DeepSeek JSON; skip = N/A not RED (AD-27) |
| `fusion/verify.py` | Mini-Verifier + Gate signals |
| `fusion/panel.py` | upstream doer/Path calls (без финального `pipeline`) |
| `fusion/_monolith.py` | brownfield body — постепенно выносить |
| `fusion/model_power.py` | `power_score` + добавить **`TEST_AUTHOR_MIN=950`** |
| `fusion/types.py` | FusionResult + Onestack fields (AD-28) |
| `routers/chat.py` | wire / bill / SSE — без role logic |
| TG guides | FR-17 connect only |

## 5. Ключевые контракты

### 5.1 Pipeline pick (жёстко)

**second_signal** (любой один): architecture/migrate lexicon · multi-file · landing-from-scratch · explicit heavy.  
`confidence < 0.6` ≠ second_signal (только ярлык `size=large`).

| Условие | `pipeline` |
| --- | --- |
| kill или simple | не `v1` (FAST/cheap; small path) |
| нет large+second_signal | `small` |
| large+second_signal+power/custom+есть ≥950 | `v1` |
| large+second_signal+power/custom+нет ≥950 | `fallback_single` |

`pipeline.py` — единственный финальный writer; Onestack несёт и `path`, и `pipeline`.

### 5.2 Brief (v1)

```json
{
  "components": [
    {
      "id": "c1",
      "role": "doer_ui",
      "goal": "...",
      "acceptance_one_liner": "...",
      "files_hint": ["src/App.tsx"]
    }
  ]
}
```

`len(components) ≤ 3`. Invalid / empty → `fallback_single` (FR-12).

### 5.3 Log Analyst

Вход: goal + log tail + files (+ short last_assistant).  
Выход: `{critical, summary, fix_hint, confidence}`.  
Битый JSON → RED. Custom без DeepSeek → **skip**.

### 5.4 Soft-Stop

HTTP 200, непустое тело (max power_score, tie→latest), короткая строка человеку, Onestack `gate=RED`, `soft_stop=true`.

### 5.5 FusionResult (additive)

К AD-14 добавить потребление: `pipeline`, `curator_model`, `roles`, `models_by_role`, `gate`, `gate_reasons`, `escalate_count`, `soft_stop`, `task_kind`, `size`, `role_table`.

## 6. Данные / флаги

- Sticky: без изменений смысла (leader/stack); **не** хранит pipeline как источник истины на следующий запрос.
- Kill / shadow / canary: parent AD-9; kill отключает Pipeline v1.
- `TEST_AUTHOR_MIN`: константа/setting без UX.

## 7. Клиентская поверхность

| Поверхность | Правило |
| --- | --- |
| IDE clients | model=`zeuscode`, Base/key по FR-17 research |
| TG «Модели» | simple / power / custom — единственный mode UX |
| Запрещено | Path/каскад/гонка/усилить кнопки; mode-suffixed model ids в пикерах |

## 8. Фазы внедрения (для CE)

1. **Contracts** — `TEST_AUTHOR_MIN`, FusionResult/Onestack fields, Role table, curator≡Leader.  
2. **Small path + Gate** — doer cap≤2, Mini, Log Analyst (skip=N/A), Escalate/Soft-Stop.  
3. **fallback_single** — curator full answer (решение A).  
4. **Pipeline v1** — Brief → Test Author → doers → test-fix → file-aware merge.  
5. **Prefs/docs** — FR-17 guides regression; no new buttons.  
6. **Eval** — SM-1/2/3/6/9 fixtures (не FR-16).

## 9. Риски → архитектурный ответ

| Риск | Ответ |
| --- | --- |
| Дорогой default | AD-22 hard trigger + SM-9 |
| Custom без сильной модели | AD-23 fallback_single |
| Расхождение API у doers | AD-24 Brief + AD-26 conflict merge |
| Log в custom без DeepSeek | AD-27 skip |
| Drift billing | AD-28 / AD-14 branches |
| IDE ест Soft-Stop как OK | CE story: явная RED-строка + Onestack; поведение клиентов = FR-16 later |

## 10. Open / assumptions

- `[ASSUMPTION]` `TEST_AUTHOR_MIN=950` калибруется без UX.  
- `[ASSUMPTION]` ×4 speedup — гипотеза, не exit criterion.  
- Детали детектора traceback и точная JSON schema test-check — Deferred → stories.

## 11. Связанные артефакты

- Spine: `ARCHITECTURE-SPINE.md` (AD-19…30 + inherited AD-1…18)  
- PRD: `prd-zeuscode-role-routing-verify-2026-07-24/`  
- Connect: `docs/CLIENT_API_CONNECT_RESEARCH.md`  
- Parent: `architecture-ZeusCode-2026-07-22/`
