# Epic 1 — независимый архитектурный аудит

**Date:** 2026-07-22  
**Scope:** Stories 1.1–1.4 vs ARCHITECTURE-SPINE AD-6/8/10/14/15/17 + epics AC  
**Tests re-run:** `test_fusion_routing|result|scrub|onestack` → **42 passed**

## Вердикт

| Слой | Оценка |
|---|---|
| Story AC (epics.md) | **PASS с долгом** |
| Architecture AD (spine) | **PARTIAL — не AD-Done** |
| Gate «Epic 1 закрыт по архитектуре» | **НЕТ** (accept-with-debt) |

---

## Stories

| Story | AC | Комментарий |
|---|---|---|
| **1.1** Facade | **PASS** | Пакет `fusion/`, нет `fusion.py`, facade re-export, тесты/imports green, `fusion↛routers` |
| **1.2** FusionResult/Bill | **PARTIAL** | FR + states + `cancelled_no_tokens=₽0` + Path не из tokens — OK. Жив agents-only fallback в `_charge_amounts` |
| **1.3** Onestack/routed_by | **PARTIAL** | `path/policy_path/escalate_from/routed_by`; `legacy_*`≠`forced_*` — OK. Serving внутри fusion всё ещё `fast\|full` (AD-15) |
| **1.4** Scrub+Brief | **PASS** (узкий) | `prepare_messages_for_policy` once; Brief = last_assistant+errors+goal. Solo-path scrub вне AC |

---

## Architecture Decisions

| AD | Вердикт | Разрыв |
|---|---|---|
| **AD-6** package | **PARTIAL** | Дерево модулей есть; исполнение всё ещё в `_monolith.py` (~2k LOC) |
| **AD-8** billing/Onestack | **PARTIAL** | Billable states + FR sync OK; Soft-Stop не на всём brownfield; agents fallback |
| **AD-10** deps | **PASS*** | `fusion↛routers` clean; `publish_gate→publish` — спорно, не Epic1 core |
| **AD-14** FusionResult | **PARTIAL** | Поля FR есть; `BranchUsage.model_id` vs spine `model`; flat tokens vs nested `usage`; **agents charge path** в chat |
| **AD-15** Path taxonomy | **FAIL** | Serving stack/`resolved`/`fusion_mode` = `fast\|full` deep in fusion; Path в основном на egress |
| **AD-17** scrub | **PARTIAL→PASS** | Once на fusion happy path; публичный `scrub_*` + solo без scrub |

\*AD-10 для Epic1 handoff: PASS по routers boundary.

---

## Adversarial checks

| # | Check | Result |
|---|---|---|
| 1 | fusion → routers | **PASS** (0 imports) |
| 2 | FR shape vs AD-14 | **PARTIAL** (`model_id`, flat tokens) |
| 3 | cancelled_no_tokens = ₽0 | **PASS** |
| 4 | Path not from tokens | **PASS** |
| 5 | legacy_* ≠ forced_* | **PASS** |
| 6 | Scrub once | **PARTIAL** (fusion once; perimeter soft) |
| 7 | Brief contract | **PASS** |
| 8 | AD-15 internal Path-only | **FAIL** |
| 9 | Parallel agents charge | **FAIL** (fallback без FR) |

---

## Долг (приоритет фикса)

1. **AD-15** — serving decision внутри `fusion/*` только Path enum; `fast|full` только Edge/Shadow adapter.  
2. **AD-14** — убрать или жёстко загейтить agents-only `_charge_amounts` для fusion completions (требовать `_fusion_result`).  
3. **AD-6** — продолжать вынос из `_monolith` (Epic 2/3 hooks уже есть).  
4. **AD-14 shape** — alias `model` на branches + optional nested `usage` для совместимости со spine.  
5. **AD-17** — solo path: scrub или явный non-fusion perimeter doc.

## Примечание по Story 1.1

AC 1.1 явно запрещал Path-rewrite / behavior break → **строгий AD-15 end-state не был deliverable 1.1**. Это архитектурный долг миграции, не «сломанный facade».
