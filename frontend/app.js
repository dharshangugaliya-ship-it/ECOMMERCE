// ===== state =====
const API = "http://localhost:5000/api";
let state = {
  token: localStorage.getItem("token"),
  user: JSON.parse(localStorage.getItem("user") || "null"),
  view: "shop",
  products: [],
  categories: [],
  cart: [],
  orders: [],
  q: "", category: "all", sort: "",
};

// ===== API client =====
let _apiRetries = 0;
const _MAX_RETRIES = 2;

function showApiBanner(show) {
  const b = document.getElementById("apiBanner");
  if (!b) return;
  b.classList.toggle("hidden", !show);
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const merged = { ...opts, headers: { ...headers, ...(opts.headers || {}) } };
  let lastErr;
  for (let attempt = 0; attempt <= _MAX_RETRIES; attempt++) {
    try {
      const res = await fetch(API + path, merged);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        // 4xx is a real response, don't retry — just throw.
        if (res.status >= 400 && res.status < 500) {
          showApiBanner(false);
          throw new Error(data.error || `HTTP ${res.status}`);
        }
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      showApiBanner(false);
      _apiRetries = 0;
      return data;
    } catch (e) {
      lastErr = e;
      // Network errors are TypeError from fetch; 5xx also retryable.
      const isNetwork = e instanceof TypeError || /failed to fetch|networkerror/i.test(String(e));
      if (!isNetwork || attempt === _MAX_RETRIES) break;
      await new Promise(r => setTimeout(r, 250 * (attempt + 1)));
    }
  }
  showApiBanner(true);
  _apiRetries++;
  throw lastErr || new Error("API unreachable");
}

function renderSkeleton(count = 8) {
  return `<div class="skeleton-grid">${Array.from({ length: count }).map(() => `
    <div class="skeleton-card">
      <div class="sk-line sk-img"></div>
      <div class="sk-line short"></div>
      <div class="sk-line med"></div>
      <div class="sk-line"></div>
    </div>`).join("")}</div>`;
}

const $ = (s) => document.querySelector(s);
const fmt = (n) => Number(n).toFixed(2);
const esc = (s) => String(s || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ===== toast =====
function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = "toast " + kind;
  el.textContent = msg;
  $("#toastHost").appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ===== modal =====
window.openModal = (html) => { $("#modal").innerHTML = `<div class="modal-content">${html}</div>`; $("#modal").classList.remove("hidden"); };
window.closeModal = () => $("#modal").classList.add("hidden");

// ===== top bar =====
function renderActions() {
  const a = $("#actions");
  if (state.user) {
    a.innerHTML = `
      <span class="welcome">Hi, ${esc(state.user.name)}</span>
      ${state.user.is_admin ? "<button onclick=\"go('admin')\">Admin</button>" : ''}
      <button onclick="go('orders')">Orders</button>
      <button onclick="go('shop')">Shop</button>
      <button class="accent" onclick="go('cart')">Cart (${state.cart.reduce((s, i) => s + i.qty, 0)})</button>
      <button onclick="toggleTheme()">🌙</button>
      <button onclick="logout()">Logout</button>
    `;
  } else {
    a.innerHTML = `
      <button onclick="go('login')">Login</button>
      <button class="accent" onclick="go('signup')">Sign Up</button>
    `;
  }
}

window.toggleTheme = () => { document.body.classList.toggle("dark"); localStorage.setItem("theme", document.body.classList.contains("dark") ? "dark" : "light"); };
window.logout = () => {
  state.token = null; state.user = null; state.cart = [];
  localStorage.removeItem("token"); localStorage.removeItem("user");
  toast("Logged out");
  go("login");
};

// ===== auth views =====
function viewLogin() {
  $("#view").innerHTML = `
    <div class="auth-card">
      <h2>Login</h2>
      <form id="authForm">
        <input name="email" type="email" placeholder="Email" required />
        <input name="password" type="password" placeholder="Password" required />
        <button type="submit">Login</button>
      </form>
      <div class="switch">No account? <a onclick="go('signup')">Sign up</a></div>
    </div>`;
  $("#authForm").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const r = await api("/auth/login", { method: "POST", body: JSON.stringify(Object.fromEntries(fd)) });
      state.token = r.token; state.user = r.user;
      localStorage.setItem("token", r.token); localStorage.setItem("user", JSON.stringify(r.user));
      toast("Welcome back!", "success");
      await loadCart(); go("shop");
    } catch (err) { toast(err.message, "error"); }
  };
}

function viewSignup() {
  $("#view").innerHTML = `
    <div class="auth-card">
      <h2>Create Account</h2>
      <form id="authForm">
        <input name="name" placeholder="Full name" required />
        <input name="email" type="email" placeholder="Email" required />
        <input name="password" type="password" placeholder="Password (6+ chars)" minlength="6" required />
        <button type="submit">Sign Up</button>
      </form>
      <div class="switch">Have an account? <a onclick="go('login')">Log in</a></div>
    </div>`;
  $("#authForm").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const r = await api("/auth/signup", { method: "POST", body: JSON.stringify(Object.fromEntries(fd)) });
      state.token = r.token; state.user = r.user;
      localStorage.setItem("token", r.token); localStorage.setItem("user", JSON.stringify(r.user));
      toast("Account created!", "success");
      await loadCart(); go("shop");
    } catch (err) { toast(err.message, "error"); }
  };
}

// ===== shop view =====
async function viewShop() {
  $("#view").innerHTML = `
    <div class="controls">
      <input id="search" type="search" placeholder="🔍 Search products..." value="${esc(state.q)}" />
      <select id="catFilter">
        <option value="all">All categories</option>
        ${state.categories.map(c => `<option value="${c}" ${state.category === c ? "selected" : ""}>${c}</option>`).join("")}
      </select>
      <select id="sortBy">
        <option value="">Sort: Default</option>
        <option value="price_asc">Price: Low → High</option>
        <option value="price_desc">Price: High → Low</option>
        <option value="name">Name: A → Z</option>
      </select>
    </div>
    <div id="grid">${renderSkeleton(8)}</div>`;
  $("#search").oninput = (e) => { state.q = e.target.value; reloadProducts(); };
  $("#catFilter").onchange = (e) => { state.category = e.target.value; reloadProducts(); };
  $("#sortBy").onchange = (e) => { state.sort = e.target.value; reloadProducts(); };
  await reloadProducts();
}

async function reloadProducts() {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.category) params.set("category", state.category);
  if (state.sort) params.set("sort", state.sort);
  $("#grid").innerHTML = renderSkeleton(8);
  try {
    state.products = await api("/products?" + params);
  } catch (e) {
    $("#grid").innerHTML = `<div class="empty">Couldn't load products. ${esc(e.message)}<br><br><button class="btn btn-primary" onclick="reloadProducts()">Retry</button></div>`;
    return;
  }
  $("#grid").innerHTML = state.products.length ? state.products.map(p => `
    <div class="card">
      <img src="${esc(p.image)}" onclick="viewProduct('${p._id}')" />
      <div class="cat">${esc(p.category)}</div>
      <h3 onclick="viewProduct('${p._id}')">${esc(p.name)}</h3>
      <div class="rating">⭐ ${p.rating || 4.0} · ${p.stock > 0 ? p.stock + " in stock" : "Out of stock"}</div>
      <div class="price">$${fmt(p.price)}</div>
      <button onclick="addToCart('${p._id}')" ${p.stock < 1 ? "disabled" : ""}>
        ${p.stock < 1 ? "Sold Out" : "Add to Cart"}
      </button>
    </div>`).join("") : `<div class="empty">No products found.</div>`;
}

window.viewProduct = (id) => {
  const p = state.products.find(x => x._id === id);
  if (!p) return;
  openModal(`
    <span class="close" onclick="closeModal()">✕</span>
    <img src="${esc(p.image)}" />
    <div class="cat">${esc(p.category)}</div>
    <h2>${esc(p.name)}</h2>
    <div class="rating">⭐ ${p.rating || 4.0}</div>
    <p>${esc(p.description)}</p>
    <div class="price" style="font-size:1.5rem;margin:12px 0;">$${fmt(p.price)}</div>
    <p>${p.stock > 0 ? p.stock + " in stock" : "Out of stock"}</p>
    <button class="btn btn-primary btn-block" onclick="addToCart('${p._id}');closeModal()" ${p.stock < 1 ? "disabled" : ""}>
      ${p.stock < 1 ? "Sold Out" : "Add to Cart"}
    </button>
  `);
};

// ===== cart view =====
async function loadCart() {
  if (!state.token) { state.cart = []; return; }
  try { state.cart = await api("/cart"); } catch { state.cart = []; }
}

window.addToCart = async (id) => {
  if (!state.user) { toast("Please log in to add items", "error"); return go("login"); }
  try {
    state.cart = await api("/cart", { method: "POST", body: JSON.stringify({ product_id: id, qty: 1 }) });
    toast("Added to cart ✓", "success");
    renderActions();
    if (state.view === "cart") viewCart();
  } catch (e) { toast(e.message, "error"); }
};

async function viewCart() {
  if (!state.user) return go("login");
  await loadCart();
  const items = state.cart;
  const total = items.reduce((s, i) => s + i.price * i.qty, 0);
  $("#view").innerHTML = `
    <div class="panel">
      <h2>Your Cart</h2>
      ${items.length === 0 ? `<div class="empty">Your cart is empty.<br><br><button class="btn btn-primary" onclick="go('shop')">Browse Products</button></div>` : `
        ${items.map(it => `
          <div class="row">
            <img src="${esc(it.image)}" />
            <div class="meta">
              <div><strong>${esc(it.name)}</strong></div>
              <div>$${fmt(it.price)} each</div>
            </div>
            <div class="qty">
              <button onclick="updateQty('${it.product_id}', ${it.qty - 1})">-</button>
              <span>${it.qty}</span>
              <button onclick="updateQty('${it.product_id}', ${it.qty + 1})">+</button>
            </div>
            <div><strong>$${fmt(it.price * it.qty)}</strong></div>
            <button class="btn btn-danger" onclick="removeItem('${it.product_id}')">🗑</button>
          </div>`).join("")}
        ${items.length ? `
          <div class="total-row"><span>Total</span><span>$${fmt(total)}</span></div>
          <div style="display:flex;gap:8px;margin-top:16px;">
            <button class="btn btn-secondary" onclick="clearCart()">Clear Cart</button>
            <button class="btn btn-primary" style="flex:1" onclick="go('checkout')">Proceed to Checkout</button>
          </div>` : ""}
      `}
    </div>`;
}

window.updateQty = async (id, qty) => {
  try {
    if (qty < 1) return removeItem(id);
    state.cart = await api(`/cart/${id}`, { method: "PATCH", body: JSON.stringify({ qty }) });
    viewCart(); renderActions();
  } catch (e) { toast(e.message, "error"); }
};
window.removeItem = async (id) => {
  state.cart = await api(`/cart/${id}`, { method: "DELETE" });
  viewCart(); renderActions();
  toast("Removed");
};
window.clearCart = async () => {
  await api("/cart", { method: "DELETE" });
  state.cart = [];
  viewCart(); renderActions();
  toast("Cart cleared");
};

// ===== checkout =====
function viewCheckout() {
  if (!state.user) return go("login");
  if (state.cart.length === 0) { toast("Cart is empty", "error"); return go("shop"); }
  const total = state.cart.reduce((s, i) => s + i.price * i.qty, 0);
  $("#view").innerHTML = `
    <div class="panel" style="max-width:560px;margin:0 auto;">
      <h2>Checkout</h2>
      <form id="checkoutForm" style="display:flex;flex-direction:column;gap:10px;">
        <input name="name" placeholder="Full name" value="${esc(state.user.name)}" required />
        <input name="email" type="email" placeholder="Email" value="${esc(state.user.email)}" required />
        <input name="address" placeholder="Shipping address" required />
        <div class="total-row"><span>Total</span><span>$${fmt(total)}</span></div>
        <button class="btn btn-primary btn-block" type="submit">Place Order</button>
        <button class="btn btn-secondary btn-block" type="button" onclick="go('cart')">Back to Cart</button>
      </form>
    </div>`;
  $("#checkoutForm").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const order = await api("/orders", { method: "POST", body: JSON.stringify({ customer: Object.fromEntries(fd) }) });
      state.cart = []; renderActions();
      viewOrderSuccess(order);
    } catch (err) { toast(err.message, "error"); }
  };
}

function viewOrderSuccess(order) {
  $("#view").innerHTML = `
    <div class="panel" style="max-width:560px;margin:0 auto;text-align:center;">
      <h2>✅ Order Confirmed!</h2>
      <p>Thank you for your purchase.</p>
      <p><strong>Order ID:</strong> <code>${order._id}</code></p>
      <p><strong>Total:</strong> $${fmt(order.total)}</p>
      <p><strong>Delivery to:</strong> ${esc(order.customer.address)}</p>
      <button class="btn btn-primary btn-block" onclick="go('orders')">View My Orders</button>
      <button class="btn btn-secondary btn-block" onclick="go('shop')">Keep Shopping</button>
    </div>`;
}

// ===== orders =====
async function viewOrders() {
  if (!state.user) return go("login");
  state.orders = await api("/orders");
  $("#view").innerHTML = `
    <h2>My Orders</h2>
    <div class="orders-list">
      ${state.orders.length === 0 ? `<div class="empty">No orders yet.</div>` :
        state.orders.map(o => `
        <div class="order">
          <div class="order-header">
            <div><strong>Order ${o._id.slice(-8).toUpperCase()}</strong><br>
              <small style="color:var(--muted)">${new Date(o.created_at).toLocaleString()}</small>
            </div>
            <span class="status">${o.status}</span>
          </div>
          <div class="items">${o.items.map(i => `${esc(i.name)} × ${i.qty}`).join(", ")}</div>
          <div class="total-row"><span>Total</span><span>$${fmt(o.total)}</span></div>
        </div>`).join("")}
    </div>`;
}

// ===== admin =====
async function viewAdmin() {
  if (!state.user) return go("login");
  if (!state.user.is_admin) { toast("Admin only", "error"); return go("shop"); }
  $("#view").innerHTML = `
    <div class="panel">
      <h2>Admin</h2>
      <div style="display:flex;gap:8px;margin-bottom:12px;">
        <button class="btn btn-primary" id="adminTabProducts">Products</button>
        <button class="btn btn-secondary" id="adminTabOrders">Orders</button>
      </div>
      <div id="adminBody">${renderSkeleton(6)}</div>
    </div>`;
  document.getElementById("adminTabProducts").onclick = () => adminProducts();
  document.getElementById("adminTabOrders").onclick = () => adminOrders();
  await adminProducts();
}

async function adminProducts() {
  document.getElementById("adminTabProducts").className = "btn btn-primary";
  document.getElementById("adminTabOrders").className = "btn btn-secondary";
  document.getElementById("adminBody").innerHTML = renderSkeleton(6);
  let products;
  try {
    products = await api("/products");
  } catch (e) {
    document.getElementById("adminBody").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    return;
  }
  document.getElementById("adminBody").innerHTML = `
    <div style="margin-bottom:12px;"><button class="btn btn-primary" onclick="adminProductForm()">+ New Product</button></div>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr style="text-align:left;border-bottom:1px solid var(--border);">
        <th style="padding:8px;">Name</th><th>Category</th><th>Price</th><th>Stock</th><th></th>
      </tr></thead>
      <tbody>
        ${products.map(p => `
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:8px;"><strong>${esc(p.name)}</strong><br><small style="color:var(--muted)">${esc(p.description || '').slice(0,80)}</small></td>
            <td>${esc(p.category)}</td>
            <td>$${fmt(p.price)}</td>
            <td>${p.stock}</td>
            <td style="display:flex;gap:6px;padding:8px;">
              <button class="btn btn-secondary" onclick="adminProductForm('${p._id}')">Edit</button>
              <button class="btn btn-danger" onclick="adminDeleteProduct('${p._id}')">Delete</button>
              <label class="btn btn-secondary" style="cursor:pointer;">
                Image
                <input type="file" accept="image/*" style="display:none" onchange="adminUploadImage('${p._id}', event)" />
              </label>
            </td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}

window.adminProductForm = (id) => {
  const editing = !!id;
  const p = editing ? state.products.find(x => x._id === id) : null;
  openModal(`
    <span class="close" onclick="closeModal()">✕</span>
    <h2>${editing ? "Edit Product" : "New Product"}</h2>
    <form id="prodForm" style="display:flex;flex-direction:column;gap:8px;">
      <input name="name" placeholder="Name" value="${editing ? esc(p.name) : ''}" required />
      <input name="category" placeholder="Category" value="${editing ? esc(p.category) : ''}" required />
      <input name="price" type="number" step="0.01" min="0.01" placeholder="Price" value="${editing ? p.price : ''}" required />
      <input name="stock" type="number" min="0" placeholder="Stock" value="${editing ? p.stock : 0}" required />
      <input name="image" placeholder="Image URL" value="${editing ? esc(p.image) : ''}" />
      <textarea name="description" placeholder="Description" rows="3">${editing ? esc(p.description) : ''}</textarea>
      <button class="btn btn-primary btn-block" type="submit">${editing ? "Save" : "Create"}</button>
    </form>`);
  document.getElementById("prodForm").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {
      name: fd.get("name"),
      category: fd.get("category"),
      price: parseFloat(fd.get("price")),
      stock: parseInt(fd.get("stock"), 10),
      image: fd.get("image") || "",
      description: fd.get("description") || "",
    };
    try {
      if (editing) {
        await api(`/admin/products/${id}`, { method: "PATCH", body: JSON.stringify(body) });
      } else {
        await api("/admin/products", { method: "POST", body: JSON.stringify(body) });
      }
      closeModal();
      toast(editing ? "Product updated" : "Product created", "success");
      await adminProducts();
    } catch (err) { toast(err.message, "error"); }
  };
};

window.adminDeleteProduct = async (id) => {
  if (!confirm("Delete this product? This cannot be undone.")) return;
  try {
    await api(`/admin/products/${id}`, { method: "DELETE" });
    toast("Deleted", "success");
    await adminProducts();
  } catch (e) { toast(e.message, "error"); }
};

window.adminUploadImage = async (id, ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const headers = { Authorization: `Bearer ${state.token}` };
    const res = await fetch(`${API}/admin/products/${id}/image`, {
      method: "POST",
      headers,
      body: fd,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    toast("Image uploaded", "success");
  } catch (e) { toast(e.message, "error"); }
};

async function adminOrders() {
  document.getElementById("adminTabProducts").className = "btn btn-secondary";
  document.getElementById("adminTabOrders").className = "btn btn-primary";
  document.getElementById("adminBody").innerHTML = renderSkeleton(4);
  let orders;
  try {
    orders = await api("/admin/orders");
  } catch (e) {
    document.getElementById("adminBody").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    return;
  }
  const STATUSES = ["pending", "confirmed", "paid", "shipped", "delivered", "cancelled"];
  document.getElementById("adminBody").innerHTML = orders.length === 0 ? `<div class="empty">No orders yet.</div>` :
    orders.map(o => `
      <div class="order" style="margin-bottom:12px;">
        <div class="order-header">
          <div><strong>Order ${o._id.slice(-8).toUpperCase()}</strong><br>
            <small style="color:var(--muted)">${new Date(o.created_at).toLocaleString()} · ${esc((o.user && o.user.email) || 'user')}</small>
          </div>
          <span class="status">${esc(o.status)}</span>
        </div>
        <div class="items">${o.items.map(i => `${esc(i.name)} × ${i.qty}`).join(", ")}</div>
        <div class="total-row"><span>Total</span><span>$${fmt(o.total)}</span></div>
        <div style="margin-top:8px;display:flex;gap:6px;align-items:center;">
          <select data-oid="${o._id}" class="statusSel">
            ${STATUSES.map(s => `<option value="${s}" ${o.status === s ? "selected" : ""}>${s}</option>`).join("")}
          </select>
          <button class="btn btn-primary" onclick="adminUpdateStatus('${o._id}')">Update</button>
        </div>
      </div>`).join("");
}

window.adminUpdateStatus = async (id) => {
  const sel = document.querySelector(`select[data-oid="${id}"]`);
  if (!sel) return;
  try {
    await api(`/admin/orders/${id}`, { method: "PATCH", body: JSON.stringify({ status: sel.value }) });
    toast("Status updated", "success");
    await adminOrders();
  } catch (e) { toast(e.message, "error"); }
};

// ===== router =====
window.go = async (v) => {
  state.view = v;
  renderActions();
  if (v === "login") viewLogin();
  else if (v === "signup") viewSignup();
  else if (v === "shop") await viewShop();
  else if (v === "cart") await viewCart();
  else if (v === "checkout") viewCheckout();
  else if (v === "orders") await viewOrders();
  else if (v === "admin") await viewAdmin();
};

// ===== boot =====
async function boot() {
  if (localStorage.getItem("theme") === "dark") document.body.classList.add("dark");
  const retryEl = document.getElementById("apiRetry");
  if (retryEl) retryEl.onclick = (e) => { e.preventDefault(); boot(); };
  try { state.categories = await api("/categories"); } catch {}
  if (state.token) {
    try {
      state.user = await api("/auth/me");
      localStorage.setItem("user", JSON.stringify(state.user));
      await loadCart();
      go("shop");
    } catch {
      // Only force re-login on a real 401, not on a network blip.
      if (String(lastBootError || "").match(/401|invalid token|token expired/)) {
        state.token = null; state.user = null; state.cart = [];
        localStorage.removeItem("token"); localStorage.removeItem("user");
        go("login");
      } else {
        // Network is down; stay on whatever view we were on and show the banner.
        go("shop");
      }
    }
  } else {
    go("login");
  }
}
let lastBootError = null;
boot().catch(err => { lastBootError = err && err.message; });
