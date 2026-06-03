/**
 * ResearchScope — Railway API client
 *
 * Overrides window._rs_supabase with Railway-backed implementations so
 * all existing pages work without changes. Also adds auth + favourites.
 *
 * Fallback chain: Railway API → Supabase → static JSON
 * Sign-in is NEVER required for browsing — only for favourites.
 * Auth UI lives on dedicated signin.html / register.html pages.
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
    if (json && Array.isArray(json.results))
      return { data: json.results, count: json.total ?? 0, error: null };
  } catch (e) {
    console.warn('[railway] queryPapers failed, falling back to Supabase:', e.message);
  }

  // 2. Fall back to Supabase
  if (_sb?.queryPapers) {
    try {
      const result = await _sb.queryPapers({ page, pageSize, search, tag, difficulty, type, source, year, sortBy, tagNormalizeMap });
      if (!result.error) return result;
      console.warn('[supabase] queryPapers error, falling back to static JSON:', result.error?.message || result.error);
    } catch (e) {
      console.warn('[supabase] queryPapers threw, falling back to static JSON:', e.message);
    }
  }

  // 3. Last resort — static JSON
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
    const PAGE = 100; // backend max page_size
    const results = [];
    for (let page = 1; results.length < limit; page++) {
      const need = Math.min(PAGE, limit - results.length);
      const json = await _apiFetch(`/papers?page_size=${need}&page=${page}`);
      if (!json?.results?.length) break;
      results.push(...json.results);
      if (json.results.length < need) break; // last page
    }
    if (results.length) return results;
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
  try {
    const json = await _apiFetch(`/search?${new URLSearchParams({ q: query.trim(), limit })}`);
    if (json?.results?.length) return json.results;
  } catch { /* fall through */ }
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
    // Save token immediately so the account is recoverable even if /auth/me fails.
    _auth.save(data.access_token, {});
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
    // Fetch profile before persisting so a /auth/me failure leaves no partial state.
    const user = await _apiFetch('/auth/me', {
      headers: { Authorization: `Bearer ${data.access_token}` },
    });
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

// ── Nav auth button + dropdown ────────────────────────────────────────────────

function _injectNavStyles() {
  const s = document.createElement('style');
  s.textContent = `
  #rs-auth-btn{
    display:flex;align-items:center;gap:.4rem;
    padding:.35rem .8rem;border-radius:.5rem;
    border:1.5px solid var(--rs-border,#e2e8f0);
    background:var(--rs-surface,#fff);cursor:pointer;
    font-size:.8rem;font-weight:600;color:var(--rs-text,#111);white-space:nowrap;
    transition:border-color .15s,box-shadow .15s;
  }
  #rs-auth-btn:hover{border-color:var(--rs-primary,#4f46e5);box-shadow:0 0 0 3px rgba(79,70,229,.1)}
  #rs-user-menu{
    position:absolute;right:0;top:calc(100% + 8px);
    background:var(--rs-surface,#fff);
    border:1px solid var(--rs-border,#e2e8f0);
    border-radius:.75rem;
    box-shadow:0 8px 24px rgba(0,0,0,.12);
    min-width:180px;z-index:999;overflow:hidden;
  }
  @keyframes rs-slide-up{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
  #rs-user-menu{animation:rs-slide-up .15s ease}
  #rs-user-menu a,#rs-user-menu button{
    display:flex;align-items:center;gap:.5rem;
    width:100%;text-align:left;padding:.6rem 1rem;
    font-size:.85rem;background:none;border:none;cursor:pointer;
    color:var(--rs-text,#111);text-decoration:none;transition:background .12s;
  }
  #rs-user-menu a:hover,#rs-user-menu button:hover{background:var(--rs-bg,#f8fafc)}
  #rs-auth-wrap{position:relative}
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
    if (!menu) { if (!_auth.isLoggedIn()) rsOpenModal(); return; }
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

// ── Auth navigation helpers ───────────────────────────────────────────────────

window.rsOpenModal = function(returnTo) {
  const page = returnTo || window.location.pathname.split('/').pop() || 'index.html';
  window.location.href = `signin.html?returnTo=${encodeURIComponent(page)}`;
};

window.rsLogout = function() {
  _authApi.logout();
  if (window.location.pathname.endsWith('favourites.html')) {
    window.location.href = 'index.html';
  }
};

// ── Supabase → static JSON fallback helper ────────────────────────────────────

async function _sbFetch(method, limit, staticPath) {
  if (_sb?.[method]) {
    try {
      const result = await _sb[method](limit);
      if (Array.isArray(result) && result.length) return result;
    } catch { /* fall through */ }
  }
  try {
    const res = await fetch(staticPath);
    const data = await res.json();
    return Array.isArray(data) ? (limit ? data.slice(0, limit) : data) : [];
  } catch { return []; }
}

// ── Override window._rs_supabase ──────────────────────────────────────────────

window._rs_supabase = {
  queryPapers:           _queryPapers,
  fetchTopPapers:        _fetchTopPapers,
  fetchConferencePapers: _fetchConferencePapers,
  fetchJournalPapers:    _fetchJournalPapers,
  searchPapersQuick:     _searchPapersQuick,
  fetchAllAuthors:  (n) => _sbFetch('fetchAllAuthors', n, 'data/authors.json'),
  fetchAllTopics:   (n) => _sbFetch('fetchAllTopics',  n, 'data/topics.json'),
  fetchAllGaps:     (n) => _sbFetch('fetchAllGaps',    n, 'data/gaps.json'),
  fetchAllLabs:     (n) => _sbFetch('fetchAllLabs',    n, 'data/labs.json'),
  getDb:            () => _sb?.getDb?.() ?? null,
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
  _injectNavStyles();
  _injectAuthButton();
});
