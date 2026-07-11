const shaderState = { mount: null, container: null };

function wantsReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function ensureContainer() {
  if (shaderState.container) return shaderState.container;
  const container = document.createElement('div');
  container.className = 'rs-field-shader';
  container.setAttribute('aria-hidden', 'true');
  document.body.prepend(container);
  shaderState.container = container;
  return container;
}

function disposeShader() {
  if (shaderState.mount?.dispose) shaderState.mount.dispose();
  shaderState.mount = null;
  if (shaderState.container) {
    shaderState.container.remove();
    shaderState.container = null;
  }
}

async function mountShader() {
  if (shaderState.mount || wantsReducedMotion()) return;
  if (document.documentElement.dataset.rsTheme !== 'field-notes') return;

  const container = ensureContainer();

  try {
    const {
      ShaderMount,
      meshGradientFragmentShader,
      getShaderColorFromString,
    } = await import('https://esm.sh/@paper-design/shaders@0.0.77');

    const uniforms = {
      u_colors: [
        getShaderColorFromString('#bfeeff'),
        getShaderColorFromString('#fffaf0'),
        getShaderColorFromString('#ffe15c'),
        getShaderColorFromString('#ffdce8'),
        getShaderColorFromString('#dff6e4'),
      ],
      u_colorsCount: 5,
      u_distortion: 0.28,
      u_swirl: 0.1,
      u_grainMixer: 0.08,
      u_grainOverlay: 0.04,
      u_fit: 2,
      u_scale: 1.08,
      u_rotation: -0.02,
      u_offsetX: 0,
      u_offsetY: 0,
      u_originX: 0.5,
      u_originY: 0.5,
      u_worldWidth: 0,
      u_worldHeight: 0,
    };

    const contextAttributes = {
      alpha: true,
      antialias: false,
      depth: false,
      stencil: false,
      premultipliedAlpha: true,
      preserveDrawingBuffer: false,
    };
    shaderState.mount = new ShaderMount(container, meshGradientFragmentShader, uniforms, contextAttributes, 0.06, 0, 1, 1920 * 1080 * 1.25);
  } catch (error) {
    container.dataset.shaderFallback = 'true';
    console.warn('Field Notes shader fallback:', error.message);
  }
}

function syncShader() {
  if (document.documentElement.dataset.rsTheme === 'field-notes') {
    mountShader();
  } else {
    disposeShader();
  }
}

window.addEventListener('researchscope:themechange', syncShader);
window.addEventListener('beforeunload', disposeShader);

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', syncShader, { once: true });
} else {
  syncShader();
}
