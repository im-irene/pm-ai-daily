'use strict';

let allItems = [];
let currentCategory = 'all';
let currentType     = 'all';
let currentDate     = 'all';
let customFrom      = null;   // Date | null
let customTo        = null;   // Date | null

// ── Data ──────────────────────────────────────────────────────────────────

async function loadData() {
  try {
    const res = await fetch('data/news.json?t=' + Date.now());
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    allItems = data.items || [];

    if (data.updated_at) {
      const d = new Date(data.updated_at);
      document.getElementById('updated-at').textContent =
        '更新：' + d.toLocaleString('zh-TW', {
          month: 'short', day: 'numeric',
          hour: '2-digit', minute: '2-digit'
        });
    }

    updateCounts();
    render();
    document.getElementById('loading').classList.add('hidden');
    document.getElementById('news-list').classList.remove('hidden');
  } catch (e) {
    document.getElementById('loading').textContent = '資料載入失敗，請確認 data/news.json 是否存在。';
  }
}

// ── Filter ────────────────────────────────────────────────────────────────

function dayBounds() {
  const now   = new Date();
  const today = new Date(now); today.setHours(0, 0, 0, 0);
  const yest  = new Date(today.getTime() - 864e5);
  return { today, yest };
}

function applyDateFilter(items, range) {
  if (customFrom || customTo) {
    return items.filter(i => {
      const d = new Date(i.published_at);
      if (customFrom && d < customFrom) return false;
      if (customTo) {
        const toEnd = new Date(customTo); toEnd.setHours(23, 59, 59, 999);
        if (d > toEnd) return false;
      }
      return true;
    });
  }
  if (range === 'all') return items;
  const { today, yest } = dayBounds();
  return items.filter(i => {
    const d = new Date(i.published_at);
    if (range === 'today')     return d >= today;
    if (range === 'yesterday') return d >= yest && d < today;
    if (range === 'earlier')   return d < yest;
    return true;
  });
}

function filterItems() {
  let items = allItems;
  if (currentCategory !== 'all') items = items.filter(i => i.category === currentCategory);
  if (currentType !== 'all')     items = items.filter(i => i.content_type === currentType);
  return applyDateFilter(items, currentDate);
}

function updateCounts() {
  // Category tabs: filtered by type + date (not cat)
  document.querySelectorAll('#cat-tabs .tab').forEach(btn => {
    const cat = btn.dataset.cat;
    let base = allItems;
    if (currentType !== 'all') base = base.filter(i => i.content_type === currentType);
    base = applyDateFilter(base, currentDate);
    btn.querySelector('.count').textContent =
      cat === 'all' ? base.length : base.filter(i => i.category === cat).length;
  });

  // Type tabs: filtered by category + date (not type)
  document.querySelectorAll('#type-tabs .tab').forEach(btn => {
    const type = btn.dataset.type;
    let base = allItems;
    if (currentCategory !== 'all') base = base.filter(i => i.category === currentCategory);
    base = applyDateFilter(base, currentDate);
    btn.querySelector('.count').textContent =
      type === 'all' ? base.length : base.filter(i => i.content_type === type).length;
  });

  // Date tabs: filtered by category + type (not date, not custom range)
  document.querySelectorAll('#date-tabs .tab').forEach(btn => {
    const range = btn.dataset.date;
    let base = allItems;
    if (currentCategory !== 'all') base = base.filter(i => i.category === currentCategory);
    if (currentType !== 'all')     base = base.filter(i => i.content_type === currentType);
    btn.querySelector('.count').textContent = applyDateFilter(base, range).length;
  });
}

// ── Rendering: Left panel ─────────────────────────────────────────────────

function render() {
  const items = filterItems();
  const list  = document.getElementById('news-list');
  const empty = document.getElementById('empty-state');

  if (items.length === 0) {
    list.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  const groups = new Map();
  for (const item of items) {
    const key = dateGroup(item.published_at);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }

  for (const grpItems of groups.values()) {
    grpItems.sort((a, b) => {
      const diff = (isChineseSource(a) ? 0 : 1) - (isChineseSource(b) ? 0 : 1);
      return diff !== 0 ? diff : new Date(b.published_at) - new Date(a.published_at);
    });
  }

  list.innerHTML = Array.from(groups.entries())
    .map(([label, grpItems]) => `
      <div class="date-group">
        <div class="date-label">${label}</div>
        ${grpItems.map(card).join('')}
      </div>`)
    .join('');
}

function card(item) {
  const mainTitle = item.title_zh || item.title;
  const stats = [];
  if (item.score > 0)    stats.push(`<span>&#9650; ${fmt(item.score)}</span>`);
  if (item.comments > 0) stats.push(`<span># ${fmt(item.comments)}</span>`);

  return `<article class="news-card cat-${item.category || 'other'}" data-id="${esc(item.id)}" onclick="openPanel('${item.id.replace(/'/g, "\\'")}')">
    <div class="card-cat-row">
      ${badge(item)}
    </div>
    ${item.content_type ? `<div class="card-type-row"><span class="badge badge-type">${esc(item.content_type)}</span></div>` : ''}
    <div class="card-meta">
      <span class="src-type">${srcTypeLabel(item.source_type)}</span>
      <span class="src-name">${esc(item.source)}</span>
      <span class="card-time">${relTime(item.published_at)}</span>
    </div>
    <div class="card-title">${esc(mainTitle)}</div>
    ${stats.length ? `<div class="card-stats">${stats.join('')}</div>` : ''}
  </article>`;
}

// ── Detail Panel ──────────────────────────────────────────────────────────

function openPanel(id) {
  const item = allItems.find(i => i.id === id);
  if (!item) return;

  document.querySelectorAll('.news-card').forEach(c => c.classList.remove('selected'));
  const el = document.querySelector(`.news-card[data-id="${CSS.escape(id)}"]`);
  if (el) el.classList.add('selected');

  const placeholder = document.getElementById('detail-placeholder');
  const content     = document.getElementById('detail-content');
  placeholder.classList.add('hidden');
  content.classList.remove('hidden');
  content.innerHTML = renderDetail(item);
  content.scrollTop = 0;

  document.getElementById('detail-panel').classList.add('open');
}

function closePanel() {
  document.getElementById('detail-panel').classList.remove('open');
  document.querySelectorAll('.news-card').forEach(c => c.classList.remove('selected'));
  document.getElementById('detail-placeholder').classList.remove('hidden');
  document.getElementById('detail-content').classList.add('hidden');
}

function renderDetail(item) {
  const mainTitle   = item.title_zh || item.title;
  const subTitle    = item.title_zh && item.title_zh !== item.title ? item.title : '';
  const summaryText = item.summary_zh || item.summary || '';
  const bodyText    = item.body_text || '';

  const stats = [];
  if (item.score > 0)    stats.push(`&#9650; ${fmt(item.score)}`);
  if (item.comments > 0) stats.push(`# ${fmt(item.comments)}`);

  return `
    <div class="detail-header">
      <button class="back-btn" onclick="closePanel()">&#8592; 返回</button>
      <a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer" class="btn-open-sm">開啟原文 &#8599;</a>
    </div>
    <div class="detail-badges">
      ${badge(item)}
      ${item.content_type ? `<span class="badge badge-type">${esc(item.content_type)}</span>` : ''}
    </div>
    <div class="detail-meta">
      <span class="src-type">${srcTypeLabel(item.source_type)}</span>
      <span>${esc(item.source)}</span>
      <span>·</span>
      <span>${relTime(item.published_at)}</span>
      ${stats.length ? `<span>·</span><span>${stats.join('&nbsp;&nbsp;')}</span>` : ''}
    </div>
    <h2 class="detail-title">${esc(mainTitle)}</h2>
    ${subTitle ? `<div class="detail-title-en">${esc(subTitle)}</div>` : ''}
    <div class="detail-divider"></div>
    <div class="detail-summary-label">Gemini 閱讀總結</div>
    ${summaryText
      ? `<div class="detail-summary">${esc(summaryText)}</div>`
      : `<div class="detail-summary-empty">總結將於下次更新後生成</div>`
    }
    ${bodyText ? `
      <div class="detail-divider"></div>
      <div class="detail-body-label">完整內容</div>
      <div class="detail-body">${esc(bodyText)}</div>
    ` : ''}
    <div class="detail-footer">
      <a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer" class="detail-source-link">在新分頁開啟原始頁面 &#8599;</a>
    </div>
  `;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function badge(item) {
  const map = { pm: ['PM', 'badge-pm'], ai: ['AI', 'badge-ai'], product: ['Product', 'badge-product'] };
  const [label, cls] = map[item.category] || ['其他', 'badge-pm'];
  return `<span class="badge ${cls}">${label}</span>`;
}

function srcTypeLabel(t) {
  return { reddit: 'Reddit', hn: 'HN', producthunt: 'PH', rss: 'RSS', ptt: 'PTT' }[t] || t.toUpperCase();
}

function isChineseSource(item) {
  if (item.source_type === 'ptt') return true;
  if (['reddit', 'hn', 'producthunt'].includes(item.source_type)) return false;
  return /[一-鿿㐀-䶿]/.test(item.title);
}

function dateGroup(iso) {
  const d     = new Date(iso);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const yest  = new Date(today.getTime() - 864e5);
  const day   = new Date(d); day.setHours(0, 0, 0, 0);
  if (day.getTime() === today.getTime()) return '今日';
  if (day.getTime() === yest.getTime())  return '昨日';
  return d.toLocaleDateString('zh-TW', { month: 'long', day: 'numeric' });
}

function relTime(iso) {
  const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (diff < 60)     return '剛剛';
  if (diff < 3600)   return Math.floor(diff / 60) + ' 分鐘前';
  if (diff < 86400)  return Math.floor(diff / 3600) + ' 小時前';
  if (diff < 172800) return '昨天';
  return new Date(iso).toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' });
}

function fmt(n)  { return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n); }

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

// ── Tab handlers ──────────────────────────────────────────────────────────

document.querySelectorAll('#cat-tabs .tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#cat-tabs .tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentCategory = btn.dataset.cat;
    updateCounts();
    closePanel();
    render();
  });
});

document.querySelectorAll('#type-tabs .tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#type-tabs .tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentType = btn.dataset.type;
    updateCounts();
    closePanel();
    render();
  });
});

document.querySelectorAll('#date-tabs .tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#date-tabs .tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentDate = btn.dataset.date;
    // clear custom range when using quick tabs
    customFrom = null;
    customTo   = null;
    document.getElementById('date-from').value = '';
    document.getElementById('date-to').value   = '';
    document.getElementById('date-from').classList.remove('active');
    document.getElementById('date-to').classList.remove('active');
    document.getElementById('date-clear').classList.remove('visible');
    updateCounts();
    closePanel();
    render();
  });
});

function applyCustomRange() {
  const fromVal = document.getElementById('date-from').value;
  const toVal   = document.getElementById('date-to').value;
  customFrom = fromVal ? new Date(fromVal) : null;
  customTo   = toVal   ? new Date(toVal)   : null;
  const hasCustom = customFrom || customTo;

  document.getElementById('date-from').classList.toggle('active', !!customFrom);
  document.getElementById('date-to').classList.toggle('active', !!customTo);
  document.getElementById('date-clear').classList.toggle('visible', hasCustom);

  // deactivate quick tabs when custom range is set
  if (hasCustom) {
    document.querySelectorAll('#date-tabs .tab').forEach(b => b.classList.remove('active'));
  } else {
    // restore "全部" as active if both cleared
    const allTab = document.querySelector('#date-tabs .tab[data-date="all"]');
    if (allTab) allTab.classList.add('active');
    currentDate = 'all';
  }

  updateCounts();
  closePanel();
  render();
}

document.getElementById('date-from').addEventListener('change', applyCustomRange);
document.getElementById('date-to').addEventListener('change', applyCustomRange);

document.getElementById('date-clear').addEventListener('click', () => {
  document.getElementById('date-from').value = '';
  document.getElementById('date-to').value   = '';
  applyCustomRange();
});

// ── Init ──────────────────────────────────────────────────────────────────

loadData();
