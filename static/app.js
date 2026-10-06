// Stockroom front end. Mini project by Shashwat Patil, Robotics and AI.
const $ = (s) => document.querySelector(s);
const state = { q: "", category: "", status: "", editingId: null };
const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(url, method = "GET", body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || "Something went wrong."), { field: data.field });
  return data;
}

let toastTimer;
function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isError ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), 2800);
}

const STATUS_LABEL = { ok: "In stock", low: "Running low", out: "Out of stock" };

function rowHtml(p) {
  const pct = Math.min(100, Math.round((p.quantity / Math.max(p.reorder_level * 3, 1)) * 100));
  return `<tr data-id="${p.id}">
    <td><div class="pname">${esc(p.name)}</div><div class="pcode">${esc(p.product_code)}</div></td>
    <td>${esc(p.category)}</td>
    <td class="num">${inr.format(p.price)}</td>
    <td><div class="stepper">
      <button data-act="dec" aria-label="Remove one ${esc(p.name)}">−</button>
      <input data-act="set" value="${p.quantity}" inputmode="numeric" aria-label="Quantity of ${esc(p.name)}">
      <button data-act="inc" aria-label="Add one ${esc(p.name)}">+</button></div></td>
    <td><div class="meter s-${p.status}"><i><b style="width:${p.status === "out" ? 0 : Math.max(pct, 6)}%"></b></i>
      <small>${STATUS_LABEL[p.status]}</small></div></td>
    <td><div class="row-actions">
      <button class="link" data-act="edit">Edit</button>
      <button class="link danger" data-act="del">Delete</button></div></td></tr>`;
}

async function loadProducts() {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.category) params.set("category", state.category);
  if (state.status) params.set("status", state.status);
  const items = await api("/api/products?" + params);
  $("#rows").innerHTML = items.map(rowHtml).join("");
  const empty = $("#empty");
  empty.hidden = items.length > 0;
  if (!items.length) {
    const filtered = state.q || state.category || state.status;
    empty.textContent = filtered
      ? "No products match these filters. Clear the search or pick another category."
      : "No products yet. Select Add product to create the first one.";
  }
}

async function loadSummary() {
  const s = await api("/api/summary");
  $("#healthBar").innerHTML = ["ok", "low", "out"]
    .map((k) => `<span class="${k}" style="flex-grow:${s[k + "_count"]}" title="${s[k + "_count"]} ${k}"></span>`)
    .join("");
  $("#okCount").textContent = s.ok_count;
  $("#lowCount").textContent = s.low_count;
  $("#outCount").textContent = s.out_count;
  $("#tProducts").textContent = s.products;
  $("#tUnits").textContent = s.units.toLocaleString("en-IN");
  $("#tValue").textContent = inr.format(s.value);
  const need = s.low_count + s.out_count;
  $("#healthText").textContent = need
    ? `${need} of ${s.products} products need restocking.`
    : s.products ? "Everything is well stocked." : "Add a product to start tracking stock.";
}

async function loadCategories() {
  const cats = await api("/api/categories");
  $("#category").innerHTML = '<option value="">All categories</option>' +
    cats.map((c) => `<option ${c === state.category ? "selected" : ""}>${esc(c)}</option>`).join("");
  $("#catList").innerHTML = cats.map((c) => `<option value="${esc(c)}">`).join("");
}

const refresh = () => Promise.all([loadProducts(), loadSummary(), loadCategories()]);

// ---- stock edits -----------------------------------------------------------
async function adjust(id, body) {
  try {
    await api(`/api/products/${id}/stock`, "PATCH", body);
    await Promise.all([loadProducts(), loadSummary()]);
  } catch (e) {
    toast(e.message, true);
    loadProducts();
  }
}

$("#rows").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn || btn.tagName === "INPUT") return;
  const tr = btn.closest("tr");
  const id = tr.dataset.id;
  const act = btn.dataset.act;
  if (act === "inc") adjust(id, { change: 1 });
  if (act === "dec") adjust(id, { change: -1 });
  if (act === "edit") openDialog(await api("/api/products/" + id));
  if (act === "del") {
    const name = tr.querySelector(".pname").textContent;
    if (!confirm(`Delete ${name}? This also removes its stock history.`)) return;
    try {
      await api("/api/products/" + id, "DELETE");
      toast("Product deleted.");
      refresh();
    } catch (err) { toast(err.message, true); refresh(); }
  }
});

$("#rows").addEventListener("change", (e) => {
  if (e.target.dataset.act === "set") {
    adjust(e.target.closest("tr").dataset.id, { quantity: e.target.value.trim(), note: "Stock set manually" });
  }
});
$("#rows").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.dataset.act === "set") e.target.blur();
});

// ---- search & filters ------------------------------------------------------
let searchTimer;
$("#search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.q = e.target.value.trim(); loadProducts(); }, 200);
});
$("#category").addEventListener("change", (e) => { state.category = e.target.value; loadProducts(); });
document.querySelectorAll(".chip").forEach((chip) =>
  chip.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c === chip));
    state.status = chip.dataset.status;
    loadProducts();
  })
);

// ---- add / edit dialog -----------------------------------------------------
const dlg = $("#dlg"), form = $("#form");

function openDialog(product = null) {
  form.reset();
  clearErrors();
  state.editingId = product ? product.id : null;
  $("#dlgTitle").textContent = product ? "Edit product" : "Add product";
  form.product_code.disabled = !!product;
  $("#qtyField").hidden = !!product;
  if (product) {
    form.product_code.value = product.product_code;
    form.name.value = product.name;
    form.category.value = product.category;
    form.price.value = product.price;
    form.reorder_level.value = product.reorder_level;
  } else {
    form.reorder_level.value = 10;
  }
  dlg.showModal();
  (product ? form.name : form.product_code).focus();
}

function clearErrors() {
  $("#formError").textContent = "";
  form.querySelectorAll(".bad").forEach((i) => i.classList.remove("bad"));
}

function clientValidate(d) {
  if (!state.editingId && !/^[A-Za-z0-9_-]{2,20}$/.test(d.product_code))
    return ["product_code", "Product ID must be 2-20 letters, digits, '-' or '_'."];
  if (!d.name) return ["name", "Product name is required."];
  if (!d.category) return ["category", "Category is required."];
  if (d.price === "" || isNaN(d.price) || Number(d.price) < 0) return ["price", "Price must be a number, 0 or more."];
  if (!state.editingId && !/^\d+$/.test(d.quantity)) return ["quantity", "Quantity must be a whole number, 0 or more."];
  if (d.reorder_level !== "" && !/^\d+$/.test(d.reorder_level)) return ["reorder_level", "Reorder level must be a whole number, 0 or more."];
  return null;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearErrors();
  const d = {};
  new FormData(form).forEach((v, k) => (d[k] = String(v).trim()));
  if (state.editingId) d.product_code = "";
  const problem = clientValidate(d);
  if (problem) return showError(...problem);
  try {
    if (state.editingId) {
      delete d.product_code;
      delete d.quantity;
      await api("/api/products/" + state.editingId, "PUT", d);
      toast("Product updated.");
    } else {
      await api("/api/products", "POST", d);
      toast("Product added.");
    }
    dlg.close();
    refresh();
  } catch (err) { showError(err.field, err.message); }
});

function showError(field, msg) {
  if (field && form[field]) { form[field].classList.add("bad"); form[field].focus(); }
  $("#formError").textContent = msg;
}

$("#addBtn").addEventListener("click", () => openDialog());
$("#cancel").addEventListener("click", () => dlg.close());
dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });

refresh().catch(() => toast("Could not reach the server. Is Flask running?", true));
