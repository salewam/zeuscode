"""Deterministic media + copy packs for cheap-model skill loop.

Skills/brief inject these — workers copy URLs/text; no hand-editing per site.
Rotate by stable hash of task text so runs don't all share one Unsplash ID.

All URLs must return HTTP 200 (verified). Dead IDs = gray hero void.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# Niche → list of (scene, url). Always https Unsplash crop URLs (live 200).
MEDIA_POOLS: dict[str, list[dict[str, str]]] = {
    "sto": [
        {
            "scene": "механик у открытого капота",
            "url": "https://images.unsplash.com/photo-1486262715619-67b85e0b08d3?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "бокс / работа у авто",
            "url": "https://images.unsplash.com/photo-1486006920555-c77dcf18193c?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "шиномонтаж / колёса",
            "url": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "инструменты и верстак",
            "url": "https://images.unsplash.com/photo-1487754180451-c456f719a1fc?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "диагностика / ноутбук у авто",
            "url": "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "спорткар / премиум кузов",
            "url": "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "мастер с инструментом",
            "url": "https://images.unsplash.com/photo-1625047509248-ec889cbff17f?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "автосервис интерьер",
            "url": "https://images.unsplash.com/photo-1530046339160-ce3e530c7d2f?auto=format&fit=crop&w=2000&q=80",
        },
    ],
    "cafe": [
        {
            "scene": "чашка латте сверху",
            "url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "интерьер кофейни, дерево",
            "url": "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "бариста за стойкой",
            "url": "https://images.unsplash.com/photo-1511920170033-f8396924c348?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "выпечка / круассан",
            "url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=2000&q=80",
        },
    ],
    "barber": [
        {
            "scene": "кресло барбера",
            "url": "https://images.unsplash.com/photo-1585747860715-2ba37e788b70?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "ножницы и расчёска",
            "url": "https://images.unsplash.com/photo-1503951914875-452162b0f3f1?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "стрижка в процессе",
            "url": "https://images.unsplash.com/photo-1622286342621-4bd786c2447c?auto=format&fit=crop&w=2000&q=80",
        },
    ],
    "service": [
        {
            "scene": "руки / ремесло",
            "url": "https://images.unsplash.com/photo-1504328345606-18bbc8c9d7d1?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "офис / встреча",
            "url": "https://images.unsplash.com/photo-1521737711867-e3b97375f902?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "ноутбук и блокнот",
            "url": "https://images.unsplash.com/photo-1432888498266-38ffec3eaf0a?auto=format&fit=crop&w=2000&q=80",
        },
        {
            "scene": "город / витрина",
            "url": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=crop&w=2000&q=80",
        },
    ],
    "deck": [
        {
            "scene": "команда за столом",
            "url": "https://images.unsplash.com/photo-1522071820081-009f0129c71c?auto=format&fit=crop&w=1600&q=80",
        },
        {
            "scene": "график / дашборд на экране",
            "url": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1600&q=80",
        },
        {
            "scene": "рукопожатие / партнёрство",
            "url": "https://images.unsplash.com/photo-1521791136064-7986c2920216?auto=format&fit=crop&w=1600&q=80",
        },
        {
            "scene": "продукт в руках",
            "url": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=1600&q=80",
        },
    ],
    # Grocery / product shop — IDs verified HTTP 200 (dead Flash IDs = gray cards)
    "grocery": [
        {
            "scene": "овощная тарелка / томаты",
            "url": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "яблоки",
            "url": "https://images.unsplash.com/photo-1560806887-1e4cd0b6cbd6?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "бананы",
            "url": "https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "морковь",
            "url": "https://images.unsplash.com/photo-1598170845058-32b9d6a5da37?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "зелень / овощи",
            "url": "https://images.unsplash.com/photo-1610348725531-843dff563e2c?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "молоко / бутылка",
            "url": "https://images.unsplash.com/photo-1628088062854-d1870b4553da?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "сыр",
            "url": "https://images.unsplash.com/photo-1486297678162-eb2a19b0a32d?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "фрукты микс",
            "url": "https://images.unsplash.com/photo-1601004890684-d8cbf643f5f2?auto=format&fit=crop&w=800&q=80",
        },
    ],
    "flowers": [
        {
            "scene": "букет пионы",
            "url": "https://images.unsplash.com/photo-1490750967868-88aa4486c946?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "розы пудровые",
            "url": "https://images.unsplash.com/photo-1487530811176-3780de880c2d?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "красные розы",
            "url": "https://images.unsplash.com/photo-1519378058457-4c29a0a2efac?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "полевые",
            "url": "https://images.unsplash.com/photo-1525310072745-f49212b5ac6d?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "белые цветы",
            "url": "https://images.unsplash.com/photo-1468327768560-75b448c4b124?auto=format&fit=crop&w=800&q=80",
        },
        {
            "scene": "яркий букет",
            "url": "https://images.unsplash.com/photo-1455659817273-f9680774153e?auto=format&fit=crop&w=800&q=80",
        },
    ],
}


def detect_media_niche(user_text: str) -> str:
    t = user_text or ""
    if re.search(
        r"(?i)автосервис|сто\b|шиномонтаж|ремонт\s+авто|автомастер|моторхаус",
        t,
    ):
        return "sto"
    if re.search(
        r"(?i)продукт|товар|магазин|grocery|лавка|супермаркет|овощ|молочк|/api/products",
        t,
    ) and not re.search(r"(?i)букет|цвет|flower|bouquet", t):
        return "grocery"
    if re.search(r"(?i)букет|цвет|flower|bouquet|флор", t):
        return "flowers"
    if re.search(r"(?i)кофе|кофейн|cafe|bakery|пекарн", t):
        return "cafe"
    if re.search(r"(?i)барбер|парикмахер|barber|стрижк", t):
        return "barber"
    if re.search(r"(?i)презентац|pitch|deck|слайд|инвестор|питч", t):
        return "deck"
    return "service"


def catalog_image_urls(niche: str = "grocery", n: int = 8) -> list[str]:
    """Verified live image URLs for catalog seed harden."""
    pool = MEDIA_POOLS.get(niche) or MEDIA_POOLS["grocery"]
    urls = [x["url"] for x in pool]
    if not urls:
        return []
    out = []
    for i in range(max(n, len(urls))):
        out.append(urls[i % len(urls)])
    return out[:n]


def allowlisted_image_ids(niche: str | None = None) -> set[str]:
    ids: set[str] = set()
    keys = [niche] if niche else list(MEDIA_POOLS)
    for k in keys:
        for item in MEDIA_POOLS.get(k) or []:
            m = re.search(r"photo-([0-9a-zA-Z_-]+)", item.get("url") or "")
            if m:
                ids.add(m.group(1))
    return ids


def _seed(text: str) -> int:
    h = hashlib.sha256((text or "x").encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def pick_media_pair(user_text: str, niche: str | None = None) -> dict[str, Any]:
    from app.skills import skills_enabled

    if not skills_enabled():
        empty = {"scene": "", "url": ""}
        return {
            "niche": niche or "generic",
            "primary": empty,
            "secondary": empty,
            "tertiary": empty,
            "fourth": empty,
            "disabled": True,
        }

    """Pick primary + secondary + tertiary + gallery[4] — never same URL twice."""
    key = niche or detect_media_niche(user_text)
    pool = MEDIA_POOLS.get(key) or MEDIA_POOLS["service"]
    n = len(pool)
    i = _seed(user_text) % n
    indices = [i]
    for offset in range(1, n):
        cand = (i + offset) % n
        if cand not in indices:
            indices.append(cand)
        if len(indices) >= min(4, n):
            break
    gallery = [pool[x] for x in indices]
    primary, secondary, tertiary = gallery[0], gallery[1], gallery[2]
    fourth = gallery[3] if len(gallery) > 3 else gallery[0]
    return {
        "niche": key,
        "primary": primary,
        "secondary": secondary,
        "tertiary": tertiary,
        "fourth": fourth,
        "gallery": gallery,
        "pool_size": n,
        "rule": (
            "Hero = primary.url (CSS background или img). "
            "Ещё ≥2–3 разных кадра в галерее/витрине/карточках (img https). "
            "Каркас секций — под нишу (не обязательно id=vitrine). "
            "ЗАПРЕТ: один URL на всю страницу; мёртвые photo-ID; assets/ без файла."
        ),
    }


def media_brief_block(pair: dict[str, Any]) -> str:
    from app.skills import skills_enabled

    if not skills_enabled() or (pair or {}).get("disabled"):
        return ""

    p, s, t = pair["primary"], pair["secondary"], pair["tertiary"]
    f = pair.get("fourth") or t
    return f"""## Media pack (обязательно — проверенные live URL)
Ниша: {pair['niche']}. Ротация по задаче.

1. **Hero:** {p['scene']}
   `{p['url']}`
2. **Кадр #2:** {s['scene']}
   `{s['url']}`
3. **Кадр #3:** {t['scene']}
   `{t['url']}`
4. **Кадр #4:** {f['scene']}
   `{f['url']}`

Must: разные photo-ID на странице (hero + ещё кадры).  
Секции/классы — под бриф (не штампуй всем `#vitrine` / `.top__nav`).
"""
