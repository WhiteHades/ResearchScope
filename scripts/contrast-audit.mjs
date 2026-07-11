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
    { name: 'desktop', width: 1366, height: 900 },
    { name: 'mobile', width: 390, height: 844 },
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
  return {
    url: location.href,
    title: document.title,
    theme: document.documentElement.dataset.rsTheme || null,
    sampleCount: samples.length,
    failures,
    warnings,
  };
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
    for (const viewport of viewports) {
      this.browser.run(['set', 'viewport', String(viewport.width), String(viewport.height)]);
      for (const media of mediaModes) {
        this.browser.run(['set', 'media', media]);
        for (const theme of themes) {
          for (const route of routes) {
            const url = `${this.base}${route}?theme=${theme}`;
            this.browser.run(['open', url]);
            const themeFile = theme === 'brutalist' ? 'brutalist.css' : 'field-notes.css';
            const ready = `document.documentElement.dataset.rsTheme === ${JSON.stringify(theme)} && (${theme === 'atelier'} || Array.from(document.styleSheets).some(sheet => sheet.href && sheet.href.includes(${JSON.stringify(themeFile)})))`;
            this.browser.run(['wait', '--fn', ready]);
            const raw = this.browser.run(['eval', '--stdin'], sampler);
            const result = JSON.parse(raw);
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
    const summary = [
      `ResearchScope contrast audit`,
      ``,
      `Routes: ${new Set(this.results.map(result => result.route)).size}`,
      `Themes: ${Array.from(new Set(this.results.map(result => result.theme))).join(', ')}`,
      `Media: ${Array.from(new Set(this.results.map(result => result.media))).join(', ')}`,
      `Viewports: ${Array.from(new Set(this.results.map(result => result.viewport))).join(', ')}`,
      `Failures: ${failures.length}`,
      ``,
      ...failures.slice(0, 80).map(failure => `- ${failure.theme} ${failure.media} ${failure.viewport} ${failure.route}: ${failure.ratio}:1 < ${failure.threshold}:1, ${failure.text} (${failure.selector})`),
    ].join('\n');
    writeFileSync(join(this.args.outDir, 'results.json'), JSON.stringify(this.results, null, 2));
    writeFileSync(join(this.args.outDir, 'summary.txt'), summary);
    if (failures.length) {
      writeFileSync(join(this.args.outDir, 'failures.json'), JSON.stringify(failures, null, 2));
      throw new Error(`Contrast audit failed with ${failures.length} failures. See ${this.args.outDir}`);
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
