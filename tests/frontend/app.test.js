const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadSearchHelpers() {
  const fetches = [];
  const context = {
    clearTimeout,
    console,
    fetch: async (url) => {
      fetches.push(url);
      return { ok: true, status: 200, json: async () => [] };
    },
    setTimeout,
    window: {
      addEventListener() {},
      location: { pathname: '/', origin: 'https://researchscope.example' },
      _rs_data: { searchPapersQuick: async () => [] },
    },
    document: {
      addEventListener() {},
      getElementById() { return null; },
      querySelectorAll() { return []; },
      createElement() { return { id: '', src: '', defer: false }; },
      head: { appendChild() {} },
    },
  };
  vm.createContext(context);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, '../../site/assets/js/app.js'), 'utf8'),
    context,
  );
  return { search: context.window.ResearchScopeSearch, fetches };
}

const { search, fetches } = loadSearchHelpers();

(async () => {
  assert.equal(search.authorPaperCount({ paper_count: 34 }), 34);
  assert.equal(search.authorPaperCount({ paper_ids: ['p1', 'p2'] }), 2);
  assert.equal(search.authorPaperCount({}), 0);

  await search.loadSearchData();
  assert.ok(fetches.includes('data/authors.json'));
  assert.ok(fetches.includes('data/topics.json'));
  assert.ok(!fetches.includes('data/search_index.json'));

  const results = await search.runSearch('needle', {
    papers: [{ title: 'A Needle in the Index', abstract: '', authors: [] }],
    authors: [],
    topics: [],
    _useApi: true,
  }, 5);
  assert.deepEqual(results.papers.map((paper) => paper.title), ['A Needle in the Index']);

  for (const page of ['site/search.html', 'site/index.html']) {
    const source = fs.readFileSync(path.join(__dirname, '../../', page), 'utf8');
    assert.match(source, /authorPaperCount\(a\)/);
  }

  console.log('app search and author helpers passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
