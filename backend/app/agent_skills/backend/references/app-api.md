# Backend — App API (каталог как templates/app-shop)

## Контракт seed (critical FAIL без этого)

≥**4** позиций, remote `https://images.unsplash.com` в **`image`**.

Обязательные поля:

| Поле | Зачем |
|------|--------|
| `id`, **`name`** (не `title`) | FE + orders `product_name`/`bouquet_name` |
| `price` | карточка / preview |
| `image` | карточка (alias `image_url` ок как доп.) |
| `desc` или `description` или `composition` | meta на карточке |
| `tag` **или** `category` | **те же строки**, что `data-filter` на FE |

### Правило filters ↔ seed
Если в HTML чипы `data-filter="Овощи|Фрукты|…"`, в seed **обязаны** быть те же `category`/`tag`.
Цветочный эталон: `tag`: хит/премиум/новый.  
Продуктовый магазин: `category`: Овощи/Фрукты/Молочка — и чипы **такие же**, не хит/премиум.

Заказ: POST отдаёт `*_name` из **`item["name"]`**, не title.

---

## Цветы (эталон)

```python path=/src/backend/routers/shop.py
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["app"])

BOUQUETS = [
    {"id": 1, "name": "Изумрудный сад", "price": 4500, "size": "высокий", "stems": 25,
     "composition": "пионы, эвкалипт", "desc": "Плотный букет.",
     "image": "https://images.unsplash.com/photo-1490750967868-88aa4486c946?w=800&q=80",
     "tag": "хит"},
    {"id": 2, "name": "Пудровое утро", "price": 3200, "size": "средний", "stems": 15,
     "composition": "розы", "desc": "Пудровые тона.",
     "image": "https://images.unsplash.com/photo-1487530811176-3780de880c2d?w=800&q=80",
     "tag": "новый"},
    {"id": 3, "name": "Алый рассвет", "price": 5600, "size": "крупный", "stems": 35,
     "composition": "розы", "desc": "На торжество.",
     "image": "https://images.unsplash.com/photo-1519378058457-4c29a0a2efac?w=800&q=80",
     "tag": "премиум"},
    {"id": 4, "name": "Летний рынок", "price": 2900, "size": "средний", "stems": 19,
     "composition": "полевые", "desc": "Лёгкий микс.",
     "image": "https://images.unsplash.com/photo-1525310072745-f49212b5ac6d?w=800&q=80",
     "tag": ""},
]
ORDERS: list[dict] = []

class OrderIn(BaseModel):
    name: str = Field(min_length=2)
    phone: str = Field(min_length=7)
    bouquet_id: int
    delivery_date: str
    address: str = Field(min_length=5)
    comment: str = ""

@router.get("/bouquets")
def list_bouquets():
    return BOUQUETS

@router.get("/orders")
def list_orders():
    return list(reversed(ORDERS))

@router.post("/orders", status_code=status.HTTP_201_CREATED)
def create_order(body: OrderIn):
    bq = next((b for b in BOUQUETS if b["id"] == body.bouquet_id), None)
    if not bq:
        raise HTTPException(404, "not found")
    oid = len(ORDERS) + 1
    row = {**body.model_dump(), "id": oid, "status": "confirmed",
           "bouquet_name": bq["name"], "total": bq["price"]}
    ORDERS.append(row)
    return row
```

## Продукты / grocery

Seed images — **только** из media pack `grocery` (проверенные 200). Не выдумывай photo-ID.

FE: уникальный UI под бриф. Контракт — `frontend/references/app-shell.md`.
`templates/app-shop*` = справка плотности / failsafe, не клон для всех юзеров.
Grocery: корзина (В корзину → badge) + вкладка покупок.

```python
PRODUCTS = [
    {"id": 1, "name": "Томаты", "price": 150, "category": "Овощи",
     "desc": "Спелые сладкие",
     "image": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=800&q=80"},
    # … ≥4, category ∈ {Овощи, Фрукты, Молочка} = data-filter на FE
]
# GET /api/products ; OrderIn.product_id ; response product_name=item["name"]
```

## Бан
- `title` вместо `name`
- filters «хит» при seed category «Овощи»
- seed без desc/composition
- мёртвые Unsplash ID (404) → серые карточки
- продуктовый FE без корзины
- `Header(...)` required без auth в brief
