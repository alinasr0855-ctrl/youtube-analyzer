/* ── State ────────────────────────────────────────────────────────────────── */
const state = {
  currentSession: null,
  sessions: [],
  chatHistory: [],
  compareA: null,
  compareB: null,
  activeTab: 'videos',
};

const API = (path) => `/api${path}`;

/* ── Utilities ────────────────────────────────────────────────────────────── */
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  $('#toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function loader(text = 'جارٍ التحميل...') {
  return `<div class="loader"><div class="spinner"></div><span>${text}</span></div>`;
}

async function api(path, opts = {}) {
  const res = await fetch(API(path), {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'خطأ غير معروف' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function formatTime(mins) {
  if (!mins) return '—';
  if (mins < 60) return `${mins} دقيقة`;
  const h = Math.floor(mins / 60), m = mins % 60;
  return m ? `${h}س ${m}د` : `${h} ساعة`;
}

/* ── Render Sidebar Sessions ─────────────────────────────────────────────── */
async function loadSidebar() {
  try {
    const { sessions } = await api('/sessions');
    state.sessions = sessions;
    const list = $('#sidebar-sessions');
    if (!sessions.length) {
      list.innerHTML = '<div class="no-sessions">لا توجد جلسات بعد</div>';
      return;
    }
    list.innerHTML = sessions.map(s => `
      <button class="session-card ${state.currentSession?.session_id === s.session_id ? 'active' : ''}"
        onclick="openSession('${s.session_id}')">
        <div class="session-name">${s.playlist_name}</div>
        <div class="session-meta">
          <span class="session-dot ${s.status === 'completed' ? 'done' : ''}"></span>
          ${s.analyzed_count}/${s.total_videos} فيديو — ${s.channel_name}
        </div>
      </button>
    `).join('');
  } catch (e) {
    console.error('Sidebar error:', e);
  }
}

/* ── Search ──────────────────────────────────────────────────────────────── */
async function doSearch() {
  const q = $('#search-input').value.trim();
  if (!q) return;
  const btn = $('#search-btn');
  btn.disabled = true;
  btn.textContent = '…جارٍ البحث';
  const results = $('#search-results');
  results.innerHTML = loader('جارٍ البحث في YouTube...');

  try {
    const data = await api('/search', {
      method: 'POST',
      body: JSON.stringify({ query: q }),
    });

    if (data.type === 'playlist') {
      renderSinglePlaylist(data.playlist);
    } else {
      renderChannels(data.channels);
    }
  } catch (e) {
    results.innerHTML = `<div class="empty-state"><div class="es-icon">⚠️</div><h3>خطأ في البحث</h3><p>${e.message}</p></div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'بحث';
  }
}

function renderSinglePlaylist(pl) {
  const results = $('#search-results');
  results.innerHTML = `
    <div class="section-title">✅ تم العثور على الـ Playlist</div>
    <div class="playlist-grid">
      ${playlistCardHTML(pl, pl.channel_id, pl.channel_name)}
    </div>`;
}

function renderChannels(channels) {
  const results = $('#search-results');
  results.innerHTML = `
    <div class="section-title">📺 القنوات المطابقة (${channels.length})</div>
    <div class="results-grid">
      ${channels.map(ch => `
        <div class="channel-card" onclick="loadPlaylists('${ch.channel_id}', '${escHtml(ch.title)}')">
          ${ch.thumbnail
            ? `<img src="${ch.thumbnail}" alt="">`
            : `<div class="fallback-avatar">📺</div>`}
          <div class="channel-info">
            <div class="name">${ch.title}</div>
            <div class="desc">${ch.description || 'لا يوجد وصف'}</div>
          </div>
        </div>`).join('')}
    </div>`;
}

async function loadPlaylists(channelId, channelName) {
  const results = $('#search-results');
  results.innerHTML = loader('جارٍ تحميل قوائم التشغيل...');
  try {
    const { playlists } = await api(`/channels/${channelId}/playlists`);
    if (!playlists.length) {
      results.innerHTML = '<div class="empty-state"><div class="es-icon">📭</div><h3>لا توجد قوائم تشغيل</h3></div>';
      return;
    }
    results.innerHTML = `
      <button class="back-btn" onclick="$('#search-results').innerHTML=''">← رجوع</button>
      <div class="section-title">📋 قوائم تشغيل: ${channelName}</div>
      <div class="playlist-grid">
        ${playlists.map(pl => playlistCardHTML(pl, channelId, channelName)).join('')}
      </div>`;
  } catch (e) {
    results.innerHTML = `<div class="empty-state"><div class="es-icon">⚠️</div><h3>${e.message}</h3></div>`;
  }
}

function playlistCardHTML(pl, channelId, channelName) {
  const data = JSON.stringify({ playlist_id: pl.playlist_id, channel_id: channelId, channel_name: channelName, playlist_name: pl.title }).replace(/'/g, '&apos;');
  return `
    <div class="playlist-card" onclick='startSession(${data})'>
      ${pl.thumbnail
        ? `<img class="playlist-thumb" src="${pl.thumbnail}" alt="">`
        : `<div class="playlist-thumb">🎬</div>`}
      <div class="playlist-body">
        <div class="playlist-title">${pl.title}</div>
        <span class="playlist-count">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h16v2H4z"/></svg>
          ${pl.video_count} فيديو
        </span>
      </div>
    </div>`;
}

/* ── Start Session ───────────────────────────────────────────────────────── */
async function startSession({ playlist_id, channel_id, channel_name, playlist_name }) {
  toast('جارٍ إنشاء الجلسة...', 'info');
  try {
    const data = await api('/sessions/start', {
      method: 'POST',
      body: JSON.stringify({ playlist_id, channel_id, channel_name, playlist_name }),
    });
    toast('تم إنشاء الجلسة بنجاح ✅', 'success');
    await loadSidebar();
    await openSession(data.session_id);
    showView('session');
  } catch (e) {
    toast(`فشل إنشاء الجلسة: ${e.message}`, 'error');
  }
}

/* ── Open Session ────────────────────────────────────────────────────────── */
async function openSession(sessionId) {
  showView('session');
  const main = $('#session-view');
  main.innerHTML = loader('جارٍ تحميل الجلسة...');
  try {
    const { session, videos } = await api(`/sessions/${sessionId}/results`);
    state.currentSession = session;
    state.chatHistory = [];
    renderSession(session, videos);
    await loadSidebar(); // refresh active indicator
  } catch (e) {
    main.innerHTML = `<div class="empty-state"><h3>خطأ: ${e.message}</h3></div>`;
  }
}

function renderSession(session, videos) {
  const analyzed = videos.filter(v => v.analyzed);
  const total = session.total_videos;
  const pct = Math.round((session.analyzed_count / total) * 100);

  const levelCounts = {};
  analyzed.forEach(v => { if (v.level) levelCounts[v.level] = (levelCounts[v.level] || 0) + 1; });
  const totalMins = analyzed.reduce((s, v) => s + (v.estimated_minutes || 0), 0);

  $('#session-view').innerHTML = `
    <button class="back-btn" onclick="showView('search')">← رجوع للبحث</button>

    <div class="session-header">
      <div class="session-title-group">
        <h2>${session.playlist_name}</h2>
        <div class="session-breadcrumb">📺 ${session.channel_name} • ${session.playlist_id}</div>
        <div class="progress-bar-wrap" style="margin-top:10px">
          <div class="progress-bar-fill" style="width:${pct}%"></div>
        </div>
        <div class="progress-text">${session.analyzed_count} من ${total} فيديو محلل (${pct}%)</div>
      </div>
      <div class="action-bar" style="margin-bottom:0">
        ${session.status !== 'completed' ? `<button class="btn btn-primary" onclick="analyzeNext()">⚡ تحليل الدفعة التالية</button>` : ''}
        <button class="btn btn-ghost btn-danger" onclick="deleteCurrentSession()">🗑 حذف</button>
      </div>
    </div>

    <div class="stats-row">
      <div class="stat-card"><div class="stat-val red">${total}</div><div class="stat-label">إجمالي الفيديوهات</div></div>
      <div class="stat-card"><div class="stat-val teal">${session.analyzed_count}</div><div class="stat-label">تم تحليله</div></div>
      <div class="stat-card"><div class="stat-val gold">${formatTime(totalMins)}</div><div class="stat-label">وقت المشاهدة</div></div>
      <div class="stat-card"><div class="stat-val">${Object.keys(levelCounts).join(' • ') || '—'}</div><div class="stat-label">المستويات</div></div>
    </div>

    <div class="tabs">
      <button class="tab-btn active" data-tab="videos" onclick="switchTab('videos', this)">
        🎬 الفيديوهات <span class="tab-count">${total}</span>
      </button>
      <button class="tab-btn" data-tab="summary"   onclick="switchTab('summary', this)">📋 الملخص</button>
      <button class="tab-btn" data-tab="path"      onclick="switchTab('path', this)">🗺️ مسار التعلم</button>
      <button class="tab-btn" data-tab="chat"      onclick="switchTab('chat', this)">💬 الدردشة</button>
      <button class="tab-btn" data-tab="compare"   onclick="switchTab('compare', this)">⚖️ المقارنة</button>
    </div>

    <div id="tab-content">
      ${renderVideosTab(videos)}
    </div>

    <div class="modal-overlay" id="video-modal" onclick="closeModal(event)">
      <div class="modal-box" onclick="event.stopPropagation()">
        <button class="modal-close" onclick="closeModal()">✕</button>
        <div id="modal-inner"></div>
      </div>
    </div>
  `;
}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
function switchTab(tabName, btn) {
  $$('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  state.activeTab = tabName;

  const content = $('#tab-content');
  if (tabName === 'videos') {
    api(`/sessions/${state.currentSession.session_id}/results`).then(({ videos }) => {
      content.innerHTML = renderVideosTab(videos);
    });
  } else if (tabName === 'summary') {
    renderSummaryTab(content);
  } else if (tabName === 'path') {
    renderPathTab(content);
  } else if (tabName === 'chat') {
    content.innerHTML = renderChatTab();
  } else if (tabName === 'compare') {
    content.innerHTML = renderCompareTab();
  }
}

/* ── Videos Tab ──────────────────────────────────────────────────────────── */
function renderVideosTab(videos) {
  if (!videos.length) return '<div class="empty-state"><div class="es-icon">📭</div><h3>لا توجد فيديوهات</h3></div>';
  return `
    <div class="videos-list">
      ${videos.map(v => `
        <div class="video-row ${v.analyzed ? 'analyzed' : ''}" id="vrow-${v.video_id}">
          <div class="video-num">${v.position + 1}</div>
          <img class="video-thumb" src="${v.thumbnail || ''}" alt="" onerror="this.style.display='none'">
          <div class="video-info">
            <div class="v-title">${v.title}</div>
            ${v.analyzed ? `
              <div class="video-badges">
                ${v.level ? `<span class="badge badge-level-${v.level}">${v.level}</span>` : ''}
                ${v.type  ? `<span class="badge badge-type">${v.type}</span>` : ''}
                ${v.estimated_minutes ? `<span class="badge badge-time">⏱ ${formatTime(v.estimated_minutes)}</span>` : ''}
                ${(v.topics || []).slice(0, 3).map(t => `<span class="badge badge-type">${t}</span>`).join('')}
              </div>` : '<div class="video-badges"><span class="badge badge-type" style="opacity:.5">لم يُحلل بعد</span></div>'}
          </div>
          ${v.analyzed
            ? `<button class="btn-analyze-video" onclick="showExplanation('${v.video_id}')">عرض الشرح</button>`
            : `<button class="btn-analyze-video" onclick="analyzeSingle('${v.video_id}')">تحليل</button>`}
        </div>`).join('')}
    </div>`;
}

/* ── Summary Tab ─────────────────────────────────────────────────────────── */
async function renderSummaryTab(container) {
  container.innerHTML = loader('جارٍ توليد الملخص...');
  try {
    const { summary } = await api(`/sessions/${state.currentSession.session_id}/summary`, { method: 'POST' });
    container.innerHTML = `
      <div class="section-title">📋 الملخص التنفيذي</div>
      <div class="ai-content">${formatMarkdown(summary)}</div>`;
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><h3>⚠️ ${e.message}</h3></div>`;
  }
}

/* ── Learning Path Tab ───────────────────────────────────────────────────── */
async function renderPathTab(container) {
  container.innerHTML = loader('جارٍ توليد مسار التعلم...');
  try {
    const { learning_path } = await api(`/sessions/${state.currentSession.session_id}/learning-path`, { method: 'POST' });
    const { sessions, videos } = await api(`/sessions/${state.currentSession.session_id}/results`);
    const videoMap = {};
    videos.forEach(v => { videoMap[v.video_id] = v; });

    const phases = learning_path.phases || [];
    if (!phases.length) {
      container.innerHTML = '<div class="empty-state"><h3>لا توجد مراحل بعد</h3><p>حلل المزيد من الفيديوهات أولاً</p></div>';
      return;
    }
    container.innerHTML = `
      <div class="section-title">🗺️ مسار التعلم الذكي</div>
      <div class="phases-list">
        ${phases.map((ph, i) => `
          <div class="phase-card">
            <div class="phase-header">
              <div class="phase-num">${i + 1}</div>
              <div>
                <div class="phase-title">${ph.title}</div>
                <div style="font-size:11px;color:var(--text-3);font-family:var(--font-en)">${(ph.video_ids || []).length} فيديو</div>
              </div>
            </div>
            <div class="phase-body">
              <div class="phase-desc">${ph.description || ''}</div>
              <div class="phase-videos">
                ${(ph.video_ids || []).map(vid => {
                  const v = videoMap[vid];
                  return v ? `<div class="phase-video-item">${v.title}</div>` : '';
                }).join('')}
              </div>
            </div>
          </div>`).join('')}
      </div>`;
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><h3>⚠️ ${e.message}</h3></div>`;
  }
}

/* ── Chat Tab ────────────────────────────────────────────────────────────── */
function renderChatTab() {
  return `
    <div class="card">
      <div class="card-header">
        <div class="card-icon teal">💬</div>
        <div><div class="card-title">دردشة مع الـ Playlist</div>
        <div class="card-sub">اسأل أي سؤال عن محتوى الـ Playlist</div></div>
      </div>
      <div class="chat-container" id="chat-messages">
        <div class="chat-msg ai">
          <div class="chat-avatar">🤖</div>
          <div class="chat-bubble">مرحباً! أنا هنا للإجابة على أسئلتك حول هذه الـ Playlist. اسألني أي شيء!</div>
        </div>
      </div>
      <div class="chat-input-row">
        <input class="chat-input" id="chat-input" placeholder="اكتب سؤالك هنا..." onkeydown="if(event.key==='Enter')sendChat()">
        <button class="btn-chat-send" onclick="sendChat()">إرسال ↑</button>
      </div>
    </div>`;
}

async function sendChat() {
  const input = $('#chat-input');
  const q = input.value.trim();
  if (!q) return;
  input.value = '';

  const messages = $('#chat-messages');
  messages.innerHTML += `
    <div class="chat-msg user">
      <div class="chat-avatar">👤</div>
      <div class="chat-bubble">${escHtml(q)}</div>
    </div>
    <div class="chat-msg ai" id="typing-msg">
      <div class="chat-avatar">🤖</div>
      <div class="chat-bubble">${loader('جارٍ التفكير...')}</div>
    </div>`;
  messages.scrollTop = messages.scrollHeight;

  state.chatHistory.push({ role: 'user', content: q });

  try {
    const data = await api(`/sessions/${state.currentSession.session_id}/chat`, {
      method: 'POST',
      body: JSON.stringify({ question: q, history: state.chatHistory }),
    });
    const typingEl = $('#typing-msg');
    if (typingEl) {
      typingEl.querySelector('.chat-bubble').innerHTML = `
        ${escHtml(data.answer)}
        ${data.referenced_videos?.length ? `
          <div class="chat-ref-videos">
            ${data.referenced_videos.map(v => `<span class="ref-chip">📹 ${v.title}</span>`).join('')}
          </div>` : ''}`;
      typingEl.removeAttribute('id');
    }
    state.chatHistory.push({ role: 'assistant', content: data.answer });
  } catch (e) {
    const el = $('#typing-msg');
    if (el) el.querySelector('.chat-bubble').textContent = `❌ ${e.message}`;
  }
  messages.scrollTop = messages.scrollHeight;
}

/* ── Compare Tab ─────────────────────────────────────────────────────────── */
function renderCompareTab() {
  const sessions = state.sessions;
  const opts = sessions.map(s => `<option value="${s.session_id}">${s.playlist_name}</option>`).join('');
  return `
    <div class="card">
      <div class="card-header">
        <div class="card-icon gold">⚖️</div>
        <div><div class="card-title">مقارنة الـ Playlists</div>
        <div class="card-sub">قارن بين جلستين محللتين</div></div>
      </div>
      <div class="compare-grid" style="margin-bottom:16px">
        <div>
          <div class="card-sub" style="margin-bottom:6px">الـ Playlist الأولى (A)</div>
          <select id="cmp-a" class="chat-input" style="width:100%" onchange="state.compareA=this.value">
            <option value="">-- اختر --</option>${opts}
          </select>
        </div>
        <div>
          <div class="card-sub" style="margin-bottom:6px">الـ Playlist الثانية (B)</div>
          <select id="cmp-b" class="chat-input" style="width:100%" onchange="state.compareB=this.value">
            <option value="">-- اختر --</option>${opts}
          </select>
        </div>
      </div>
      <button class="btn btn-primary" onclick="runCompare()">⚖️ قارن الآن</button>
      <div id="compare-result" style="margin-top:20px"></div>
    </div>`;
}

async function runCompare() {
  const a = state.compareA || $('#cmp-a')?.value;
  const b = state.compareB || $('#cmp-b')?.value;
  if (!a || !b || a === b) {
    toast('اختر جلستين مختلفتين', 'error');
    return;
  }
  const result = $('#compare-result');
  result.innerHTML = loader('جارٍ المقارنة...');
  try {
    const data = await api('/compare', {
      method: 'POST',
      body: JSON.stringify({ session_id_a: a, session_id_b: b }),
    });
    result.innerHTML = `
      <table class="compare-table">
        <thead>
          <tr>
            <th>المعيار</th>
            <th>${data.playlist_a_name || 'A'}</th>
            <th>${data.playlist_b_name || 'B'}</th>
          </tr>
        </thead>
        <tbody>
          ${(data.criteria || []).map(c => `
            <tr>
              <td><strong>${c.name}</strong></td>
              <td>${c.playlist_a}</td>
              <td>${c.playlist_b}</td>
            </tr>`).join('')}
        </tbody>
      </table>
      <div class="ai-content" style="margin-top:14px">
        <strong>🏆 الفائز: ${data.winner}</strong>\n\n${data.recommendation}
      </div>`;
  } catch (e) {
    result.innerHTML = `<div class="empty-state"><h3>⚠️ ${e.message}</h3></div>`;
  }
}

/* ── Analyze Actions ─────────────────────────────────────────────────────── */
async function analyzeNext() {
  const btn = $('.btn-primary');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ جارٍ التحليل...'; }
  try {
    const data = await api(`/sessions/${state.currentSession.session_id}/analyze-next`, { method: 'POST' });
    if (data.is_complete) toast('🎉 تم تحليل جميع الفيديوهات!', 'success');
    else toast(`✅ تم تحليل دفعة جديدة (${data.analyzed_count}/${data.total_videos})`, 'success');
    await openSession(state.currentSession.session_id);
  } catch (e) {
    toast(`❌ ${e.message}`, 'error');
    if (btn) { btn.disabled = false; btn.textContent = '⚡ تحليل الدفعة التالية'; }
  }
}

async function analyzeSingle(videoId) {
  const btn = $(`#vrow-${videoId} .btn-analyze-video`);
  if (btn) { btn.disabled = true; btn.textContent = '⏳...'; }
  try {
    await api(`/sessions/${state.currentSession.session_id}/analyze-video`, {
      method: 'POST',
      body: JSON.stringify({ video_id: videoId }),
    });
    toast('✅ تم تحليل الفيديو', 'success');
    await openSession(state.currentSession.session_id);
  } catch (e) {
    toast(`❌ ${e.message}`, 'error');
  }
}

/* ── Explanation Modal ───────────────────────────────────────────────────── */
async function showExplanation(videoId) {
  const { videos } = await api(`/sessions/${state.currentSession.session_id}/results`);
  const v = videos.find(x => x.video_id === videoId);
  if (!v) return;
  $('#modal-inner').innerHTML = `
    <div class="modal-title">${v.title}</div>
    <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      ${v.level ? `<span class="badge badge-level-${v.level}">${v.level}</span>` : ''}
      ${v.type  ? `<span class="badge badge-type">${v.type}</span>` : ''}
      ${v.estimated_minutes ? `<span class="badge badge-time">⏱ ${formatTime(v.estimated_minutes)}</span>` : ''}
    </div>
    <div class="modal-body">${formatMarkdown(v.explanation || 'لا يوجد شرح متاح')}</div>`;
  $('#video-modal').classList.add('open');
}

function closeModal(e) {
  if (!e || e.target === $('#video-modal')) {
    $('#video-modal')?.classList.remove('open');
  }
}

/* ── Delete Session ──────────────────────────────────────────────────────── */
async function deleteCurrentSession() {
  if (!confirm('هل أنت متأكد من حذف هذه الجلسة؟')) return;
  try {
    await api(`/sessions/${state.currentSession.session_id}`, { method: 'DELETE' });
    toast('تم حذف الجلسة', 'success');
    state.currentSession = null;
    showView('search');
    await loadSidebar();
  } catch (e) {
    toast(`❌ ${e.message}`, 'error');
  }
}

/* ── Views ───────────────────────────────────────────────────────────────── */
function showView(view) {
  $('#search-section').style.display = view === 'search' ? 'block' : 'none';
  $('#session-view').style.display   = view === 'session' ? 'block' : 'none';
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatMarkdown(text) {
  if (!text) return '';
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^(#{1,3})\s+(.+)$/gm, (_, h, t) => `<strong style="font-size:${16 - h.length}px;color:var(--text)">${t}</strong>`)
    .replace(/\n/g, '<br>');
}

/* ── Init ────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  showView('search');
  loadSidebar();
  $('#search-input').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
});
