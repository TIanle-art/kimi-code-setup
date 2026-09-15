// ==UserScript==
// @name         Kimi Web 状态栏（缓存率 + 余额）
// @namespace    kimi-code-setup
// @version      1.0.0
// @description  在 kimi web 页面角落显示本机 exa-bridge 的 /status：会话缓存命中率与当前 provider 余额（与 TUI footer 同源）。桥不在时自动隐藏，不影响页面。
// @match        http://127.0.0.1/*
// @match        http://localhost/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  // ---- 可改的两个常量 ----
  const BRIDGE_URL = 'http://127.0.0.1:8787'; // 桥端口改过就同步这里
  const REFRESH_MS = 10000;                   // 刷新间隔

  const POS_KEY = 'kimi-web-status-pos';
  const COLLAPSE_KEY = 'kimi-web-status-collapsed';
  const dark = !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);

  let box, cacheVal, balVal, detail;
  let collapsed = localStorage.getItem(COLLAPSE_KEY) === '1';
  let miss = 0;

  function el(tag, css, text) {
    const node = document.createElement(tag);
    if (css) node.style.cssText = css;
    if (text != null) node.textContent = text;
    return node;
  }

  function currentSessionId() {
    const m = location.href.match(/session_[A-Za-z0-9-]{8,}/);
    return m ? m[0] : '';
  }

  function cacheColor(rate) {
    if (rate == null) return dark ? '#9aa0a6' : '#5f6368';
    if (rate >= 80) return dark ? '#4ec87e' : '#0e7a38';
    if (rate >= 50) return dark ? '#e8a838' : '#92660a';
    return dark ? '#e85454' : '#b91c1c';
  }

  function build() {
    box = el('div', [
      'position:fixed', 'right:16px', 'bottom:16px', 'z-index:2147483647',
      'display:none', 'padding:6px 10px 5px', 'border-radius:10px',
      'font:12px/1.45 -apple-system,"SF Pro Text",system-ui,sans-serif',
      'background:' + (dark ? 'rgba(32,33,36,.86)' : 'rgba(255,255,255,.92)'),
      'color:' + (dark ? '#e8eaed' : '#202124'),
      'border:1px solid ' + (dark ? 'rgba(255,255,255,.14)' : 'rgba(0,0,0,.10)'),
      'box-shadow:0 2px 10px rgba(0,0,0,.18)',
      'cursor:grab', 'user-select:none', 'touch-action:none', 'max-width:70vw',
    ].join(';'));
    const row = el('div', 'display:flex;gap:8px;align-items:baseline;white-space:nowrap');
    cacheVal = el('b', 'font-variant-numeric:tabular-nums;font-size:13px', '—');
    balVal = el('b', 'font-variant-numeric:tabular-nums;font-size:13px', '—');
    row.append(el('span', 'opacity:.55', 'cache'), cacheVal,
               el('span', 'opacity:.55;margin-left:4px', 'bal'), balVal);
    detail = el('div', 'opacity:.55;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:60vw', '');
    box.append(row, detail);
  }

  function applyCollapse() {
    detail.style.display = collapsed ? 'none' : '';
  }

  function place() {
    try {
      const pos = JSON.parse(localStorage.getItem(POS_KEY) || 'null');
      if (pos && typeof pos.x === 'number' && typeof pos.y === 'number') {
        box.style.left = pos.x + 'px';
        box.style.top = pos.y + 'px';
        box.style.right = 'auto';
        box.style.bottom = 'auto';
      }
    } catch (e) { /* 位置坏了就用默认角落 */ }
  }

  function makeDraggable() {
    let sx = 0, sy = 0, ox = 0, oy = 0, moved = false, dragging = false;
    box.addEventListener('pointerdown', function (ev) {
      dragging = true; moved = false;
      sx = ev.clientX; sy = ev.clientY;
      const r = box.getBoundingClientRect();
      ox = r.left; oy = r.top;
      box.style.cursor = 'grabbing';
      if (box.setPointerCapture) box.setPointerCapture(ev.pointerId);
    });
    box.addEventListener('pointermove', function (ev) {
      if (!dragging) return;
      const dx = ev.clientX - sx, dy = ev.clientY - sy;
      if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
      if (!moved) return;
      const x = Math.max(0, Math.min(window.innerWidth - 60, ox + dx));
      const y = Math.max(0, Math.min(window.innerHeight - 24, oy + dy));
      box.style.left = x + 'px';
      box.style.top = y + 'px';
      box.style.right = 'auto';
      box.style.bottom = 'auto';
    });
    box.addEventListener('pointerup', function (ev) {
      dragging = false;
      box.style.cursor = 'grab';
      if (moved) {
        const r = box.getBoundingClientRect();
        localStorage.setItem(POS_KEY, JSON.stringify({ x: Math.round(r.left), y: Math.round(r.top) }));
      } else {
        collapsed = !collapsed;
        localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
        applyCollapse();
      }
      if (box.releasePointerCapture) box.releasePointerCapture(ev.pointerId);
    });
  }

  function render(data) {
    cacheVal.textContent = (data.cache == null) ? '—' : data.cache + '%';
    cacheVal.style.color = cacheColor(data.cache);
    balVal.textContent = data.balance || '—';
    const text = String(data.text || '');
    const i = text.indexOf('cached');
    detail.textContent = i >= 0 ? text.slice(i) : text;
  }

  function pump(data) {
    miss = 0;
    render(data);
    applyCollapse();
    box.style.display = 'block';
  }

  function fail() {
    if (++miss >= 2) box.style.display = 'none';
  }

  function poll() {
    const sid = currentSessionId();
    GM_xmlhttpRequest({
      method: 'GET',
      url: BRIDGE_URL + '/status' + (sid ? '?session=' + encodeURIComponent(sid) : ''),
      timeout: 5000,
      onload: function (resp) {
        let data = null;
        try { data = JSON.parse(resp.responseText); } catch (e) { data = null; }
        if (resp.status === 200 && data && data.ok) pump(data);
        else fail();
      },
      onerror: fail,
      ontimeout: fail,
    });
  }

  build();
  place();
  makeDraggable();
  document.body.appendChild(box);
  applyCollapse();
  poll();
  setInterval(poll, REFRESH_MS);
})();
