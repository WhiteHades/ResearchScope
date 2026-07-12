#!/usr/bin/env node
import { execFileSync, spawn } from 'node:child_process';

const port = 8793;
const session = 'rs-field-notes-perf';
const routes = ['/', '/papers.html', '/topics.html'];
const server = spawn('python3', ['-m', 'http.server', String(port), '--bind', '127.0.0.1', '--directory', 'site'], {
  stdio: 'ignore',
});

function browser(args) {
  return execFileSync('agent-browser', ['--session', session, ...args], {
    encoding: 'utf8',
    maxBuffer: 1024 * 1024,
  }).trim();
}

async function waitForServer() {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    try {
      execFileSync('python3', ['-c', `import socket; s=socket.create_connection(('127.0.0.1', ${port}), 0.25); s.close()`], { stdio: 'ignore' });
      return;
    } catch (_) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }
  throw new Error('Timed out waiting for the static server');
}

const sampler = String.raw`
(async () => {
  window.scrollTo(0, 0);
  await new Promise(resolve => setTimeout(resolve, 300));
  const frames = [];
  let previous = performance.now();
  const start = previous;
  await new Promise(resolve => {
    function step(now) {
      frames.push(now - previous);
      previous = now;
      const progress = Math.min((now - start) / 2500, 1);
      window.scrollTo(0, progress * (document.documentElement.scrollHeight - innerHeight));
      if (progress < 1) requestAnimationFrame(step);
      else resolve();
    }
    requestAnimationFrame(step);
  });
  frames.shift();
  frames.sort((a, b) => a - b);
  return {
    frames: frames.length,
    p95: Number(frames[Math.floor(frames.length * 0.95)].toFixed(2)),
    max: Number(frames.at(-1).toFixed(2)),
    over20: frames.filter(frame => frame > 20).length,
    shaderCanvas: Boolean(document.querySelector('.rs-field-shader canvas')),
    infiniteAnimations: document.getAnimations().filter(animation => animation.effect?.getTiming().iterations === Infinity).length,
    backgroundAttachment: getComputedStyle(document.body).backgroundAttachment,
  };
})()
`;

try {
  await waitForServer();
  try { browser(['close']); } catch (_) {}
  browser(['set', 'viewport', '1280', '800']);
  const results = [];
  for (const route of routes) {
    browser(['open', `http://127.0.0.1:${port}${route}?theme=field-notes&perf=audit`]);
    browser(['wait', '--load', 'networkidle']);
    results.push({ route, ...JSON.parse(browser(['eval', sampler])) });
  }
  console.log(JSON.stringify(results, null, 2));

  const failed = results.some(result => {
    const fixedBackground = result.backgroundAttachment.split(',').some(value => value.trim() === 'fixed');
    return result.shaderCanvas || result.infiniteAnimations || fixedBackground || result.p95 > 20 || result.over20 > 10;
  });
  if (failed) process.exitCode = 1;
} finally {
  try { browser(['close']); } catch (_) {}
  server.kill();
}
