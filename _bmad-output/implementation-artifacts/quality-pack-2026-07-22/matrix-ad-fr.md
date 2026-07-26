# AD / FR matrix — Quality Pack 2026-07-22

Legend: **PASS** = proven live or strong automated gate · **PARTIAL** = code+tests, weak live · **NOT_PROVEN** = no live evidence · **FAIL** = broken in live pack

## Architecture decisions

| AD | Topic | Verdict | Evidence |
|---|---|---|---|
| AD-1 | Gateway + Path orchestrator | PASS | live `zeus/fusion` → Path + Onestack |
| AD-2 | Public id + Path enum | PASS | model `zeus/fusion`; paths FAST/CASCADE/FULL |
| AD-3 | Deterministic Path order | PARTIAL | live routing works; offline eval path_match 70% |
| AD-4 | Context ownership / Brief | PARTIAL | unit/epic3; not inspected live payloads |
| AD-5 | Early-exit verify authority | PARTIAL | CASCADE escalate live; Mini quality NOT_PROVEN |
| AD-6 | fusion↛routers | PASS | invariants-check + tests |
| AD-7 | Sticky Leader/stack only | PASS | sticky leaders `gemini-3.1-pro`×3; Path still escalated |
| AD-8 | Honest billing / FusionResult | PARTIAL | `fusion_result` keys on non-stream; credits null in pack |
| AD-9 | Shadow/canary/kill | PARTIAL | shadow+kill unit PASS; kill **live FAIL** 502; shadow flag off on prod |
| AD-10 | Dependency direction | PASS | fusion no routers import |
| AD-11 | Prefs precedence | PARTIAL | effort/kill prefs code PASS; kill live FAIL |
| AD-12 | Runtime budgets | PARTIAL | present + light enforce; KIE 429 still real constraint |
| AD-13 | Eval gate | PARTIAL | N=50 offline; path pass_rate 70%; no live oracle |
| AD-14 | FusionResult handoff | PASS | live non-stream includes fusion_result/onestack |
| AD-15 | Path taxonomy internal | PASS | serving Path enums in Onestack |
| AD-16 | Single Leader mutator | PASS | pick_leader sticky unit + sticky leaders stable live |
| AD-17 | Scrub once | PARTIAL | epic1 tests; not live probed |
| AD-18 | Deploy envelope | PASS | prod deploy active; health ok |

## Invariant spot-checks (A5)

| Check | Verdict |
|---|---|
| sticky → pick_leader | PASS |
| shadow serve baseline | PASS (unit; forced flag) |
| kill_switch clamp | PASS unit / **FAIL live** (502 cancelled flash) |
| rate limit logging | PASS (journal UPSTREAM_RATE_LIMIT earlier) |
| cancel_event | PARTIAL (SSE abort simulated; Soft-Stop billing NOT_PROVEN) |
| FusionResult billing | PARTIAL |
| fusion↛routers | PASS |

## Live cases summary

Source: `live/summary.json` — **11 ok / 1 fail / 0 weak**, HTTP 200×11, 429×0

| Case | Result | Notes |
|---|---|---|
| chitchat | ok | FAST / flash |
| trivial UI | ok | CASCADE escalate |
| code fix | ok | CASCADE |
| architecture | ok | CASCADE |
| review | ok | CASCADE |
| effort=high | ok | FULL via cascade_escalate_full |
| kill-switch | **fail** | 502 `Fusion fast: нет ответа (deepseek-v4-flash: cancelled)` |
| stream | ok | answer ok; Onestack fields often missing in SSE parse |
| sticky×3 | ok | same leader gemini-3.1-pro |
| cancel midstream | ok* | client abort simulated (~120B); not full billing proof |

## MVP FR closure (approx.)

MVP FRs ≈ 30 (excl. FR6/11/27 deferred).

| Band | Count (approx) | Examples |
|---|---|---|
| PASS / strong | ~16 | FR1,2,3,7,8,10,16,18(partial flags),20(shape),23(partial),26,28(partial),29(presence),34,37 |
| PARTIAL | ~10 | FR4,5,9,12,13,14,15,19,21,22,24,25,31,32 |
| FAIL / NOT_PROVEN live | ~4 | Kill live path, live Eval oracle, shadow-on-prod, Soft-Stop bill proof |

**Rough MVP closure: ~70–75% implemented, ~55% live-proven.**
