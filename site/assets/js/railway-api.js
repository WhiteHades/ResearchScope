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

  // 2. Fall back to Supabase — swallow errors so papers.html never sees them
  if (_sb?.queryPapers) {
    try {
      const result = await _sb.queryPapers({ page, pageSize, search, tag, difficulty, type, source, year, sortBy, tagNormalizeMap });
      if (!result.error) return result;
      console.warn('[supabase] queryPapers error, falling back to static JSON:', result.error?.message || result.error);
    } catch (e) {
      console.warn('[supabase] queryPapers threw, falling back to static JSON:', e.message);
    }
  }

  // 3. Last resort — static JSON (always works, no auth needed)
  try {
    const res = await fetch('data/papers.json');
    const all = await res.json();
    const start = (page - 1) * pageSize;
    const filtered = search
      ? all.filter(p => (p.title||'').toLowerCase().includes(search.toLowerCase()) ||
                        (p.abstract||'').toLowerCase().includes(search.toLowerCase()))
      : all;
    return { data: filtered.slice(start, start + pageSize), count: filtered.length, error: null };
  } catch (e) {
    console.warn('[static] papers.json failed:', e.message);
  }

  return { data: [], count: 0, error: null };
}

async function _fetchTopPapers(limit = 500) {
  try {
    const json = await _apiFetch(`/papers?page_size=${Math.min(limit, 100)}&page=1`);
    if (json?.results?.length) return json.results;
  } catch { /* fall through */ }
  try { if (_sb?.fetchTopPapers) return await _sb.fetchTopPapers(limit); } catch { /* fall through */ }
  try {
    const res = await fetch('data/papers.json');
    const all = await res.json();
    return all.slice(0, limit);
  } catch { /* ignore */ }
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

    <!-- Header -->
    <div class="rs-modal-header">
      <div class="rs-modal-logo">🔭</div>
      <h2 class="rs-modal-title" id="rs-modal-heading">Welcome back</h2>
      <p class="rs-modal-subtitle" id="rs-modal-sub">Sign in to save papers and sync favourites</p>
      <button onclick="rsCloseModal()" class="rs-modal-close" aria-label="Close">
        <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <!-- Tab switcher -->
    <div class="rs-modal-tabs">
      <button id="rs-tab-login"    onclick="rsTab('login')"    class="rs-tab active">Sign in</button>
      <button id="rs-tab-register" onclick="rsTab('register')" class="rs-tab">Create account</button>
    </div>

    <!-- Error -->
    <div id="rs-auth-error" class="rs-auth-error hidden">
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="flex-shrink:0">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
      </svg>
      <span id="rs-auth-error-text"></span>
    </div>

    <!-- Login form -->
    <form id="rs-form-login" onsubmit="rsSubmitLogin(event)" class="rs-auth-form" autocomplete="on">
      <div class="rs-field">
        <label for="rs-login-email">Email address</label>
        <input id="rs-login-email" type="email" placeholder="you@example.com" required autocomplete="email"/>
      </div>
      <div class="rs-field">
        <label for="rs-login-password">Password</label>
        <input id="rs-login-password" type="password" placeholder="••••••••" required autocomplete="current-password"/>
      </div>
      <button type="submit" id="rs-login-btn" class="rs-submit-btn">
        <span id="rs-login-label">Sign in</span>
        <span id="rs-login-spinner" class="rs-btn-spinner hidden"></span>
      </button>
    </form>

    <!-- Register form -->
    <form id="rs-form-register" onsubmit="rsSubmitRegister(event)" class="rs-auth-form hidden" autocomplete="on">
      <div class="rs-field">
        <label for="rs-reg-name">Name <span style="opacity:.5;font-weight:400">(optional)</span></label>
        <input id="rs-reg-name" type="text" placeholder="Your name" autocomplete="name"/>
      </div>
      <div class="rs-field">
        <label for="rs-reg-email">Email address</label>
        <input id="rs-reg-email" type="email" placeholder="you@example.com" required autocomplete="email"/>
      </div>
      <div class="rs-field">
        <label for="rs-reg-password">Password</label>
        <input id="rs-reg-password" type="password" placeholder="Min. 8 characters" required minlength="8" autocomplete="new-password"/>
      </div>
      <button type="submit" id="rs-reg-btn" class="rs-submit-btn">
        <span id="rs-reg-label">Create account</span>
        <span id="rs-reg-spinner" class="rs-btn-spinner hidden"></span>
      </button>
    </form>

    <!-- Footer switch -->
    <p class="rs-modal-footer">
      <span id="rs-footer-login">No account? <button onclick="rsTab('register')" class="rs-link-btn">Create one free</button></span>
      <span id="rs-footer-register" class="hidden">Already have an account? <button onclick="rsTab('login')" class="rs-link-btn">Sign in</button></span>
    </p>

  </div>`;
  document.body.appendChild(el);
}

function _buildAuthStyles() {
  const s = document.createElement('style');
  s.textContent = `
  /* ── Modal overlay ─────────────────────────── */
  #rs-auth-modal {
    position: fixed; inset: 0; z-index: 9999;
    display: flex; align-items: center; justify-content: center;
    padding: 1rem;
    animation: rs-fade-in .18s ease;
  }
  #rs-auth-modal.hidden { display: none; }
  @keyframes rs-fade-in { from { opacity:0 } to { opacity:1 } }

  .rs-modal-backdrop {
    position: absolute; inset: 0;
    background: rgba(0,0,0,.5);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
  }

  /* ── Card ─────────────────────────────────── */
  .rs-modal-box {
    position: relative;
    width: min(420px, 100%);
    background: var(--rs-surface, #fff);
    border-radius: 1.25rem;
    padding: 2rem;
    box-shadow: 0 24px 64px rgba(0,0,0,.22), 0 0 0 1px rgba(0,0,0,.06);
    animation: rs-slide-up .22s cubic-bezier(.4,0,.2,1);
  }
  @keyframes rs-slide-up { from { opacity:0; transform:translateY(16px) } to { opacity:1; transform:none } }

  /* ── Header ───────────────────────────────── */
  .rs-modal-header { text-align: center; margin-bottom: 1.5rem; }
  .rs-modal-logo { font-size: 2rem; line-height: 1; margin-bottom: .5rem; }
  .rs-modal-title { font-size: 1.25rem; font-weight: 700; color: var(--rs-text,#111); margin: 0 0 .35rem; }
  .rs-modal-subtitle { font-size: .82rem; color: var(--rs-muted,#888); margin: 0; }
  .rs-modal-close {
    position: absolute; top: 1rem; right: 1rem;
    background: var(--rs-bg,#f8fafc); border: 1px solid var(--rs-border,#e2e8f0);
    border-radius: .5rem; cursor: pointer; color: var(--rs-muted,#888);
    width: 32px; height: 32px;
    display: flex; align-items: center; justify-content: center;
    transition: background .15s, color .15s;
  }
  .rs-modal-close:hover { background: var(--rs-border,#e2e8f0); color: var(--rs-text,#111); }

  /* ── Tabs ─────────────────────────────────── */
  .rs-modal-tabs {
    display: flex; gap: 0; margin-bottom: 1.5rem;
    background: var(--rs-bg,#f8fafc);
    border: 1px solid var(--rs-border,#e2e8f0);
    border-radius: .65rem; padding: .25rem;
  }
  .rs-tab {
    flex: 1; padding: .45rem .75rem;
    border: none; border-radius: .45rem;
    background: none; cursor: pointer;
    font-size: .85rem; font-weight: 500;
    color: var(--rs-muted,#888);
    transition: all .18s;
  }
  .rs-tab.active {
    background: var(--rs-surface,#fff);
    color: var(--rs-primary,#4f46e5);
    box-shadow: 0 1px 4px rgba(0,0,0,.1);
  }

  /* ── Error ────────────────────────────────── */
  .rs-auth-error {
    display: flex; align-items: flex-start; gap: .5rem;
    font-size: .82rem; color: #dc2626;
    background: #fef2f2; border: 1px solid #fecaca;
    border-radius: .5rem; padding: .6rem .75rem;
    margin-bottom: 1rem;
  }

  /* ── Fields ───────────────────────────────── */
  .rs-auth-form { display: flex; flex-direction: column; gap: 1rem; }
  .rs-field { display: flex; flex-direction: column; gap: .35rem; }
  .rs-field label { font-size: .8rem; font-weight: 600; color: var(--rs-text,#111); }
  .rs-field input {
    padding: .65rem .9rem;
    border: 1.5px solid var(--rs-border,#e2e8f0);
    border-radius: .6rem;
    font-size: .9rem;
    background: var(--rs-bg,#f8fafc);
    color: var(--rs-text,#111);
    outline: none;
    transition: border-color .15s, box-shadow .15s;
    font-family: inherit;
  }
  .rs-field input::placeholder { color: var(--rs-muted,#94a3b8); }
  .rs-field input:focus {
    border-color: var(--rs-primary,#4f46e5);
    box-shadow: 0 0 0 3px rgba(79,70,229,.12);
    background: var(--rs-surface,#fff);
  }

  /* ── Submit button ────────────────────────── */
  .rs-submit-btn {
    display: flex; align-items: center; justify-content: center; gap: .5rem;
    padding: .75rem;
    background: linear-gradient(135deg, #6366f1, #4f46e5);
    color: #fff; border: none; border-radius: .65rem;
    font-size: .95rem; font-weight: 600;
    cursor: pointer; margin-top: .25rem;
    transition: opacity .15s, transform .12s;
    box-shadow: 0 4px 12px rgba(79,70,229,.35);
    font-family: inherit;
  }
  .rs-submit-btn:hover { opacity: .92; transform: translateY(-1px); }
  .rs-submit-btn:active { transform: none; }
  .rs-submit-btn:disabled { opacity: .6; cursor: not-allowed; transform: none; }

  /* ── Spinner ──────────────────────────────── */
  .rs-btn-spinner {
    width: 16px; height: 16px;
    border: 2px solid rgba(255,255,255,.35);
    border-top-color: #fff;
    border-radius: 50%;
    animation: rs-spin .7s linear infinite;
  }
  @keyframes rs-spin { to { transform: rotate(360deg) } }

  /* ── Footer ───────────────────────────────── */
  .rs-modal-footer { text-align: center; font-size: .82rem; color: var(--rs-muted,#888); margin: 1.25rem 0 0; }
  .rs-link-btn {
    background: none; border: none; cursor: pointer;
    color: var(--rs-primary,#4f46e5); font-weight: 600;
    font-size: inherit; font-family: inherit; padding: 0;
  }
  .rs-link-btn:hover { text-decoration: underline; }

  /* ── Nav auth button ──────────────────────── */
  #rs-auth-btn {
    display: flex; align-items: center; gap: .4rem;
    padding: .35rem .8rem;
    border-radius: .5rem;
    border: 1.5px solid var(--rs-border,#e2e8f0);
    background: var(--rs-surface,#fff);
    cursor: pointer; font-size: .8rem; font-weight: 600;
    color: var(--rs-text,#111); white-space: nowrap;
    transition: border-color .15s, box-shadow .15s;
  }
  #rs-auth-btn:hover {
    border-color: var(--rs-primary,#4f46e5);
    box-shadow: 0 0 0 3px rgba(79,70,229,.1);
  }

  /* ── User dropdown ────────────────────────── */
  #rs-user-menu {
    position: absolute; right: 0; top: calc(100% + 8px);
    background: var(--rs-surface,#fff);
    border: 1px solid var(--rs-border,#e2e8f0);
    border-radius: .75rem;
    box-shadow: 0 8px 24px rgba(0,0,0,.12);
    min-width: 180px; z-index: 999; overflow: hidden;
    animation: rs-slide-up .15s ease;
  }
  #rs-user-menu a, #rs-user-menu button {
    display: flex; align-items: center; gap: .5rem;
    width: 100%; text-align: left;
    padding: .6rem 1rem; font-size: .85rem;
    background: none; border: none; cursor: pointer;
    color: var(--rs-text,#111); text-decoration: none;
    transition: background .12s;
  }
  #rs-user-menu a:hover, #rs-user-menu button:hover { background: var(--rs-bg,#f8fafc); }
  #rs-auth-wrap { position: relative; }
  `;
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
  document.getElementById('rs-auth-error')?.classList.add('hidden');
};

window.rsTab = function(tab) {
  const isLogin = tab === 'login';
  document.getElementById('rs-form-login').classList.toggle('hidden', !isLogin);
  document.getElementById('rs-form-register').classList.toggle('hidden', isLogin);
  document.getElementById('rs-tab-login').classList.toggle('active', isLogin);
  document.getElementById('rs-tab-register').classList.toggle('active', !isLogin);
  document.getElementById('rs-footer-login').classList.toggle('hidden', !isLogin);
  document.getElementById('rs-footer-register').classList.toggle('hidden', isLogin);
  document.getElementById('rs-auth-error')?.classList.add('hidden');
  document.getElementById('rs-modal-heading').textContent = isLogin ? 'Welcome back' : 'Create your account';
  document.getElementById('rs-modal-sub').textContent = isLogin
    ? 'Sign in to save papers and sync favourites'
    : 'Free account — no credit card required';
};

function _setFormLoading(btnId, spinnerId, labelId, loading) {
  const btn = document.getElementById(btnId);
  const spinner = document.getElementById(spinnerId);
  const label = document.getElementById(labelId);
  if (btn) btn.disabled = loading;
  if (spinner) spinner.classList.toggle('hidden', !loading);
  if (label) label.style.opacity = loading ? '.5' : '1';
}

function _showAuthError(msg) {
  const el = document.getElementById('rs-auth-error');
  const txt = document.getElementById('rs-auth-error-text');
  if (el)  el.classList.remove('hidden');
  if (txt) txt.textContent = msg;
}

window.rsSubmitLogin = async function(e) {
  e.preventDefault();
  _setFormLoading('rs-login-btn', 'rs-login-spinner', 'rs-login-label', true);
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
    _setFormLoading('rs-login-btn', 'rs-login-spinner', 'rs-login-label', false);
  }
};

window.rsSubmitRegister = async function(e) {
  e.preventDefault();
  _setFormLoading('rs-reg-btn', 'rs-reg-spinner', 'rs-reg-label', true);
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
    _setFormLoading('rs-reg-btn', 'rs-reg-spinner', 'rs-reg-label', false);
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
