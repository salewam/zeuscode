"""Power scores grounded in public July 2026 leaderboards.

Primary source (chat): Artificial Analysis Intelligence Index (AA)
  https://artificialanalysis.ai/leaderboards/models
  Map: power = 400 + AA×10  →  AA 60 = 1000, AA 50 = 900, AA 40 = 800

Secondary (when AA missing): LMArena / Chatbot Arena Elo bands (July 2026)
  https://lmarena.ai  (summaries: localaimaster / swfte snapshots)

Image: Artificial Analysis / LMArena text-to-image Elo + 2026 roundups
  (GPT Image 2 #1, Nano Banana Pro / FLUX.2 / Seedream 5 top tier)

Video/music: relative industry tiering (Kling 3 / Veo / Seedance top),
  kept below strong chat so they never steal UI Author.

Snapshot note: 2026-07-23. Re-check AA/Arena when frontier shifts.
"""

from __future__ import annotations

import os
from typing import Iterable

# Role Routing: Architect / Test Author / conflict-merge gate (PRD FR-18 / AD-21).
# Override via env without UX. Default 950 matches planning snapshot.
def _env_test_author_min() -> int:
    raw = (os.environ.get("ZEUS_TEST_AUTHOR_MIN") or "").strip()
    if not raw:
        return 950
    try:
        return max(0, min(2000, int(raw)))
    except ValueError:
        return 950


TEST_AUTHOR_MIN: int = _env_test_author_min()

# Artificial Analysis Intelligence Index (reasoning / max-effort where listed)
_AA_INDEX: dict[str, float] = {
    "claude-fable-5": 60.0,
    "gpt-5.6-sol": 59.0,  # Sol max
    "claude-opus-4-8": 56.0,  # Opus 4.8 max
    "gpt-5.6-terra": 55.0,  # Terra max
    "grok-4-5": 54.0,  # Grok 4.5 high
    "claude-sonnet-5": 53.0,  # Sonnet 5 max
    "gpt-5.6-luna": 51.0,  # Luna max
    # gpt-5.5 mainline ≈ between Terra and Luna; Instant AA~29 is not this SKU
    "gpt-5.5": 55.0,
    "gpt-5.4": 51.0,
    "gemini-3.5-flash": 50.0,
    "gemini-3.1-pro": 46.0,  # Gemini 3.1 Pro Preview
    "deepseek-v4-pro": 44.0,  # V4 Pro max
    "gpt-5.4-codex": 44.0,  # ~GPT-5.3 Codex xhigh class
    "deepseek-v4-flash": 40.0,  # V4 Flash max
    "claude-haiku-4-5": 30.0,  # Claude 4.5 Haiku
    "gemini-2.5-pro": 26.0,
    "gemini-3.1-flash-lite": 25.0,  # not in catalog; heuristic anchor
}

# LMArena-style overall Elo (approx July 2026) when AA is thin/missing
_ARENA_ELO: dict[str, int] = {
    "claude-opus-4-8": 1512,
    "gpt-5.5": 1506,
    "gemini-3.1-pro": 1505,
    "claude-opus-4-7": 1505,
    "grok-4-3": 1496,
    "claude-opus-4-6": 1490,
    "claude-sonnet-4-6": 1480,
    "claude-sonnet-4-5": 1470,
    "claude-opus-4-5": 1460,
    "gemini-3-pro": 1455,
    "deepseek-v4-pro": 1410,
    "gemini-3-flash": 1380,
    "gpt-5-2": 1370,
    "gemini-2.5-flash": 1320,
    "deepseek-chat": 1280,
    "deepseek-v4-flash": 1260,
}

# Small craft/coding bias for UI Author (Frontend Code Arena / SWE leaders, July 2026)
# Fable #2 FE Arena, GPT-5.6 Sol #3, Opus 4.8 top overall coding — not huge, just tie-break.
_UI_CRAFT_BIAS: dict[str, int] = {
    "claude-fable-5": 12,
    "gpt-5.6-sol": 10,
    "claude-opus-4-8": 8,
    "claude-sonnet-5": 6,
    "gpt-5.4-codex": 6,
    "grok-4-5": 4,
}

# Image Arena / 2026 roundups → 300–500 band (below chat)
_IMAGE_POWER: dict[str, int] = {
    "gpt-image-2": 495,  # AA / LMArena text-to-image #1 (~Elo 1338–1512 reports)
    "google-nano-banana-pro": 480,
    "black-forest-labs-flux-2-pro": 470,
    "gpt-image-1.5": 460,
    "seedream-5-pro": 455,
    "google-imagen4": 445,
    "google-nano-banana-2": 440,
    "openai-4o-image": 430,
    "black-forest-labs-flux-2-flex": 425,
    "seedream-5.0-lite": 415,
    "google-nano-banana": 410,
    "ideogram-v3": 405,  # typography specialist
    "seedream-4.5": 400,
    "wan-2.7-image-pro": 390,
    "google-nano-banana-edit": 385,
    "black-forest-labs-flux1-kontext": 380,
    "wan-2.7-image": 370,
    "ideogram-character": 360,
    "qwen-z-image": 350,
    "qwen-image": 340,
    "nano-banana-2-lite": 335,
    "ideogram-v3-remix": 330,
    "ideogram-character-remix": 325,
    "ideogram-v3-edit": 320,
    "ideogram-character-edit": 315,
    "ideogram-v3-reframe": 310,
    "qwen-image-edit": 300,
    "qwen2-image-edit": 295,
    "recraft-crisp-upscale": 260,
    "topaz-image-upscaler": 255,
    "recraft-remove-background": 240,
}

# Video relative tiers (Kling 3 / Veo / Seedance lead 2026 API stacks)
_VIDEO_POWER: dict[str, int] = {
    "kling-3.0": 470,
    "kling-3.0-turbo": 465,
    "google-veo-3.1": 460,
    "bytedance/seedance-2": 455,
    "kling-3.0-motion-control": 450,
    "bytedance/seedance-2-fast": 445,
    "kling-2.6": 430,
    "grok-imagine-video-1-5-preview": 425,
    "runway-aleph": 420,
    "wan-2.7-video": 415,
    "hailuo-2.3": 410,
    "bytedance/seedance-1.5-pro": 405,
    "kling-2.6-motion-control": 400,
    "kling-2.5-turbo": 390,
    "grok-imagine": 385,
    "wan-2.6": 380,
    "runway": 375,
    "bytedance/seedance-2-mini": 370,
    "gemini-omni-video": 365,
    "wan-2.5": 360,
    "kling-2.1": 350,
    "hailuo-02": 345,
    "happyhorse-1.1": 340,
    "omnihuman-1-5": 335,
    "meigen-ai-infinitetalk": 330,
    "kling-ai-avtar": 325,
    "happyhorse-1.0": 320,
    "wan-2.2-animate": 315,
    "wan-2.2": 310,
    "grok-imagine/extend": 305,
    "volcengine": 300,
    "wan-2.2-a14b-turbo-api-speech-to-video": 285,
    "topaz-video-upscaler": 270,
}

_MUSIC_POWER: dict[str, int] = {
    "elevenlabs-v3": 340,
    "suno": 330,
    "elevenlabs-text-to-speech": 320,
}

# Zeus product stacks (routing labels, not LMSYS models)
_PRODUCT_POWER: dict[str, int] = {
    "zeuscode": 995,
    "zeus/fusion": 995,
    "ultra-mode": 930,
    "studio-premium": 920,
    "studio-ultra": 900,
    "studio-standard": 840,
    "studio-light": 780,
}

# Explicit overrides / older aliases still referenced in code paths
_EXTRA: dict[str, int] = {
    "gpt-5.3": 920,
    "gpt-5.2": 910,
    "gpt-5.1": 900,
    "gpt-5": 890,
    "o3-pro": 900,
    "o3": 885,
    "deepseek-reasoner": 820,
    "grok-4": 800,
    "gpt-4.1": 820,
    "gpt-4o": 780,
}


def _aa_to_power(aa: float) -> int:
    return int(round(400 + float(aa) * 10))


def _elo_to_power(elo: int) -> int:
    # Elo 1510 → ~990, 1400 → ~880, 1300 → ~780, 1200 → ~680
    return int(max(600, min(990, round(elo - 520))))


def _build_power_table() -> dict[str, int]:
    out: dict[str, int] = {}
    out.update(_PRODUCT_POWER)
    out.update(_IMAGE_POWER)
    out.update(_VIDEO_POWER)
    out.update(_MUSIC_POWER)
    out.update(_EXTRA)

    # Chat: AA Index wins when present; Arena Elo only as fallback.
    chat_ids = set(_AA_INDEX) | set(_ARENA_ELO) | set(_UI_CRAFT_BIAS)
    chat_ids |= {
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-opus-4-5",
        "claude-sonnet-4-6",
        "claude-sonnet-4-5",
        "gemini-3-pro",
        "gemini-3-flash",
        "gemini-2.5-flash",
        "gpt-5.5",
        "gpt-5-2",
        "deepseek-chat",
        "grok-4-3",
    }
    for mid in sorted(chat_ids):
        if mid in _AA_INDEX:
            score = _aa_to_power(_AA_INDEX[mid])
        elif mid in _ARENA_ELO:
            score = _elo_to_power(_ARENA_ELO[mid])
        else:
            continue
        score += int(_UI_CRAFT_BIAS.get(mid, 0))
        out[mid] = int(max(600, min(1000, score)))

    return out


_POWER: dict[str, int] = _build_power_table()


def _family(model_id: str) -> str:
    m = (model_id or "").lower()
    if m.startswith("zeus/") or "fusion" in m:
        return "fusion"
    if "studio-" in m:
        return "studio"
    if "ultra" in m:
        return "ultra"
    if "claude" in m or "opus" in m or "sonnet" in m or "haiku" in m or "fable" in m:
        return "claude"
    if "gpt" in m or m.startswith("o1") or m.startswith("o3") or m.startswith("o4") or "openai" in m:
        return "openai"
    if "gemini" in m:
        return "gemini"
    if "deepseek" in m:
        return "deepseek"
    if "grok" in m:
        return "grok"
    if any(x in m for x in ("flux", "imagen", "ideogram", "seedream", "nano-banana", "qwen", "recraft")):
        return "image"
    if any(x in m for x in ("kling", "seedance", "runway", "veo", "wan-", "hailuo", "happyhorse")):
        return "video"
    if any(x in m for x in ("elevenlabs", "suno")):
        return "music"
    return "other"


def _heuristic_score(model_id: str) -> int:
    mid = (model_id or "").strip().lower()
    fam = _family(mid)
    if fam == "claude":
        return 880 if "opus" in mid or "fable" in mid else 820 if "sonnet" in mid else 700
    if fam == "openai":
        return 900 if "5.6" in mid or "5.5" in mid else 850
    if fam == "gemini":
        return 860 if "pro" in mid else 740
    if fam == "deepseek":
        return 840 if "pro" in mid else 720
    if fam == "grok":
        return 840
    if fam == "image":
        return 320
    if fam == "video":
        return 320
    if fam == "music":
        return 300
    if fam in {"fusion", "ultra", "studio"}:
        return 850
    return 500


def power_score(model_id: str) -> int:
    mid = (model_id or "").strip()
    if not mid:
        return 0
    if mid in _POWER:
        return int(_POWER[mid])
    best = -1
    for k, v in _POWER.items():
        if k in mid or mid in k:
            best = max(best, int(v) - 5)
    if best >= 0:
        return best
    return _heuristic_score(mid)


def power_scores(panel: Iterable[str]) -> dict[str, int]:
    return {m: power_score(m) for m in panel if (m or "").strip()}


def catalog_power_coverage() -> dict[str, int]:
    try:
        from app.catalog import public_catalog

        return {str(r["id"]): power_score(str(r["id"])) for r in public_catalog() if r.get("id")}
    except Exception:  # noqa: BLE001
        return dict(_POWER)


def missing_explicit_scores() -> list[str]:
    try:
        from app.catalog import public_catalog

        return sorted(
            str(r["id"])
            for r in public_catalog()
            if r.get("id") and str(r["id"]) not in _POWER
        )
    except Exception:  # noqa: BLE001
        return []


def pick_author(panel: list[str], *, hint: str | None = None) -> str:
    clean = [m.strip() for m in panel if (m or "").strip()]
    if not clean:
        return (hint or "").strip() or ""
    scored = sorted(
        clean,
        key=lambda m: (
            power_score(m),
            1 if hint and m == hint else 0,
        ),
        reverse=True,
    )
    return scored[0]


def pick_critics(
    panel: list[str],
    author: str,
    *,
    n: int = 2,
) -> list[str]:
    rest = [m.strip() for m in panel if (m or "").strip() and m.strip() != author]
    if not rest:
        return []
    auth_fam = _family(author)
    rest_sorted = sorted(
        rest,
        key=lambda m: (
            0 if _family(m) != auth_fam else 1,
            -power_score(m),
        ),
    )
    picked: list[str] = []
    seen_fam: set[str] = set()
    for m in rest_sorted:
        fam = _family(m)
        if fam in seen_fam and len(rest_sorted) > n:
            continue
        picked.append(m)
        seen_fam.add(fam)
        if len(picked) >= n:
            break
    if len(picked) < n:
        for m in rest_sorted:
            if m not in picked:
                picked.append(m)
            if len(picked) >= n:
                break
    return picked[:n]
