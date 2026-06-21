/**
 * ResearchScope – shared JS utilities
 */

// ── Data fetching ──────────────────────────────────────────────────────
async function fetchData(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`fetchData(${url}) failed:`, err.message);
    return null;
  }
}

// ── Debounce ───────────────────────────────────────────────────────────
function debounce(fn, delay = 250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

// ── Render helpers ─────────────────────────────────────────────────────
function renderBadge(text, type = 'tag') {
  return `<span class="badge badge-${type}">${escHtml(text)}</span>`;
}

function difficultyBadge(d) {
  return renderBadge(d || 'intermediate', d || 'intermediate');
}

function scoreBadge(score) {
  return `<span class="badge badge-score score-badge-tip" title="Paper score (0–10): weighted by citation impact, recency, venue rank, acceptance tier (oral/spotlight), topic relevance, and content quality">${(+score || 0).toFixed(1)}</span>`;
}

function tagChips(tags) {
  if (!tags || !tags.length) return '';
  return tags.map(t => renderBadge(t, 'tag')).join(' ');
}

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function truncate(str, max = 120) {
  if (!str) return '';
  return str.length > max ? str.slice(0, max) + '…' : str;
}

// ── Difficulty badge ───────────────────────────────────────────────────
function difficultyBadge(paper) {
  const lvl = paper.difficulty_level || paper.difficulty || 'L2';
  const labels = { L1: 'L1 Beginner', L2: 'L2 Intermediate', L3: 'L3 Advanced', L4: 'L4 Frontier',
                   beginner: 'L1 Beginner', intermediate: 'L2 Intermediate', advanced: 'L3 Advanced', frontier: 'L4 Frontier' };
  const cls = { L1: 'badge-l1', L2: 'badge-l2', L3: 'badge-l3', L4: 'badge-l4',
                beginner: 'badge-l1', intermediate: 'badge-l2', advanced: 'badge-l3', frontier: 'badge-l4' };
  return `<span class="badge ${cls[lvl] || 'badge-l2'}">${labels[lvl] || lvl}</span>`;
}

// ── Conference rank badge ──────────────────────────────────────────────
function rankBadge(rank) {
  if (!rank) return '';
  const cls = rank === 'A*' ? 'rank-astar' : (rank === 'A' ? 'rank-a' : 'rank-b');
  return `<span class="badge ${cls}">${escHtml(rank)}</span>`;
}

// ── Acceptance-tier badge (oral / spotlight) ───────────────────────────
// Only oral & spotlight are shown — they mark the top decile of accepted
// work. Posters are the default tier and get no badge to avoid clutter.
function presentationBadge(type) {
  const t = (type || '').toLowerCase();
  if (t === 'oral')      return `<span class="badge badge-oral" title="Oral presentation — top accepted tier">Oral</span>`;
  if (t === 'spotlight') return `<span class="badge badge-spotlight" title="Spotlight — highlighted accepted paper">Spotlight</span>`;
  return '';
}

// ── Source badge ───────────────────────────────────────────────────────
function sourceBadge(paper) {
  const src = paper.source || '';
  if (src === 'arxiv') return `<span class="badge badge-arxiv">arXiv</span>`;
  if (src.includes('acl')) return `<span class="badge badge-acl">ACL</span>`;
  return `<span class="badge badge-conf">${escHtml(paper.venue || src)}</span>`;
}

// ── Score bar ──────────────────────────────────────────────────────────
function scoreBar(label, score, max = 10) {
  const pct = Math.round((score || 0) / max * 100);
  return `<div class="score-bar-wrap">
    <span style="font-size:0.72rem;color:var(--rs-muted);min-width:9rem">${escHtml(label)}</span>
    <div class="score-bar-bg"><div class="score-bar-fill" style="width:${pct}%"></div></div>
    <span class="score-bar-label">${(+score || 0).toFixed(1)}</span>
  </div>`;
}

// ── Extract arXiv ID from a paper URL ──────────────────────────────────
function extractArxivId(url) {
  if (!url) return null;
  const m = url.match(/arxiv\.org\/(?:abs|pdf)\/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)(?![0-9])/);
  return m ? m[1] : null;
}

// ── CiteLens link for a paper (only when arXiv ID is available) ─────────
function citelensBtn(paper) {
  const arxivId = extractArxivId(paper.paper_url || paper.url || '');
  if (!arxivId) return '';
  const href = `https://kishormorol.github.io/CiteLens/?q=${encodeURIComponent(arxivId)}`;
  return `<a href="${escHtml(href)}" target="_blank" rel="noopener"
    class="mt-3 inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-md border"
    style="color:var(--rs-primary);border-color:var(--rs-primary);opacity:0.85"
    title="See who cited this paper — powered by CiteLens">
    Analyze citations
  </a>`;
}

// ── Paper card (used in homepage & topics) ─────────────────────────────
function renderPaperCard(paper, opts = {}) {
  const url = paper.paper_url || paper.url || '#';
  const authors = (paper.authors || []).slice(0, 3).join(', ');
  const extra   = (paper.authors || []).length > 3 ? ` +${paper.authors.length - 3}` : '';
  const typeStr = paper.paper_type ? `<span class="badge badge-type">${escHtml(paper.paper_type)}</span>` : '';
  const whyStr  = paper.why_it_matters
    ? `<p class="text-xs mt-2 italic" style="color:var(--rs-primary)">${escHtml(truncate(paper.why_it_matters, 160))}</p>`
    : '';
  return `
  <div class="rs-card p-5 mb-4">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div class="flex-1 min-w-0">
        <a href="${escHtml(url)}" target="_blank" rel="noopener"
           class="text-base font-semibold hover:text-indigo-600 transition-colors">
          ${escHtml(paper.title)}
        </a>
        <p class="text-xs mt-1" style="color:var(--rs-muted)">
          ${escHtml(authors)}${escHtml(extra)} &middot; ${escHtml(paper.venue || '')} ${paper.year || ''}
        </p>
      </div>
      <div class="flex gap-1 flex-shrink-0 flex-wrap">
        <span class="badge badge-score">${(+paper.paper_score || 0).toFixed(1)}</span>
        ${difficultyBadge(paper)}
        ${rankBadge(paper.conference_rank)}
        ${presentationBadge(paper.presentation_type)}
        ${sourceBadge(paper)}
      </div>
    </div>
    ${whyStr}
    <p class="text-sm mt-3 leading-relaxed" style="color:var(--rs-muted)">
      ${escHtml(truncate(paper.summary || paper.abstract, 200))}
    </p>
    <div class="mt-3 flex flex-wrap gap-1">
      ${typeStr}
      ${tagChips(paper.tags)}
    </div>
    ${opts.showScoreBars ? `
    <div class="mt-3 border-t pt-3" style="border-color:var(--rs-border)">
      ${scoreBar('Paper Score', paper.paper_score)}
      ${scoreBar('Read First', paper.read_first_score)}
      ${scoreBar('Content Potential', paper.content_potential_score)}
    </div>` : ''}
    ${citelensBtn(paper)}
  </div>`;
}

// ── Stats bar ──────────────────────────────────────────────────────────
async function loadStats() {
  const stats = await fetchData('data/stats.json');
  if (!stats) return;
  const map = {
    'stat-papers':  stats.total_papers,
    'stat-topics':  stats.total_topics,
    'stat-authors': stats.total_authors,
    'stat-gaps':    stats.total_gaps,
    'stat-labs':    stats.total_labs,
    'stat-unis':    stats.total_universities,
  };
  for (const [id, val] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (el) el.textContent = (val ?? 0).toLocaleString();
  }
  // Hero tagline count + stats bar — seed from the snapshot, then override with
  // the live API total so the site always shows the real corpus size.
  const heroEl = document.getElementById('hero-paper-count');
  if (heroEl && stats.total_papers) {
    heroEl.textContent = stats.total_papers.toLocaleString();
  }
  if (window._rs_data?.fetchPaperCount) {
    window._rs_data.fetchPaperCount().then(total => {
      if (!Number.isFinite(total)) return;
      const live = total.toLocaleString();
      const papersEl = document.getElementById('stat-papers');
      if (papersEl) papersEl.textContent = live;
      if (heroEl) heroEl.textContent = live;
    });
  }
  const genEl = document.getElementById('stat-generated');
  if (genEl && stats.generated_at) {
    genEl.textContent = 'Updated ' + new Date(stats.generated_at).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' });
  }
}

// ── Paginator ──────────────────────────────────────────────────────────
function renderPaginator(containerId, current, total, onChange) {
  const el = document.getElementById(containerId);
  if (!el || total <= 1) return;
  let html = `<div class="flex gap-1 flex-wrap justify-center mt-4">`;
  html += `<button class="pager-btn" onclick="(${onChange})(${current - 1})" ${current <= 1 ? 'disabled' : ''}>← Prev</button>`;
  const pages = Math.min(total, 7);
  let start = Math.max(1, current - 3);
  let end   = Math.min(total, start + pages - 1);
  start = Math.max(1, end - pages + 1);
  for (let p = start; p <= end; p++) {
    html += `<button class="pager-btn ${p === current ? 'active' : ''}" onclick="(${onChange})(${p})">${p}</button>`;
  }
  html += `<button class="pager-btn" onclick="(${onChange})(${current + 1})" ${current >= total ? 'disabled' : ''}>Next →</button>`;
  html += `</div>`;
  el.innerHTML = html;
}

// ── Search / filter ────────────────────────────────────────────────────
function buildSearchFilter(fields) {
  return (item, query) => {
    const q = query.toLowerCase();
    return fields.some(f => (item[f] || '').toString().toLowerCase().includes(q));
  };
}

// ── Spinner / empty ────────────────────────────────────────────────────
function showSpinner(containerId) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = '<div class="spinner"></div>';
}

function showEmpty(containerId, msg = 'No data available') {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = `
    <div class="empty-state">
      <svg width="48" height="48" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
      </svg>
      <p class="text-lg font-medium">${escHtml(msg)}</p>
      <p class="text-sm mt-1">Run the pipeline to generate data, or check back later.</p>
    </div>`;
}

// ── Global Search ─────────────────────────────────────────────────────
let _searchData = null;

async function loadSearchData() {
  if (_searchData) return _searchData;
  // Authors and topics are small — always load from JSON.
  // Papers: use the Railway API if available (covers the full dataset), else
  // fall back to the static search index.
  const [authors, topics] = await Promise.all([
    fetch('data/authors.json').then(r => r.json()).catch(() => []),
    fetch('data/topics.json').then(r => r.json()).catch(() => []),
  ]);
  _searchData = { papers: [], authors, topics, _useApi: !!window._rs_data };
  return _searchData;
}

async function runSearch(query, data, limit = 5) {
  const q = query.toLowerCase().trim();
  if (!q) return { papers: [], authors: [], topics: [] };

  // Papers — prefer the Railway API (live, full dataset) over the static JSON index
  let papers = [];
  if (data._useApi) {
    papers = await window._rs_data.searchPapersQuick(q, limit);
  } else {
    papers = (data.papers || [])
      .filter(p => p.title?.toLowerCase().includes(q) ||
                   p.abstract?.toLowerCase().includes(q) ||
                   p.authors?.some(a => a.toLowerCase().includes(q)))
      .slice(0, limit);
  }

  const authors = (data.authors || [])
    .filter(a => a.name?.toLowerCase().includes(q))
    .slice(0, limit);

  const topics = (data.topics || [])
    .filter(t => t.name?.toLowerCase().includes(q) ||
                 t.keywords?.some(k => k.toLowerCase().includes(q)))
    .slice(0, limit);

  return { papers, authors, topics };
}

function renderDropdown(results, query, dropdown) {
  const { papers, authors, topics } = results;
  const total = papers.length + authors.length + topics.length;

  if (total === 0) {
    dropdown.innerHTML = `<p class="search-empty">No results for "<strong>${escHtml(query)}</strong>"</p>`;
    return;
  }

  let html = '';

  if (papers.length) {
    html += `<div class="search-section-label">Papers</div>`;
    papers.forEach(p => {
      html += `<a class="search-result-item" href="papers?q=${encodeURIComponent(p.title)}">
        <div class="sr-title">${escHtml(p.title)}</div>
        <div class="sr-meta">${escHtml(p.venue || 'arXiv')} · ${p.year || ''}</div>
      </a>`;
    });
  }

  if (authors.length) {
    html += `<div class="search-section-label">Authors</div>`;
    authors.forEach(a => {
      html += `<a class="search-result-item" href="authors?q=${encodeURIComponent(a.name)}">
        <div class="sr-title">${escHtml(a.name)}</div>
        <div class="sr-meta">${a.paper_ids?.length || 0} papers</div>
      </a>`;
    });
  }

  if (topics.length) {
    html += `<div class="search-section-label">Topics</div>`;
    topics.forEach(t => {
      html += `<a class="search-result-item" href="topics#${escHtml(t.id)}">
        <div class="sr-title">${escHtml(t.name)}</div>
        <div class="sr-meta">${t.paper_ids?.length || 0} papers</div>
      </a>`;
    });
  }

  html += `<a class="search-see-all" href="search?q=${encodeURIComponent(query)}">See all results →</a>`;
  dropdown.innerHTML = html;
}

function initSearch() {
  const input    = document.getElementById('global-search');
  const dropdown = document.getElementById('search-dropdown');
  if (!input || !dropdown) return;

  let debounce;

  input.addEventListener('focus', () => loadSearchData());

  input.addEventListener('input', () => {
    clearTimeout(debounce);
    const q = input.value.trim();
    if (!q) { dropdown.classList.add('hidden'); return; }

    debounce = setTimeout(async () => {
      const data    = await loadSearchData();
      const results = await runSearch(q, data, 4);
      renderDropdown(results, q, dropdown);
      dropdown.classList.remove('hidden');
    }, 180);
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && input.value.trim()) {
      window.location.href = `search?q=${encodeURIComponent(input.value.trim())}`;
    }
    if (e.key === 'Escape') {
      dropdown.classList.add('hidden');
      input.blur();
    }
  });

  document.addEventListener('click', e => {
    if (!input.closest('.search-wrap').contains(e.target)) {
      dropdown.classList.add('hidden');
    }
  });
}

// ── GitHub Star count ─────────────────────────────────────────────────
async function initStarCount() {
  try {
    const res = await fetch('https://api.github.com/repos/kishormorol/ResearchScope');
    if (!res.ok) return;
    const data = await res.json();
    const count = data.stargazers_count ?? 0;
    const label = count >= 1000
      ? (count / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
      : String(count);
    document.querySelectorAll('.github-star-count').forEach(el => {
      el.textContent = label;
    });
  } catch (_) { /* silently fail — button still works without count */ }
}

// ── Paper of the Day ──────────────────────────────────────────────────
// Featured paper must be *current* — picked from the freshest publication
// date available in the data, not the all-time top scorers (which skew weeks
// or months old). We anchor on the most recent published_date present, widen
// the window only if that single day is sparse, then rotate daily for variety.
const DAY_MS = 86400000;

function pickPaperOfTheDay(papers, poolSize = 60) {
  if (!papers || !papers.length) return null;

  const dated = papers.filter(p => p.published_date);
  let pool;
  if (dated.length) {
    const latest = dated.reduce(
      (max, p) => (p.published_date > max ? p.published_date : max),
      dated[0].published_date
    ).slice(0, 10);
    const latestMs = new Date(latest).getTime();
    // Prefer the latest day; widen to a few recent days only if too few papers.
    for (const windowDays of [0, 2, 6]) {
      pool = dated.filter(p => {
        const d = new Date(p.published_date.slice(0, 10)).getTime();
        return d <= latestMs && latestMs - d <= windowDays * DAY_MS;
      });
      if (pool.length >= 5) break;
    }
  } else {
    pool = papers.slice();
  }

  pool = pool
    .sort((a, b) => (b.paper_score || 0) - (a.paper_score || 0))
    .slice(0, Math.min(poolSize, pool.length));
  if (!pool.length) return null;

  const today = new Date();
  const startOfYear = new Date(today.getFullYear(), 0, 1);
  const dayOfYear = Math.floor((today - startOfYear) / DAY_MS);
  return pool[dayOfYear % pool.length];
}

function tweetPaperUrl(paper) {
  const venue   = [paper.venue, paper.year].filter(Boolean).join(' ');
  const score   = paper.paper_score ? ` | ${(+paper.paper_score).toFixed(1)}/10` : '';
  const snippet = (paper.abstract || paper.summary || '').slice(0, 160);
  const pageUrl = `https://kishormorol.github.io/ResearchScope/papers?q=${encodeURIComponent(paper.title || '')}`;
  const text    = `${paper.title}\n${venue}${score}\n\n${snippet}…\n\nResearchScope\n${pageUrl}\n\n#AIResearch #MachineLearning #ResearchScope`;
  return `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}`;
}

function renderPotdCard(paper) {
  if (!paper) return '';
  const url     = paper.paper_url || paper.url || '#';
  const venue   = [paper.venue, paper.year].filter(Boolean).join(' · ');
  const authors = (paper.authors || []).slice(0, 3).join(', ');
  const extra   = (paper.authors || []).length > 3 ? ` +${paper.authors.length - 3}` : '';
  const tags    = (paper.tags || []).slice(0, 3).map(t =>
    `<span style="background:rgba(255,255,255,0.2);color:#fff;padding:2px 8px;border-radius:99px;font-size:0.7rem;font-weight:600">${escHtml(t)}</span>`
  ).join('');

  const tomorrowMs = new Date(new Date().setHours(24,0,0,0)) - Date.now();
  const hoursLeft = Math.floor(tomorrowMs / 3600000);
  const minsLeft  = Math.floor((tomorrowMs % 3600000) / 60000);
  const nextLabel = hoursLeft > 0 ? `New paper in ${hoursLeft}h ${minsLeft}m` : `New paper in ${minsLeft}m`;

  return `
  <div class="potd-wrap">
    <div class="potd-label">
      Paper of the Day
      <span style="font-size:0.65rem;opacity:0.6;font-weight:400">${new Date().toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric'})}</span>
    </div>
    <div class="potd-title">
      <a href="${escHtml(url)}" target="_blank" rel="noopener">${escHtml(paper.title)}</a>
    </div>
    <div class="potd-meta">
      ${venue ? escHtml(venue) + (authors ? ' · ' : '') : ''}${escHtml(authors)}${escHtml(extra)}
      ${paper.paper_score ? ` · ${(+paper.paper_score).toFixed(1)}/10` : ''}
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:0.3rem;margin-bottom:0.75rem">${tags}</div>
    <p class="potd-abstract">${escHtml((paper.abstract || paper.summary || '').slice(0, 300))}</p>
    <div class="potd-actions">
      <a href="${escHtml(url)}" target="_blank" rel="noopener" class="potd-btn potd-btn-primary">Read Paper →</a>
      ${(() => { const aid = extractArxivId(url); return aid ? `<a href="https://kishormorol.github.io/CiteLens/?q=${encodeURIComponent(aid)}" target="_blank" rel="noopener" class="potd-btn potd-btn-ghost" title="See who cited this paper">Analyze citations</a>` : ''; })()}
      <a href="${escHtml(tweetPaperUrl(paper))}" target="_blank" rel="noopener" class="potd-btn potd-btn-ghost">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.738-8.835L1.254 2.25H8.08l4.259 5.631zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
        Share
      </a>
      <button onclick="copyPotdLink('${escHtml(url)}',this)" class="potd-btn potd-btn-ghost">Copy Link</button>
      <span class="potd-next">${nextLabel}</span>
    </div>
  </div>`;
}

function copyPotdLink(url, btn) {
  navigator.clipboard.writeText(url).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 2000);
  });
}

// ── Nav builder ────────────────────────────────────────────────────────
function buildDropdownNav() {
  const linksDiv = document.getElementById('rs-nav-links');
  const mobLinks  = document.getElementById('rs-mob-links');
  if (!linksDiv && !mobLinks) return;

  const page = window.location.pathname.split('/').pop() || './';

  function navLink(href, label) {
    const cls = 'rs-nav-top-link' + (href === page ? ' active' : '');
    return `<a href="${href}" class="${cls}">${label}</a>`;
  }

  function dropdown(label, items) {
    const hasActive = items.some(([href]) => href && href === page);
    const rows = items.map(([href, lbl, divider]) => {
      if (divider) return `<div class="rs-nav-dd-divider"></div>`;
      return `<a href="${href}"${href === page ? ' class="active"' : ''}>${lbl}</a>`;
    }).join('');
    return `<div class="rs-nav-dd">
      <button class="rs-nav-dd-btn${hasActive ? ' active' : ''}">${label}<span class="rs-nav-dd-arrow">▾</span></button>
      <div class="rs-nav-dd-menu">${rows}</div>
    </div>`;
  }

  if (linksDiv) {
    linksDiv.innerHTML =
      navLink('papers', 'Papers') +
      dropdown('Venues', [
        ['conferences', 'Conferences'],
        ['journals',    'Journals'],
        [null, null, true],
        ['conference-recommender', 'Conference Recommender'],
        ['journal-recommender',    'Journal Recommender'],
      ]) +
      dropdown('Discover', [
        ['topics', 'Topics'],
        ['gaps',   'Research Gaps'],
        ['digest', 'Digest'],
      ]) +
      dropdown('People', [
        ['authors', 'Authors'],
        ['labs',    'Labs & Unis'],
      ]) +
      navLink('deadlines', 'Deadlines');
  }

  if (mobLinks) {
    const ml = (href, lbl) =>
      `<a href="${href}" class="mobile-nav-link${href === page ? ' active' : ''}">${lbl}</a>`;
    const sec = t => `<p class="mobile-nav-section">${t}</p>`;
    mobLinks.innerHTML =
      ml('./',  'Home') +
      ml('papers', 'Papers') +
      sec('Venues') +
      ml('conferences',           'Conferences') +
      ml('journals',              'Journals') +
      ml('conference-recommender','Conference Recommender') +
      ml('journal-recommender',   'Journal Recommender') +
      sec('Discover') +
      ml('topics', 'Topics') +
      ml('gaps',   'Research Gaps') +
      ml('digest', 'Digest') +
      sec('People') +
      ml('authors',    'Authors') +
      ml('labs',       'Labs & Unis') +
      ml('deadlines',  'Deadlines') +
      ml('favourites', 'My Favourites');
  }
}

// ── Init ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initStarCount();
  buildDropdownNav();

  // Highlight active nav link (desktop + mobile) — runs after buildDropdownNav
  const path = window.location.pathname.split('/').pop() || './';
  document.querySelectorAll('.rs-nav a[href], .mobile-nav-link').forEach(a => {
    if (a.getAttribute('href') === path) a.classList.add('active');
  });

  // Global search
  initSearch();

  // Mobile menu toggle (with t-panel + t-icon-swap transitions)
  const mobileBtn  = document.getElementById('mobile-menu-btn');
  const mobileMenu = document.getElementById('mobile-menu');
  const iconOpen   = document.getElementById('hamburger-icon');
  const iconClose  = document.getElementById('close-icon');

  if (mobileBtn && mobileMenu) {
    // Add t-panel + t-icon-swap class hooks. Tailwind's `hidden` keeps the
    // breakpoint hide (>1024px) intact; on mobile widths the t-panel classes
    // drive the open/close animation.
    mobileMenu.classList.add('t-panel');
    if (iconOpen && iconClose) {
      iconOpen.classList.add('t-icon-swap-svg');
      iconClose.classList.add('t-icon-swap-svg');
    }

    let menuClosingTimer = null;
    const dur = () => parseInt(getComputedStyle(mobileMenu).getPropertyValue('--panel-close-dur')) || 200;

    const setIcon = (showingClose) => {
      if (!iconOpen || !iconClose) return;
      const out  = showingClose ? iconOpen  : iconClose;
      const into = showingClose ? iconClose : iconOpen;
      out.classList.add('is-leaving');
      into.classList.remove('is-leaving');
      setTimeout(() => out.classList.remove('is-leaving'), 220);
    };

    mobileBtn.addEventListener('click', () => {
      const isOpen = mobileMenu.classList.contains('is-open');
      if (menuClosingTimer) { clearTimeout(menuClosingTimer); menuClosingTimer = null; }
      if (isOpen) {
        // closing
        mobileMenu.classList.remove('is-open');
        mobileMenu.classList.add('is-closing');
        mobileBtn.setAttribute('aria-expanded', 'false');
        setIcon(false);
        menuClosingTimer = setTimeout(() => {
          mobileMenu.classList.add('hidden');
          mobileMenu.classList.remove('is-closing');
          menuClosingTimer = null;
        }, dur());
      } else {
        // opening
        mobileMenu.classList.remove('hidden');
        // force reflow so animation replays after a prior close
        void mobileMenu.offsetWidth;
        mobileMenu.classList.remove('is-closing');
        mobileMenu.classList.add('is-open');
        mobileBtn.setAttribute('aria-expanded', 'true');
        setIcon(true);
      }
    });

    // Close menu when a link is tapped
    mobileMenu.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => {
        if (menuClosingTimer) { clearTimeout(menuClosingTimer); menuClosingTimer = null; }
        mobileMenu.classList.remove('is-open');
        mobileMenu.classList.add('is-closing');
        setIcon(false);
        mobileBtn.setAttribute('aria-expanded', 'false');
        menuClosingTimer = setTimeout(() => {
          mobileMenu.classList.add('hidden');
          mobileMenu.classList.remove('is-closing');
          menuClosingTimer = null;
        }, dur());
      });
    });
  }
});

// ── transitions-dev: Dropdown (Venues / Discover / People nav dropdowns) ──
function initNavDropdowns() {
  document.querySelectorAll('.rs-nav-dd').forEach(dd => {
    const menu = dd.querySelector('.rs-nav-dd-menu');
    if (!menu) return;
    menu.classList.add('t-dropdown-menu');
    let closeTimer = null;

    const open = () => {
      if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
      menu.classList.remove('is-closing');
      menu.classList.add('is-open');
    };
    const close = () => {
      if (!menu.classList.contains('is-open')) return;
      menu.classList.remove('is-open');
      menu.classList.add('is-closing');
      const dur = parseInt(getComputedStyle(menu).getPropertyValue('--dropdown-close-dur')) || 120;
      closeTimer = setTimeout(() => {
        menu.classList.remove('is-closing');
        closeTimer = null;
      }, dur);
    };
    /* Hover bridge: extend the open state to BOTH the parent and the menu
       itself. Moving the mouse from button → menu now keeps `is-open`
       active even when the cursor briefly crosses the visual gap. */
    const enterMenu = () => { if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; } open(); };
    const leaveAll  = (e) => {
      // Only close when leaving the parent AND the menu simultaneously
      const to = e.relatedTarget;
      if (to && (dd.contains(to) || menu.contains(to))) return;
      close();
    };

    dd.addEventListener('mouseenter', open);
    dd.addEventListener('mouseleave', leaveAll);
    menu.addEventListener('mouseenter', enterMenu);
    menu.addEventListener('mouseleave', leaveAll);
    dd.addEventListener('focusin', open);
    dd.addEventListener('focusout', e => {
      if (!dd.contains(e.relatedTarget) && !menu.contains(e.relatedTarget)) close();
    });
    menu.addEventListener('focusin', enterMenu);
  });
}

// ── transitions-dev: Notification badge pulse on GitHub star count update ──
function pulseStarBadge() {
  document.querySelectorAll('.github-star-btn').forEach(btn => {
    if (btn.querySelector('.t-badge__pulse')) return;
    const dot = document.createElement('span');
    dot.className = 't-badge__pulse';
    dot.setAttribute('aria-hidden', 'true');
    btn.classList.add('t-badge');
    btn.appendChild(dot);
  });
}

// ── transitions-dev: Text states swap helper ───────────────────────────
// Usage: textSwap(el, 'new value')
function textSwap(el, nextText) {
  if (!el || el.textContent === nextText) return;
  el.classList.add('is-leaving');
  setTimeout(() => {
    el.textContent = nextText;
    el.classList.remove('is-leaving');
    el.classList.add('is-entering');
    void el.offsetWidth;
    el.classList.remove('is-entering');
  }, 180);
}

// ── Bootstrap transitions ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initNavDropdowns();
  pulseStarBadge();
});
