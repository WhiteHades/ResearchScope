(function () {
  'use strict';

  const core = window.ResearchScopeChatCore;
  const api = window._rs_api;
  const params = new URLSearchParams(location.search);
  const state = {
    paperId: params.get('id') || '',
    requestedSessionId: params.get('session') || '',
    paper: null,
    document: null,
    session: null,
    sessions: [],
    messages: [],
    viewerUrl: '',
    generating: false,
    abortController: null,
    pollTimer: null,
  };

  const el = (id) => document.getElementById(id);

  function setDocumentState(label, failed) {
    const badge = el('document-state');
    badge.textContent = label;
    badge.classList.toggle('failed', !!failed);
  }

  function setComposer(enabled, note) {
    el('chat-input').disabled = !enabled;
    el('send-message').disabled = !enabled || state.generating;
    el('composer-note').textContent = note || '';
  }

  function showPdf(url, page) {
    const safeUrl = core.safeViewerUrl(url, location.href, api.baseUrl);
    if (!safeUrl) {
      showPdfUnavailable(url);
      return false;
    }
    const clean = safeUrl.split('#')[0];
    el('paper-frame').src = `${clean}#page=${page || 1}`;
    el('paper-frame').style.display = 'block';
    el('paper-placeholder').style.display = 'none';
    el('external-pdf').href = clean;
    el('external-pdf').classList.remove('hidden');
    return true;
  }

  function showPdfUnavailable(url) {
    let externalUrl = '';
    try {
      const candidate = new URL(url || '', location.href);
      if (candidate.protocol === 'https:') externalUrl = candidate.href;
    } catch (_) { /* invalid external URL */ }

    el('paper-frame').removeAttribute('src');
    el('paper-frame').style.display = 'none';
    el('paper-placeholder').style.display = 'grid';
    el('paper-placeholder').innerHTML = '<div><h2 class="font-bold mb-2">PDF preview unavailable</h2><p>This publisher does not allow its PDF to be embedded.</p></div>';
    if (externalUrl) {
      el('external-pdf').href = externalUrl;
      el('external-pdf').classList.remove('hidden');
    }
  }

  function messageNode(message) {
    const article = document.createElement('article');
    article.className = `message ${message.role}${message.status === 'failed' ? ' failed' : ''}`;
    article.dataset.messageId = message.id || '';
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = core.displayAnswerText(
      message.content || (message.status === 'pending' ? 'Thinking…' : ''),
    );
    article.appendChild(bubble);

    if (message.citations && message.citations.length) {
      const row = document.createElement('div');
      row.className = 'citation-row';
      const label = document.createElement('span');
      label.className = 'citation-row-label';
      label.textContent = 'Sources';
      row.appendChild(label);
      message.citations.forEach((citation) => {
        const button = document.createElement('button');
        button.className = 'citation-chip';
        const start = core.citationPage(citation);
        const end = Number(citation.page_end || start);
        const sourceNumber = Number(String(citation.label || '').replace(/^S/, '')) || 1;
        const pageText = start === end ? `p. ${start}` : `pp. ${start}–${end}`;
        button.textContent = `[${sourceNumber}] ${pageText}`;
        button.title = citation.excerpt || 'Open cited page';
        button.setAttribute('aria-label', `Source ${sourceNumber}, ${pageText}`);
        button.addEventListener('click', () => {
          showPdf(state.viewerUrl || state.document?.viewer_url || state.paper?.pdf_url, start);
          activateMobilePane('paper');
        });
        row.appendChild(button);
      });
      article.appendChild(row);
    }
    return article;
  }

  function renderMessages() {
    const root = el('messages');
    root.querySelectorAll('.message').forEach((node) => node.remove());
    el('chat-empty').style.display = state.messages.length ? 'none' : 'grid';
    state.messages.forEach((message) => root.appendChild(messageNode(message)));
    root.scrollTop = root.scrollHeight;
  }

  function appendMessage(message) {
    state.messages.push(message);
    renderMessages();
  }

  function updateAssistantMessage(id, patch) {
    const message = state.messages.find((item) => item.id === id);
    if (message) Object.assign(message, patch);
    renderMessages();
  }

  async function loadPaper(paperId) {
    if (!paperId) return;
    try {
      state.paper = await api.papers.get(paperId);
      const isArxiv = String(state.paper.id || '').startsWith('arxiv:') ||
        String(state.paper.source || '').toLowerCase() === 'arxiv';
      if (!isArxiv) {
        el('paper-title').textContent = 'Chat with arXiv';
        el('paper-meta').textContent = 'This workspace currently supports arXiv papers only.';
        setDocumentState('arXiv only', true);
        el('paper-placeholder').innerHTML = '<div><h2 class="font-bold mb-2">Choose an arXiv paper</h2><p>Open the dedicated Chat with arXiv section to continue.</p><a class="chat-action inline-flex mt-4" href="chat-arxiv">Browse arXiv papers</a></div>';
        return false;
      }
      el('paper-title').textContent = state.paper.title;
      const authors = (state.paper.authors || []).slice(0, 4).join(', ');
      el('paper-meta').textContent = [authors, state.paper.venue, state.paper.year].filter(Boolean).join(' · ');
      document.title = `${state.paper.title} – ResearchScope`;
      let viewer = null;
      try {
        viewer = await api.papers.viewer(paperId);
      } catch (_) { /* fall back to metadata URL below */ }
      if (viewer?.viewer_url) {
        state.viewerUrl = new URL(viewer.viewer_url, `${api.baseUrl}/`).href;
      }
      showPdf(state.viewerUrl || state.paper.pdf_url || state.paper.paper_url, 1);
      if (viewer?.external_url) el('external-pdf').href = viewer.external_url;
      return true;
    } catch (error) {
      setDocumentState('Paper unavailable', true);
      el('paper-placeholder').innerHTML = '<div><h2 class="font-bold mb-2">Paper not found</h2><p>The requested paper could not be loaded.</p></div>';
      return false;
    }
  }

  async function preparePaper() {
    if (!state.paperId || !api.auth.isLoggedIn()) return;
    try {
      state.document = await api.documents.status(state.paperId);
      if (state.viewerUrl || state.document.viewer_url) {
        showPdf(state.viewerUrl || state.document.viewer_url, 1);
      }
      if (state.document.status === 'ready') {
        el('retry-prepare').classList.add('hidden');
        setDocumentState(`${state.document.page_count} pages · Ready`);
        setComposer(true, 'Answers are grounded in the prepared PDF.');
        return;
      }
      if (state.document.status === 'failed') {
        el('retry-prepare').classList.remove('hidden');
        setDocumentState('Preparation failed', true);
        setComposer(false, `Full PDF unavailable (${state.document.error_code || 'unknown error'}).`);
        return;
      }
      if (state.document.status === 'not_prepared') {
        state.document = await api.documents.prepare(state.paperId);
      }
      setDocumentState(state.document.status === 'preparing' ? 'Preparing…' : 'Queued…');
      setComposer(false, 'Preparing the full paper for grounded chat…');
      clearTimeout(state.pollTimer);
      state.pollTimer = setTimeout(preparePaper, 1800);
    } catch (error) {
      setDocumentState('Chat unavailable', true);
      setComposer(false, error.message === 'chat_disabled' ? 'Chat is disabled by the administrator.' : error.message);
    }
  }

  async function loadSessions() {
    if (!api.auth.isLoggedIn()) {
      renderHistory();
      return;
    }
    try {
      const result = await api.chat.listSessions({ limit: 100 });
      state.sessions = result.results || [];
      renderHistory();
      if (state.requestedSessionId) {
        await openSession(state.requestedSessionId, false);
        state.requestedSessionId = '';
      } else if (state.paperId) {
        const recent = state.sessions.find((session) => session.paper_id === state.paperId);
        if (recent) await openSession(recent.id, false);
      }
    } catch (_) {
      el('history-list').textContent = 'Could not load chat history.';
    }
  }

  function renderHistory() {
    const root = el('history-list');
    root.replaceChildren();
    if (!api.auth.isLoggedIn()) {
      const p = document.createElement('p');
      p.className = 'text-sm';
      p.textContent = 'Sign in to view saved paper chats.';
      root.appendChild(p);
      return;
    }
    if (!state.sessions.length) {
      const p = document.createElement('p');
      p.className = 'text-sm';
      p.textContent = 'No paper chats yet.';
      root.appendChild(p);
      return;
    }
    state.sessions.forEach((session) => {
      const item = document.createElement('article');
      item.className = 'history-item';
      const main = document.createElement('button');
      main.className = 'history-main';
      const title = document.createElement('div');
      title.className = 'history-title';
      title.textContent = session.title;
      const meta = document.createElement('div');
      meta.className = 'history-meta';
      meta.textContent = `${session.paper_title || session.paper_id} · ${session.message_count} messages`;
      main.append(title, meta);
      main.addEventListener('click', () => openSession(session.id, true));
      const actions = document.createElement('div');
      actions.className = 'history-actions';
      const rename = document.createElement('button');
      rename.textContent = 'Rename';
      rename.addEventListener('click', () => renameSession(session));
      const remove = document.createElement('button');
      remove.className = 'history-danger';
      remove.textContent = 'Delete';
      remove.addEventListener('click', () => deleteSession(session));
      actions.append(rename, remove);
      item.append(main, actions);
      root.appendChild(item);
    });
  }

  async function openSession(sessionId, navigate) {
    const detail = await api.chat.getSession(sessionId);
    if (navigate && detail.paper_id !== state.paperId) {
      location.href = core.workspaceUrl(detail.paper_id, detail.id);
      return;
    }
    state.session = detail;
    state.messages = detail.messages || [];
    renderMessages();
    setView('assistant');
  }

  async function renameSession(session) {
    const title = window.prompt('Chat title', session.title);
    if (!title || title.trim() === session.title) return;
    await api.chat.updateSession(session.id, { title: title.trim() });
    await loadSessions();
  }

  async function deleteSession(session) {
    if (!window.confirm(`Delete “${session.title}”?`)) return;
    await api.chat.deleteSession(session.id);
    if (state.session?.id === session.id) newChat();
    await loadSessions();
  }

  function newChat() {
    state.session = null;
    state.messages = [];
    renderMessages();
    setView('assistant');
    el('chat-input').focus();
  }

  async function ensureSession() {
    if (state.session) return state.session;
    state.session = await api.chat.createSession(state.paperId);
    state.sessions.unshift(state.session);
    renderHistory();
    return state.session;
  }

  async function sendMessage() {
    const input = el('chat-input');
    const content = input.value.trim();
    if (!content || state.generating || state.document?.status !== 'ready') return;
    if (!api.auth.isLoggedIn()) {
      window.rsOpenModal(`chat-paper?id=${encodeURIComponent(state.paperId)}`);
      return;
    }
    const session = await ensureSession();
    const requestId = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
    const userId = `local-user-${requestId}`;
    const assistantId = `local-assistant-${requestId}`;
    appendMessage({ id: userId, role: 'user', content, citations: [], status: 'complete' });
    appendMessage({ id: assistantId, role: 'assistant', content: '', citations: [], status: 'pending' });
    input.value = '';
    state.generating = true;
    state.abortController = new AbortController();
    el('send-message').textContent = '■';
    el('send-message').disabled = false;

    try {
      const response = await api.chat.sendMessage(
        session.id, content, requestId, state.abortController.signal,
      );
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let answer = '';
      let citations = [];
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const parsed = core.consumeSse(buffer);
        buffer = parsed.rest;
        for (const event of parsed.events) {
          if (event.type === 'message_started' && event.data.assistant_message_id) {
            const message = state.messages.find((item) => item.id === assistantId);
            if (message) message.id = event.data.assistant_message_id;
          } else if (event.type === 'delta') {
            answer += event.data.text || '';
            updateAssistantMessage(
              state.messages.find((item) => item.id !== userId && item.role === 'assistant' && item.status === 'pending')?.id || assistantId,
              { content: answer },
            );
          } else if (event.type === 'citations') {
            citations = event.data.citations || [];
          } else if (event.type === 'message_completed') {
            answer = event.data.content || answer;
            citations = event.data.citations || citations;
          } else if (event.type === 'error') {
            throw new Error(event.data.code || 'chat_generation_failed');
          }
        }
        if (done) break;
      }
      const pending = state.messages.find((item) => item.role === 'assistant' && item.status === 'pending');
      if (pending) Object.assign(pending, { content: answer, citations, status: 'complete' });
      renderMessages();
      await loadSessions();
    } catch (error) {
      const pending = state.messages.find((item) => item.role === 'assistant' && item.status === 'pending');
      if (pending) Object.assign(pending, {
        content: error.name === 'AbortError' ? 'Generation cancelled.' : `Could not answer: ${error.message}`,
        status: 'failed',
      });
      renderMessages();
    } finally {
      state.generating = false;
      state.abortController = null;
      el('send-message').textContent = '↑';
      setComposer(state.document?.status === 'ready', 'Answers are grounded in the prepared PDF.');
    }
  }

  function setView(view) {
    document.querySelectorAll('.assistant-tab').forEach((button) => {
      button.classList.toggle('active', button.dataset.view === view);
    });
    el('assistant-view').classList.toggle('hidden-view', view !== 'assistant');
    el('history-view').classList.toggle('hidden-view', view !== 'history');
  }

  function activateMobilePane(pane) {
    document.querySelectorAll('.mobile-pane-tab').forEach((button) => {
      button.classList.toggle('active', button.dataset.pane === pane);
    });
    el('paper-pane').classList.toggle('mobile-hidden', pane !== 'paper');
    el('assistant-pane').classList.toggle('mobile-hidden', pane !== 'assistant');
  }

  function bindEvents() {
    document.querySelectorAll('.assistant-tab').forEach((button) => {
      button.addEventListener('click', () => setView(button.dataset.view));
    });
    document.querySelectorAll('.mobile-pane-tab').forEach((button) => {
      button.addEventListener('click', () => activateMobilePane(button.dataset.pane));
    });
    document.querySelectorAll('.suggestion').forEach((button) => {
      button.addEventListener('click', () => {
        el('chat-input').value = button.textContent;
        sendMessage();
      });
    });
    el('new-chat').addEventListener('click', newChat);
    el('retry-prepare').addEventListener('click', async () => {
      el('retry-prepare').classList.add('hidden');
      setDocumentState('Queued…');
      setComposer(false, 'Retrying full PDF preparation…');
      try {
        state.document = await api.documents.prepare(state.paperId);
        clearTimeout(state.pollTimer);
        state.pollTimer = setTimeout(preparePaper, 1200);
      } catch (error) {
        setDocumentState('Chat unavailable', true);
        setComposer(false, error.message);
      }
    });
    el('send-message').addEventListener('click', () => {
      if (state.generating) state.abortController?.abort();
      else sendMessage();
    });
    el('chat-input').addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
      }
    });
    el('delete-all-chats').addEventListener('click', async () => {
      if (!api.auth.isLoggedIn() || !window.confirm('Delete all of your paper chats?')) return;
      await api.chat.deleteAllSessions();
      newChat();
      await loadSessions();
    });
  }

  async function init() {
    bindEvents();
    if (!state.paperId) {
      setComposer(false, 'Choose a paper from ResearchScope to start a chat.');
      await loadSessions();
      setView('history');
      return;
    }
    const paperLoaded = await loadPaper(state.paperId);
    if (!paperLoaded) {
      setComposer(false, 'Choose an arXiv paper to use this workspace.');
      return;
    }
    if (!api.auth.isLoggedIn()) {
      setDocumentState('Sign in to prepare');
      setComposer(false, 'Sign in to prepare the full PDF and save chat history.');
      el('empty-copy').textContent = 'Sign in to prepare this paper and start a grounded chat.';
    } else {
      await preparePaper();
    }
    await loadSessions();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
