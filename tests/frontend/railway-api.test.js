const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function createClient(fetchImpl) {
  const values = new Map([
    ['rs_jwt', 'stale-token'],
    ['rs_user', JSON.stringify({ name: 'Stale User' })],
  ]);
  const events = [];
  const context = {
    URLSearchParams,
    URL,
    CustomEvent: class CustomEvent {
      constructor(type) { this.type = type; }
    },
    fetch: fetchImpl,
    location: {
      hostname: '127.0.0.1',
      origin: 'http://127.0.0.1:8080',
      pathname: '/chat-paper',
    },
    localStorage: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, String(value)),
      removeItem: (key) => values.delete(key),
    },
    document: {
      addEventListener() {},
      getElementById() { return null; },
    },
    window: {
      dispatchEvent: (event) => events.push(event.type),
    },
    setTimeout,
  };
  context.window.location = context.location;
  context.window.localStorage = context.localStorage;
  vm.createContext(context);
  const source = fs.readFileSync(
    path.join(__dirname, '../../site/assets/js/railway-api.js'),
    'utf8',
  );
  vm.runInContext(source, context);
  return {
    api: context.window._rs_api,
    data: context.window._rs_data,
    safeReturnTo: context.window.rsSafeReturnTo,
    values,
    events,
  };
}

function unauthorized() {
  return {
    ok: false,
    status: 401,
    statusText: 'Unauthorized',
    json: async () => ({ detail: 'Invalid token' }),
  };
}

(async () => {
  const helperClient = createClient(async () => unauthorized());
  assert.equal(
    helperClient.safeReturnTo('papers.html?q=attention', 'https://researchscope.example/ResearchScope/signin.html'),
    '/ResearchScope/papers.html?q=attention',
  );
  assert.equal(
    helperClient.safeReturnTo('https://evil.example/steal', 'https://researchscope.example/ResearchScope/signin.html'),
    './',
  );
  assert.equal(
    helperClient.safeReturnTo('//evil.example/steal', 'https://researchscope.example/ResearchScope/signin.html'),
    './',
  );

  const jsonClient = createClient(async () => unauthorized());
  await assert.rejects(
    jsonClient.api.documents.status('arxiv:2601.1'),
    (error) => {
      assert.equal(error.status, 401);
      assert.equal(error.authExpired, true);
      assert.equal(error.message, 'Your session has expired. Please sign in again.');
      return true;
    },
  );
  assert.equal(jsonClient.values.has('rs_jwt'), false);
  assert.equal(jsonClient.values.has('rs_user'), false);
  assert.deepEqual(jsonClient.events, ['rs:auth-expired']);

  const rawClient = createClient(async () => unauthorized());
  await assert.rejects(
    rawClient.api.chat.sendMessage('session-1', 'hello', 'request-1'),
    (error) => error.status === 401 && error.authExpired === true,
  );
  assert.equal(rawClient.values.has('rs_jwt'), false);

  const requests = [];
  const loginClient = createClient(async (url, options) => {
    requests.push({ url, authorization: options.headers.Authorization });
    if (url.endsWith('/auth/login')) {
      return { ok: true, status: 200, json: async () => ({ access_token: 'fresh-token' }) };
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ id: 1, email: 'qa@example.com', name: 'QA' }),
    };
  });
  await loginClient.api.auth.login('qa@example.com', 'password');
  assert.equal(requests[1].authorization, 'Bearer fresh-token');
  assert.equal(loginClient.values.get('rs_jwt'), 'fresh-token');

  const staticRequests = [];
  const conferenceRows = [
    {
      id: 'conference:1', title: 'Zeta result', abstract: '', authors: [],
      difficulty_level: 'L4', paper_type: 'theory', year: 2026,
      tags: ['LLMs'], venue: 'ICLR', conference_rank: 'A*',
    },
    {
      id: 'conference:2', title: 'Alpha result', abstract: '', authors: [],
      difficulty_level: 'L1', paper_type: 'survey', year: 2025,
      tags: ['RAG'], venue: 'ICML', conference_rank: 'A',
    },
  ];
  const staticClient = createClient(async (url) => {
    staticRequests.push(url);
    if (url.includes('/papers?')) return unauthorized();
    if (url === 'data/conferences.json') {
      return { ok: true, status: 200, json: async () => conferenceRows };
    }
    if (url === 'data/papers.json') {
      return { ok: true, status: 200, json: async () => [{ id: 'arxiv:1' }] };
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
  const staticResult = await staticClient.data.queryPapers({
    source: 'conference',
    pageSize: 10,
  });
  assert.deepEqual(staticResult.data, conferenceRows);
  assert.equal(staticResult.count, 2);
  assert.ok(staticRequests.includes('data/conferences.json'));

  const filteredResult = await staticClient.data.queryPapers({
    source: 'conference', difficulty: 'L1', type: 'survey', year: '2025',
    tag: 'RAG', venue: 'ICML', rank: 'A', pageSize: 10,
  });
  assert.deepEqual(filteredResult.data.map((paper) => paper.id), ['conference:2']);

  const sortedResult = await staticClient.data.queryPapers({
    source: 'conference', sortBy: 'title', pageSize: 10,
  });
  assert.deepEqual(
    sortedResult.data.map((paper) => paper.title),
    ['Alpha result', 'Zeta result'],
  );

  for (const page of ['site/signin.html', 'site/register.html']) {
    const source = fs.readFileSync(path.join(__dirname, '../../', page), 'utf8');
    assert.match(source, /rsSafeReturnTo/);
    assert.doesNotMatch(source, /const returnTo\s*=\s*params\.get\('returnTo'\)/);
  }

  console.log('railway API auth-expiry tests passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
