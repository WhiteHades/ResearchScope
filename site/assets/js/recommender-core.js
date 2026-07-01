/**
 * recommender-core.js — shared logic for the Conference & Journal recommenders.
 *
 * Both recommender pages used to carry their own ~250-line copy of this code,
 * which had already drifted apart. This module is the single source of truth.
 * Depends on globals from app.js (loaded first): escHtml, rankBadge, debounce.
 *
 * Exposed as window.RecCore.
 */
(function () {
  'use strict';

  const byId = (id) => document.getElementById(id);

  // ── Vocabulary ──────────────────────────────────────────────────────────
  const STOP_WORDS = new Set([
    'a','an','and','are','as','at','be','been','being','by','can','could','did','do','does',
    'for','from','had','has','have','having','how','in','into','is','it','its','may','me',
    'method','model','models','must','not','now','of','on','or','other','our','out','own',
    'paper','present','propose','proposed','she','show','shows','so','some','such',
    'than','that','the','their','them','there','these','they','this','those','through',
    'to','too','up','use','using','via','was','we','well','were','what','when','where',
    'which','while','who','will','with','would','you','your',
    'achieve','achieves','approach','approaches','based','different','first',
    'however','methods','new','novel','results','study','task','tasks','work',
  ]);
  const PLACEHOLDER_WORDS = new Set([
    'lorem','ipsum','dolor','sit','amet','consectetur','todo','tbd','placeholder','dummy','sample',
  ]);

  const FIELD_HINTS = {
    ML:      ['machine','learning','optimization','representation','bayesian','reinforcement','generalization','training','gradient','neural','network','networks'],
    NLP:     ['language','nlp','translation','linguistic','multilingual','summarization','dialogue','question','answering','llm','llms','text','tokens'],
    CV:      ['vision','image','images','video','visual','segmentation','detection','recognition','geometry','diffusion','pixel','3d'],
    AI:      ['agent','agents','planning','reasoning','knowledge','decision','autonomous','logic','artificial','search'],
    HCI:     ['human','user','users','interface','interaction','usability','participants','qualitative','survey-study'],
    IR:      ['retrieval','ranking','query','relevance','recommendation','recommendations','rag','search','index'],
    DM:      ['mining','graph','graphs','discovery','anomaly','causal','clustering','pattern'],
    SE:      ['software','program','code','testing','developer','debugging','repair','repository','compiler'],
    General: ['survey','review','benchmark','dataset','empirical','application','reproducibility'],
  };

  // ── Abstract structure detection ────────────────────────────────────────
  const STRUCTURE_PATTERNS = {
    problem:      /we (address|tackle|study|investigate|focus on|aim to)|the (problem of|challenge of|task of|issue of|limitation of)|existing (methods|approaches|systems|models) (fail|suffer|cannot|lack|struggle)|prior work|previous (methods|work|approaches)/i,
    method:       /we (propose|introduce|present|develop|design|build|create)|our (method|approach|model|system|framework|algorithm|architecture)|this (paper|work) (proposes|introduces|presents|develops)|we design/i,
    evaluation:   /we (evaluate|test|validate|demonstrate|benchmark|assess)|experiment(s|al)|on (the |)([\w-]+ )?(dataset|benchmark|corpus|task|collection)|compar(e|ing|ison) (with|against|to|versus)|\d+ (dataset|benchmark|task)/i,
    contribution: /outperform|state.of.the.art|sota|surpass|significant(ly)?|novel|first (to|work)|improve(s|d|ment)?|achieves?[\s(]+[\d.]+\s*%|better than|superior|our (results|method) (show|achieve)/i,
    datasets:     /\d+[,\d]*[km]?\s*(sample|example|instance|image|token|document|sentence|record|pair|annotation)s?|\b(imagenet|coco|squad|glue|superglue|wmt|ms.?marco|wikipedia|laion|openwebtext)\b/i,
  };
  const NOVELTY_SIGNALS = [
    'outperform','outperforms','state-of-the-art','state of the art','sota',
    'surpass','surpasses','significant','significantly','novel','novelty',
    'first to','first work','improve','improves','improvement','superior',
    'we propose','we introduce','we present','we design','advance','demonstrate',
    'achieves','new approach','new method','new framework',
  ];

  // ── Tokenisation ────────────────────────────────────────────────────────
  function tokenize(text) {
    return (text || '').toLowerCase().match(/[a-z][a-z0-9+-]{2,}/g)
      ?.filter((w) => !STOP_WORDS.has(w) && w.length <= 32) || [];
  }

  function extractBigrams(text) {
    const toks = tokenize(text);
    const bigrams = new Set();
    for (let i = 0; i < toks.length - 1; i++) {
      if (toks[i] !== toks[i + 1]) bigrams.add(`${toks[i]} ${toks[i + 1]}`);
    }
    return bigrams;
  }

  /**
   * Infer the most likely field. Title terms count double (they carry more
   * signal). Returns {field, confidence, scores}; field is null when there is
   * no clear signal (no more 'ML' fallback that silently mislabels papers).
   */
  function inferField(title, abstract) {
    const titleToks = new Set(tokenize(title));
    const allToks = new Set([...titleToks, ...tokenize(abstract)]);
    const scores = {};
    for (const [field, hints] of Object.entries(FIELD_HINTS)) {
      if (field === 'General') continue; // too generic to auto-pick
      let s = 0;
      for (const h of hints) {
        if (titleToks.has(h)) s += 2;
        else if (allToks.has(h)) s += 1;
      }
      scores[field] = s;
    }
    const ranked = Object.entries(scores).filter(([, s]) => s > 0).sort(([, a], [, b]) => b - a);
    if (!ranked.length) return { field: null, confidence: 0, scores };
    const [best, bestScore] = ranked[0];
    const second = ranked[1] ? ranked[1][1] : 0;
    // Confidence: how dominant the top field is over the runner-up.
    const confidence = bestScore >= 3 && bestScore >= second * 2 ? 'high'
      : bestScore >= 2 ? 'medium' : 'low';
    return { field: best, confidence, scores };
  }

  // ── Draft quality gate ──────────────────────────────────────────────────
  function draftQuality(title, abstract) {
    const text = `${title || ''} ${abstract || ''}`.trim();
    const tokens = tokenize(text);
    const informative = tokens.filter((t) => !PLACEHOLDER_WORDS.has(t));
    const uniqueInformative = new Set(informative);
    if (text.length < 80)
      return { ok: false, reason: 'Add a title and at least a short abstract before matching.' };
    if (/\blorem\s+ipsum\b/i.test(text) ||
        tokens.filter((t) => PLACEHOLDER_WORDS.has(t)).length / (tokens.length || 1) >= 0.35)
      return { ok: false, reason: 'Enter a real abstract with problem, method, evaluation, and main contribution.' };
    if (informative.length < 35 || uniqueInformative.size < 18)
      return { ok: false, reason: 'Add more specific details: problem, method, datasets, evaluation, and contribution.' };
    return { ok: true, tokens: informative, uniqueTokens: uniqueInformative };
  }

  function analyzeAbstract(title, abstract) {
    const fullText = `${title} ${abstract}`;
    const absText = abstract || '';
    const wordCount = absText.trim() ? absText.trim().split(/\s+/).length : 0;
    const structure = Object.fromEntries(
      Object.entries(STRUCTURE_PATTERNS).map(([k, re]) => [k, re.test(absText)])
    );
    const lower = fullText.toLowerCase();
    const noveltyFound = [...new Set(NOVELTY_SIGNALS.filter((s) => lower.includes(s.toLowerCase())))].slice(0, 6);
    const tokens = new Set(tokenize(fullText));
    const fieldScores = {};
    for (const [f, hints] of Object.entries(FIELD_HINTS)) fieldScores[f] = hints.filter((h) => tokens.has(h)).length;
    const sortedFields = Object.entries(fieldScores).filter(([, s]) => s > 0).sort(([, a], [, b]) => b - a).slice(0, 4);
    const suggestions = [];
    if (!structure.problem)      suggestions.push('Frame the problem: "we address…" or "existing methods fail to…"');
    if (!structure.method)       suggestions.push('Describe your approach: "we propose…" or "our method…"');
    if (!structure.evaluation)   suggestions.push('Mention evaluation: "we evaluate on…" or reference datasets/benchmarks');
    if (!structure.contribution) suggestions.push('State your gains: "outperforms", "state-of-the-art", or quantified improvements');
    if (wordCount < 100)         suggestions.push(`Short abstract (${wordCount} words) — 150–250 words gives better matching signal`);
    return {
      structure, noveltyFound, fieldScores, sortedFields, wordCount,
      structureScore: Object.values(structure).filter(Boolean).length, suggestions,
    };
  }

  function renderAnalysisPanel(analysis) {
    const check = (ok) => ok
      ? `<svg width="11" height="11" fill="none" stroke="var(--rs-success)" viewBox="0 0 24 24" style="flex-shrink:0;margin-top:1px"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>`
      : `<svg width="11" height="11" fill="none" stroke="var(--rs-danger)" viewBox="0 0 24 24" style="flex-shrink:0;margin-top:1px"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/></svg>`;
    const structRows = [
      ['Problem framing',    analysis.structure.problem],
      ['Method description', analysis.structure.method],
      ['Evaluation',         analysis.structure.evaluation],
      ['Contribution claim', analysis.structure.contribution],
      ['Dataset mention',    analysis.structure.datasets],
    ];
    const noveltyHtml = analysis.noveltyFound.length
      ? analysis.noveltyFound.map((s) => `<span class="badge signal-strong" style="font-size:.62rem">${escHtml(s)}</span>`).join(' ')
      : `<span class="text-xs" style="color:var(--rs-muted)">None — add explicit claims</span>`;
    const fieldHtml = analysis.sortedFields.slice(0, 3).map(([f, s]) =>
      `<div class="flex items-center gap-1.5 text-xs">
         <span style="min-width:2.25rem;font-weight:700;color:var(--rs-primary)">${escHtml(f)}</span>
         <div style="flex:1;height:4px;border-radius:2px;background:var(--rs-border)">
           <div style="height:100%;border-radius:2px;background:var(--rs-primary);width:${Math.min(100, s * 22)}%"></div>
         </div>
         <span style="color:var(--rs-muted);font-size:.68rem">${s}</span>
       </div>`).join('');
    const wc = analysis.wordCount;
    const wcColor = wc < 80 ? 'var(--rs-danger)' : wc < 120 ? 'var(--rs-warning)' : 'var(--rs-success)';
    const wcLabel = wc < 80 ? 'too short' : wc < 120 ? 'borderline' : 'good';
    const sc = analysis.structureScore;
    const quality = sc >= 4 ? 'Strong' : sc >= 3 ? 'Good' : sc >= 2 ? 'Fair' : 'Weak';
    const qClass = sc >= 4 ? 'rs-status--success' : sc >= 3 ? 'rs-status--info' : sc >= 2 ? 'rs-status--warning' : 'rs-status--danger';
    const tipsHtml = analysis.suggestions.length
      ? `<div class="mt-3 p-2.5 rounded-lg space-y-1" style="background:var(--rs-primary-50);border:1px solid var(--rs-danger-line)">
          ${analysis.suggestions.map((s) => `<div class="text-xs" style="color:var(--rs-primary)">${escHtml(s)}</div>`).join('')}
         </div>`
      : `<div class="mt-3 p-2.5 rounded-lg text-xs" style="background:var(--rs-success-bg);border:1px solid var(--rs-success-line);color:var(--rs-success)">Abstract looks well-structured — good basis for matching.</div>`;
    return `
    <div class="recommender-panel mb-4">
      <div class="flex items-center justify-between mb-3">
        <p class="text-xs font-bold uppercase tracking-wider" style="color:var(--rs-muted)">Abstract Analysis</p>
        <span class="rs-status ${qClass}">${quality} structure (${sc}/5)</span>
      </div>
      <div class="grid sm:grid-cols-3 gap-4">
        <div>
          <p class="text-xs font-semibold mb-2" style="color:var(--rs-text)">Sections detected</p>
          <div class="space-y-1.5">${structRows.map(([l, ok]) => `
            <div class="flex items-center gap-1.5 text-xs" style="color:${ok ? 'var(--rs-text)' : 'var(--rs-muted)'}">${check(ok)} ${escHtml(l)}</div>`).join('')}</div>
          <p class="text-xs mt-2.5" style="color:var(--rs-muted)">${wc} words · <span style="color:${wcColor};font-weight:600">${wcLabel}</span></p>
        </div>
        <div>
          <p class="text-xs font-semibold mb-2" style="color:var(--rs-text)">Novelty / claim signals</p>
          <div class="flex flex-wrap gap-1">${noveltyHtml}</div>
        </div>
        <div>
          <p class="text-xs font-semibold mb-2" style="color:var(--rs-text)">Field signals</p>
          <div class="space-y-1.5">${fieldHtml || `<span class="text-xs" style="color:var(--rs-muted)">No strong field signals</span>`}</div>
        </div>
      </div>
      ${tipsHtml}
    </div>`;
  }

  // ── Scoring ─────────────────────────────────────────────────────────────
  function weightedKeywordScore(queryTokens, weightedKeywords, queryBigrams, fallbackKeywords) {
    let score = 0;
    const strong = [], moderate = [];
    const terms = (weightedKeywords && weightedKeywords.length)
      ? weightedKeywords
      : (fallbackKeywords || []).map((t) => ({ term: t, weight: 0.25 }));
    terms.forEach((item) => {
      const keyword = item.term || item;
      const weight = Number(item.weight || 0.25);
      const parts = tokenize(keyword);
      if (!parts.length) return;
      const hits = parts.filter((p) => queryTokens.has(p)).length;
      if (hits === parts.length) {
        const isPhrase = parts.length > 1;
        const phraseBonus = (isPhrase && queryBigrams && queryBigrams.has(parts.join(' '))) ? 1.5 : 1.0;
        const pts = weight * (isPhrase ? 20 : 12) * phraseBonus;
        score += pts;
        (pts >= 5 ? strong : moderate).push(keyword);
      } else if (hits > 0) {
        score += weight * 4 * (hits / parts.length);
        moderate.push(keyword);
      }
    });
    const top20 = terms.slice(0, 20);
    const covered = top20.filter((item) => {
      const p = tokenize(item.term || item);
      return p.length && p.every((t) => queryTokens.has(t));
    }).length;
    const coverage = top20.length ? Math.round((covered / top20.length) * 100) : 0;
    return {
      score,
      matched: [...new Set([...strong, ...moderate])].slice(0, 10),
      strong: [...new Set(strong)].slice(0, 5),
      moderate: [...new Set(moderate)].slice(0, 5),
      coverage,
    };
  }

  function fitLabel(score, coverage = 0) {
    if (score >= 35 || (score >= 28 && coverage >= 35))
      return { label: 'Excellent fit', cls: 'recommender-fit-excellent' };
    if (score >= 24) return { label: 'Strong fit',   cls: 'recommender-fit-strong' };
    if (score >= 14) return { label: 'Moderate fit', cls: 'recommender-fit-moderate' };
    if (score >= 7)  return { label: 'Stretch fit',  cls: 'recommender-fit-stretch' };
    return               { label: 'Unlikely fit',  cls: 'recommender-fit-unlikely' };
  }

  function fitLegend() {
    const items = [
      ['Excellent fit', 'recommender-fit-excellent'],
      ['Strong fit', 'recommender-fit-strong'],
      ['Moderate fit', 'recommender-fit-moderate'],
      ['Stretch fit', 'recommender-fit-stretch'],
    ];
    return `<div class="flex flex-wrap items-center gap-1.5 mt-2">
      <span class="text-xs" style="color:var(--rs-muted)">Fit scale:</span>
      ${items.map(([l, c]) => `<span class="badge ${c}" style="font-size:.6rem">${l}</span>`).join('')}
    </div>`;
  }

  function generateRationale(item, venueWord = 'venue') {
    const { venue, score, strong = [], moderate = [] } = item;
    const top = (strong.length ? strong : moderate).slice(0, 3);
    if (!top.length) return `Primarily a field-based match — topic overlap is weak.`;
    const sigs = top.map((s) => `<em>${escHtml(s)}</em>`).join(', ');
    if (score >= 35) return `Excellent alignment on ${sigs}. Your abstract directly matches ${escHtml(venue.short)}'s core themes.`;
    if (score >= 24) return `Strong overlap on ${sigs}. ${escHtml(venue.short)} regularly publishes this work — align your framing to ${venueWord} conventions.`;
    if (score >= 14) return `Partial match on ${sigs}. Plausible but competitive — make your contribution explicit relative to ${venueWord} priorities.`;
    return `Weak overlap. Check whether ${escHtml(venue.short)} fits your work, or add more field-specific language.`;
  }

  function similarPapers(papers, queryTokens, limit = 5) {
    return (papers || [])
      .map((p) => {
        const hits = (p.terms || []).filter((t) => queryTokens.has(t)).length;
        const tagHits = (p.tags || []).filter((t) => tokenize(t).some((x) => queryTokens.has(x))).length;
        return { ...p, sim: hits + tagHits * 2 };
      })
      .filter((p) => p.sim > 0)
      .sort((a, b) => b.sim - a.sim)
      .slice(0, limit);
  }

  // ── Shared result fragments ─────────────────────────────────────────────
  function breakdownBars(rows, topScore) {
    const cap = Math.max(topScore, 1);
    const pct = (v) => Math.max(0, Math.min(100, Math.round((v / cap) * 100)));
    const row = (label, cls, val) => {
      if (val <= 0) return '';
      return `
      <div class="flex items-center gap-2 text-xs" style="color:var(--rs-muted)">
        <span style="width:5.5rem;flex-shrink:0">${label}</span>
        <div class="breakdown-bar"><div class="${cls}" style="width:${pct(val)}%"></div></div>
        <span style="width:2rem;text-align:right">+${Math.round(val)}</span>
      </div>`;
    };
    return `<div class="space-y-1 mt-2">${rows.map(([l, c, v]) => row(l, c, v)).join('')}</div>`;
  }

  function coverageBar(coverage) {
    return `
    <div class="flex items-center gap-2 text-xs mt-2" style="color:var(--rs-muted)">
      <span style="flex-shrink:0">Topic coverage</span>
      <div class="coverage-bar" style="flex:1"><div class="coverage-fill" style="width:${coverage}%"></div></div>
      <span style="flex-shrink:0;font-weight:600">${coverage}%</span>
    </div>`;
  }

  function matchedSignalsBlock(item) {
    const strongHtml = item.strong && item.strong.length
      ? item.strong.map((s) => `<span class="badge signal-strong" style="font-size:.65rem">${escHtml(s)}</span>`).join(' ') : '';
    const moderateHtml = item.moderate && item.moderate.length
      ? item.moderate.map((s) => `<span class="badge signal-moderate" style="font-size:.65rem">${escHtml(s)}</span>`).join(' ') : '';
    if (!strongHtml && !moderateHtml) return '';
    return `
    <div class="mt-3">
      <p class="text-xs font-bold uppercase mb-1.5" style="color:var(--rs-muted)">Matched signals</p>
      ${strongHtml ? `<div class="flex flex-wrap gap-1 mb-1"><span class="text-xs" style="color:var(--rs-muted);min-width:4rem">Strong:</span>${strongHtml}</div>` : ''}
      ${moderateHtml ? `<div class="flex flex-wrap gap-1"><span class="text-xs" style="color:var(--rs-muted);min-width:4rem">Partial:</span>${moderateHtml}</div>` : ''}
    </div>`;
  }

  function similarPapersBlock(similar, fallbackVenueShort, emptyMsg) {
    if (!similar.length)
      return `<p class="text-xs" style="color:var(--rs-muted)">${escHtml(emptyMsg)}</p>`;
    return similar.map((p) => `
      <div class="recommender-paper">
        <a href="${escHtml(p.url || '#')}" target="_blank" rel="noopener" class="text-sm font-semibold hover:underline">${escHtml(p.title)}</a>
        <div class="text-xs mt-0.5" style="color:var(--rs-muted)">${escHtml(p.venue || fallbackVenueShort)} ${escHtml(String(p.year || ''))}</div>
        ${p.abstract ? `<div class="paper-abstract-snippet">${escHtml(p.abstract.slice(0, 160))}…</div>` : ''}
      </div>`).join('');
  }

  // ── Shortlist export ────────────────────────────────────────────────────
  function buildShortlistMarkdown(ranked, kind) {
    const lines = [`# ResearchScope — ${kind} shortlist`, ''];
    ranked.forEach((item, i) => {
      const v = item.venue;
      lines.push(`${i + 1}. **${v.short}**${v.name && v.name !== v.short ? ` — ${v.name}` : ''} · ${item.fit.label} · score ${Math.round(item.score)}`);
      if (item.strong && item.strong.length) lines.push(`   - Strong signals: ${item.strong.join(', ')}`);
    });
    lines.push('', `Generated by ResearchScope · fit labels are advisory, not acceptance predictions.`);
    return lines.join('\n');
  }

  function attachShortlistCopy(btnId, ranked, kind) {
    const btn = byId(btnId);
    if (!btn) return;
    btn.onclick = async () => {
      try {
        await navigator.clipboard.writeText(buildShortlistMarkdown(ranked, kind));
        const prev = btn.textContent;
        btn.textContent = 'Copied';
        setTimeout(() => { btn.textContent = prev; }, 1500);
      } catch {
        btn.textContent = 'Copy failed';
      }
    };
  }

  // ── Form wiring (autosave, counter, field hint, keyboard submit, sample) ─
  function updateCounter(absId, ctId) {
    const el = byId(absId), ct = byId(ctId);
    if (!el || !ct) return;
    const words = el.value.trim() ? el.value.trim().split(/\s+/).length : 0;
    ct.textContent = `${el.value.length} chars · ~${words} words`;
  }

  function runRecommend(btn, recommend) {
    if (btn) { btn.disabled = true; btn.dataset.label = btn.dataset.label || btn.textContent; btn.textContent = 'Analyzing…'; }
    setTimeout(() => {
      try { recommend(); } finally {
        if (btn) { btn.disabled = false; btn.textContent = btn.dataset.label; }
      }
      const res = byId('recommender-results');
      if (res && res.children.length) res.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 20);
  }

  function wireForm(opts) {
    const { storageKey, recommend, sample } = opts;
    const titleEl = byId('paper-title'), absEl = byId('paper-abstract'), btn = byId('recommend-btn');
    if (!titleEl || !absEl) return;

    // Restore previous input
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
      if (saved) {
        if (saved.title != null) titleEl.value = saved.title;
        if (saved.abstract != null) absEl.value = saved.abstract;
      }
    } catch { /* ignore */ }

    const save = debounce(() => {
      try { localStorage.setItem(storageKey, JSON.stringify({ title: titleEl.value, abstract: absEl.value })); } catch { /* ignore */ }
    }, 500);

    const refreshCount = () => updateCounter('paper-abstract', 'abstract-counter');
    const refreshHint = debounce(() => {
      const fEl = byId('paper-field');
      if (!fEl || fEl.value !== 'auto') return;
      const t = titleEl.value.trim(), a = absEl.value.trim();
      const hint = byId('field-hint');
      if (!hint) return;
      if (t && a.length > 80) {
        const { field, confidence } = inferField(t, a);
        hint.textContent = field ? `Detected: ${field} (${confidence} confidence)` : 'No clear field yet — pick one manually';
      } else {
        hint.textContent = '';
      }
    }, 400);

    absEl.addEventListener('input', refreshCount);
    absEl.addEventListener('input', refreshHint);
    titleEl.addEventListener('input', save);
    absEl.addEventListener('input', save);
    refreshCount();

    const submit = () => runRecommend(btn, recommend);
    [titleEl, absEl].forEach((el) => el.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); submit(); }
    }));
    if (btn) btn.addEventListener('click', submit);

    const sampleBtn = byId('rec-sample-btn');
    if (sampleBtn && sample) sampleBtn.addEventListener('click', () => {
      titleEl.value = sample.title;
      absEl.value = sample.abstract;
      refreshCount(); save(); refreshHint(); submit();
    });
  }

  // Sample drafts for the "Try a sample" button.
  const SAMPLES = {
    conference: {
      title: 'Retrieval-Augmented Reasoning for Long-Context Question Answering',
      abstract: 'Large language models struggle to answer questions that require reasoning over very long documents, because relevant evidence is scattered and easily lost in the context window. We propose RAR, a retrieval-augmented reasoning framework that interleaves sparse retrieval with chain-of-thought generation, dynamically fetching supporting passages at each reasoning step. We evaluate RAR on three long-context question answering benchmarks, including HotpotQA and a new 200k-token corpus, and show that it outperforms strong retrieval-augmented baselines by 7.4 F1 on average while using 40% fewer retrieved tokens. Ablations demonstrate that step-wise retrieval is the key driver of the improvement, and our analysis shows the approach generalizes across model scales.',
    },
    journal: {
      title: 'A Survey of Graph Neural Networks for Anomaly Detection in Dynamic Networks',
      abstract: 'Anomaly detection in dynamic graphs is a central problem in data mining, with applications spanning fraud detection, intrusion detection, and social network monitoring. This survey systematically reviews graph neural network approaches for detecting anomalous nodes, edges, and subgraphs in evolving networks. We propose a taxonomy organized around temporal modeling, supervision signal, and anomaly granularity, and we critically compare representative methods on standard benchmarks in terms of accuracy, scalability, and robustness. We further analyze open challenges including concept drift, label scarcity, and reproducibility, and outline promising research directions for the community.',
    },
  };

  window.RecCore = {
    STOP_WORDS, PLACEHOLDER_WORDS, FIELD_HINTS, NOVELTY_SIGNALS,
    tokenize, extractBigrams, inferField, draftQuality, analyzeAbstract,
    renderAnalysisPanel, weightedKeywordScore, fitLabel, fitLegend,
    generateRationale, similarPapers, breakdownBars, coverageBar,
    matchedSignalsBlock, similarPapersBlock, buildShortlistMarkdown,
    attachShortlistCopy, updateCounter, wireForm, SAMPLES,
  };
})();
