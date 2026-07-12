(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ResearchScopeChatCore = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function workspaceUrl(paperId, sessionId) {
    const params = new URLSearchParams();
    if (paperId) params.set('id', String(paperId));
    if (sessionId) params.set('session', String(sessionId));
    return `chat-paper${params.size ? `?${params}` : ''}`;
  }

  function consumeSse(buffer) {
    const normalized = buffer.replace(/\r\n/g, '\n');
    const blocks = normalized.split('\n\n');
    const rest = blocks.pop() || '';
    const events = [];
    for (const block of blocks) {
      let type = 'message';
      const data = [];
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) type = line.slice(6).trim();
        if (line.startsWith('data:')) data.push(line.slice(5).trim());
      }
      if (!data.length) continue;
      try { events.push({ type, data: JSON.parse(data.join('\n')) }); }
      catch (_) { events.push({ type: 'error', data: { code: 'invalid_stream_event' } }); }
    }
    return { events, rest };
  }

  function citationPage(citation) {
    const page = Number(citation && citation.page_start);
    return Number.isFinite(page) && page > 0 ? page : 1;
  }

  function safeViewerUrl(value, baseUrl, apiBaseUrl) {
    if (!value) return '';
    try {
      const url = new URL(value, baseUrl || 'https://researchscope.invalid/');
      const allowed = [
        'arxiv.org', 'openreview.net', 'aclanthology.org',
        'proceedings.mlr.press', 'openaccess.thecvf.com',
        'semanticscholar.org', 'pdfs.semanticscholar.org',
      ];
      const host = url.hostname.toLowerCase();
      const trusted = allowed.some((item) => host === item || host.endsWith(`.${item}`));
      const base = new URL(baseUrl || 'https://researchscope.invalid/');
      const localHosts = ['127.0.0.1', 'localhost'];
      const localViewer = localHosts.includes(base.hostname) && localHosts.includes(host) &&
        (url.protocol === 'http:' || url.protocol === 'https:');
      let trustedApiViewer = false;
      if (apiBaseUrl) {
        const api = new URL(apiBaseUrl, base);
        trustedApiViewer = url.protocol === 'https:' && url.origin === api.origin;
      }
      return (url.protocol === 'https:' && (trusted || trustedApiViewer)) || localViewer
        ? url.href
        : '';
    } catch (_) {
      return '';
    }
  }

  return { citationPage, consumeSse, safeViewerUrl, workspaceUrl };
});
