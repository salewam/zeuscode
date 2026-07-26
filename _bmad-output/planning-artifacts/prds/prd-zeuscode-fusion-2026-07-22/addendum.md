# Addendum — Zeus Fusion PRD

Техническое ТЗ и трассировка. Не заменяет PRD.

## Источник ТЗ

- `docs/ZEUS_FUSION_ROADMAP_V3.1.md` — канонический продукт-спек / backlog ID A–F и фазы 0–6
- Brownfield: `backend/app/fusion.py`, TG Mini App, publish
- VP updates 2026-07-22: honest MVP; Path policy→MoR post-pass→mode clamp; §6.4 canary exit

## Трассировка Roadmap ID → FR

| ТЗ | PRD |
|---|---|
| A1 | FR-4 |
| A2 | FR-8 |
| A3 | FR-9 |
| A4 | FR-16 |
| A5 | FR-5 |
| A6–A7 | FR-6 (**v1.x**) |
| A8–A9 | v1.x with FR-11 |
| A10, A19 | FR-29 |
| A12 | FR-32 |
| A13 | **out MVP** (§6.3); ≠ FR-29 overflow |
| A14 | FR-17 |
| A15 | FR-18 |
| A16 | FR-10 |
| A17 MoR v1 | FR-28 MoR **post-pass** (0|1 step) |
| A18 | FR-5 + FR-29 |
| B1 | FR-10 |
| B2, B5, B14 | FR-13, FR-10 rank top-K |
| B3, B4 | FR-8, FR-12 |
| B6, B7, B10 | FR-10 |
| B9 | FR-11 (**v1.x**) |
| B11 | later |
| B13 Aspect v1 | FR-31 |
| B12, A11, E14 | FR-27 |
| C1–C7, C13–C14 | FR-14, FR-15, FR-29 |
| C8 | FR-18 |
| C9–C11 | FR-29 |
| C12 | FR-27 |
| D1–D4, D8 | FR-19, FR-14, FR-20 |
| D5–D7 | FR-21, FR-22 |
| E1–E2, E4 | FR-24 log-only, FR-25 |
| E3 Elo writeback | v1.x |
| E6 min alerts | §6.2 + §6.4 |
| E7 full dashboard | out MVP |
| E8–E9, E16–E17 | FR-2, FR-3, FR-23, FR-37 |
| E10 | FR-34 |
| E11 | out MVP Done (§6.3) |
| E15 | FR-26 + §6.4 |
| E18 | §6.4 canary exit |
| Path policy | FR-28 + fixtures F1–F15, I1–I3 |
| Legacy matrix | FR-37 |

## Mechanism notes (для Architecture)

- Path: classify Phase (+ design_lexicon→plan) → first-match → MoR local scores +0|1 → mode clamp
- Sticky = Leader/stack only; **not** Path Phase
- Effort=high = complexity +1 only (no floor)
- FULL before RACE; design_lexicon ⇒ FULL; lexicon_v1 frozen in baseline
- `routed_by`: legacy_* ≠ forced_*; closed set in FR-28
- A2 MVP subset: light CASCADE may stop after stronger_leader (≠ always FULL)
- RACE both-fail: FULL / Soft-Stop / disaster
- Aspects before near-duplicate τ
- Onestack `path` = final; `policy_path` + `escalate_from`
- MoR MVP = local heuristics (no LLM); bill $0 unless separate call
- Eval: `min(correctness,completeness)≥3`

## Phased delivery

- **Product MVP** = Phase 0–1 + Phase 2 include (§6.2)
- **Canary 100%** = §6.4 (≠ MVP Done)
- **v1.x** = Phase 3 (DUAL, Tradeoff, Presets, A8/A9)
- **Elo writeback** = Phase 4
- **Agent** = Phase 5 / FR-27
---
