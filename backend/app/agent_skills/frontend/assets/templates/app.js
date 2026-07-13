/**
 * Template app.js — form submit with loading/error states.
 * Copy to /src/frontend/app.js and point fetch URL to real API.
 */

function showError(el, msg) {
  if (!el) return;
  el.hidden = !msg;
  el.textContent = msg || "";
}

const form = document.getElementById("main-form") || document.getElementById("login-form");
if (form) {
  const errEl = document.getElementById("form-error");
  const btn = document.getElementById("submit-btn");
  const idleLabel = btn?.textContent || "Сохранить";

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError(errEl, "");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Сохраняем…";
    }
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      const res = await fetch("/api/example", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        showError(errEl, "Не удалось сохранить. Попробуйте ещё раз.");
        return;
      }
      // success: navigate or reset per product
    } catch {
      showError(errEl, "Сеть недоступна. Проверьте соединение.");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = idleLabel;
      }
    }
  });
}

/** Optional list renderer — wire to #content-root */
export function renderList(root, { status, items = [], error = "" }) {
  if (!root) return;
  root.dataset.state = status;
  root.setAttribute("aria-busy", status === "loading" ? "true" : "false");
  if (status === "loading") {
    root.innerHTML = `<div aria-label="Загрузка"><div class="skeleton"></div><div class="skeleton"></div></div>`;
    return;
  }
  if (status === "error") {
    root.innerHTML = `<p role="alert">${error}</p><button type="button" data-action="retry" class="btn">Повторить</button>`;
    return;
  }
  if (!items.length) {
    root.innerHTML = `<section class="empty" aria-labelledby="empty-title">
      <h2 id="empty-title">Пока пусто</h2>
      <p>Добавьте первый элемент, чтобы начать.</p>
      <button type="button" class="btn" data-action="create">Создать</button>
    </section>`;
    return;
  }
  root.innerHTML = `<ul role="list">${items.map((t) => `<li>${t}</li>`).join("")}</ul>`;
}
