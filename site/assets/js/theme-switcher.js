(function () {
  'use strict';

  const THEMES = [
    {
      id: 'atelier',
      name: 'Atelier Zero',
      shortName: 'Atelier',
      description: 'Warm research atelier',
      swatch: 'linear-gradient(135deg, #eee4c9 0 48%, #a63b2d 49% 100%)',
      css: '',
    },
    {
      id: 'brutalist',
      name: 'Industrial Brutalist',
      shortName: 'Brutalist',
      description: 'Grid, ink, redline systems',
      swatch: 'linear-gradient(135deg, #f4f4f0 0 45%, #050505 46% 74%, #e61919 75% 100%)',
      css: 'assets/css/themes/brutalist.css',
    },
    {
      id: 'field-notes',
      name: 'Field Notes',
      shortName: 'Notes',
      description: 'Playful notebook collage',
      swatch: 'linear-gradient(135deg, #bfeeff 0 38%, #ffe15c 39% 70%, #ffdce8 71% 100%)',
      css: 'assets/css/themes/field-notes.css',
    },
  ];

  class ThemeSwitcher {
    constructor(themes) {
      this.themes = themes;
      this.storageKey = 'researchscope-theme';
      this.linkId = 'rs-theme-css';
      this.current = this.resolveInitialTheme();
      this.apply(this.current, false);
      this.loadFieldShader();
      this.ready(() => this.mount());
    }

    ready(callback) {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', callback, { once: true });
      } else {
        callback();
      }
    }

    resolveInitialTheme() {
      const params = new URLSearchParams(window.location.search);
      const requested = params.get('theme');
      const saved = window.localStorage?.getItem(this.storageKey);
      return this.hasTheme(requested) ? requested : (this.hasTheme(saved) ? saved : 'atelier');
    }

    hasTheme(id) {
      return Boolean(id && this.themes.some(theme => theme.id === id));
    }

    getTheme(id) {
      return this.themes.find(theme => theme.id === id) || this.themes[0];
    }

    apply(id, persist = true) {
      const theme = this.getTheme(id);
      this.current = theme.id;
      document.documentElement.dataset.rsTheme = theme.id;

      let link = document.getElementById(this.linkId);
      if (!theme.css) {
        if (link) link.remove();
      } else {
        if (!link) {
          link = document.createElement('link');
          link.id = this.linkId;
          link.rel = 'stylesheet';
          document.head.appendChild(link);
        }
        link.href = `${theme.css}?v=theme-unified-1`;
      }

      if (persist) window.localStorage?.setItem(this.storageKey, theme.id);
      this.updateControls();
      window.dispatchEvent(new CustomEvent('researchscope:themechange', { detail: { theme: theme.id } }));
    }

    cycle() {
      const index = this.themes.findIndex(theme => theme.id === this.current);
      this.apply(this.themes[(index + 1) % this.themes.length].id);
    }

    mount() {
      this.mountDesktop();
      this.mountMobile();
      this.updateControls();
      document.addEventListener('click', event => this.handleOutsideClick(event));
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape') this.closeMenu();
      });
    }

    mountDesktop() {
      const mobileButton = document.getElementById('mobile-menu-btn');
      const navActions = mobileButton?.parentElement;
      if (!navActions || document.getElementById('rs-theme-switcher')) return;

      const root = document.createElement('div');
      root.id = 'rs-theme-switcher';
      root.className = 'rs-theme-switcher hidden lg:block';
      root.innerHTML = `
        <button class="rs-theme-button" type="button" aria-haspopup="menu" aria-expanded="false">
          <span class="rs-theme-dot" aria-hidden="true"></span>
          <span>Theme</span>
          <span class="rs-theme-label"></span>
        </button>
        <div class="rs-theme-menu" role="menu" aria-label="ResearchScope themes">
          ${this.themes.map(theme => this.optionMarkup(theme)).join('')}
        </div>
      `;
      navActions.insertBefore(root, navActions.firstChild);

      root.querySelector('.rs-theme-button').addEventListener('click', () => {
        root.classList.toggle('is-open');
        root.querySelector('.rs-theme-button').setAttribute('aria-expanded', String(root.classList.contains('is-open')));
      });
      root.querySelectorAll('[data-rs-theme-option]').forEach(button => {
        button.addEventListener('click', () => {
          this.apply(button.dataset.rsThemeOption);
          this.closeMenu();
        });
      });
    }

    mountMobile() {
      const mobileLinks = document.getElementById('rs-mob-links');
      if (!mobileLinks || document.getElementById('rs-theme-mobile')) return;

      const root = document.createElement('div');
      root.id = 'rs-theme-mobile';
      root.className = 'rs-theme-mobile';
      root.innerHTML = `
        <span class="rs-theme-mobile__title">Theme</span>
        <div class="rs-theme-mobile__options">
          ${this.themes.map(theme => this.optionMarkup(theme, true)).join('')}
        </div>
      `;
      mobileLinks.prepend(root);
      root.querySelectorAll('[data-rs-theme-option]').forEach(button => {
        button.addEventListener('click', () => this.apply(button.dataset.rsThemeOption));
      });
    }

    optionMarkup(theme, compact = false) {
      return `
        <button class="rs-theme-option" type="button" role="menuitemradio" data-rs-theme-option="${theme.id}" aria-checked="false">
          <span class="rs-theme-option__swatch" style="background:${theme.swatch}" aria-hidden="true"></span>
          <span>
            <span class="rs-theme-option__name">${compact ? theme.shortName : theme.name}</span>
            <span class="rs-theme-option__desc">${theme.description}</span>
          </span>
        </button>
      `;
    }

    updateControls() {
      const theme = this.getTheme(this.current);
      document.querySelectorAll('.rs-theme-label').forEach(label => { label.textContent = theme.shortName; });
      document.querySelectorAll('[data-rs-theme-option]').forEach(option => {
        option.setAttribute('aria-checked', String(option.dataset.rsThemeOption === theme.id));
      });
    }

    handleOutsideClick(event) {
      const root = document.getElementById('rs-theme-switcher');
      if (root && !root.contains(event.target)) this.closeMenu();
    }

    closeMenu() {
      const root = document.getElementById('rs-theme-switcher');
      if (!root) return;
      root.classList.remove('is-open');
      root.querySelector('.rs-theme-button')?.setAttribute('aria-expanded', 'false');
    }

    loadFieldShader() {
      if (document.getElementById('rs-field-notes-shader-script')) return;
      const script = document.createElement('script');
      script.id = 'rs-field-notes-shader-script';
      script.type = 'module';
      script.src = 'assets/js/field-notes-shader.js?v=theme-unified-1';
      document.head.appendChild(script);
    }
  }

  window.ResearchScopeThemes = THEMES;
  window.ResearchScopeThemeSwitcher = new ThemeSwitcher(THEMES);
})();
