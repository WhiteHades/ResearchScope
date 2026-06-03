/**
 * ResearchScope — Railway API client
 *
 * Overrides window._rs_supabase with Railway-backed implementations so
 * all existing pages work without changes. Also adds auth + favourites.
 *
 * Fallback chain: Railway API → Supabase → static JSON
 * Sign-in is NEVER required for browsing — only for favourites.
 */

const RS_API = 'https://researchscope-production.up.railway.app';

// Save the Supabase client loaded before us so we can fall back to it
const _sb = window._rs_supabase || null;

// ── Auth state ────────────────────────────────────────────────────────────────

const _auth = {
  TOKEN_KEY: 'rs_jwt',
  USER_KEY:  'rs_user',

  token() { return localStorage.getItem(this.TOKEN_KEY); },
  user()  {
    try { return JSON.parse(localStorage.getItem(this.USER_KEY) || 'null'); }
    catch { return null; }
  },
  isLoggedIn() { return !!this.token(); },
  save(token, user) {
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.USER_KEY, JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
  },
};

// ── Core fetch helper ─────────────────────────────────────────────────────────

async function _apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  const token = _auth.token();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${RS_API}${path}`, { ...opts, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw Object.assign(new Error(err.detail || 'API error'), { status: res.status });
  }
  return res.status === 204 ? null : res.json();
}

// ── Papers ────────────────────────────────────────────────────────────────────

async function _queryPapers({
  page = 1, pageSize = 25,
  search = '', tag = '', difficulty = '', type = '',
  source = '', year = '', sortBy = 'paper_score',
  tagNormalizeMap = {},
} = {}) {
  const params = new URLSearchParams({ page, page_size: pageSize });
  if (search) params.set('search', search);
  if (tag)    params.set('tag', tag);
  if (year)   params.set('year', year);
  if (source === 'arxiv')           params.set('source_type', 'preprint');
  else if (source === 'conference') params.set('source_type', 'conference');
  else if (source === 'journal')    params.set('source_type', 'journal');

  // 1. Try Railway
  try {
    const json = await _apiFetch(`/papers?${params}`);
    if (json && (json.total > 0 || json.results?.length > 0))
      return { data: json.results || [], count: json.total || 0, error: null };
  } catch (e) {
    console.warn('[railway] queryPapers failed, falling back to Supabase:', e.message);
  }

  // 2. Fall back to Supabase
  if (_sb?.queryPapers) {
    return _sb.queryPapers({ page, pageSize, search, tag, difficulty, type, source, year, sortBy, tagNormalizeMap });
  }

  return { data: [], count: 0, error: null };
}

async function _fetchTopPapers(limit = 500) {
  try {
    const json = await _apiFetch(`/papers?page_size=${Math.min(limit, 100)}&page=1`);
    if (json?.results?.length) return json.results;
  } catch { /* fall through */ }
  if (_sb?.fetchTopPapers) return _sb.fetchTopPapers(limit);
  return [];
}

async function _fetchConferencePapers(limit = 2000) {
  try {
    const json = await _apiFetch(`/papers/conferences?page_size=${Math.min(limit, 100)}&page=1`);
    if (json?.results?.length) return json.results;
  } catch { /* fall through */ }
  if (_sb?.fetchConferencePapers) return _sb.fetchConferencePapers(limit);
  return [];
}

async function _fetchJournalPapers(limit = 2000) {
  try {
    const json = await _apiFetch(`/papers/journals?page_size=${Math.min(limit, 100)}&page=1`);
    if (json?.results?.length) return json.results;
  } catch { /* fall through */ }
  return [];
}

async function _searchPapersQuick(query, limit = 5) {
  if (!query || query.trim().length < 2) return [];
  // 1. Try Railway full-text search
  try {
    const json = await _apiFetch(`/search?${new URLSearchParams({ q: query.trim(), limit })}`);
    if (json?.results?.length) return json.results;
  } catch { /* fall through */ }
  // 2. Fall back to Supabase
  if (_sb?.searchPapersQuick) return _sb.searchPapersQuick(query, limit);
  return [];
}

// ── Auth API ──────────────────────────────────────────────────────────────────

const _authApi = {
  async register(email, password, name = '') {
    const data = await _apiFetch('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    });
    const user = await _apiFetch('/auth/me', {
      headers: { Authorization: `Bearer ${data.access_token}` },
    });
    _auth.save(data.access_token, user);
    return user;
  },

  async login(email, password) {
    const data = await _apiFetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    _auth.save(data.access_token, {});
    const user = await _apiFetch('/auth/me');
    _auth.save(data.access_token, user);
    return user;
  },

  logout() {
    _auth.clear();
    _updateAuthNav();
  },

  isLoggedIn: () => _auth.isLoggedIn(),
  currentUser: () => _auth.user(),
};

// ── Favourites API ────────────────────────────────────────────────────────────

const _favsApi = {
  async list() {
    return _apiFetch('/favourites');
  },
  async add(paperId) {
    return _apiFetch(`/favourites/${encodeURIComponent(paperId)}`, { method: 'POST' });
  },
  async remove(paperId) {
    return _apiFetch(`/favourites/${encodeURIComponent(paperId)}`, { method: 'DELETE' });
  },
};

// ── Auth UI ───────────────────────────────────────────────────────────────────

function _buildModal() {
  const el = document.createElement('div');
  el.id = 'rs-auth-modal';
  el.classList.add('hidden');
  el.innerHTML = `
  <div class="rs-modal-backdrop" onclick="rsCloseModal()"></div>
  <div class="rs-modal-box">
    <button onclick="rsCloseModal()" class="rs-modal-close">✕</button>
    <div class="rs-modal-tabs">
      <button id="rs-tab-login"    onclick="rsTab('login')"    class="rs-tab active">Sign in</button>
      <button id="rs-tab-register" onclick="rsTab('register')" class="rs-tab">Register</button>
    </div>
    <p id="rs-auth-error" class="rs-auth-error hidden"></p>

    <!-- Login -->
    <form id="rs-form-login" onsubmit="rsSubmitLogin(event)" class="rs-auth-form">
      <input id="rs-login-email"    type="email"    placeholder="Email"    required autocomplete="email"/>
      <input id="rs-login-password" type="password" placeholder="Password" required autocomplete="current-password"/>
      <button type="submit" id="rs-login-btn">Sign in</button>
    </form>

    <!-- Register -->
    <form id="rs-form-register" onsubmit="rsSubmitRegister(event)" class="rs-auth-form hidden">
      <input id="rs-reg-name"     type="text"     placeholder="Name (optional)"/>
      <input id="rs-reg-email"    type="email"    placeholder="Email"    required autocomplete="email"/>
      <input id="rs-reg-password" type="password" placeholder="Password (min 8 chars)" required minlength="8" autocomplete="new-password"/>
      <button type="submit" id="rs-reg-btn">Create account</button>
    </form>
  </div>`;
  document.body.appendChild(el);
}

function _buildAuthStyles() {
  const s = document.createElement('style');
  s.textContent = `
  #rs-auth-modal { position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center }
  #rs-auth-modal.hidden { display:none }
  .rs-modal-backdrop { position:absolute;inset:0;background:rgba(0,0,0,.45) }
  .rs-modal-box { position:relative;background:var(--rs-surface,#fff);border-radius:1rem;padding:2rem;width:min(400px,92vw);box-shadow:0 20px 60px rgba(0,0,0,.25) }
  .rs-modal-close { position:absolute;top:.75rem;right:.75rem;background:none;border:none;font-size:1.1rem;cursor:pointer;color:var(--rs-muted,#888) }
  .rs-modal-tabs { display:flex;gap:.5rem;margin-bottom:1.25rem }
  .rs-tab { flex:1;padding:.5rem;border:1px solid var(--rs-border,#e5e7eb);border-radius:.5rem;background:none;cursor:pointer;font-size:.9rem;font-weight:500;color:var(--rs-muted,#888) }
  .rs-tab.active { background:var(--rs-primary,#6366f1);color:#fff;border-color:var(--rs-primary,#6366f1) }
  .rs-auth-form { display:flex;flex-direction:column;gap:.75rem }
  .rs-auth-form input { padding:.6rem .9rem;border:1px solid var(--rs-border,#e5e7eb);border-radius:.5rem;font-size:.9rem;background:var(--rs-bg,#f9fafb);color:var(--rs-text,#111) }
  .rs-auth-form button[type=submit] { padding:.65rem;background:var(--rs-primary,#6366f1);color:#fff;border:none;border-radius:.5rem;font-weight:600;cursor:pointer;font-size:.95rem }
  .rs-auth-form button[type=submit]:hover { opacity:.9 }
  .rs-auth-error { color:#dc2626;font-size:.82rem;margin-bottom:.5rem;padding:.4rem .75rem;background:#fef2f2;border-radius:.4rem }
  #rs-auth-btn { display:flex;align-items:center;gap:.35rem;padding:.3rem .7rem;border-radius:.5rem;border:1px solid var(--rs-border,#e5e7eb);background:none;cursor:pointer;font-size:.8rem;font-weight:500;color:var(--rs-text,#111);white-space:nowrap }
  #rs-auth-btn:hover { border-color:var(--rs-primary,#6366f1);color:var(--rs-primary,#6366f1) }
  #rs-user-menu { position:absolute;right:0;top:2.5rem;background:var(--rs-surface,#fff);border:1px solid var(--rs-border,#e5e7eb);border-radius:.6rem;box-shadow:0 8px 24px rgba(0,0,0,.12);min-width:160px;z-index:999;overflow:hidden }
  #rs-user-menu a, #rs-user-menu button { display:block;width:100%;text-align:left;padding:.6rem 1rem;font-size:.85rem;background:none;border:none;cursor:pointer;color:var(--rs-text,#111);text-decoration:none }
  #rs-user-menu a:hover, #rs-user-menu button:hover { background:var(--rs-hover,#f3f4f6) }
  #rs-auth-wrap { position:relative }`;
  document.head.appendChild(s);
}

function _injectAuthButton() {
  const toggle = document.getElementById('theme-toggle');
  if (!toggle) return;

  const wrap = document.createElement('div');
  wrap.id = 'rs-auth-wrap';
  wrap.className = 'hidden lg:block';
  toggle.parentNode.insertBefore(wrap, toggle);

  const btn = document.createElement('button');
  btn.id = 'rs-auth-btn';
  wrap.appendChild(btn);

  _updateAuthNav();

  wrap.addEventListener('click', (e) => {
    const menu = document.getElementById('rs-user-menu');
    if (!menu) { rsOpenModal(); return; }
    menu.remove();
  });
}

function _updateAuthNav() {
  const btn = document.getElementById('rs-auth-btn');
  if (!btn) return;

  const user = _auth.user();
  if (_auth.isLoggedIn() && user) {
    const initial = (user.name || user.email || '?')[0].toUpperCase();
    btn.innerHTML = `<span style="width:22px;height:22px;border-radius:50%;background:var(--rs-primary,#6366f1);color:#fff;display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700">${escHtml(initial)}</span>${escHtml(user.name || user.email)}`;
    btn.onclick = (e) => { e.stopPropagation(); _showUserMenu(); };
  } else {
    btn.innerHTML = `<svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>Sign in`;
    btn.onclick = (e) => { e.stopPropagation(); rsOpenModal(); };
  }
}

function _showUserMenu() {
  document.getElementById('rs-user-menu')?.remove();
  const user = _auth.user();
  const wrap = document.getElementById('rs-auth-wrap');
  if (!wrap) return;

  const menu = document.createElement('div');
  menu.id = 'rs-user-menu';
  menu.innerHTML = `
    <div style="padding:.6rem 1rem;font-size:.75rem;color:var(--rs-muted,#888);border-bottom:1px solid var(--rs-border,#e5e7eb)">${escHtml(user?.email || '')}</div>
    <a href="favourites.html">⭐ My Favourites</a>
    <button onclick="rsLogout()">Sign out</button>`;
  wrap.appendChild(menu);

  setTimeout(() => document.addEventListener('click', function close(e) {
    if (!wrap.contains(e.target)) { menu.remove(); document.removeEventListener('click', close); }
  }), 0);
}

// ── Global modal helpers ──────────────────────────────────────────────────────

window.rsOpenModal = function() {
  document.getElementById('rs-auth-modal')?.classList.remove('hidden');
};

window.rsCloseModal = function() {
  document.getElementById('rs-auth-modal')?.classList.add('hidden');
  document.getElementById('rs-auth-error').classList.add('hidden');
};

window.rsTab = function(tab) {
  document.getElementById('rs-form-login').classList.toggle('hidden',    tab !== 'login');
  document.getElementById('rs-form-register').classList.toggle('hidden', tab !== 'register');
  document.getElementById('rs-tab-login').classList.toggle('active',    tab === 'login');
  document.getElementById('rs-tab-register').classList.toggle('active', tab === 'register');
  document.getElementById('rs-auth-error').classList.add('hidden');
};

function _setFormLoading(btnId, loading, label) {
  const btn = document.getElementById(btnId);
  if (btn) { btn.disabled = loading; btn.textContent = loading ? 'Please wait…' : label; }
}

function _showAuthError(msg) {
  const el = document.getElementById('rs-auth-error');
  if (el) { el.textContent = msg; el.classList.remove('hidden'); }
}

window.rsSubmitLogin = async function(e) {
  e.preventDefault();
  _setFormLoading('rs-login-btn', true, 'Sign in');
  try {
    await _authApi.login(
      document.getElementById('rs-login-email').value,
      document.getElementById('rs-login-password').value,
    );
    rsCloseModal();
    _updateAuthNav();
  } catch (err) {
    _showAuthError(err.message || 'Login failed. Check your credentials.');
  } finally {
    _setFormLoading('rs-login-btn', false, 'Sign in');
  }
};

window.rsSubmitRegister = async function(e) {
  e.preventDefault();
  _setFormLoading('rs-reg-btn', true, 'Create account');
  try {
    await _authApi.register(
      document.getElementById('rs-reg-email').value,
      document.getElementById('rs-reg-password').value,
      document.getElementById('rs-reg-name').value,
    );
    rsCloseModal();
    _updateAuthNav();
  } catch (err) {
    _showAuthError(err.message || 'Registration failed. Try a different email.');
  } finally {
    _setFormLoading('rs-reg-btn', false, 'Create account');
  }
};

window.rsLogout = function() {
  _authApi.logout();
  if (window.location.pathname.endsWith('favourites.html')) {
    window.location.href = 'index.html';
  }
};

// ── Override window._rs_supabase ──────────────────────────────────────────────

window._rs_supabase = {
  // Papers
  queryPapers:           _queryPapers,
  fetchTopPapers:        _fetchTopPapers,
  fetchConferencePapers: _fetchConferencePapers,
  fetchJournalPapers:    _fetchJournalPapers,
  searchPapersQuick:     _searchPapersQuick,
  // Keep Supabase-only methods as no-ops (authors/topics/gaps still use static JSON)
  fetchAllAuthors:  () => Promise.resolve([]),
  fetchAllTopics:   () => Promise.resolve([]),
  fetchAllGaps:     () => Promise.resolve([]),
  fetchAllLabs:     () => Promise.resolve([]),
  getDb:            () => null,
};

// ── Public API surface ────────────────────────────────────────────────────────

window._rs_api = {
  auth:       _authApi,
  favourites: _favsApi,
  papers: {
    list:        (p) => _apiFetch(`/papers?${new URLSearchParams(p)}`),
    get:         (id) => _apiFetch(`/papers/${encodeURIComponent(id)}`),
    conferences: (p)  => _apiFetch(`/papers/conferences?${new URLSearchParams(p)}`),
    journals:    (p)  => _apiFetch(`/papers/journals?${new URLSearchParams(p)}`),
  },
  search: (q, opts = {}) => _apiFetch(`/search?${new URLSearchParams({ q, ...opts })}`),
};

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  _buildAuthStyles();
  _buildModal();
  _injectAuthButton();
});
