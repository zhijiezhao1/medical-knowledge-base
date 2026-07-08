// ================================================================
// 医学知识库 - 纯原生 JavaScript 前端（无任何 CDN 依赖）
// ================================================================

(function() {
  'use strict';
  console.log('app.js loaded v27');

  // ========== 配置 ==========
  // 用相对路径，让前端跟着当前域名走（避免硬编码 Railway 域名导致迁移服务时失效）
  const API = '/api';
  const DEBOUNCE_MS = 500;
  const MAX_FILE_SIZE = 50 * 1024 * 1024;
  const CORRECT_PASSWORD = 'zhishiku';
  const APP_VERSION = '1.0.0';


  // ========== 密码验证 ==========
  let passwordGate, passwordForm, passwordInput, passwordError;
  
  function checkPassword() {
    if (!passwordGate) return true;
    
    // 检测是否为硬刷新（清空缓存并刷新）
    // performance.navigation.type: 0=正常导航, 1=硬刷新, 2=后退
    const isHardReload = performance.navigation.type === 1;
    console.log('isHardReload:', isHardReload, 'type:', performance.navigation.type);
    
    // 硬刷新时清除所有认证数据
    if (isHardReload) {
      localStorage.removeItem('kb_auth');
      localStorage.removeItem('kb_auth_time');
      localStorage.removeItem('kb_auth_version');
    }
    
    try {
      const stored = localStorage.getItem('kb_auth');
      const timestamp = localStorage.getItem('kb_auth_time');
      const version = localStorage.getItem('kb_auth_version');
      
      if (stored === CORRECT_PASSWORD && timestamp) {
        const expiresIn = 24 * 60 * 60 * 1000; // 24小时
        if (Date.now() - parseInt(timestamp) < expiresIn) {
          passwordGate.style.display = 'none';
          return true;
        }
      }
    } catch (e) {
      console.log('localStorage error:', e);
    }
    return false;
  }
  
  function validatePassword(e) {
    e.preventDefault();
    const pwd = passwordInput.value.trim();
    if (pwd === CORRECT_PASSWORD) {
      localStorage.setItem('kb_auth', CORRECT_PASSWORD);
      localStorage.setItem('kb_auth_time', Date.now().toString());
      localStorage.setItem('kb_auth_version', APP_VERSION);
      passwordGate.style.display = 'none';
    } else {
      passwordError.style.display = 'block';
      passwordInput.classList.add('shake');
      setTimeout(() => passwordInput.classList.remove('shake'), 500);
    }
  }
  
  function initPassword() {
    console.log('initPassword called');
    passwordGate = $('#passwordGate');
    passwordForm = $('#passwordForm');
    passwordInput = $('#passwordInput');
    passwordError = $('#passwordError');
    console.log('passwordGate:', passwordGate);
    console.log('checkPassword result:', checkPassword());
    if (passwordGate && !checkPassword()) {
      console.log('Adding event listener');
      passwordForm.addEventListener('submit', validatePassword);
      passwordInput.focus();
    }
  }
  // ========== 状态 ==========
  let state = {
    documents: [],
    loading: true,
    uploading: false,
    expandedIds: new Set(),
    formatFilter: 'all',
    sortOrder: 'desc',
    searchOpen: false,
    searchKeyword: '',
    searchResults: [],
    searchLoading: false,
    deleteTarget: null,
    currentMatch: 0,
    totalMatches: 0,
    activeSearchKeyword: '',
    searchRequestId: 0,
  };

  let debounceTimer = null;

  // ========== 工具函数 ==========
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const formatDate = (str) => {
    if (!str) return '';
    const d = new Date(str);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  };

  const formatSize = (b) => {
    if (!b) return '';
    if (b < 1024) return b + ' B';
    if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB';
    return (b / 1024 / 1024).toFixed(1) + ' MB';
  };

  const debounce = (fn, ms) => {
    return (...args) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => fn(...args), ms);
    };
  };

  const escapeHTML = (str) => {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  };

  // ========== API ==========
  const api = {
    async getDocs() {
      const url = API + '/documents?format=' + state.formatFilter + '&sort=' + state.sortOrder;
      const r = await fetch(url);
      const d = await r.json();
      return d.documents || [];
    },
    async getDoc(id) {
      const r = await fetch(API + '/documents/' + id);
      return r.json();
    },
    async upload(file) {
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch(API + '/documents/upload', { method: 'POST', body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || '上传失败');
      return d;
    },
    async deleteDoc(id) {
      const r = await fetch(API + '/documents/' + id, { method: 'DELETE' });
      return r.json();
    },
    async search(kw) {
      const r = await fetch(API + '/search?q=' + encodeURIComponent(kw));
      return r.json();
    },
  };

  // ========== Toast ==========
  let toastTimer = null;
  function showToast(msg, type) {
    type = type || 'success';
    const cont = $('#toastContainer');
    cont.innerHTML = '<div class="upload-toast ' + type + '">' +
      (type === 'loading' ? '<div class="spinner" style="width:16px;height:16px;border-width:2px;"></div>' : '') +
      '<span>' + escapeHTML(msg) + '</span></div>';
    if (type !== 'loading' && toastTimer) clearTimeout(toastTimer);
    if (type !== 'loading') {
      toastTimer = setTimeout(() => {
        if ($('#toastContainer')) $('#toastContainer').innerHTML = '';
      }, type === 'success' ? 3000 : 5000);
    }
  }

  // ========== 加载文档列表 ==========
  async function loadDocs() {
    state.loading = true;
    render();
    try {
      state.documents = await api.getDocs();
    } catch (e) {
      console.error(e);
      showToast('加载失败，请检查服务器是否运行', 'error');
      state.documents = [];
    }
    state.loading = false;
    render();
  }

  // ========== 上传文件 ==========
  async function handleUpload(file) {
    if (!file) return;
    if (file.size > MAX_FILE_SIZE) {
      showToast('文件超过 50MB 限制（' + formatSize(file.size) + '）', 'error');
      return;
    }
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!['.docx', '.rtf', '.txt'].includes(ext)) {
      showToast('不支持的格式：' + ext + '，仅支持 .docx .rtf .txt', 'error');
      return;
    }
    state.uploading = true;
    showToast('正在上传：' + file.name, 'loading');
    try {
      const result = await api.upload(file);
      showToast('上传成功：' + file.name, 'success');
      await loadDocs();

      render();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      showToast(e.message || '上传失败', 'error');
    } finally {
      state.uploading = false;
      render();
    }
  }

  // ========== 删除文档 ==========
  async function handleDelete(doc) {
    try {
      await api.deleteDoc(doc.id);
      state.documents = state.documents.filter(d => d.id !== doc.id);
      state.expandedIds.delete(doc.id);
      state.deleteTarget = null;
      showToast('已删除：' + doc.title, 'success');
      render();
    } catch (e) {
      showToast('删除失败', 'error');
      state.deleteTarget = null;
      render();
    }
  }

  // ========== 加载文档内容 ==========
  async function loadDocContent(id, container) {
    console.log('loadDocContent called, id:', id);
    try {
      const data = await api.getDoc(id);
      const html = data.html_content || '<p style="color:var(--text-muted)">文档内容为空</p>';
      container.innerHTML = '<div class="doc-body-content">' + html + '</div>';
      console.log('[loadDocContent] activeSearchKeyword:', state.activeSearchKeyword, 'length:', state.activeSearchKeyword?.length);
      if (state.activeSearchKeyword) {
        highlightKeyword(container, state.activeSearchKeyword);
        const marks = container.querySelectorAll('mark.search-highlight');
        state.totalMatches = marks.length;
        state.currentMatch = 0;
        console.log('[loadDocContent] totalMatches:', marks.length, 'keyword:', state.activeSearchKeyword);
        addPositionControls(container, id);
        // 初始定位到第一个匹配项（不论匹配多少处，都自动滚到第一处）
        if (marks.length > 0) {
          marks.forEach(m => m.classList.remove('focused'));
          marks[0].classList.add('focused');
          requestAnimationFrame(() => {
            marks[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
          });
        }
      }
    } catch (e) {
      container.innerHTML = '<p style="color:var(--error)">加载失败</p>';
    }
  }

  // ========== 关键词高亮 ==========
  function highlightKeyword(container, keyword) {
    const kw = keyword || state.activeSearchKeyword;
    if (!kw) return;
    // 先清除已有的高亮（避免重复高亮，让函数变成幂等）
    const existingMarks = container.querySelectorAll('mark.search-highlight');
    existingMarks.forEach(mark => {
      const textNode = document.createTextNode(mark.textContent);
      mark.parentNode.replaceChild(textNode, mark);
    });
    container.normalize();
    const esc = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
   textNodes.forEach(node => {
     const text = node.textContent;
     const regex = new RegExp('(' + esc + ')', 'gi');
     if (!regex.test(text)) return;
     regex.lastIndex = 0;
     const frag = document.createDocumentFragment();
      let last = 0;
      let match;
      while ((match = regex.exec(text)) !== null) {
        if (match.index > last) frag.appendChild(document.createTextNode(text.slice(last, match.index)));
        const mark = document.createElement('mark');
        mark.className = 'search-highlight';
        mark.textContent = match[0];
        frag.appendChild(mark);
        last = match.index + match[0].length;
      }
      if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
      if (frag.childNodes.length > 0) node.parentNode.replaceChild(frag, node);
    });
  }

  // ========== 滚动到文档第一个匹配项 ==========
  // 兼容两种情况：文档正在异步加载 / 文档已经加载过（但高亮可能过时）
  function scrollDocToFirstMatch(docId) {
    let attempts = 0;
    const tick = () => {
      attempts++;
      const wrapper = document.getElementById('body-' + docId);
      if (!wrapper) {
        if (attempts < 40) setTimeout(tick, 100); // 最多等 ~4 秒
        return;
      }
      // 文档还在加载中（loadDocContent 异步 fetch）
      if (wrapper.dataset.loaded !== '1') {
        if (attempts < 40) setTimeout(tick, 100);
        return;
      }
      // 检查或重新应用高亮
      let marks = wrapper.querySelectorAll('mark.search-highlight');
      if (marks.length === 0 && state.activeSearchKeyword) {
        highlightKeyword(wrapper, state.activeSearchKeyword);
        marks = wrapper.querySelectorAll('mark.search-highlight');
        state.totalMatches = marks.length;
        addPositionControls(wrapper, docId);
      }
      if (marks.length === 0) return;
      // 滚动到第一个匹配项
      state.currentMatch = 0;
      marks.forEach(m => m.classList.remove('focused'));
      marks[0].classList.add('focused');
      requestAnimationFrame(() => {
        marks[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    };
    tick();
  }

  // ========== 定位控件 ==========
  function addPositionControls(container, docId) {
    const old = container.parentElement.querySelector('.position-controls');
    if (old) old.remove();
    if (!state.activeSearchKeyword || state.totalMatches <= 0) return;
    const ctrl = document.createElement('div');
    ctrl.className = 'position-controls';
    ctrl.innerHTML = '<button class="position-btn" id="prevMatch">↑ 上一处 (' + Math.max(1, state.currentMatch) + '/' + state.totalMatches + ')</button>' +
      '<button class="position-btn" id="nextMatch">下一处 (' + Math.min(state.totalMatches, state.currentMatch + 1) + '/' + state.totalMatches + ') ↓</button>';
    container.parentElement.appendChild(ctrl);
    ctrl.querySelector('#prevMatch').onclick = () => scrollToMatch(container, -1);
    ctrl.querySelector('#nextMatch').onclick = () => scrollToMatch(container, 1);
  }

  function scrollToMatch(container, dir) {
    const marks = container.querySelectorAll('mark.search-highlight');
    console.log('[scrollToMatch] marks:', marks.length, 'dir:', dir, 'total:', state.totalMatches);
    if (marks.length === 0 || state.totalMatches <= 0) return;
    // 边界处理
    if (dir !== 0 && state.totalMatches === 1) return; // 只有一个匹配时不响应上下翻页
    // 当只有一个匹配时，直接定位到该位置
    if (state.totalMatches === 1 && dir === 0) {
      if (marks[0]) {
        marks[0].classList.add('focused');
        requestAnimationFrame(() => {
          marks[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
      }
      return;
    }
    state.currentMatch = Math.max(0, Math.min(state.totalMatches - 1, state.currentMatch + dir));
    marks.forEach(m => m.classList.remove('focused'));
    if (marks[state.currentMatch]) {
      marks[state.currentMatch].classList.add('focused');
      marks[state.currentMatch].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    const btns = container.parentElement.querySelectorAll('.position-btn');
    if (btns[0]) btns[0].textContent = '↑ 上一处 (' + Math.max(1, state.currentMatch + 1) + '/' + state.totalMatches + ')';
    if (btns[1]) btns[1].textContent = '下一处 (' + Math.min(state.totalMatches, state.currentMatch + 2) + '/' + state.totalMatches + ') ↓';
  }

  // ========== 搜索 ==========
  function doSearch(kw) {
    console.log('[doSearch] kw:', kw, '| reqId will be:', state.searchRequestId + 1);
    if (!kw.trim()) {
      state.searchResults = [];
      state.searchLoading = false;
      renderSearchResults();
      return;
    }
    const reqId = ++state.searchRequestId;
    state.searchLoading = true;
    renderSearchResults();
    api.search(kw).then(data => {
      console.log('[doSearch response] kw:', kw, '| reqId:', reqId, '| currentReqId:', state.searchRequestId);
      if (reqId !== state.searchRequestId) { console.log('[doSearch] ignoring stale response'); return; }
      state.activeSearchKeyword = kw;
      state.searchKeyword = kw;
      state.searchResults = data.results || [];
      state.searchLoading = false;
      state.totalMatches = state.searchResults.reduce((s, r) => s + r.match_count, 0);
      renderSearchResults();
    }).catch(() => {
      if (reqId !== state.searchRequestId) return;
      state.searchResults = [];
      state.searchLoading = false;
      renderSearchResults();
    });
  }

  const debouncedSearch = debounce(doSearch, DEBOUNCE_MS);

  function renderSearchResults() {
    console.log('[renderSearchResults] searchKeyword:', state.searchKeyword, '| results:', state.searchResults.length, '| loading:', state.searchLoading);
    const countEl = $('#searchCount');
    const listEl = $('#searchResults');
    const kw = state.searchKeyword;

    if (!kw || !kw.trim()) {
      countEl.textContent = '';
      listEl.innerHTML = '';
      return;
    }

    if (state.searchLoading) {
      countEl.textContent = '搜索中...';
      listEl.innerHTML = '';
      return;
    }

    const total = state.searchResults.reduce((s, r) => s + r.match_count, 0);
    if (state.searchResults.length === 0) {
      countEl.textContent = '未找到匹配结果';
      listEl.innerHTML = '<div class="search-no-result"><div class="search-no-result-icon">🔍</div><div>未找到相关内容</div><div style="font-size:12px;margin-top:4px;opacity:0.7">请尝试更换关键词，或上传更多文档</div></div>';
      return;
    }

    countEl.textContent = '共找到 ' + total + ' 个匹配（' + state.searchResults.length + ' 个文档）';
    listEl.innerHTML = state.searchResults.map(r => {
      return '<div class="search-result-item" data-id="' + r.id + '">' +
        '<div class="search-result-header">' +
        '<div class="search-result-title"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>' + escapeHTML(r.title) + '<span style="font-size:11px;color:var(--text-muted);margin-left:4px">[' + (r.format || '').toUpperCase() + ']</span></div>' +
        '<span class="search-match-count">共 ' + r.match_count + ' 处</span></div>' +
        (r.context ? '<div class="search-result-snippet">' + r.context + '</div>' : '') +
        '</div>';
    }).join('');

    // 点击结果展开文档
    listEl.querySelectorAll('.search-result-item').forEach(item => {
      item.onclick = () => {
        const id = parseInt(item.dataset.id);
        state.expandedIds.add(id);
        state.activeSearchKeyword = state.searchKeyword;
        state.searchResults = [];
        state.searchOpen = false;
        $('#pageContent').style.paddingTop = '';
        $('#searchPanel').style.display = 'none';
        $('#searchResults').innerHTML = '';
        $('#searchCount').textContent = '';
        render();
        // 滚动到该文档的第一个匹配项（处理文档正在加载或已加载两种情况）
        scrollDocToFirstMatch(id);
      };
    });
  }

  // ========== 展开/收起文档 ==========
  function toggleDoc(id) {
    console.log('toggleDoc called, id:', id);
    if (state.expandedIds.has(id)) {
      state.expandedIds.delete(id);
    } else {
      state.expandedIds.add(id);
    }
    render();
  }

  // ========== 打开/关闭搜索面板 ==========
  function openSearch() {
    state.searchOpen = true;
    const inputVal = ($('#navSearch') && $('#navSearch').value) || ($('#searchInput') && $('#searchInput').value) || '';
    state.searchKeyword = inputVal;
    $('#pageContent').style.paddingTop = '170px';
    $('#searchPanel').style.display = 'block';
    $('#searchInput').value = inputVal;
    $('#navSearch').value = inputVal;
    $('#searchInput').focus();
    if (!inputVal.trim()) {
      $('#searchResults').innerHTML = '';
      $('#searchCount').textContent = '';
    }
  }

  function closeSearch() {
    state.searchKeyword = '';
    state.searchResults = [];
    if ($('#searchInput')) $('#searchInput').value = '';
    if ($('#navSearch')) $('#navSearch').value = '';
    if ($('#searchResults')) $('#searchResults').innerHTML = '';
    if ($('#searchCount')) $('#searchCount').textContent = '';
    state.searchOpen = false;
    $('#pageContent').style.paddingTop = '';
    if ($('#searchPanel')) $('#searchPanel').style.display = 'none';
  }

  // ========== 渲染 ==========
  function render() {
    $('#loadingState').style.display = state.loading ? 'flex' : 'none';
    const hasDocs = state.documents.length > 0;
    $('#docList').style.display = hasDocs ? 'flex' : 'none';
    $('#emptyState').style.display = (!state.loading && !hasDocs) ? 'block' : 'none';

    // 文档列表
    let docHtml = '';
    console.log('render: state.expandedIds:', state.expandedIds);
    console.log('render: typeof expandedIds.values().next().value:', typeof [...state.expandedIds][0]);
    for (const doc of state.documents) {
      console.log('render: checking doc.id:', doc.id, 'typeof:', typeof doc.id);
      const isExpanded = state.expandedIds.has(doc.id);
      console.log('render: state.expandedIds.has(doc.id):', isExpanded);
      console.log('render: state.expandedIds contents:', Array.from(state.expandedIds));
      const expandIcon = isExpanded ? '180deg' : '0deg';
      const maxH = isExpanded ? '2000px' : '0';
      const bodyHtml = isExpanded ? '<div class="doc-body-wrapper" id="body-' + doc.id + '"><div class="loading-state"><div class="spinner"></div>加载文档内容...</div></div>' : '';
      console.log('render: bodyHtml for id', doc.id, ':', bodyHtml ? 'HAS BODY' : 'NO BODY');
      docHtml += '<div class="doc-card' + (isExpanded ? ' expanded' : '') + '" id="doc-' + doc.id + '">' +
        '<div class="doc-card-header" data-id="' + doc.id + '">' +
        '<div class="doc-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>' +
        '<div class="doc-info"><div class="doc-title" title="' + escapeHTML(doc.title) + '">' + escapeHTML(doc.title) + '</div>' +
        '<div class="doc-meta"><span class="doc-time">' + formatDate(doc.upload_time) + '</span>' +
        '<span class="doc-format-tag">' + (doc.format || '').toUpperCase() + '</span>' +
        (doc.file_size ? '<span class="doc-time">' + formatSize(doc.file_size) + '</span>' : '') +
        '</div></div>' +
        '<div class="doc-actions">' +
        '<button class="doc-delete" data-id="' + doc.id + '" title="删除"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></button>' +
        '<button class="doc-expand-btn" aria-label="展开/收起"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="transition:transform 0.3s;transform:rotate(' + expandIcon + 'deg)"><polyline points="6 9 12 15 18 9"/></svg></button>' +
        '</div></div>' +
        '<div class="doc-card-body" style="max-height:' + maxH + '">' +
        '<div class="doc-card-body-inner"><div class="doc-toolbar"><button class="btn-print" data-id="' + doc.id + '"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>打印</button></div>' +
        bodyHtml +
        '</div></div></div>';
    }
    console.log('render: docHtml total length:', docHtml.length);
    console.log('render: contains body-8:', docHtml.includes('body-8'));
    $('#docList').innerHTML = docHtml;
    console.log('render: innerHTML set, checking actual DOM...');
    const actualBody = document.getElementById('body-8');
    console.log('render: actual body-8 in DOM:', !!actualBody);

    // 绑定事件
    $$('.doc-card-header').forEach(el => {
      el.onclick = (e) => {
        if (e.target.closest('.doc-delete')) return;
        toggleDoc(parseInt(el.dataset.id));
      };
    });

    $$('.doc-delete').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const id = parseInt(btn.dataset.id);
        const doc = state.documents.find(d => d.id === id);
        if (doc) {
          state.deleteTarget = doc;
          $('#deleteMsg').innerHTML = '确定要删除「<strong>' + escapeHTML(doc.title) + '</strong>」吗？此操作无法撤销。';
          $('#deleteDialog').style.display = 'flex';
        }
      };
    });

    $$('.btn-print').forEach(btn => {
      btn.onclick = async () => {
        const id = parseInt(btn.dataset.id);
        try {
          const data = await api.getDoc(id);
          const w = window.open('', '_blank');
          if (w) {
            w.document.write('<html><head><title>' + escapeHTML(data.title) + '</title><style>body{font-family:sans-serif;padding:40px;line-height:1.7;white-space:pre-wrap}mark{background:#FFE066}table{border-collapse:collapse;width:100%}td,th{border:1px solid #000;padding:6px 10px}</style></head><body>' + (data.html_content || '') + '</body></html>');
            w.document.close();
            w.print();
          }
        } catch (e) { alert('打印失败'); }
      };
    });

    // 加载展开的文档内容
    console.log('Loading expanded docs, expandedIds:', Array.from(state.expandedIds));
    state.expandedIds.forEach(id => {
      const wrapper = document.getElementById('body-' + id);
      console.log('getElementById body-' + id + ':', wrapper);
      if (wrapper && !wrapper.dataset.loaded) {
        wrapper.dataset.loaded = '1';
        loadDocContent(id, wrapper);
      }
    });

    // 筛选高亮
    $$('.filter-tab').forEach(tab => {
      tab.classList.toggle('active', tab.dataset.filter === state.formatFilter);
    });
  }

  // ========== 事件绑定 ==========
  function bindEvents() {
    // 阻止双击缩放
    document.addEventListener("dblclick", (e) => e.preventDefault());

    // 上传区点击
    $('#uploadZone').onclick = () => { if (!state.uploading) $('#fileInput').click(); };

    // 拖拽上传
    $('#uploadZone').ondragover = (e) => { e.preventDefault(); $('#uploadZone').classList.add('drag-over'); };
    $('#uploadZone').ondragleave = () => $('#uploadZone').classList.remove('drag-over');
    $('#uploadZone').ondrop = (e) => {
      e.preventDefault();
      $('#uploadZone').classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) handleUpload(file);
    };

    // 文件选择
    $('#fileInput').onchange = (e) => {
      const file = e.target.files[0];
      if (file) handleUpload(file);
      e.target.value = '';
    };

    // 导航栏上传按钮
    $('#navUploadBtn').onclick = () => $('#fileInput').click();

    // Mobile FAB
    $('#fabBtn').onclick = () => $('#fileInput').click();

    // 筛选
    $$('.filter-tab').forEach(tab => {
      tab.onclick = () => {
        state.formatFilter = tab.dataset.filter;
        loadDocs();
      };
    });
    // 搜索框
    $('#navSearch').onfocus = openSearch;
    $('#navSearch').oninput = (e) => {
      const kw = e.target.value;
      state.searchKeyword = kw;
      if (!state.searchOpen) {
        state.searchOpen = true;
        $('#pageContent').style.paddingTop = '170px';
        $('#searchPanel').style.display = 'block';
        $('#searchInput').value = kw;
        $('#searchInput').focus();
      } else {
        $('#searchInput').value = kw;
      }
      if (kw.trim()) {
        doSearch(kw);
      } else {
        state.activeSearchKeyword = '';
        state.searchResults = [];
        $('#searchResults').innerHTML = '';
        $('#searchCount').textContent = '';
      }
    };

    $('#searchInput').oninput = (e) => {
      const kw = e.target.value;
      state.searchKeyword = kw;
      $('#navSearch').value = kw;
      if (kw.trim()) {
        doSearch(kw);
      } else {
        state.activeSearchKeyword = '';
        state.searchResults = [];
        $('#searchResults').innerHTML = '';
        $('#searchCount').textContent = '';
      }
    };

    $('#searchInput').onkeydown = (e) => { if (e.key === 'Escape') closeSearch(); };
    $('#closeSearchBtn').onclick = closeSearch;

    // 删除确认
    $('#cancelDelete').onclick = () => {
      state.deleteTarget = null;
      $('#deleteDialog').style.display = 'none';
    };
    $('#confirmDelete').onclick = () => {
      if (state.deleteTarget) handleDelete(state.deleteTarget);
      $('#deleteDialog').style.display = 'none';
    };
    $('#deleteDialog').onclick = (e) => {
      if (e.target === $('#deleteDialog')) {
        state.deleteTarget = null;
        $('#deleteDialog').style.display = 'none';
      }
    };

    // 键盘快捷键
    document.onkeydown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        openSearch();
      }
      if (e.key === 'Escape') {
        if (state.searchOpen) closeSearch();
        if (state.deleteTarget) {
          state.deleteTarget = null;
          $('#deleteDialog').style.display = 'none';
        }
      }
    };
  }

  // ========== 启动 ==========
  document.addEventListener('DOMContentLoaded', () => {
    initPassword();
    loadDocs();
    bindEvents();
  });

})();
