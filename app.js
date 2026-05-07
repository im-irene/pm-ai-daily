'use strict';

let allItems = [];
let currentFilter = 'all';

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

function filterItems(filter) {
  if (filter === 'all')         return allItems;
  if (filter === 'pm')          return allItems.filter(i => i.category === 'pm');
  if (filter === 'ai')          return allItems.filter(i => i.category === 'ai');
  if (filter === 'community')   return allItems.filter(i => i.source_type === 'reddit');
  if (filter === 'producthunt') return allItems.filter(i => i.source_type === 'producthunt');
  return allItems;
}

function updateCounts() {
  document.getElementById('count-all').textContent = allItems.length;
  document.getElementById('count-pm').textContent = allItems.filter(i => i.category === 'pm').length;
  document.getElementById('count-ai').textContent = allItems.filter(i => i.category === 'ai').length;
  document.getElementById('count-community').textContent = allItems.filter(i => i.source_type === 'reddit').length;
  document.getElementById('count-producthunt').textContent = allItems.filter(i => i.source_type === 'producthunt').length;
}

// ── Rendering ─────────────────────────────────────────────────────────────

function render() {
  const items = filterItems(currentFilter);
  const list  = document.getElementById('news-list');
  const empty = document.getElementById('empty-state');

  if (items.length === 0) {
    list.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  // Group by date label
  const groups = new Map();
  for (const item of items) {
    const key = dateGroup(item.published_at);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
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
  const stats = [];
  if (item.score > 0)    stats.push(`<span>&#9650; ${fmt(item.score)}</span>`);
  if (item.comments > 0) stats.push(`<span># ${fmt(item.comments)}</span>`);

  return `<article class="news-card">
    <div class="card-meta">
      ${badge(item)}
      <span class="src-type">${srcTypeLabel(item.source_type)}</span>
      <span class="src-name">${esc(item.source)}</span>
      <span class="card-time">${relTime(item.published_at)}</span>
    </div>
    <div class="card-title">
      <a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a>
    </div>
    ${item.summary ? `<div class="card-summary">${esc(item.summary)}</div>` : ''}
    ${stats.length ? `<div class="card-stats">${stats.join('')}</div>` : ''}
  </article>`;
}

function badge(item) {
  const map = {
    pm:      ['PM',      'badge-pm'],
    ai:      ['AI',      'badge-ai'],
    product: ['Product', 'badge-product'],
  };
  const [label, cls] = map[item.category] || ['Other', 'badge-pm'];
  return `<span class="badge ${cls}">${label}</span>`;
}

function srcTypeLabel(t) {
  return { reddit: 'Reddit', hn: 'HN', producthunt: 'PH', rss: 'RSS' }[t] || t.toUpperCase();
}

// ── Utils ─────────────────────────────────────────────────────────────────

function dateGroup(iso) {
  const d = new Date(iso);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const yest  = new Date(today.getTime() - 864e5);
  const day   = new Date(d);  day.setHours(0, 0, 0, 0);

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

function fmt(n) {
  return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
}

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

// ── Tab handlers ──────────────────────────────────────────────────────────

document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    render();
  });
});

// ── Init ──────────────────────────────────────────────────────────────────

loadData();
