const $ = (id) => document.getElementById(id);
const toastEl = $("toast");
const statusCatalog = $("status-catalog");
const statusOrder = $("status-order");
const statusOrders = $("status-orders");
const catalogList = $("catalog-list");
const ordersList = $("orders-list");
const bouquetSelect = $("bouquet_id");
const form = $("order-form");
const submitBtn = $("submit-btn");
const preview = $("order-preview");
const badge = $("orders-badge");

const API = ".";
let bouquets = [];
let filter = "all";
let selectedId = null;

function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => { toastEl.hidden = true; }, 2600);
}

function money(n) {
  return Number(n || 0).toLocaleString("ru-RU") + " ₽";
}

function imgOf(b) {
  return b.image || b.image_url || "";
}

function metaLine(b) {
  const bits = [
    b.composition,
    b.category,
    b.size,
    b.stems != null && b.stems !== "" ? `${b.stems} шт.` : "",
  ].filter(Boolean);
  return bits.join(" · ");
}

function descLine(b) {
  return b.desc || b.description || "";
}

function setView(view) {
  document.querySelectorAll("[data-screen]").forEach((s) => {
    s.hidden = s.dataset.screen !== view;
  });
  document.querySelectorAll("[data-view]").forEach((b) => {
    b.classList.toggle("is-on", b.dataset.view === view);
  });
  if (view === "catalog") renderCatalog();
  if (view === "order") syncOrderForm();
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

function fillSelect() {
  bouquetSelect.innerHTML = bouquets
    .map((b) => `<option value="${b.id}">${b.name} — ${money(b.price)}</option>`)
    .join("");
  if (selectedId) bouquetSelect.value = String(selectedId);
}

function renderPreview(id) {
  const b = bouquets.find((x) => x.id === Number(id));
  if (!b) {
    preview.innerHTML = `<div class="preview__empty">Выберите букет в каталоге</div>`;
    return;
  }
  preview.innerHTML = `
    <img src="${imgOf(b)}" alt="${b.name}" />
    <div class="preview__body">
      <h2>${b.name}</h2>
      <div>${money(b.price)}${metaLine(b) ? " · " + metaLine(b) : ""}</div>
      ${descLine(b) ? `<p class="meta">${descLine(b)}</p>` : ""}
    </div>`;
}

function syncOrderForm() {
  fillSelect();
  renderPreview(bouquetSelect.value || selectedId);
}

function renderCatalog() {
  if (!bouquets.length) return;
  const rows = bouquets.filter((b) => filter === "all" || b.tag === filter);
  if (!rows.length) {
    statusCatalog.hidden = false;
    statusCatalog.className = "banner";
    statusCatalog.textContent = "В этой категории пока пусто";
    catalogList.innerHTML = "";
    return;
  }
  statusCatalog.hidden = true;
  catalogList.innerHTML = rows
    .map(
      (b) => `<article class="card">
        <div class="card__media">
          ${b.tag ? `<span class="card__tag">${b.tag}</span>` : ""}
          <img src="${imgOf(b)}" alt="${b.name}" loading="lazy" />
        </div>
        <div class="card__body">
          <h3>${b.name}</h3>
          ${metaLine(b) ? `<div class="meta">${metaLine(b)}</div>` : ""}
          ${descLine(b) ? `<div class="meta">${descLine(b)}</div>` : ""}
          <div class="price-row">
            <div class="price">${money(b.price)}</div>
            <button type="button" data-pick="${b.id}">В заказ</button>
          </div>
        </div>
      </article>`
    )
    .join("");
  catalogList.querySelectorAll("[data-pick]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedId = Number(btn.dataset.pick);
      setView("order");
      bouquetSelect.value = String(selectedId);
      renderPreview(selectedId);
    });
  });
}

async function loadCatalog() {
  statusCatalog.hidden = false;
  statusCatalog.className = "banner";
  statusCatalog.textContent = "Загрузка каталога…";
  catalogList.innerHTML = "";
  try {
    bouquets = await fetchJSON(`${API}/api/bouquets`);
    fillSelect();
    renderCatalog();
  } catch {
    statusCatalog.className = "banner is-error";
    statusCatalog.textContent = "Не удалось загрузить каталог. Обновите страницу.";
    showToast("Ошибка каталога");
  }
}

bouquetSelect.addEventListener("change", () => {
  selectedId = Number(bouquetSelect.value);
  renderPreview(selectedId);
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  statusOrder.hidden = true;
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }
  submitBtn.disabled = true;
  try {
    const payload = Object.fromEntries(new FormData(form).entries());
    payload.bouquet_id = Number(payload.bouquet_id);
    const data = await fetchJSON(`${API}/api/orders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    statusOrder.hidden = false;
    statusOrder.className = "banner is-ok";
    statusOrder.textContent = `Заказ №${data.id} принят · ${data.bouquet_name} · ${money(data.total)}`;
    showToast("Заказ оформлен");
    form.reset();
    const d = new Date();
    d.setDate(d.getDate() + 1);
    $("delivery_date").value = d.toISOString().slice(0, 10);
    if (selectedId) bouquetSelect.value = String(selectedId);
    renderPreview(bouquetSelect.value);
    await loadOrders(false);
    badge.hidden = false;
  } catch {
    statusOrder.hidden = false;
    statusOrder.className = "banner is-error";
    statusOrder.textContent = "Не удалось оформить заказ";
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
      statusOrders.textContent = "Пока нет заказов — оформите первый в разделе «Новый заказ».";
      ordersList.innerHTML = "";
      return;
    }
    statusOrders.hidden = true;
    ordersList.innerHTML = rows
      .map(
        (o) => `<article class="order-item">
          <div>
            <strong>№${o.id} · ${o.bouquet_name || "Букет"}</strong>
            <div class="muted">${o.name} · ${o.phone}</div>
            <div class="muted">${o.address || ""} · ${o.delivery_date || ""}</div>
            ${o.comment ? `<div class="muted">${o.comment}</div>` : ""}
          </div>
          <div>
            <div class="pill">${o.status || "confirmed"}</div>
            <div style="margin-top:.45rem;font-weight:700;text-align:right">${money(o.total || 0)}</div>
          </div>
        </article>`
      )
      .join("");
  } catch {
    statusOrders.hidden = false;
    statusOrders.className = "banner is-error";
    statusOrders.textContent = "Не удалось загрузить заказы";
  }
}

const tomorrow = new Date();
tomorrow.setDate(tomorrow.getDate() + 1);
$("delivery_date").value = tomorrow.toISOString().slice(0, 10);
$("delivery_date").min = tomorrow.toISOString().slice(0, 10);

loadCatalog();
loadOrders(false);
