(function () {
  'use strict';

  const root = document.documentElement;
  const cacheKey = 'ui-integrity-18';
  const stylesheets = {
    brutalist: 'assets/css/themes/brutalist.css',
    'field-notes': 'assets/css/themes/field-notes.css',
  };
  const requested = new URLSearchParams(window.location.search).get('theme');
  let saved = null;

  try {
    saved = window.localStorage.getItem('researchscope-theme');
  } catch (_) {
    // Storage can be unavailable in privacy-restricted browsing contexts.
  }

  const hasTheme = value => value === 'atelier' || Object.hasOwn(stylesheets, value);
  const theme = hasTheme(requested)
    ? requested
    : (hasTheme(saved) ? saved : 'atelier');
  root.dataset.rsTheme = theme;
  window.ResearchScopeInitialTheme = theme;

  const stylesheet = stylesheets[theme];
  if (!stylesheet) return;

  root.classList.add('rs-theme-loading');
  root.style.backgroundColor = theme === 'field-notes' ? '#fffcf0' : '#f4f4f0';

  const gate = document.createElement('style');
  gate.id = 'rs-theme-gate';
  gate.textContent = 'html.rs-theme-loading body{visibility:hidden}';
  document.head.appendChild(gate);

  const link = document.createElement('link');
  link.id = 'rs-theme-css';
  link.rel = 'stylesheet';
  link.href = `${stylesheet}?v=${cacheKey}`;

  let revealed = false;
  const reveal = function () {
    if (revealed) return;
    revealed = true;
    root.classList.remove('rs-theme-loading');
    root.style.removeProperty('background-color');
    gate.remove();
  };

  link.addEventListener('load', reveal, { once: true });
  link.addEventListener('error', reveal, { once: true });
  document.head.appendChild(link);
  window.setTimeout(reveal, 4000);
})();
