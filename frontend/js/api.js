const API = 'http://localhost:8000';

function getStarDisplay(rating) {
    const full = Math.round(rating);
    let stars = '';
    for (let i = 1; i <= 5; i++) {
        stars += i <= full ? '★' : '☆';
    }
    return `<span style="color:#FFD700">${stars}</span> ${rating > 0 ? rating.toFixed(1) : 'No reviews'}`;
}

function formatWhatsApp(number) {
    if (!number) return '';
    let num = number.replace(/\D/g, '');
    if (num.startsWith('0')) num = '92' + num.slice(1);
    if (!num.startsWith('92')) num = '92' + num;
    return num;
}

// ─── CART ───────────────────────────────────────────
let cart = JSON.parse(localStorage.getItem('findx_cart') || '[]');

function saveCart(){
  localStorage.setItem('findx_cart', JSON.stringify(cart));
  updateCartCount();
}
function updateCartCount(){
  const el = document.getElementById('cartCount');
  if(el) el.textContent = cart.length;
}
function addToCart(product){
  cart.push(product);
  saveCart();
  showToast('✓ ' + product.title + ' added to cart');
}
function removeFromCart(index){
  cart.splice(index,1);
  saveCart();
}

// ─── TOAST ──────────────────────────────────────────
function showToast(msg){
  const t = document.getElementById('toast');
  if(!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// ─── AUTH ───────────────────────────────────────────
function getToken(){ return localStorage.getItem('findx_token'); }
function setToken(t){ localStorage.setItem('findx_token', t); }
function clearToken(){ localStorage.removeItem('findx_token'); localStorage.removeItem('findx_user'); }
function getUser(){ return JSON.parse(localStorage.getItem('findx_user') || 'null'); }
function setUser(u){ localStorage.setItem('findx_user', JSON.stringify(u)); }
function isLoggedIn(){ return !!getToken(); }
function isAdmin(){ const u = getUser(); return u && (u.role === 'admin' || u.role === 'UserRole.admin'); }

function logout(){
  clearToken();
  window.location.href = 'index.html';
}

// ─── HTTP HELPERS ────────────────────────────────────
async function apiGet(path){
  const r = await fetch(API + path, { headers:{'Authorization':'Bearer '+getToken(),'ngrok-skip-browser-warning':'true'} });
  return r.json();
}
async function apiPost(path, data){
  const r = await fetch(API + path, {
    method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+getToken(),'ngrok-skip-browser-warning':'true'},
    body: JSON.stringify(data)
  });
  return r.json();
}
async function apiPut(path, data={}){
  const r = await fetch(API + path, {
    method:'PUT',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+getToken(),'ngrok-skip-browser-warning':'true'},
    body: JSON.stringify(data)
  });
  return r.json();
}
async function apiDelete(path){
  const r = await fetch(API + path, {
    method:'DELETE',
    headers:{'Authorization':'Bearer '+getToken(),'ngrok-skip-browser-warning':'true'}
  });
  return r.json();
}

// ─── SEARCH ──────────────────────────────────────────
async function searchListings(q='', category='', maxPrice='', city=''){
  let url = `${API}/api/search/?q=${encodeURIComponent(q)}`;
  if(category) url += `&category=${category}`;
  if(maxPrice)  url += `&max_price=${maxPrice}`;
  if(city)      url += `&city=${encodeURIComponent(city)}`;
  const r = await fetch(url, { headers:{'ngrok-skip-browser-warning':'true'} });
  return r.json();
}

// ─── REUSABLE HTML COMPONENTS ────────────────────────
function navHTML(){
  const user = getUser();
  const isBuyer = !user || user.role === 'buyer';
  return `
  <nav>
    <a href="index.html" class="logo">Find<span>X</span></a>
    <div class="nav-links">
      ${isBuyer ? `
        <a href="cart.html" class="cart-icon">
          🛒<div class="cart-count" id="cartCount">${cart.length}</div>
        </a>` : ''}
      ${user
        ? `<span style="font-size:13px;color:var(--text2);margin-right:4px">${user.name}</span>
           ${(user.role === 'admin' || user.role === 'UserRole.admin')   ? `<a href="admin.html"  class="nav-btn">Admin Panel</a>`  : ''}
           ${(user.role === 'seller' || user.role === 'UserRole.seller') ? `<a href="seller.html" class="nav-btn">My Store</a>`     : ''}
           <button class="nav-btn" onclick="logout()">Logout</button>`
        : `<a href="login.html" class="nav-btn">Login</a>
           <a href="register.html" class="nav-btn solid">Sign up</a>`
      }
    </div>
  </nav>`;
}

function footerHTML(){
  return `
  <footer>
    Find X &mdash; Lahore Hyperlocal Marketplace &nbsp;&middot;&nbsp;
    Final Year Project &nbsp;&middot;&nbsp;
    Built with FastAPI + PostgreSQL
  </footer>
  <div class="toast" id="toast"></div>`;
}

function productCardHTML(item){
  const safeItem = JSON.stringify(item).replace(/"/g,'&quot;');
  const user = getUser();
  const isBuyer = !user || user.role === 'buyer';
  return `
  <div class="product-card">
    ${item.delivery_available ? '<div class="product-badge badge-delivery">🚚 Delivery</div>' : ''}
    <div class="product-img">
      ${item.image_url
        ? `<img src="${item.image_url}" alt="${item.title}" loading="lazy">`
        : '<span>📦</span>'}
    </div>
    <div class="product-info">
      <div class="product-store">
        ${item.store_name || 'Store'} <span class="verified">✓</span> &middot; ${item.city || 'Lahore'}
      </div>
      <div class="product-name">${item.title}</div>
      <div class="product-bottom">
        <div class="product-price">PKR ${Number(item.price).toLocaleString()}</div>
        <div class="product-rating">${getStarDisplay(item.avg_rating || 0)} (${item.review_count || 0})</div>
      </div>
      ${isBuyer ? `
        <button class="btn btn-outline btn-full" style="margin-top:8px"
          onclick='addToCart(${safeItem})'>+ Add to Cart</button>` : ''}
      <a href="https://wa.me/${formatWhatsApp(item.whatsapp_number)}?text=Hi! I am interested in ${encodeURIComponent(item.title)}"
        target="_blank"
        class="btn btn-green btn-full" style="margin-top:6px">
        💬 Contact on WhatsApp
      </a>
      ${isBuyer ? `
      <button class="btn btn-outline btn-full" style="margin-top:6px;border-color:var(--cyan);color:var(--cyan)"
        onclick='openReviewModal("${item.store_id}","${item.id}","${item.title}")'>
        ⭐ Write a Review
      </button>` : ''}
      ${item.reviews && item.reviews.length > 0 ? `
      <div style="margin-top:12px;border-top:1px solid var(--border);padding-top:10px">
        <div style="font-size:12px;color:var(--text2);margin-bottom:8px">
          <span style="color:#FFD700">★</span> ${item.avg_rating || 0} · ${item.review_count || item.reviews.length} review${item.review_count > 1 ? 's' : ''}
        </div>
        <div id="reviews-shown-${item.id}">
          ${item.reviews.slice(0,2).map(r => `
            <div style="background:var(--bg3);border-radius:8px;padding:8px;margin-bottom:6px">
              <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                <span style="font-size:12px;font-weight:600">${r.buyer_name}</span>
                <span style="font-size:11px;color:#FFD700">${'★'.repeat(r.rating)}${'☆'.repeat(5-r.rating)}</span>
              </div>
              <div style="font-size:11px;color:var(--text2)">${r.comment || ''}</div>
            </div>
          `).join('')}
        </div>
        <div id="reviews-extra-${item.id}" style="display:none"></div>
        ${item.review_count > 2 ? `
          <button id="reviewbtn-${item.id}"
            onclick="toggleReviews('${item.id}')"
            style="font-size:12px;color:var(--cyan);background:none;border:none;cursor:pointer;padding:4px 0;display:flex;align-items:center;gap:4px">
            <span id="reviewbtn-icon-${item.id}">▼</span>
            <span id="reviewbtn-text-${item.id}">Show ${item.review_count - 2} more reviews</span>
          </button>
        ` : ''}
      </div>` : ''}
    </div>
  </div>`;
}

function showAlert(id, msg, type='error'){
  const el = document.getElementById(id);
  if(!el) return;
  el.textContent = msg;
  el.className = `alert alert-${type} show`;
}

function hideAlert(id){
  const el = document.getElementById(id);
  if(el) el.className = 'alert';
}

document.addEventListener('DOMContentLoaded', () => {
  updateCartCount();
});

async function submitReview(storeId, listingId, buyerName, rating, comment) {
    return await apiPost('/api/reviews/', {
        store_id:   storeId,
        listing_id: listingId,
        buyer_name: buyerName,
        rating:     rating,
        comment:    comment
    });
}

async function getStoreReviews(storeId) {
    return await apiGet(`/api/reviews/store/${storeId}`);
}

// ── Reviews ───────────────────────────────────────────
const reviewsExpanded = {};

async function toggleReviews(listingId) {
  const shown      = document.getElementById(`reviews-shown-${listingId}`);
  const extra      = document.getElementById(`reviews-extra-${listingId}`);
  const btnText    = document.getElementById(`reviewbtn-text-${listingId}`);
  const btnIcon    = document.getElementById(`reviewbtn-icon-${listingId}`);
  const isExpanded = reviewsExpanded[listingId];

  if (!isExpanded) {
    try {
      const data = await apiGet(`/api/reviews/listing/${listingId}`);
      shown.style.display = 'none';
      extra.innerHTML = `
        <div style="max-height:260px;overflow-y:auto;padding-right:4px;
          scrollbar-width:thin;scrollbar-color:var(--cyan) var(--bg3)">
          ${data.map(r => `
            <div style="background:var(--bg3);border-radius:8px;padding:8px;margin-bottom:6px">
              <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                <span style="font-size:12px;font-weight:600">${r.buyer_name}</span>
                <span style="font-size:11px;color:#FFD700">${'★'.repeat(r.rating)}${'☆'.repeat(5-r.rating)}</span>
              </div>
              <div style="font-size:11px;color:var(--text2)">${r.comment || ''}</div>
            </div>
          `).join('')}
        </div>
      `;
      extra.style.display = 'block';
      btnText.textContent = 'Show less';
      btnIcon.textContent = '▲';
      reviewsExpanded[listingId] = true;
    } catch(e) {
      console.error('Failed to load reviews:', e);
    }
  } else {
    shown.style.display = 'block';
    extra.style.display = 'none';
    extra.innerHTML = '';
    btnText.textContent = 'Show more reviews';
    btnIcon.textContent = '▼';
    reviewsExpanded[listingId] = false;
  }
}