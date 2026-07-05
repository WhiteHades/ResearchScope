# CSS Architecture

Atelier Zero keeps the public CSS entrypoints stable while splitting implementation into smaller modules.

- `style.css` is the site-wide facade. It imports core tokens, foundations, components, features, motion, overrides, then theme layers.
- `library.css` is the library/listing-page facade. It imports page-specific library modules.
- `conference-recommender.css` is the recommender-page facade. It imports recommender layout, signal, and theme-control modules.
- `core/` owns design tokens and document foundation.
- `components/` owns reusable UI objects.
- `features/` owns larger feature surfaces such as topic graph and digest/share sections.
- `pages/` owns page-specific modules loaded by page-level facades.
- `motion/` owns animation and interaction feedback rules.
- `overrides/` owns audit and compatibility layers that intentionally win late in the cascade.
- `themes/` owns theme-specific overrides. Base components should not import theme modules.

SDLC rules:

1. Keep facade files as import manifests only.
2. Add selectors to the narrowest module that owns the behavior.
3. Preserve import order unless a verification run proves a cascade change is safe.
4. Do not duplicate a selector in a later override unless the reason is contrast, theme, browser, or page-specific hardening.
5. Run static checks and browser route sweeps after touching shared modules.
