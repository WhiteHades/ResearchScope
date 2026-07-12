#!/usr/bin/env node
import { mkdirSync, writeFileSync } from 'node:fs';
import { execFileSync, spawn } from 'node:child_process';
import { join } from 'node:path';

const CONFIG = {
  port: 8791,
  outDir: '/tmp/opencode/researchscope-contrast',
  routes: [
    '/',
    '/papers.html',
    '/conferences.html',
    '/journals.html',
    '/topics.html',
    '/digest.html',
    '/deadlines.html',
    '/conference-recommender.html',
    '/journal-recommender.html',
    '/favourites.html',
    '/library.html',
    '/profile.html',
    '/search.html',
    '/authors.html',
    '/labs.html',
    '/gaps.html',
    '/signin.html',
    '/register.html',
  ],
  quickRoutes: ['/', '/digest.html', '/papers.html', '/conference-recommender.html', '/favourites.html', '/signin.html'],
  themes: ['atelier', 'brutalist', 'field-notes'],
  media: ['light', 'dark'],
  viewports: [
    { name: 'mobile', width: 390, height: 844 },
    { name: 'compact', width: 1279, height: 900 },
    { name: 'desktop', width: 1280, height: 900 },
  ],
};

class Args {
  constructor(argv) {
    this.quick = argv.includes('--quick');
    this.keepServer = argv.includes('--keep-server');
    this.outDir = this.value(argv, '--out') || CONFIG.outDir;
    this.port = Number(this.value(argv, '--port') || CONFIG.port);
    this.route = this.value(argv, '--route');
    this.theme = this.value(argv, '--theme');
    this.media = this.value(argv, '--media');
    this.viewport = this.value(argv, '--viewport');
    this.session = this.value(argv, '--session') || 'rs-contrast-audit';
    this.shell = argv.includes('--shell');
    this.persistedTheme = argv.includes('--persisted-theme');
  }

  value(argv, flag) {
    const index = argv.indexOf(flag);
    return index >= 0 ? argv[index + 1] : null;
  }
}

class StaticServer {
  constructor(port) {
    this.port = port;
    this.process = null;
  }

  start() {
    this.process = spawn('python3', ['-m', 'http.server', String(this.port), '--bind', '127.0.0.1', '--directory', 'site'], {
      stdio: 'ignore',
    });
    return new Promise((resolve, reject) => {
      const deadline = Date.now() + 5000;
      const tick = () => {
        try {
          execFileSync('python3', ['-c', `import socket; s=socket.create_connection(('127.0.0.1', ${this.port}), 0.25); s.close()`], { stdio: 'ignore' });
          resolve();
        } catch (error) {
          if (Date.now() > deadline) reject(error);
          else setTimeout(tick, 100);
        }
      };
      tick();
    });
  }

  stop() {
    if (this.process) this.process.kill();
  }
}

class AgentBrowser {
  constructor(session) {
    this.session = session;
  }

  run(args, input = null) {
    return execFileSync('agent-browser', ['--session', this.session, ...args], {
      input,
      encoding: 'utf8',
      maxBuffer: 1024 * 1024 * 30,
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
  }

  close() {
    try {
      this.run(['close']);
    } catch (_) {
      // The audit should not fail during cleanup.
    }
  }
}

const sampler = String.raw`
(() => {
  const FORCE_SELECTORS = [
    'a', 'button', 'input', 'select', 'textarea', 'label',
    '.hero-gradient', '.rs-card', '.editorial-card', '.gap-card', '.digest-paper-card',
    '.potd-wrap', '.digest-header', '.star-cta', '.next-banner', '.deadline-card',
    '.topic-accordion', '.topic-graph-shell', '.recommender-panel', '.recommender-result',
    '.recommender-paper', '.library-card', '.auth-card', '.auth-brand', '.auth-panel',
    '.badge', '.rs-status', '.rs-chip', '.pager-btn', '.github-star-btn', '.star-cta-btn'
  ];

  const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'SVG']);

  function parseColor(value) {
    const rgbMatch = value && value.match(/rgba?\(([^)]+)\)/);
    if (rgbMatch) {
      const parts = rgbMatch[1].split(/,\s*/).map(Number);
      return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
    }
    const hexMatch = value && value.match(/^#([0-9a-f]{6})$/i);
    if (hexMatch) {
      const raw = hexMatch[1];
      return [Number.parseInt(raw.slice(0, 2), 16), Number.parseInt(raw.slice(2, 4), 16), Number.parseInt(raw.slice(4, 6), 16), 1];
    }
    const oklchMatch = value && value.match(/oklch\(([^)]+)\)/);
    if (oklchMatch) return oklchToRgb(oklchMatch[1]);
    return [255, 255, 255, 0];
  }

  function oklchToRgb(raw) {
    const [coords, alphaRaw] = raw.split('/').map(part => part.trim());
    const parts = coords.split(/\s+/);
    const L = parts[0].endsWith('%') ? Number.parseFloat(parts[0]) / 100 : Number.parseFloat(parts[0]);
    const C = Number.parseFloat(parts[1]);
    const h = Number.parseFloat(parts[2]) * Math.PI / 180;
    const alpha = alphaRaw == null ? 1 : (alphaRaw.endsWith('%') ? Number.parseFloat(alphaRaw) / 100 : Number.parseFloat(alphaRaw));
    const a = C * Math.cos(h);
    const b = C * Math.sin(h);
    const lPrime = L + 0.3963377774 * a + 0.2158037573 * b;
    const mPrime = L - 0.1055613458 * a - 0.0638541728 * b;
    const sPrime = L - 0.0894841775 * a - 1.2914855480 * b;
    const l = lPrime ** 3;
    const m = mPrime ** 3;
    const s = sPrime ** 3;
    const linear = [
      +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    ];
    const srgb = linear.map(channel => {
      const value = channel <= 0.0031308 ? 12.92 * channel : 1.055 * Math.sign(channel) * Math.abs(channel) ** (1 / 2.4) - 0.055;
      return Math.round(Math.max(0, Math.min(1, value)) * 255);
    });
    return [srgb[0], srgb[1], srgb[2], Number.isFinite(alpha) ? alpha : 1];
  }

  function composite(top, bottom) {
    const alpha = top[3] + bottom[3] * (1 - top[3]);
    if (!alpha) return [255, 255, 255, 0];
    return [
      Math.round((top[0] * top[3] + bottom[0] * bottom[3] * (1 - top[3])) / alpha),
      Math.round((top[1] * top[3] + bottom[1] * bottom[3] * (1 - top[3])) / alpha),
      Math.round((top[2] * top[3] + bottom[2] * bottom[3] * (1 - top[3])) / alpha),
      alpha,
    ];
  }

  function luminance(channel) {
    const value = channel / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  }

  function contrast(fg, bg) {
    const l1 = 0.2126 * luminance(fg[0]) + 0.7152 * luminance(fg[1]) + 0.0722 * luminance(fg[2]);
    const l2 = 0.2126 * luminance(bg[0]) + 0.7152 * luminance(bg[1]) + 0.0722 * luminance(bg[2]);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  }

  function visible(el) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return false;
    if (SKIP_TAGS.has(el.tagName)) return false;
    if (el.closest('[hidden], .hidden, [aria-hidden="true"]')) return false;
    if (el.closest(':disabled, [aria-disabled="true"]')) return false;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function path(el) {
    const parts = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE && node !== document.documentElement) {
      let part = node.tagName.toLowerCase();
      if (node.id) part += '#' + node.id;
      else if (node.className && typeof node.className === 'string') part += '.' + node.className.trim().split(/\s+/).slice(0, 3).join('.');
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ');
  }

  function background(el) {
    let bg = [255, 255, 255, 1];
    let imageRisk = false;
    const chain = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE) {
      chain.unshift(node);
      node = node.parentElement;
    }
    for (const item of chain) {
      const style = getComputedStyle(item);
      const layer = parseColor(style.backgroundColor);
      if (layer[3] > 0) bg = composite(layer, bg);
      if (style.backgroundImage && style.backgroundImage !== 'none') imageRisk = true;
    }
    return { color: bg, imageRisk };
  }

  function sample(el) {
    const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    if (!text) return null;
    const style = getComputedStyle(el);
    const fg = parseColor(style.color);
    const bg = background(el);
    let opacity = 1;
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE) {
      opacity *= Number(getComputedStyle(node).opacity) || 0;
      node = node.parentElement;
    }
    const renderedFg = composite([fg[0], fg[1], fg[2], fg[3] * opacity], bg.color);
    const fontSize = Number.parseFloat(style.fontSize) || 16;
    const fontWeight = Number.parseInt(style.fontWeight, 10) || 400;
    const large = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
    const threshold = large ? 3 : 4.5;
    const ratio = contrast(renderedFg, bg.color);
    return {
      text: text.slice(0, 120),
      selector: path(el),
      color: style.color,
      opacity: Number(opacity.toFixed(3)),
      background: 'rgb(' + bg.color.slice(0, 3).join(', ') + ')',
      backgroundRisk: bg.imageRisk,
      fontSize,
      fontWeight,
      ratio: Number(ratio.toFixed(2)),
      threshold,
      large,
    };
  }

  const elements = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.textContent || !node.textContent.trim()) return NodeFilter.FILTER_REJECT;
      const el = node.parentElement;
      return visible(el) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });
  while (walker.nextNode()) elements.add(walker.currentNode.parentElement);
  for (const selector of FORCE_SELECTORS) document.querySelectorAll(selector).forEach(el => { if (visible(el)) elements.add(el); });

  const samples = Array.from(elements).map(sample).filter(Boolean);
  const failures = samples.filter(item => item.ratio < item.threshold);
  const warnings = samples.filter(item => item.backgroundRisk && item.ratio < item.threshold + 1);
  for (const item of failures) {
    const el = Array.from(elements).find(candidate => path(candidate) === item.selector);
    if (el) el.setAttribute('data-contrast-fail', 'true');
  }
  const uiFailures = [];
  if (document.documentElement.scrollWidth > window.innerWidth + 1) {
    uiFailures.push({ type: 'horizontal-overflow', detail: document.documentElement.scrollWidth + 'px document at ' + window.innerWidth + 'px viewport' });
  }
  const heroHeading = document.querySelector('.hero-gradient .rs-display-1');
  if (document.documentElement.dataset.rsTheme === 'field-notes' && heroHeading) {
    const heroStyle = getComputedStyle(heroHeading);
    if (Number.parseFloat(heroStyle.lineHeight) < Number.parseFloat(heroStyle.fontSize) * 0.96) {
      uiFailures.push({ type: 'hero-line-collision', detail: heroStyle.lineHeight + ' line height at ' + heroStyle.fontSize + ' font size' });
    }
  }
  const footer = document.querySelector('footer');
  if (footer && footer.parentElement !== document.body) {
    uiFailures.push({ type: 'footer-containment', detail: path(footer.parentElement) });
  }
  document.querySelectorAll('button, input, select, textarea').forEach(control => {
    if (!visible(control)) return;
    const label = control.getAttribute('aria-label') || control.getAttribute('title') || control.getAttribute('placeholder') || control.textContent.trim() || control.closest('label')?.textContent.trim() || (control.id && document.querySelector('label[for="' + CSS.escape(control.id) + '"]')?.textContent.trim());
    if (!label) uiFailures.push({ type: 'unlabelled-control', detail: path(control) });
  });

  const integrityLink = document.getElementById('rs-ui-integrity-css');
  const bootstrapScript = document.querySelector('head script[src*="/theme-bootstrap.js"]');
  if (!bootstrapScript) uiFailures.push({ type: 'missing-theme-bootstrap', detail: 'theme-bootstrap.js must load from head' });
  if (document.documentElement.classList.contains('rs-theme-loading')) uiFailures.push({ type: 'theme-bootstrap-pending', detail: document.documentElement.dataset.rsTheme || 'unknown theme' });
  if (window.ResearchScopeInitialTheme !== document.documentElement.dataset.rsTheme) uiFailures.push({ type: 'theme-bootstrap-mismatch', detail: String(window.ResearchScopeInitialTheme) + ' -> ' + String(document.documentElement.dataset.rsTheme) });
  const expectedVersion = integrityLink ? new URL(integrityLink.href).searchParams.get('v') : null;
  if (!expectedVersion) uiFailures.push({ type: 'missing-integrity-stylesheet', detail: 'rs-ui-integrity-css' });
  if (bootstrapScript && expectedVersion && new URL(bootstrapScript.src).searchParams.get('v') !== expectedVersion) uiFailures.push({ type: 'stale-theme-bootstrap', detail: bootstrapScript.src });
  const localStyles = new Set();
  const visitedSheets = new Set();
  function collectStyles(sheet) {
    if (!sheet || visitedSheets.has(sheet)) return;
    visitedSheets.add(sheet);
    if (sheet.href && new URL(sheet.href).origin === location.origin && new URL(sheet.href).pathname.includes('/assets/css/')) localStyles.add(sheet.href);
    try {
      Array.from(sheet.cssRules || []).forEach(rule => { if (rule.styleSheet) collectStyles(rule.styleSheet); });
    } catch (_) {}
  }
  Array.from(document.styleSheets).forEach(collectStyles);
  if (expectedVersion) {
    Array.from(localStyles).forEach(href => {
      if (new URL(href).searchParams.get('v') !== expectedVersion) uiFailures.push({ type: 'stale-css-import', detail: href });
    });
  }
  const localLinks = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).filter(link => link.href.startsWith(location.origin) && link.href.includes('/assets/css/'));
  if (integrityLink && localLinks.at(-1) !== integrityLink) uiFailures.push({ type: 'integrity-cascade-order', detail: localLinks.map(link => link.id || link.href).join(' -> ') });

  return {
    url: location.href,
    title: document.title,
    theme: document.documentElement.dataset.rsTheme || null,
    sampleCount: samples.length,
    failures,
    warnings,
    uiFailures,
  };
})()
`;

const shellSampler = String.raw`
(() => {
  const failures = [];
  const visible = element => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const label = element => element.id || element.textContent.trim().replace(/\s+/g, ' ').slice(0, 40);
  const navRow = document.querySelector('.rs-nav .flex.items-center.h-14');
  if (navRow) {
    const navElements = [
      navRow.querySelector(':scope > a:first-child'),
      ...document.querySelectorAll('#rs-nav-links > *'),
      ...document.querySelectorAll('#rs-nav-actions > *'),
    ].filter(visible);
    for (let left = 0; left < navElements.length; left++) {
      for (let right = left + 1; right < navElements.length; right++) {
        const a = navElements[left].getBoundingClientRect();
        const b = navElements[right].getBoundingClientRect();
        const overlapWidth = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const overlapHeight = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (overlapWidth > 1 && overlapHeight > 1) failures.push({ type: 'nav-overlap', detail: label(navElements[left]) + ' intersects ' + label(navElements[right]) });
      }
    }
    const rowRect = navRow.getBoundingClientRect();
    navElements.forEach(element => {
      const rect = element.getBoundingClientRect();
      if (rect.left < rowRect.left - 1 || rect.right > rowRect.right + 1) failures.push({ type: 'nav-overflow', detail: label(element) + ' escapes the navigation row' });
    });
    const desktopLinksVisible = visible(document.getElementById('rs-nav-links'));
    const mobileButtonVisible = visible(document.getElementById('mobile-menu-btn'));
    if (window.innerWidth < 1280 && (desktopLinksVisible || !mobileButtonVisible)) failures.push({ type: 'nav-breakpoint', detail: 'compact navigation not active below 1280px' });
    if (window.innerWidth >= 1280 && (!desktopLinksVisible || mobileButtonVisible)) failures.push({ type: 'nav-breakpoint', detail: 'desktop navigation not active at 1280px' });
  }
  const hitTest = (element, type) => {
    const rect = element?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) {
      failures.push({ type, detail: 'zero-sized overlay' });
      return;
    }
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + Math.min(rect.height / 2, 30));
    if (!hit || !element.contains(hit)) failures.push({ type, detail: hit ? hit.tagName.toLowerCase() + '.' + String(hit.className) : 'no hit target' });
  };

  if (window.innerWidth >= 1280) {
    const dropdown = document.querySelectorAll('.rs-nav-dd')[2];
    const dropdownButton = dropdown?.querySelector('.rs-nav-dd-btn');
    const dropdownMenu = dropdown?.querySelector('.rs-nav-dd-menu');
    dropdownButton?.click();
    if (!dropdown?.classList.contains('is-open') || dropdownButton?.getAttribute('aria-expanded') !== 'true') failures.push({ type: 'dropdown-open-state', detail: 'People menu did not open' });
    hitTest(dropdownMenu, 'dropdown-stacking');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    if (dropdownButton?.getAttribute('aria-expanded') !== 'false') failures.push({ type: 'dropdown-close-state', detail: 'Escape did not close People menu' });

    const themeButton = document.querySelector('.rs-theme-button');
    const themeMenu = document.querySelector('.rs-theme-menu');
    themeButton?.click();
    if (themeButton?.getAttribute('aria-expanded') !== 'true') failures.push({ type: 'theme-menu-open-state', detail: 'Theme menu did not open' });
    hitTest(themeMenu, 'theme-menu-stacking');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    if (themeButton?.getAttribute('aria-expanded') !== 'false' || document.activeElement !== themeButton) failures.push({ type: 'theme-menu-close-state', detail: 'Escape did not close and restore focus' });
  } else {
    const mobileButton = document.getElementById('mobile-menu-btn');
    const mobileMenu = document.getElementById('mobile-menu');
    mobileButton?.click();
    if (!mobileMenu?.classList.contains('is-open') || mobileButton?.getAttribute('aria-expanded') !== 'true') failures.push({ type: 'mobile-menu-open-state', detail: 'Mobile menu did not open' });
    hitTest(mobileMenu, 'mobile-menu-stacking');
    if (!document.getElementById('rs-mobile-auth') || !mobileMenu?.querySelector('a[href="search.html"]')) failures.push({ type: 'mobile-menu-content', detail: 'Search or account controls missing' });
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    if (mobileButton?.getAttribute('aria-expanded') !== 'false') failures.push({ type: 'mobile-menu-close-state', detail: 'Escape did not close mobile menu' });
  }
  return failures;
})()
`;

class ContrastAudit {
  constructor(args) {
    this.args = args;
    this.browser = new AgentBrowser(args.session);
    this.base = `http://127.0.0.1:${args.port}`;
    this.results = [];
  }

  async run() {
    mkdirSync(this.args.outDir, { recursive: true });
    const routes = this.args.route ? [this.args.route] : (this.args.quick ? CONFIG.quickRoutes : CONFIG.routes);
    const viewports = this.args.viewport ? CONFIG.viewports.filter(viewport => viewport.name === this.args.viewport) : CONFIG.viewports;
    const mediaModes = this.args.media ? [this.args.media] : CONFIG.media;
    const themes = this.args.theme ? [this.args.theme] : CONFIG.themes;
    if (!viewports.length) throw new Error(`Unknown viewport: ${this.args.viewport}`);
    if (themes.some(theme => !CONFIG.themes.includes(theme))) throw new Error(`Unknown theme: ${this.args.theme}`);
    if (mediaModes.some(media => !CONFIG.media.includes(media))) throw new Error(`Unknown media mode: ${this.args.media}`);
    if (this.args.persistedTheme) this.browser.run(['open', `${this.base}/?theme=atelier`]);
    for (const viewport of viewports) {
      this.browser.run(['set', 'viewport', String(viewport.width), String(viewport.height)]);
      for (const media of mediaModes) {
        this.browser.run(['set', 'media', media]);
        for (const theme of themes) {
          if (this.args.persistedTheme) this.browser.run(['eval', `localStorage.setItem('researchscope-theme', ${JSON.stringify(theme)}); true`]);
          for (const route of routes) {
            const url = this.args.persistedTheme
              ? `${this.base}${route}?audit=persisted-${theme}`
              : `${this.base}${route}?theme=${theme}`;
            this.browser.run(['open', url]);
            const themeFile = theme === 'brutalist' ? 'brutalist.css' : 'field-notes.css';
            const ready = `document.documentElement.dataset.rsTheme === ${JSON.stringify(theme)} && (${theme === 'atelier'} || Array.from(document.styleSheets).some(sheet => sheet.href && sheet.href.includes(${JSON.stringify(themeFile)})))`;
            this.browser.run(['wait', '--fn', ready]);
            const raw = this.browser.run(['eval', '--stdin'], sampler);
            const result = JSON.parse(raw);
            if (this.args.shell) result.uiFailures.push(...JSON.parse(this.browser.run(['eval', '--stdin'], shellSampler)));
            this.results.push({ route, theme, media, viewport: viewport.name, ...result });
          }
        }
      }
    }
    this.writeReports();
  }

  writeReports() {
    const failures = this.results.flatMap(result => result.failures.map(failure => ({
      route: result.route,
      theme: result.theme,
      media: result.media,
      viewport: result.viewport,
      ...failure,
    })));
    const uiFailures = this.results.flatMap(result => result.uiFailures.map(failure => ({
      route: result.route,
      theme: result.theme,
      media: result.media,
      viewport: result.viewport,
      ...failure,
    })));
    const summary = [
      `ResearchScope contrast audit`,
      ``,
      `Routes: ${new Set(this.results.map(result => result.route)).size}`,
      `Themes: ${Array.from(new Set(this.results.map(result => result.theme))).join(', ')}`,
      `Media: ${Array.from(new Set(this.results.map(result => result.media))).join(', ')}`,
      `Viewports: ${Array.from(new Set(this.results.map(result => result.viewport))).join(', ')}`,
      `Failures: ${failures.length}`,
      `UI failures: ${uiFailures.length}`,
      ``,
      ...failures.slice(0, 80).map(failure => `- ${failure.theme} ${failure.media} ${failure.viewport} ${failure.route}: ${failure.ratio}:1 < ${failure.threshold}:1, ${failure.text} (${failure.selector})`),
      ...uiFailures.slice(0, 80).map(failure => `- ${failure.theme} ${failure.media} ${failure.viewport} ${failure.route}: ${failure.type}, ${failure.detail}`),
    ].join('\n');
    writeFileSync(join(this.args.outDir, 'results.json'), JSON.stringify(this.results, null, 2));
    writeFileSync(join(this.args.outDir, 'summary.txt'), summary);
    writeFileSync(join(this.args.outDir, 'ui-failures.json'), JSON.stringify(uiFailures, null, 2));
    if (failures.length || uiFailures.length) {
      writeFileSync(join(this.args.outDir, 'failures.json'), JSON.stringify(failures, null, 2));
      throw new Error(`UI audit failed with ${failures.length} contrast and ${uiFailures.length} interface failures. See ${this.args.outDir}`);
    }
    console.log(`Contrast audit passed. Report: ${this.args.outDir}`);
  }

  close() {
    this.browser.close();
  }
}

const args = new Args(process.argv.slice(2));
const server = new StaticServer(args.port);
const audit = new ContrastAudit(args);

try {
  await server.start();
  await audit.run();
} finally {
  audit.close();
  if (!args.keepServer) server.stop();
}
