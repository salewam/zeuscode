const $ = (id) => document.getElementById(id);
const toastEl = $("toast");
const statusCatalog = $("status-catalog");
const statusOrder = $("status-order");
const statusOrders = $("status-orders");
const catalogList = $("catalog-list");
const ordersList = $("orders-list");
const cartLines = $("cart-lines");
const productSelect = $("product_id");
const form = $("order-form");
const submitBtn = $("submit-btn");
const preview = $("order-preview");
const badge = $("orders-badge");
const cartBadge = $("cart-badge");

const API = ".";
const IMG_FALLBACK =
  "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=800&q=80";

let products = [];
let cart = []; // {id, name, price, image, qty}
let filter = "all";

function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    toastEl.hidden = true;
  }, 2600);
}

function money(n) {
  return Number(n || 0).toLocaleString("ru-RU") + " ₽";
}

function imgOf(p) {
  return p.image || p.image_url || IMG_FALLBACK;
}

function metaLine(p) {
  const bits = [p.category || p.tag, p.composition, p.size].filter(Boolean);
  return bits.join(" · ");
}

function descLine(p) {
  return p.desc || p.description || "";
}

function setView(view) {
  document.querySelectorAll("[data-screen]").forEach((s) => {
    s.hidden = s.dataset.screen !== view;
  });
  document.querySelectorAll("[data-view]").forEach((b) => {
    b.classList.toggle("is-on", b.dataset.view === view);
  });
  if (view === "catalog") renderCatalog();
  if (view === "order") renderCart();
  if (view === "orders") loadOrders();
}

document.querySelectorAll("[data-view]").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});

document.querySelectorAll("[data-filter]").forEach((chip) => {
  chip.addEventListener("click", () => {
    filter = chip.dataset.filter;
    document.querySelectorAll("[data-filter]").forEach((c) => {
      c.classList.toggle("is-on", c === chip);
    });
    renderCatalog();
  });
});

$("refresh-orders").addEventListener("click", () => loadOrders());

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

function updateCartBadge() {
  const n = cart.reduce((s, x) => s + x.qty, 0);
  cartBadge.hidden = n === 0;
  cartBadge.textContent = String(n);
}

function addToCart(id) {
  const p = products.find((x) => x.id === Number(id));
  if (!p) return;
  const hit = cart.find((x) => x.id === p.id);
  if (hit) hit.qty += 1;
  else
    cart.push({
      id: p.id,
      name: p.name || p.title,
      price: p.price,
      image: imgOf(p),
      qty: 1,
    });
  updateCartBadge();
  showToast(`В корзине: ${p.name || p.title}`);
  syncHiddenSelect();
}

function removeFromCart(id) {
  cart = cart.filter((x) => x.id !== Number(id));
  updateCartBadge();
  renderCart();
}

function syncHiddenSelect() {
  if (!productSelect) return;
  productSelect.innerHTML = products
    .map(
      (p) =>
        `<option value="${p.id}">${p.name || p.title} — ${money(p.price)}</option>`
    )
    .join("");
  if (cart[0]) productSelect.value = String(cart[0].id);
}

function renderCart() {
  syncHiddenSelect();
  if (!cart.length) {
    preview.innerHTML = `<div class="preview__empty">Корзина пуста — добавьте товары из каталога</div>`;
    cartLines.innerHTML = "";
    return;
  }
  const total = cart.reduce((s, x) => s + x.price * x.qty, 0);
  preview.innerHTML = `
    <img src="${cart[0].image}" alt="" onerror="this.src='${IMG_FALLBACK}'" />
    <div class="preview__body">
      <h2>${cart.length} поз. в корзине</h2>
      <div>${money(total)}</div>
      <p class="meta">${cart.map((x) => `${x.name} ×${x.qty}`).join(", ")}</p>
    </div>`;
  cartLines.innerHTML = cart
    .map(
      (x) => `<article class="order-item">
        <div>
          <strong>${x.name}</strong>
          <div class="muted">${money(x.price)} × ${x.qty}</div>
        </div>
        <div>
          <div class="price">${money(x.price * x.qty)}</div>
          <button type="button" class="btn btn--ghost" data-remove="${x.id}">Убрать</button>
        </div>
      </article>`
    )
    .join("");
  cartLines.querySelectorAll("[data-remove]").forEach((btn) => {
    btn.addEventListener("click", () => removeFromCart(btn.dataset.remove));
  });
}

function renderCatalog() {
  if (!products.length) return;
  const rows = products.filter(
    (p) => filter === "all" || p.category === filter || p.tag === filter
  );
  if (!rows.length) {
    statusCatalog.hidden = false;
    statusCatalog.className = "banner";
    statusCatalog.textContent = "В этой категории пока пусто";
    catalogList.innerHTML = "";
    return;
  }
  statusCatalog.hidden = true;
  catalogList.innerHTML = rows
    .map((p) => {
      const tag = p.category || p.tag || "";
      const meta = metaLine(p);
      const desc = descLine(p);
      return `<article class="card">
        <div class="card__media">
          ${tag ? `<span class="card__tag">${tag}</span>` : ""}
          <img src="${imgOf(p)}" alt="${p.name || p.title || ""}" loading="lazy"
               onerror="this.onerror=null;this.src='${IMG_FALLBACK}'" />
        </div>
        <div class="card__body">
          <h3>${p.name || p.title || "Товар"}</h3>
          ${meta ? `<div class="meta">${meta}</div>` : ""}
          ${desc ? `<div class="meta">${desc}</div>` : ""}
          <div class="price-row">
            <div class="price">${money(p.price)}</div>
            <button type="button" data-pick="${p.id}">В корзину</button>
          </div>
        </div>
      </article>`;
    })
    .join("");
  catalogList.querySelectorAll("[data-pick]").forEach((btn) => {
    btn.addEventListener("click", () => {
      addToCart(btn.dataset.pick);
    });
  });
}

async function loadCatalog() {
  statusCatalog.hidden = false;
  statusCatalog.className = "banner";
  statusCatalog.textContent = "Загрузка каталога…";
  catalogList.innerHTML = "";
  try {
    products = await fetchJSON(`${API}/api/products`);
    syncHiddenSelect();
    renderCatalog();
  } catch {
    statusCatalog.className = "banner is-error";
    statusCatalog.textContent = "Не удалось загрузить каталог. Обновите страницу.";
    showToast("Ошибка каталога");
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  statusOrder.hidden = true;
  if (!cart.length) {
    statusOrder.hidden = false;
    statusOrder.className = "banner is-error";
    statusOrder.textContent = "Корзина пуста";
    return;
  }
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }
  submitBtn.disabled = true;
  try {
    const base = Object.fromEntries(new FormData(form).entries());
    const created = [];
    for (const line of cart) {
      for (let i = 0; i < line.qty; i++) {
        const payload = {
          ...base,
          product_id: line.id,
          comment: [base.comment, cart.length > 1 ? `корзина: ${line.name}` : ""]
            .filter(Boolean)
            .join(" · "),
        };
        const data = await fetchJSON(`${API}/api/orders`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        created.push(data);
      }
    }
    statusOrder.hidden = false;
    statusOrder.className = "banner is-ok";
    statusOrder.textContent = `Оформлено покупок: ${created.length}. Смотрите вкладку «Покупки».`;
    showToast("Покупка оформлена");
    cart = [];
    updateCartBadge();
    renderCart();
    form.reset();
    const d = new Date();
    d.setDate(d.getDate() + 1);
    $("delivery_date").value = d.toISOString().slice(0, 10);
    await loadOrders(false);
    setView("orders");
  } catch {
    statusOrder.hidden = false;
    statusOrder.className = "banner is-error";
    statusOrder.textContent = "Не удалось оформить покупку";
    showToast("Ошибка отправки");
  } finally {
    submitBtn.disabled = false;
  }
});

async function loadOrders(showStatus = true) {
  if (showStatus) {
    statusOrders.hidden = false;
    statusOrders.className = "banner";
    statusOrders.textContent = "Загрузка…";
  }
  try {
    const rows = await fetchJSON(`${API}/api/orders`);
    badge.hidden = rows.length === 0;
    badge.textContent = String(rows.length);
    if (!rows.length) {
      statusOrders.hidden = false;
      statusOrders.className = "banner";
      statusOrders.textContent =
        "Пока нет покупок — соберите корзину в каталоге и оформите заказ.";
      ordersList.innerHTML = "";
      return;
    }
    statusOrders.hidden = true;
    ordersList.innerHTML = rows
      .map(
        (o) => `<article class="order-item">
          <div>
            <strong>№${o.id} · ${o.product_name || o.bouquet_name || "Товар"}</strong>
            <div class="muted">${o.name} · ${o.phone}</div>
            <div class="muted">${o.address || ""} · ${o.delivery_date || ""}</div>
            ${o.comment ? `<div class="muted">${o.comment}</div>` : ""}
          </div>
          <div>
            <div class="pill">${o.status || "confirmed"}</div>
            <div class="price" style="margin-top:.45rem;text-align:right">${money(o.total || 0)}</div>
          </div>
        </article>`
      )
      .join("");
  } catch {
    statusOrders.hidden = false;
    statusOrders.className = "banner is-error";
    statusOrders.textContent = "Не удалось загрузить покупки";
  }
}

const tomorrow = new Date();
tomorrow.setDate(tomorrow.getDate() + 1);
$("delivery_date").value = tomorrow.toISOString().slice(0, 10);
$("delivery_date").min = tomorrow.toISOString().slice(0, 10);

loadCatalog();
loadOrders(false);
updateCartBadge();
