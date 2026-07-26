"""Per-user uniqueness packs for landing briefs.

Same quality bar (taste/gates), different brand/copy/layout/media per user_text seed.
Never stamp MotоrХаус unless the user asked for it.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

STO_BRANDS = [
    ("СеверМотор", "мастерской, коротко и по делу"),
    ("Бокс№7", "уличный, без пафоса"),
    ("КапотПро", "технический, честный"),
    ("ДрайвСервис", "быстрый, городской"),
    ("Мастерская Юг", "соседский, надёжный"),
    ("Ремень и Вал", "гаражный, с характером"),
    ("ПитерБокс", "северный, спокойный"),
    ("АвтоЛиния", "чёткий сервисный"),
    ("Шестерня", "рабочий, без воды"),
    ("ТрекСТО", "спортивный, точный"),
    ("Гараж 31", "локальный, честный"),
]

STO_ADDRESSES = [
    ("Москва, Ленинградский пр-т, 80с16", "+7 (495) 308-11-40", "Пн–Сб 09:00–21:00"),
    ("Москва, Варшавское ш., 125с1", "+7 (495) 647-22-18", "Пн–Сб 08:00–20:00"),
    ("Москва, ул. Подольских Курсантов, 7", "+7 (495) 211-90-33", "Пн–Вс 09:00–21:00"),
    ("Химки, ул. Репина, 34", "+7 (495) 789-14-02", "Пн–Сб 09:00–20:00"),
    ("Москва, Алтуфьевское ш., 48", "+7 (495) 456-70-21", "Пн–Сб 09:00–21:00, Вс 10:00–18:00"),
    ("Москва, Каширское ш., 31с1", "+7 (495) 120-45-67", "Пн–Сб 09:00–21:00, Вс 10:00–18:00"),
    ("Санкт-Петербург, Московский пр., 222", "+7 (812) 309-55-17", "Пн–Сб 09:00–21:00"),
    ("Москва, ш. Энтузиастов, 56с21", "+7 (495) 980-44-12", "Пн–Сб 08:30–20:30"),
]

PALETTES = [
    {
        "asphalt": "#1a1c1e",
        "shop": "#f3f1ec",
        "band": "#e4e0d6",
        "amber": "#c47a2c",
        "amber_hover": "#a86520",
        "metal": "#c5c9ce",
    },
    {
        "asphalt": "#17191b",
        "shop": "#efece6",
        "band": "#ddd6c8",
        "amber": "#b85f1f",
        "amber_hover": "#9a4e18",
        "metal": "#b9bdc2",
    },
    {
        "asphalt": "#1c1814",
        "shop": "#f5f0e8",
        "band": "#e7dccb",
        "amber": "#d4892a",
        "amber_hover": "#b8721f",
        "metal": "#c8c2b8",
    },
    {
        "asphalt": "#121416",
        "shop": "#eceff2",
        "band": "#d5d8e0",
        "amber": "#c95c2c",
        "amber_hover": "#a84922",
        "metal": "#b4bac2",
    },
]

H1_ANGLES = [
    "{place} — смета до старта",
    "Ремонт и ТО в одном боксе — без очереди «на глаз»",
    "Запись сегодня · подъёмник под ваш слот",
    "От диагностики до ходовой — фиксируем цену до работ",
    "Сделаем авто снова тихим и предсказуемым",
    "ТО, ходовая, электрика — один адрес, одна смета",
]

VITRINE_TITLES = [
    ("Бокс и работы", "Живой участок — не стоковые абстракции."),
    ("Как выглядит сервис", "Реальный бокс, реальные узлы, без «премиум-воды»."),
    ("Цех сегодня", "Фото с смены: подъёмник, верстак, результат."),
    ("Место силы", "Туда приезжают, когда нужен результат, а не буклет."),
]

LAYOUTS = [
    {
        "id": "classic_stack",
        "order": "Hero → медиа-ряд → услуги → шаги → why → отзывы → FAQ → форма → footer",
        "why": "img_left",
    },
    {
        "id": "why_early",
        "order": "Hero → why → медиа-ряд → услуги → шаги → отзывы → FAQ → форма → footer",
        "why": "img_right",
    },
    {
        "id": "services_first",
        "order": "Hero → услуги → медиа-ряд → why → шаги → отзывы → FAQ → форма → footer",
        "why": "img_left",
    },
    {
        "id": "proof_mid",
        "order": "Hero → медиа-ряд → услуги → отзывы → why → шаги → FAQ → форма → footer",
        "why": "img_right",
    },
]

SERVICE_PACKS = [
    [
        (
            "Диагностика",
            1500,
            "Компьютер + подъёмник. Отчёт с кодами и рекомендациями — на руки.",
            ["сканер OBD", "осмотр ходовой", "письменный отчёт"],
        ),
        (
            "ТО по регламенту",
            4500,
            "Масло, фильтры, жидкости по карте завода. Без «универсального» масла наугад.",
            ["масло + фильтр", "проверка уровней", "сброс сервиса"],
        ),
        (
            "Ходовая / тормоза",
            2500,
            "Стук, увод, скрип — чиним узлы. Цену работ фиксируем до старта.",
            ["подвеска", "тормоза", "сход-развал по запросу"],
        ),
        (
            "Шиномонтаж",
            1800,
            "Переобувка R15–R21, балансировка, давление. Хранение — по договорённости.",
            ["монтаж", "балансировка", "вентиль"],
        ),
        (
            "Электрика",
            2000,
            "Не заводится, ECU, генератор, стартер. Ищем причину прибором.",
            ["обрыв", "генератор/стартер", "ECU"],
        ),
        (
            "Кузов / полировка",
            5000,
            "Сколы и локальный ремонт после ДТП. Смета после осмотра.",
            ["осмотр", "локальный ремонт", "полировка"],
        ),
    ],
    [
        (
            "Экспресс-осмотр",
            1200,
            "30 минут: утечки, тормоза, ремни, аккумулятор. Список «сейчас / потом».",
            ["чеклист 20 пунктов", "фото узлов", "рекомендации"],
        ),
        (
            "Замена масла Pro",
            3900,
            "Масло + фильтр под допуск, сброс сервиса, проверка уровней.",
            ["масло", "фильтр", "сброс сервиса"],
        ),
        (
            "Тормоза под ключ",
            3200,
            "Колодки/диски, смазка направляющих, прокачка контура.",
            ["колодки/диски", "направляющие", "прокачка"],
        ),
        (
            "Развал-схождение",
            2800,
            "Компьютерный стенд после ходовой или сезонной переобувки.",
            ["стенд", "протокол", "регулировка"],
        ),
        (
            "Кондиционер",
            3500,
            "Заправка, поиск утечек, антибактериальная обработка.",
            ["заправка", "утечки", "антибак"],
        ),
        (
            "Детейлинг кузова",
            6000,
            "Мойка + полировка ЛКП + защита. Оценка по состоянию ЛКП.",
            ["мойка", "полировка", "защита"],
        ),
    ],
    [
        (
            "Компьютерная диагностика",
            1800,
            "Сканер: ошибки, адаптации, тест-актуаторы. Отчёт на руки.",
            ["чтение ошибок", "адаптации", "отчёт"],
        ),
        (
            "Ходовая «тишина»",
            2700,
            "Стук на кочках — сайлентблоки/опоры/тяги без угадываний.",
            ["диагностика", "замена узлов", "повторный осмотр"],
        ),
        (
            "ТО 15/30/60",
            5200,
            "Регламент по пробегу: масло, свечи, фильтры, жидкости.",
            ["регламент", "расходники", "чеклист"],
        ),
        (
            "Шины + хранение",
            2200,
            "Сезонная переобувка и склад комплекта до следующего сезона.",
            ["монтаж", "балансировка", "хранение"],
        ),
        (
            "Старт / заряд",
            2100,
            "АКБ, генератор, стартер — замер и замена.",
            ["замер АКБ", "генератор", "стартер"],
        ),
        (
            "Локальная покраска",
            7500,
            "Элемент после скола/парковки. Цвет в тон.",
            ["подбор цвета", "покраска", "полировка стыка"],
        ),
    ],
]

REVIEW_PACKS = [
    [
        ("Сделали ходовую за день — цену назвали до старта.", "Игорь", "Toyota Camry"),
        ("Вечером форма — утром уже на подъёмнике.", "Марина", "Kia Rio"),
        ("По электрике нашли генератор за час.", "Алексей", "VW Polo"),
    ],
    [
        ("Без навязывания «поменять всё». Честный список работ.", "Дмитрий", "Skoda Octavia"),
        ("Переобувка + хранение — без очереди.", "Елена", "Hyundai Solaris"),
        ("После ТО машина снова едет ровно.", "Павел", "Mazda 6"),
    ],
    [
        ("Смету прислали до визита — удобно.", "Ольга", "Renault Duster"),
        ("Тормоза за полдня, педаль стала короткой.", "Никита", "Ford Focus"),
        ("Кондей заправили, запах убрали.", "Анна", "Nissan Qashqai"),
    ],
]

FAQ_PACKS = [
    [
        ("Можно без записи?", "Да, но онлайн-слот быстрее — мастер отвечает ~15 минут."),
        ("Чьи запчасти?", "Оригинал или аналог на выбор, фиксируем в заказ-наряде."),
        ("Гарантия?", "90 дней на работы; по запчастям — условия поставщика."),
    ],
    [
        ("Сколько ждать ответ?", "В рабочие часы обычно до 15 минут."),
        ("Можно со своими запчастями?", "Да, предупредите в заявке."),
        ("Есть подменный авто?", "По запросу — уточняем при записи."),
    ],
    [
        ("Фото для страховки?", "Да, фото узлов и заказ-наряд отдаём."),
        ("Работаете с юрлицами?", "Да, счёт и закрывающие — стандартно."),
        ("Если смета вырастет?", "Только после вашего ОК."),
    ],
]


def seed_hex(text: str, n: int = 8) -> str:
    return hashlib.sha256((text or "x").encode("utf-8")).hexdigest()[:n]


def seed_int(text: str) -> int:
    return int(seed_hex(text, 8), 16)


def _pick(seq: list[Any], seed: int, salt: int = 0) -> Any:
    return seq[(seed + salt) % len(seq)]


def extract_brand(user_text: str) -> str | None:
    t = user_text or ""
    patterns = [
        r"(?i)бренд[:\s]+[«\"]?([A-Za-zА-Яа-яЁё0-9№\-]{2,40})[»\"]?",
        r"(?i)называется\s+[«\"]?([A-Za-zА-Яа-яЁё0-9№\-]{2,40})[»\"]?",
        r"(?i)автосервис(?:а|у|е)?\s+[«\"]([A-Za-zА-Яа-яЁё0-9№\-\s]{2,40})[»\"]",
        r"(?i)[«\"]([A-Za-zА-Яа-яЁё0-9№\-]{2,40})[»\"]\s*(?:—|-)?\s*автосервис",
        r"(?i)\b(МоторХаус|СеверМотор|Бокс№7|КапотПро|ДрайвСервис|Шестерня|ТрекСТО)\b",
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            name = m.group(1).strip(" «»\"'")
            if len(name) >= 2 and name.lower() not in ("лендинг", "сайт", "сто"):
                return name
    return None


def extract_phone(user_text: str) -> str | None:
    m = re.search(
        r"(\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})",
        user_text or "",
    )
    return m.group(1).strip() if m else None


def extract_address(user_text: str) -> str | None:
    t = user_text or ""
    colloq = [
        (r"(?i)ленинградк", "Москва, Ленинградский пр-т"),
        (r"(?i)варшавк", "Москва, Варшавское ш."),
        (r"(?i)каширск", "Москва, Каширское ш."),
        (r"(?i)алтуфьев", "Москва, Алтуфьевское ш."),
        (r"(?i)химк", "Химки"),
    ]
    for pat, label in colloq:
        if re.search(pat, t):
            return label
    m = re.search(
        r"(?i)((?:Москва|Санкт-Петербург|Химки|Казань|Екатеринбург)"
        r"[^,.\n]{0,40}(?:,\s*[^,.\n]{3,50})?)",
        t,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip(" ,")
    m2 = re.search(
        r"(?i)((?:ул\.|пр-т|ш\.|проспект|шоссе)[^,.\n]{3,60})",
        t,
    )
    return re.sub(r"\s+", " ", m2.group(1)).strip(" ,") if m2 else None


def build_sto_identity(user_text: str) -> dict[str, Any]:
    s = seed_int(user_text)
    uniq = seed_hex(user_text, 10)

    user_brand = extract_brand(user_text)
    if user_brand:
        brand, tone = user_brand, "под бренд клиента, без чужого штампа"
    else:
        brand, tone = _pick(STO_BRANDS, s, 1)

    user_phone = extract_phone(user_text)
    user_addr = extract_address(user_text)
    addr, phone, hours = _pick(STO_ADDRESSES, s, 3)
    if user_addr:
        addr = user_addr
    if user_phone:
        phone = user_phone

    if re.search(r"(?i)моторхаус", user_text or ""):
        brand, tone = "МоторХаус", "мастерской, без премиум-воды"
    if re.search(r"(?i)каширск", user_text or ""):
        addr = "Москва, Каширское ш., 31с1"
        if not user_phone:
            phone = "+7 (495) 120-45-67"
            hours = "Пн–Сб 09:00–21:00, Вс 10:00–18:00"

    pal = _pick(PALETTES, s, 5)
    layout = _pick(LAYOUTS, s, 7)
    h1_tmpl = _pick(H1_ANGLES, s, 11)
    place = addr.split(",")[0].strip() if addr else "в боксе"
    street = addr.split(",")[-1].strip() if "," in addr else place
    h1 = h1_tmpl.format(place=street)
    vit_title, vit_sub = _pick(VITRINE_TITLES, s, 13)
    services = list(_pick(SERVICE_PACKS, s, 17))
    reviews = _pick(REVIEW_PACKS, s, 19)
    faq = _pick(FAQ_PACKS, s, 23)

    rot = s % len(services)
    services = services[rot:] + services[:rot]

    return {
        "uniq": uniq,
        "brand": brand,
        "tone": tone,
        "city": place,
        "address": addr,
        "phone": phone,
        "hours": hours,
        "palette": pal,
        "layout": layout,
        "h1": h1,
        "vitrine_title": vit_title,
        "vitrine_sub": vit_sub,
        "services": services,
        "reviews": reviews,
        "faq": faq,
        "stamp_forbidden": brand != "МоторХаус",
        "lead": (
            f"{brand}: запись онлайн, мастер перезвонит в рабочие часы. "
            f"Адрес — {addr}."
        ),
        "cta_primary": "Записаться",
        "cta_secondary": "Позвонить",
    }


def uniqueness_brief_block(ident: dict[str, Any]) -> str:
    pal = ident["palette"]
    lay = ident["layout"]
    ban = ""
    if ident.get("stamp_forbidden"):
        ban = (
            "\n## BAN clone-штампа (major)\n"
            "Запрещено копировать чужой бренд: «МоторХаус», «Каширское ш., 31с1», "
            "«+7 (495) 120-45-67», H1 «Ремонт и ТО на Каширском — смета до старта», "
            "отзывы Игорь Camry / Марина Rio / Алексей Polo — если это не ваш UNIQUE бренд.\n"
            "Запрещено сдавать один и тот же каркас (sticky+Georgia+#vitrine+.btn) "
            "с заменой только названия — invent layout/type под этот seed.\n"
        )
    services_md = []
    for i, (name, price, note, includes) in enumerate(ident["services"], 1):
        inc = "; ".join(includes)
        price_s = f"{price:,}".replace(",", " ")
        services_md.append(
            f"{i}. **{name}** от {price_s} ₽ — {note} Включает: {inc}."
        )
    reviews_md = " · ".join(f"{n} ({d}): «{q}»" for q, n, d in ident["reviews"])
    faq_md = "\n".join(f"- **{q}** — {a}" for q, a in ident["faq"])

    return (
        f"## UNIQUE (обязательно — иначе clone FAIL)\n"
        f"- `data-uniq=\"{ident['uniq']}\"` на `<html>`\n"
        f"- Бренд в title и заметном chrome **точно**: «{ident['brand']}» "
        f"(класс имени — любой, не обязан `.brand`)\n"
        f"- H1 (угол): {ident['h1']}\n"
        f"- Телефон: {ident['phone']} · Адрес: {ident['address']} · {ident['hours']}\n"
        f"- Порядок секций `{lay['id']}`: {lay['order']} "
        f"(медиа-ряд = ≥2 разных photo URL; id/классы — свои)\n"
        f"- Why-блок: media {lay['why']}\n"
        f"- Цвета (токены назови как угодно): ink {pal['asphalt']} / "
        f"surface {pal['shop']} / accent {pal['amber']} / mute {pal['band']}\n"
        f"- Медиа h2: «{ident['vitrine_title']}» — {ident['vitrine_sub']}\n"
        f"- Tone: {ident['tone']}\n"
        f"- **Не** копируй CSS-классы эталона (#vitrine / .top__nav / .btn) — "
        f"свой каркас, свой type, свой chrome.\n"
        f"{ban}\n"
        f"## Услуги (этот юзер — не чужой прайс)\n"
        + "\n".join(services_md)
        + f"\n\n## Отзывы\n{reviews_md}\n\n## FAQ\n{faq_md}\n"
    )


def css_skeleton_from_identity(ident: dict[str, Any], hero_url: str) -> str:
    """Tokens-only hint — never dump a full MotorHaus layout into the brief."""
    p = ident["palette"]
    why = ident["layout"]["why"]
    return (
        f"/* UNIQUE tokens seed={ident['uniq']} — invent layout/type yourself */\n"
        f":root{{\n"
        f"  --ink:{p['asphalt']};\n"
        f"  --surface:{p['shop']};\n"
        f"  --mute:{p['band']};\n"
        f"  --accent:{p['amber']};\n"
        f"  --accent-hover:{p['amber_hover']};\n"
        f"  --line:{p['metal']};\n"
        f"}}\n"
        f"/* hero photo hint (не обязан 90deg veil / sticky / Georgia):\n"
        f"   {hero_url}\n"
        f"   why media: {why}\n"
        f"*/\n"
    )
