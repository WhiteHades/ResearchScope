/**
 * ResearchScope — Railway API client
 *
 * Provides window._rs_data, the data client used by every page, plus auth
 * and favourites. Backed by the Railway FastAPI service.
 *
 * Fallback chain: Railway API → static JSON (site/data/*.json)
 * Sign-in is NEVER required for browsing — only for favourites.
 * Auth UI lives on dedicated signin / register pages.
 */

const RS_API = 'https://researchscope-production.up.railway.app';

// Public site shows at most this many papers per section (arXiv / conference /
// journal) — 3 000 total. The full corpus stays available via the API and the
// Hugging Face dataset; this just bounds what the browse pages paginate through.
const SECTION_CAP = 1000;

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
  rank = '', venue = '',
  tagNormalizeMap = {},
} = {}) {
  const params = new URLSearchParams({ page, page_size: pageSize });
  if (search) params.set('search', search);
  if (tag)    params.set('tag', tag);
  if (year)   params.set('year', year);
  if (rank)   params.set('rank', rank);
  if (venue)  params.set('venue', venue);
  if (source === 'arxiv')           params.set('source_type', 'preprint');
  else if (source === 'conference') params.set('source_type', 'conference');
  else if (source === 'journal')    params.set('source_type', 'journal');

  const start = (page - 1) * pageSize;

  // 1. Try Railway — clamp the reported count and trim rows past the cap so the
  // browse page paginates through at most SECTION_CAP papers for this section.
  try {
    const json = await _apiFetch(`/papers?${params}`);
    if (json && Array.isArray(json.results)) {
      const count = Math.min(json.total ?? 0, SECTION_CAP);
      let data = json.results;
      if (start >= SECTION_CAP) data = [];
      else if (start + data.length > SECTION_CAP) data = data.slice(0, SECTION_CAP - start);
      return { data, count, error: null };
    }
  } catch (e) {
    console.warn('[railway] queryPapers failed, falling back to static JSON:', e.message);
  }

  // 2. Last resort — static JSON (already capped at 1 000 by the generator)
  try {
    const res = await fetch('data/papers.json');
    const all = await res.json();
    const filtered = search
      ? all.filter(p => (p.title||'').toLowerCase().includes(search.toLowerCase()) ||
                        (p.abstract||'').toLowerCase().includes(search.toLowerCase()))
      : all;
    const count = Math.min(filtered.length, SECTION_CAP);
    return { data: filtered.slice(start, Math.min(start + pageSize, SECTION_CAP)), count, error: null };
  } catch (e) {
    console.warn('[static] papers.json failed:', e.message);
  }

  return { data: [], count: 0, error: null };
}

async function _fetchTopPapers(limit = 500) {
  // arXiv preprints only — matches the data/papers.json static fallback below
  // (which is the arXiv section). Without source_type=preprint the global
  // /papers endpoint is ranked across all sources and is now dominated by
  // conference/journal papers, which starved arXiv-only consumers like the
  // weekly digest of any results.
  try {
    const PAGE = 100; // backend max page_size
    const results = [];
    for (let page = 1; results.length < limit; page++) {
      const need = Math.min(PAGE, limit - results.length);
      const json = await _apiFetch(`/papers?source_type=preprint&page_size=${need}&page=${page}`);
      if (!json?.results?.length) break;
      results.push(...json.results);
      if (json.results.length < need) break; // last page
    }
    if (results.length) return results;
  } catch { /* fall through */ }
  try {
    const res = await fetch('data/papers.json');
    const all = await res.json();
    return all.slice(0, limit);
  } catch { /* ignore */ }
  return [];
}

async function _fetchConferencePapers(limit = 1000) {
  try {
    const PAGE = 100;
    const results = [];
    for (let page = 1; results.length < limit; page++) {
      const need = Math.min(PAGE, limit - results.length);
      const json = await _apiFetch(`/papers/conferences?page_size=${need}&page=${page}&rank=A*`);
      if (!json?.results?.length) break;
      results.push(...json.results);
      if (json.results.length < need) break;
    }
    if (results.length) return results;
  } catch { /* fall through */ }
  try {
    const res = await fetch('data/conferences.json');
    const all = await res.json();
    return Array.isArray(all) ? all.slice(0, limit) : [];
  } catch { /* ignore */ }
  return [];
}

async function _fetchJournalPapers(limit = 2000) {
  try {
    const json = await _apiFetch(`/papers/journals?page_size=${Math.min(limit, 100)}&page=1`);
    if (json?.results?.length) return json.results;
  } catch { /* fall through */ }
  try {
    const res = await fetch('data/journals.json');
    const all = await res.json();
    return Array.isArray(all) ? all.slice(0, limit) : [];
  } catch { /* ignore */ }
  return [];
}

async function _fetchPaperCount() {
  // Live total across every source (preprint + conference + journal). This is the
  // real corpus size on Railway — unaffected by the browse-page SECTION_CAP and
  // never stale, unlike the data/stats.json snapshot used as the fallback.
  try {
    const json = await _apiFetch('/papers?page=1&page_size=1');
    if (json && Number.isFinite(json.total)) return json.total;
  } catch { /* fall through */ }
  try {
    const res = await fetch('data/stats.json');
    const stats = await res.json();
    if (stats && Number.isFinite(stats.total_papers)) return stats.total_papers;
  } catch { /* ignore */ }
  return null;
}

async function _searchPapersQuick(query, limit = 5) {
  if (!query || query.trim().length < 2) return [];
  try {
    const json = await _apiFetch(`/search?${new URLSearchParams({ q: query.trim(), limit })}`);
    if (json?.results?.length) return json.results;
  } catch { /* fall through */ }
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

  async updateProfile(data) {
    const user = await _apiFetch('/auth/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    _auth.save(_auth.token(), user);
    _updateAuthNav();
    return user;
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
  async updateNotes(paperId, notes) {
    return _apiFetch(`/favourites/${encodeURIComponent(paperId)}/notes`, {
      method: 'PATCH',
      body: JSON.stringify({ notes }),
    });
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
  const anchor = document.querySelector('.rs-nav .flex.items-center.gap-2.justify-end');
  if (!anchor) return;

  const wrap = document.createElement('div');
  wrap.id = 'rs-auth-wrap';
  wrap.className = 'hidden lg:block';
  anchor.insertBefore(wrap, anchor.firstChild);

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
    <div style="padding:.65rem 1rem;border-bottom:1px solid var(--rs-border,#e5e7eb)">
      <div style="font-size:.82rem;font-weight:700;color:var(--rs-text,#111)">${escHtml(user?.name || user?.email || '')}</div>
      ${user?.name ? `<div style="font-size:.72rem;color:var(--rs-muted,#888)">${escHtml(user.email || '')}</div>` : ''}
    </div>
    <a href="profile">Profile &amp; Settings</a>
    <a href="favourites">My Favourites</a>
    <div style="height:1px;background:var(--rs-border,#e5e7eb);margin:.25rem 0"></div>
    <button onclick="rsLogout()" style="color:#dc2626">Sign out</button>`;
  wrap.appendChild(menu);

  setTimeout(() => document.addEventListener('click', function close(e) {
    if (!wrap.contains(e.target)) { menu.remove(); document.removeEventListener('click', close); }
  }), 0);
}

// ── Auth navigation helpers ───────────────────────────────────────────────────

window.rsOpenModal = function(returnTo) {
  const page = returnTo || window.location.pathname.split('/').pop() || './';
  window.location.href = `signin?returnTo=${encodeURIComponent(page)}`;
};

window.rsLogout = function() {
  _authApi.logout();
  if (window.location.pathname.endsWith('favourites')) {
    window.location.href = './';
  }
};

// ── Static JSON fetch helper ──────────────────────────────────────────────────

async function _staticFetch(staticPath, limit) {
  try {
    const res = await fetch(staticPath);
    const data = await res.json();
    return Array.isArray(data) ? (limit ? data.slice(0, limit) : data) : [];
  } catch { return []; }
}

// ── window._rs_data — the data client used by every page ──────────────────────

window._rs_data = {
  queryPapers:           _queryPapers,
  fetchTopPapers:        _fetchTopPapers,
  fetchConferencePapers: _fetchConferencePapers,
  fetchJournalPapers:    _fetchJournalPapers,
  fetchPaperCount:       _fetchPaperCount,
  searchPapersQuick:     _searchPapersQuick,
  fetchAllAuthors:  (n) => _staticFetch('data/authors.json', n),
  fetchAllTopics:   (n) => _staticFetch('data/topics.json',  n),
  fetchAllGaps:     (n) => _staticFetch('data/gaps.json',    n),
  fetchAllLabs:     (n) => _staticFetch('data/labs.json',    n),
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
