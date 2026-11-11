// PostKaro page: Post (videos and the clip editor), Queue, Posted, Accounts. Plain JavaScript, no build step.
// icon(name, size, cls) comes from icons.js.
'use strict';

const KEY = document.querySelector('meta[name=pk-key]').content;
const PLATS = ['youtube', 'instagram', 'facebook'];
const NAMES = {youtube: 'YouTube', instagram: 'Instagram', facebook: 'Facebook'};
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
let S = null;            // /api/state
let timer = null;        // the current page's refresh timer

// ---------------------------------------------------------------- helpers

function esc(t) {
  return String(t ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}
async function api(path, method = 'GET', body) {
  const r = await fetch('/api' + path, {method, headers: {'X-PostKaro': KEY, 'Content-Type': 'application/json'},
                                        body: body === undefined ? undefined : JSON.stringify(body)});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `${r.status} ${r.statusText}`);
  return j;
}
function debounce(fn, ms) {
  let h;
  return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); };
}
function acc(platform) {
  return (S?.accounts || []).find(a => a.platform === platform && a.active);
}
function pf(platform, size = 15) {
  return `<span class="pf ${platform}">${icon(platform, size)}${NAMES[platform]}</span>`;
}
function fmtDur(s) {
  s = Math.round(s || 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
function addDays(day, n) {
  const x = new Date(day + 'T12:00:00Z');
  x.setUTCDate(x.getUTCDate() + n);
  return x.toISOString().slice(0, 10);
}
function dayLabel(local) {                // 'YYYY-MM-DDTHH:MM' (user's time zone) -> Today / Tomorrow / Wed 12 Nov
  const d = local.slice(0, 10), today = (S?.now || '').slice(0, 10);
  if (d === today) return 'Today';
  if (d === addDays(today, 1)) return 'Tomorrow';
  if (d === addDays(today, -1)) return 'Yesterday';
  return new Date(d + 'T12:00:00').toLocaleDateString(undefined, {weekday: 'short', day: 'numeric', month: 'short'});
}
function whenText(local) {
  return local ? `${dayLabel(local)} · ${local.slice(11, 16)}` : 'Now';
}
function dayLabelUtc(iso) {               // a UTC timestamp -> Today / Wed 12 Nov (this computer's clock)
  const d = new Date(iso);
  return dayLabel(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}T00:00`);
}
function ago(iso) {
  if (!iso) return 'never';
  const m = Math.round((Date.now() - Date.parse(iso)) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m} min ago`;
  if (m < 60 * 24) return `${Math.round(m / 60)} h ago`;
  return `${Math.round(m / 1440)} days ago`;
}
function initials(name) {
  const w = String(name || '?').replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/);
  return ((w[0] || '?')[0] + (w.length > 1 ? w[1][0] : '')).toUpperCase();
}
function thumb(src) {
  return `<img class="thumb" src="${esc(src)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;
}
function tagCount(text) {
  return (String(text || '').match(/(^|[^\w#])#[^\s#.,!?;:()\[\]{}"'।]+/g) || []).length;
}

// toasts
function toast(text, kind = 'info', ms) {
  const box = $('#toasts');
  const t = document.createElement('div');
  t.className = `toast ${kind}`;
  t.innerHTML = `${icon({ok: 'circle-check', bad: 'circle-alert'}[kind] || 'info', 16)}<div class="grow"></div>
                 <button aria-label="Dismiss">${icon('x', 14)}</button>`;
  $('.grow', t).textContent = text;
  $('button', t).onclick = () => t.remove();
  box.append(t);
  while (box.children.length > 3) box.firstElementChild.remove();
  setTimeout(() => t.remove(), ms || (kind === 'bad' ? 9000 : 4500));
}

// a button shows a spinner while its work runs
async function busy(btn, fn) {
  if (!btn) return fn();
  const html = btn.innerHTML;
  btn.classList.add('is-loading');
  btn.disabled = true;
  btn.innerHTML = icon('loader-circle', 15) + `<span>${esc(btn.textContent.trim())}</span>`;
  try { return await fn(); } finally {
    if (btn.isConnected) { btn.innerHTML = html; btn.disabled = false; btn.classList.remove('is-loading'); }
  }
}

// dialogs (native <dialog>: focus stays inside, Esc closes)
function dialog(html, onOk) {
  return new Promise(resolve => {
    const d = $('#modal');
    d.innerHTML = `<form>${html}</form>`;
    const form = $('form', d);
    let result = null;
    form.onsubmit = e => { e.preventDefault(); result = onOk(form); d.close(); };
    $$('[data-cancel]', d).forEach(b => b.onclick = () => d.close());
    d.onclose = () => resolve(result);
    d.showModal();
    ($('[autofocus]', d) || $('[data-cancel]', d))?.focus();
  });
}
function confirmDialog({title, body, ok = 'Confirm', danger = false}) {
  return dialog(`<div class="modal-body"><h2 id="modal-title">${esc(title)}</h2>${body ? `<p>${esc(body)}</p>` : ''}</div>
    <div class="modal-foot"><button type="button" class="btn" data-cancel>Cancel</button>
    <button type="submit" class="btn ${danger ? 'btn-dangerous' : 'btn-primary'}">${esc(ok)}</button></div>`, () => true)
    .then(r => r === true);
}
function timeDialog({title, body, value}) {
  return dialog(`<div class="modal-body"><h2 id="modal-title">${esc(title)}</h2>${body ? `<p>${esc(body)}</p>` : ''}
      <label class="field"><span class="field-label">Date and time (${esc(S.settings.timezone)})</span>
      <input class="input num" type="datetime-local" name="when" required value="${esc(value || '')}" autofocus></label></div>
    <div class="modal-foot"><button type="button" class="btn" data-cancel>Cancel</button>
    <button type="submit" class="btn btn-primary">Schedule</button></div>`, form => form.when.value);
}

// a post's state as a badge
function stateBadge(p) {
  const t = p.when ? whenText(p.when) : 'now';
  const time = p.when ? p.when.slice(11, 16) : '';
  switch (p.state) {
    case 'draft': return '';
    case 'scheduled': return `<span class="badge info"${p.platform === 'instagram' && p.when ? ' title="Uploads up to a day before its time"' : ''}>${icon('clock', 12)}Scheduled · ${esc(t)}</span>`;
    case 'uploading': return `<span class="badge info">${icon('loader-circle', 12, 'spin')}Uploading${p.progress != null ? ' ' + Math.round(p.progress * 100) + '%' : ''}</span>`;
    case 'processing': return `<span class="badge info">${icon('loader-circle', 12, 'spin')}Processing</span>`;
    case 'waiting': return p.platform === 'instagram'
      ? `<span class="badge info" title="PostKaro publishes it at its time. Keep this computer on.">${icon('clock', 12)}Ready · publishes ${esc(time || 'now')}</span>`
      : `<span class="badge info" title="${NAMES[p.platform]} makes it live by itself">${icon('check', 12)}Uploaded · live ${esc(time ? 'at ' + time : 'soon')}</span>`;
    case 'publishing': return `<span class="badge info">${icon('loader-circle', 12, 'spin')}Publishing</span>`;
    case 'live': return `<span class="badge ok"><span class="dot"></span>Live</span>`;
    case 'failed': return `<span class="badge bad"><span class="dot"></span>Failed</span>`;
    case 'missed': return `<span class="badge warn" title="This computer was off at its time">${icon('triangle-alert', 12)}Missed</span>`;
    case 'cancelled': return `<span class="badge">Cancelled</span>`;
    default: return `<span class="badge">${esc(p.state)}</span>`;
  }
}
const ACTIONS = {
  scheduled: ['cancel'], processing: ['cancel'], waiting: ['cancel'], failed: ['retry', 'draft'],
  missed: ['now', 'newtime', 'skip'], cancelled: ['draft'],
};
const ACT_LABEL = {cancel: 'Cancel', retry: 'Retry', draft: 'Back to drafts', now: 'Post now', newtime: 'New time', skip: 'Skip'};
const ACT_ICON = {cancel: 'x', retry: 'rotate-ccw', draft: 'undo-2', now: 'send', newtime: 'calendar-clock', skip: 'chevron-right'};
function actionButtons(p) {
  const btns = (ACTIONS[p.state] || []).map(a =>
    `<button class="btn btn-sm ${a === 'cancel' ? 'btn-ghost' : ''}" data-act="${a}" data-id="${p.id}">${icon(ACT_ICON[a], 14)}${ACT_LABEL[a]}</button>`);
  if (p.state === 'live' && p.url) {
    btns.push(`<a class="btn btn-sm" href="${esc(p.url)}" target="_blank" rel="noopener">${icon('external-link', 14)}Open</a>`);
  }
  return btns.join('');
}
async function postAct(id, act, btn) {
  try {
    if (act === 'newtime') {
      const when = await timeDialog({title: 'Pick a new time', body: 'The post goes out at this time.', value: S.now});
      if (!when) return false;
      await busy(btn, () => api(`/post/${id}/time`, 'POST', {when}));
    } else {
      if (act === 'cancel' && !await confirmDialog({
        title: 'Cancel this post?', ok: 'Cancel post', danger: true,
        body: 'If it is already uploaded, PostKaro removes it from the platform. You can schedule it again later.'})) return false;
      await busy(btn, () => api(`/post/${id}/${act}`, 'POST', {}));
    }
    toast({cancel: 'Post cancelled.', retry: 'Trying again.', draft: 'Back in drafts.', now: 'Posting now.',
           newtime: 'Scheduled for the new time.', skip: 'Skipped.'}[act], 'ok');
    await loadState();
    return true;
  } catch (e) { toast(e.message, 'bad'); return false; }
}

// ---------------------------------------------------------------- shell

async function loadState() {
  S = await api('/state');
  $('#marks').innerHTML = PLATS.map(p => {
    const a = acc(p);
    const st = a ? a.status : 'off';
    const tip = a ? `${NAMES[p]}: ${a.name}${a.problem ? ' · ' + a.problem : ''}` : `${NAMES[p]}: not connected`;
    return `<span class="mark ${st}" title="${esc(tip)}">${icon(p, 15)}</span>`;
  }).join('');
  const n = ['scheduled', 'uploading', 'processing', 'waiting', 'publishing', 'missed'].reduce((t, k) => t + (S.counts[k] || 0), 0);
  $('#qcount').textContent = n || '';
}

const ROUTES = [
  [/^#?\/?$/, 'post', home], [/^#\/post\/(\d+)$/, 'post', batchPage], [/^#\/queue$/, 'queue', queuePage],
  [/^#\/posted$/, 'posted', postedPage], [/^#\/accounts$/, 'accounts', accountsPage],
];
async function route() {
  clearInterval(timer);
  const h = location.hash || '#/';
  for (const [re, nav, fn] of ROUTES) {
    const m = h.match(re);
    if (!m) continue;
    $$('[data-nav]').forEach(a => {
      if (a.dataset.nav === nav) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    try { await fn(...m.slice(1)); } catch (e) {
      $('#main').innerHTML = `<div class="notice warn">${icon('circle-alert')}<span>${esc(e.message)}</span></div>`;
    }
    return;
  }
  location.hash = '#/';
}
addEventListener('hashchange', () => { route(); window.scrollTo(0, 0); });
addEventListener('scroll', () => { const s = $('.sticky-head'); if (s) s.classList.toggle('stuck', scrollY > 24); }, {passive: true});

// ---------------------------------------------------------------- Post: the list of videos

async function home() {
  const list = await api('/batches');
  const none = PLATS.every(p => !acc(p));
  const chip = (n, cls, label) => n ? `<span class="badge ${cls}">${n} ${label}</span>` : '';
  $('#main').innerHTML = `
    <div class="page-head"><div><h1>Post</h1>
      <p class="lead">Add a video from ClipKaro, check each platform's title and caption, then schedule it.</p></div></div>
    ${none ? `<div class="notice" style="margin-bottom:20px">${icon('info')}<span>Connect your accounts first:
      <a class="link" href="#/accounts">open Accounts</a>.</span></div>` : ''}
    <form id="add">
      <label class="field-label" for="path" style="margin-bottom:6px">Add a video</label>
      <div class="import">
        <div class="input-icon">${icon('folder-open')}<input id="path" class="input" autocomplete="off" spellcheck="false"
          placeholder="ClipKaro project folder or post.json"></div>
        <button class="btn btn-primary" id="add-btn">${icon('plus')}Add</button>
      </div>
      <p class="import-help">ClipKaro adds finished videos here by itself and ends with a “Post them” link. To add an older
        one, paste its folder, for example <code>…/Claude_Clipper/output/my-video-abc123</code>.</p>
    </form>
    <section class="section">
      <div class="section-head"><h2>Videos ${list.length ? `<span class="count-label">${list.length}</span>` : ''}</h2></div>
      ${list.length ? `<div class="list">${list.map(b => `
        <a class="row" href="#/post/${b.id}">
          ${b.first_clip ? thumb(`/media/thumb/${b.first_clip}`) : '<span class="thumb"></span>'}
          <span class="grow"><span class="title">${esc(b.title || b.project)}</span>
            <span class="sub">${b.channel ? esc(b.channel) + ' · ' : ''}${b.clips} clip${b.clips === 1 ? '' : 's'}${b.created ? ' · added ' + esc(dayLabelUtc(b.created)) : ''}</span></span>
          <span class="chips">${chip(b.drafts, '', 'to schedule')}${chip(b.scheduled, 'info', 'scheduled')}${chip(b.live, 'ok', 'live')}${chip(b.failed, 'bad', 'failed')}</span>
          <span class="faint">${icon('chevron-right')}</span>
        </a>`).join('')}</div>`
      : `<div class="panel empty"><img src="/static/img/mascot.png" alt="">
          <h2>No videos yet</h2>
          <p>Finish a video in ClipKaro and click its “Post them” link, or paste a project folder above.</p></div>`}
    </section>`;
  $('#add').onsubmit = async e => {
    e.preventDefault();
    const path = $('#path').value.trim();
    if (!path) { $('#path').focus(); return toast('Paste the path of a ClipKaro project folder or a post.json.', 'bad'); }
    try {
      const r = await busy($('#add-btn'), () => api('/import', 'POST', {path}));
      location.hash = '#/post/' + r.id;
    } catch (err) { toast(err.message, 'bad'); }
  };
}

// ---------------------------------------------------------------- Post: one video

async function batchPage(id) {
  const b = await api('/batch/' + id);
  const live = b.clips.filter(c => !c.removed), removed = b.clips.filter(c => c.removed);
  $('#main').innerHTML = `
    <div class="sticky-head">
      <a class="back" href="#/">${icon('arrow-left', 14)}All videos</a>
      <div class="page-head"><div style="min-width:0"><h1>${esc(b.title || b.project)}</h1>
        <div class="meta">${b.channel ? `<span>${esc(b.channel)}</span><span class="sep">·</span>` : ''}
          <span>${live.length} clip${live.length === 1 ? '' : 's'}</span>
          ${b.source_url ? `<span class="sep">·</span><a class="link" href="${esc(b.source_url)}" target="_blank" rel="noopener">Full video</a>` : ''}</div></div>
        <div class="actions">
          <button class="btn" id="plan" title="Fill in times: your usual time on each platform, best clips first">${icon('wand-sparkles', 15)}Plan for me</button>
          <button class="btn btn-primary" id="sched">${icon('send', 15)}<span id="sched-label">Schedule</span></button>
        </div></div>
    </div>
    ${b.own ? '' : `<div class="notice warn" style="margin:8px 0 4px">${icon('triangle-alert')}<span>This video is from
      <b>${esc(b.channel)}</b>, not one of your channels. Clips of other people's videos can get copyright claims or
      less reach. You decide. Your own channels are listed in <a class="link" href="#/accounts">Accounts</a>.</span></div>`}
    <div id="clips">${live.map(c => clipHTML(c)).join('')}</div>
    ${live.length ? '' : `<div class="panel empty"><img src="/static/img/mascot.png" alt=""><h2>No clips left</h2>
      <p>Every clip of this video was removed. Restore one below.</p></div>`}
    ${removed.length ? `<section class="section"><details class="disclose"><summary>${icon('chevron-right', 14)}Removed clips (${removed.length})</summary>
      <div class="list">${removed.map(c => `<div class="row"><span class="grow"><span class="title">#${c.no} ${esc(c.title)}</span></span>
        <button class="btn btn-sm" data-restore="${c.id}">${icon('undo-2', 14)}Restore</button></div>`).join('')}</div></details></section>` : ''}`;
  wireBatch(id);
  updateSchedLabel();
  timer = setInterval(() => refreshStates(id), 5000);
}

function clipHTML(c) {
  return `<section class="clip" data-clip="${c.id}">
    <div class="clip-video">${c.exists
      ? `<video src="${c.media}" poster="${c.thumb}" controls preload="none" playsinline aria-label="Clip ${c.no}"></video>`
      : '<div class="gone">Video file not found</div>'}</div>
    <div style="min-width:0">
      <div class="clip-head"><div class="grow">
          <h2><span class="no">#${c.no}</span>${esc(c.title)}</h2>
          <div class="meta"><span class="num">${fmtDur(c.duration)}</span>${c.score != null ? `<span class="sep">·</span><span>Clip score ${c.score}</span>` : ''}
            ${c.deep ? '<span class="sep">·</span><span class="badge">Deep clip</span>' : ''}</div></div>
        <button class="btn btn-ghost btn-icon btn-sm btn-danger" data-remove="${c.id}" title="Remove from this video" aria-label="Remove clip ${c.no}">${icon('trash-2', 15)}</button>
      </div>
      ${c.warnings.map(w => `<div class="notice warn">${icon('triangle-alert')}<span>${esc(w)}</span></div>`).join('')}
      <div class="panel">${PLATS.map(p => c.posts[p] ? postHTML(c.posts[p]) : '').join('')}</div>
    </div>
  </section>`;
}

function counterText(p) {
  if (p.platform === 'youtube') return {title: `${p.title_chars}/100`, body: `${p.desc_bytes}/5000 bytes`};
  if (p.platform === 'instagram') return {body: `${p.chars}/2200 · ${p.hashtags}/5 hashtags`};
  return {body: `${p.chars} characters`};
}
function postHTML(p) {
  const a = acc(p.platform);
  const draft = p.state === 'draft', locked = p.state === 'live';
  const cnt = counterText(p);
  const ro = locked ? 'readonly' : '';
  const fields = p.platform === 'youtube' ? `
      <div class="field"><label class="field-label" for="t${p.id}"><span>Title</span>
        <span class="counter ${p.title_chars > 100 ? 'over' : ''}" data-cnt="title">${cnt.title}</span></label>
        <input id="t${p.id}" class="input" data-f="title" value="${esc(p.title)}" maxlength="140" ${ro}></div>
      <details class="disclose"><summary>${icon('chevron-right', 14)}Description <span class="faint">(optional)</span></summary>
        <div class="field"><label class="field-label" for="d${p.id}"><span class="sr-only">Description</span><span></span>
          <span class="counter ${p.desc_bytes > 5000 ? 'over' : ''}" data-cnt="body">${cnt.body}</span></label>
          <textarea id="d${p.id}" class="textarea" data-f="body" rows="4" ${ro}>${esc(p.body)}</textarea></div></details>`
    : `<div class="field"><label class="field-label" for="d${p.id}"><span>Caption</span>
        <span class="counter ${p.chars > 2200 || (p.platform === 'instagram' && p.hashtags > 5) ? 'over' : ''}" data-cnt="body">${cnt.body}</span></label>
        <textarea id="d${p.id}" class="textarea" data-f="body" rows="3" ${ro}>${esc(p.body)}</textarea></div>`;
  return `<div class="plat ${p.enabled ? '' : 'off'} ${locked ? 'locked' : ''}" data-post="${p.id}" data-plat="${p.platform}" data-state="${p.state}">
    <div class="plat-side">
      <label class="switch"><input type="checkbox" data-f="enabled" ${p.enabled ? 'checked' : ''} ${draft ? '' : 'disabled'}
        aria-label="Post to ${NAMES[p.platform]}"><span class="track"></span>${pf(p.platform)}</label>
      <div class="to">${a ? `to <b>${esc(a.name)}</b>` : `Not connected · <a class="link" href="#/accounts">Connect</a>`}</div>
      <div class="st">${stateBadge(p)}</div>
    </div>
    <div class="plat-off">Not posting to ${NAMES[p.platform]}.</div>
    <div class="plat-main">
      ${fields}
      <div class="plat-foot">
        <div class="when"><label class="sr-only" for="w${p.id}">When to post on ${NAMES[p.platform]}</label>
          <input id="w${p.id}" class="input num" type="datetime-local" data-f="when" value="${esc(p.when)}" ${ro}>
          <span class="hint">${p.when ? '' : 'Empty: posts when you schedule'}</span></div>
        <div class="plat-actions">${actionButtons(p)}</div>
      </div>
      <ul class="msgs">${msgsHTML(p)}</ul>
    </div>
  </div>`;
}
function msgsHTML(p) {
  return p.errors.map(e => `<li class="err">${icon('circle-alert', 14)}<span>${esc(e)}</span></li>`).join('') +
    p.warnings.map(w => `<li class="warn">${icon('triangle-alert', 14)}<span>${esc(w)}</span></li>`).join('') +
    (p.error && p.state !== 'live' ? `<li class="err">${icon('circle-x', 14)}<span>${esc(p.error)}</span></li>` : '');
}

function wireBatch(bid) {
  const clips = $('#clips');
  const savers = {};
  const save = async (row, field, value) => {
    try {
      const v = await api('/post/' + row.dataset.post, 'PATCH', {[field]: value});
      $('.msgs', row).innerHTML = msgsHTML(v);
      row.classList.toggle('off', !v.enabled);
      $('.st', row).innerHTML = stateBadge(v);
      const hint = $('.when .hint', row);
      if (hint) hint.textContent = v.when ? '' : 'Empty: posts when you schedule';
      updateSchedLabel();
    } catch (e) { toast(e.message, 'bad'); }
  };
  clips.addEventListener('input', e => {
    const f = e.target.dataset.f, row = e.target.closest('.plat');
    if (!row || !['title', 'body'].includes(f)) return;
    liveCount(row, f, e.target.value);
    const k = row.dataset.post + f;
    (savers[k] ||= debounce(save, 700))(row, f, e.target.value);
  });
  clips.addEventListener('change', e => {
    const f = e.target.dataset.f, row = e.target.closest('.plat');
    if (!row) return;
    if (f === 'enabled') { row.classList.toggle('off', !e.target.checked); updateSchedLabel(); save(row, 'enabled', e.target.checked); }
    if (f === 'when') save(row, 'when', e.target.value);
  });
  clips.addEventListener('click', async e => {
    const act = e.target.closest('[data-act]');
    if (act && await postAct(act.dataset.id, act.dataset.act, act)) batchPage(bid);
    const rm = e.target.closest('[data-remove]');
    if (rm) {
      if (!await confirmDialog({title: 'Remove this clip?', ok: 'Remove', danger: true,
        body: 'Its scheduled posts are cancelled. You can restore the clip later from “Removed clips”.'})) return;
      try { await busy(rm, () => api(`/clip/${rm.dataset.remove}/remove`, 'POST', {})); toast('Clip removed.', 'ok'); batchPage(bid); }
      catch (err) { toast(err.message, 'bad'); }
    }
  });
  $$('[data-restore]').forEach(el => el.onclick = async () => {
    try { await busy(el, () => api(`/clip/${el.dataset.restore}/restore`, 'POST', {})); batchPage(bid); }
    catch (err) { toast(err.message, 'bad'); }
  });
  $('#plan').onclick = async e => {
    try {
      await busy(e.currentTarget, () => api(`/batch/${bid}/plan`, 'POST', {}));
      await batchPage(bid);
      toast('Times filled in. Change any you like, then schedule.', 'ok');
    } catch (err) { toast(err.message, 'bad'); }
  };
  $('#sched').onclick = e => scheduleAll(bid, e.currentTarget);
}

function liveCount(row, field, value) {
  const plat = row.dataset.plat, el = $(`[data-cnt="${field}"]`, row);
  if (!el) return;
  if (plat === 'youtube' && field === 'title') {
    el.textContent = `${value.length}/100`;
    el.classList.toggle('over', value.length > 100);
  } else if (plat === 'youtube') {
    const n = new TextEncoder().encode(value).length;
    el.textContent = `${n}/5000 bytes`;
    el.classList.toggle('over', n > 5000);
  } else if (plat === 'instagram') {
    const tags = tagCount(value);
    el.textContent = `${value.length}/2200 · ${tags}/5 hashtags`;
    el.classList.toggle('over', value.length > 2200 || tags > 5);
  } else {
    el.textContent = `${value.length} characters`;
  }
}

function tickedDrafts() {
  return $$('.plat[data-state="draft"]').filter(r => $('input[data-f="enabled"]', r)?.checked);
}
function updateSchedLabel() {
  const n = tickedDrafts().length, b = $('#sched');
  if (!b) return;
  $('#sched-label').textContent = n ? `Schedule ${n} post${n === 1 ? '' : 's'}` : 'Schedule';
  b.disabled = !n;
}

async function scheduleAll(bid, btn) {
  const rows = tickedDrafts();
  if (!rows.length) return toast('Nothing ticked to schedule.');
  const now = rows.filter(r => !$('[data-f="when"]', r).value).length;
  if (!await confirmDialog({title: `Schedule ${rows.length} post${rows.length === 1 ? '' : 's'}?`, ok: 'Schedule',
    body: now ? `${now} of them have no time and go out right away.` : 'Each goes out at the time shown.'})) return;
  try {
    const r = await busy(btn, () => api('/schedule', 'POST', {batch: Number(bid)}));
    await loadState();
    await batchPage(bid);
    if (r.skipped.length) {
      toast(`${r.scheduled} scheduled. ${r.skipped.length} skipped: ` +
        r.skipped.map(s => `#${s.clip} ${NAMES[s.platform]}: ${s.why.join(' ')}`).join(' | '), 'bad', 15000);
    } else {
      toast(`${r.scheduled} scheduled${r.now ? `, ${r.now} going out now` : ''}.`, 'ok');
    }
  } catch (e) { toast(e.message, 'bad'); }
}

async function refreshStates(bid) {
  if (!location.hash.startsWith('#/post/') || $('#modal').open) return;
  const b = await api('/batch/' + bid).catch(() => null);
  if (!b) return;
  for (const c of b.clips) for (const p of Object.values(c.posts)) {
    const row = $(`.plat[data-post="${p.id}"]`);
    if (!row) continue;
    if (row.dataset.state !== p.state) {                     // state changed: redraw this platform's row
      const tmp = document.createElement('div');
      tmp.innerHTML = postHTML(p);
      row.replaceWith(tmp.firstElementChild);
    } else if (p.state === 'uploading') {
      $('.st', row).innerHTML = stateBadge(p);
    }
  }
  updateSchedLabel();
}

// ---------------------------------------------------------------- Queue

async function queuePage() {
  const list = await api('/queue');
  const groups = [];
  for (const p of list) {
    const d = p.when ? dayLabel(p.when) : 'Now';
    if (!groups.length || groups[groups.length - 1].d !== d) groups.push({d, items: []});
    groups[groups.length - 1].items.push(p);
  }
  $('#main').innerHTML = `
    <div class="page-head"><div><h1>Queue</h1>
      <p class="lead">Posts waiting for their time. YouTube and Facebook go live by themselves; Instagram needs this
        computer on at its time.</p></div></div>
    ${groups.length ? groups.map(g => `<div class="group-label">${esc(g.d)}</div>
      <div class="list">${g.items.map(p => qRow(p, p.when ? p.when.slice(11, 16) : 'Now')).join('')}</div>`).join('')
      : `<div class="panel empty"><img src="/static/img/mascot.png" alt=""><h2>Nothing waiting</h2>
          <p>Scheduled posts show up here until they go live.</p>
          <a class="btn" href="#/" style="margin-top:10px">${icon('arrow-left', 14)}Go to Post</a></div>`}`;
  timer = setInterval(async () => {
    if (location.hash === '#/queue' && !$('#modal').open && !$('#main').contains(document.activeElement)) {
      await loadState(); queuePage();
    }
  }, 8000);
}

function qRow(p, timeText) {
  const preview = (p.platform === 'youtube' ? p.title : p.body || '').split('\n')[0];
  return `<div class="q-row" data-post="${p.id}">
    <span class="time">${esc(timeText)}</span>
    ${thumb(p.thumb || `/media/thumb/${p.clip_id}`)}
    <div class="info"><a href="#/post/${p.batch}">#${p.no} ${esc(p.clip_title)}</a>
      <div class="sub">${esc(preview && preview !== p.clip_title ? preview : p.video)}</div>
      ${p.error && p.state !== 'live' ? `<div class="why">${esc(p.error)}</div>` : ''}</div>
    <span class="pfcell">${pf(p.platform)}</span>
    <span class="status">${stateBadge(p)}</span>
    <span class="acts">${actionButtons(p)}</span>
  </div>`;
}

// one click handler for the Queue and Posted lists (the page itself is redrawn, the handler stays)
$('#main').addEventListener('click', async e => {
  if (!['#/queue', '#/posted'].includes(location.hash)) return;
  const b = e.target.closest('[data-act]');
  if (b && await postAct(b.dataset.id, b.dataset.act, b)) (location.hash === '#/queue' ? queuePage : postedPage)();
});

// ---------------------------------------------------------------- Posted

let postedFilter = 'all';
async function postedPage() {
  const list = await api('/posted');
  const n = s => list.filter(p => p.state === s).length;
  const shown = postedFilter === 'all' ? list : list.filter(p => p.state === postedFilter);
  const seg = [['all', 'All', list.length], ['live', 'Live', n('live')], ['failed', 'Failed', n('failed')],
               ['cancelled', 'Cancelled', n('cancelled')]];
  $('#main').innerHTML = `
    <div class="page-head"><div><h1>Posted</h1><p class="lead">Everything PostKaro sent, newest first.</p></div>
      ${list.length ? `<div class="seg" role="group" aria-label="Show">${seg.map(([k, label, c]) =>
        `<button type="button" data-filter="${k}" aria-pressed="${postedFilter === k}">${label} <span class="faint num">${c}</span></button>`).join('')}</div>` : ''}</div>
    ${shown.length ? `<div class="list posted">${shown.map(p => qRow(p, whenText(p.posted || p.updated))).join('')}</div>`
      : `<div class="panel empty"><img src="/static/img/mascot.png" alt="">
          <h2>${list.length ? 'Nothing here' : 'Nothing posted yet'}</h2>
          <p>${list.length ? 'No posts match this filter.' : 'Live posts and their links show up here, with anything that failed.'}</p></div>`}`;
  $$('[data-filter]').forEach(b => b.onclick = () => { postedFilter = b.dataset.filter; postedPage(); });
}

// ---------------------------------------------------------------- Accounts

const CATEGORIES = [['24', 'Entertainment'], ['22', 'People & Blogs'], ['27', 'Education'], ['20', 'Gaming'],
                    ['25', 'News & Politics'], ['23', 'Comedy'], ['28', 'Science & Technology'], ['1', 'Film & Animation']];

function accStatus(a) {
  if (a.status === 'broken') return '<span class="badge bad"><span class="dot"></span>Login failed</span>';
  if (a.status === 'warn') return '<span class="badge warn"><span class="dot"></span>Reconnect soon</span>';
  return '<span class="badge ok"><span class="dot"></span>Connected</span>';
}
function accRow(a, login) {
  const id = `${a.platform}|${a.account_id}`;
  return `<div class="acc ${a.status}">
    <span class="avatar" aria-hidden="true">${esc(initials(a.name))}</span>
    <div class="who"><div class="name"><span>${esc(a.name)}</span>${a.active ? '<span class="badge brand" title="New posts go here">Default</span>' : ''}</div>
      ${a.username ? `<div class="handle">@${esc(a.username)}</div>` : ''}
      ${a.problem && a.status !== 'ok' ? `<div class="problem">${esc(a.problem)}</div>` : ''}</div>
    ${accStatus(a)}
    <span class="checked" title="${esc(a.checked || '')}">Checked ${esc(ago(a.checked))}</span>
    <div class="acts">
      ${a.status !== 'ok' ? `<button class="btn btn-sm" data-connect="${login}">${icon('refresh-cw', 14)}Reconnect</button>` : ''}
      ${a.active ? '' : `<button class="btn btn-sm" data-activate="${esc(id)}">Make default</button>`}
      <button class="btn btn-ghost btn-icon btn-sm" data-check="${esc(id)}" title="Check connection" aria-label="Check connection of ${esc(a.name)}">${icon('refresh-cw', 15)}</button>
      <button class="btn btn-ghost btn-icon btn-sm btn-danger" data-disconnect="${esc(id)}" title="Disconnect" aria-label="Disconnect ${esc(a.name)}">${icon('unplug', 15)}</button>
    </div>
  </div>`;
}

async function accountsPage() {
  await loadState();
  const s = S.settings;
  const list = p => S.accounts.filter(a => a.platform === p);
  const yt = list('youtube'), ig = list('instagram'), fb = list('facebook');
  const opt = (v, cur, label) => `<option value="${esc(v)}" ${String(cur) === String(v) ? 'selected' : ''}>${esc(label ?? v)}</option>`;
  $('#main').innerHTML = `
    <div class="page-head"><div><h1>Accounts</h1>
      <p class="lead">Where PostKaro posts. Logins stay on this computer, encrypted, with the key in
        ${esc(S.vault.where)}. The setup guide is <code>docs/connect-accounts.md</code> in the PostKaro folder.</p></div></div>
    ${S.vault.ok ? '' : `<div class="notice warn">${icon('triangle-alert')}<span>${esc(S.vault.problem || 'The password store has a problem.')}</span></div>`}

    <section class="panel integration">
      <div class="int-head"><span class="int-logo youtube">${icon('youtube', 20)}</span>
        <div class="grow"><h2>YouTube</h2><p>Shorts on your channels. New posts go to the default channel.</p></div>
        <button class="btn ${yt.length ? '' : 'btn-primary'}" data-connect="google" ${S.apps.google ? '' : 'disabled'}>
          ${icon(yt.length ? 'plus' : 'link-2', 15)}${yt.length ? 'Add channel' : 'Connect YouTube'}</button></div>
      ${S.apps.google ? '' : `<div class="setup">
        <p><b>First, your own Google app</b> (one time, about 15 minutes: guide part A). Then paste the downloaded
          <code>client_secret_….json</code> here, or choose the file.</p>
        <label class="sr-only" for="gjson">Google client JSON</label>
        <textarea id="gjson" class="textarea" rows="3" placeholder='{"installed":{"client_id":"…","client_secret":"…"}}'></textarea>
        <div style="display:flex;gap:8px;flex-wrap:wrap"><label class="btn">${icon('upload', 15)}Choose file
          <input type="file" id="gfile" accept=".json,application/json" class="sr-only"></label>
          <button class="btn btn-primary" id="gsave">Save Google app</button></div></div>`}
      <div class="int-body">${yt.length ? yt.map(a => accRow(a, 'google')).join('') : '<div class="no-accounts">No channel connected yet.</div>'}</div>
      ${S.apps.google ? `<div class="int-foot"><span class="ok-line">${icon('circle-check', 14)}Google app saved</span>
        <button class="btn-link" data-delapp="google">Replace</button></div>` : ''}
    </section>

    <section class="panel integration">
      <div class="int-head"><span class="int-logo meta">${icon('instagram', 18)}</span>
        <div class="grow"><h2>Instagram and Facebook</h2><p>Reels on your Instagram professional account and your Facebook
          Pages. One Meta login connects both.</p></div>
        <button class="btn ${fb.length ? '' : 'btn-primary'}" data-connect="meta" ${S.apps.meta ? '' : 'disabled'}>
          ${icon(fb.length ? 'refresh-cw' : 'link-2', 15)}${fb.length ? 'Reconnect' : 'Connect'}</button></div>
      ${S.apps.meta ? '' : `<div class="setup">
        <p><b>First, your own Meta app</b> (one time, about 20 minutes: guide part B). Then paste its App ID and App
          Secret from App settings → Basic.</p>
        <div class="two"><label class="field"><span class="field-label">App ID</span><input id="mid" class="input" inputmode="numeric" autocomplete="off"></label>
          <label class="field"><span class="field-label">App Secret</span><input id="msecret" class="input" type="password" autocomplete="off"></label>
          <button class="btn btn-primary" id="msave">Save Meta app</button></div></div>`}
      <div class="int-body">
        ${ig.length || fb.length ? `
          <div class="sub-label">Instagram</div>
          ${ig.length ? ig.map(a => accRow(a, 'meta')).join('') : '<div class="no-accounts">No Instagram account found. It must be a Creator or Business account linked to your Facebook Page; then Reconnect.</div>'}
          <div class="sub-label">Facebook Pages</div>
          ${fb.map(a => accRow(a, 'meta')).join('')}` : '<div class="no-accounts">Nothing connected yet.</div>'}
      </div>
      <div class="int-foot">
        ${S.apps.meta ? `<span class="ok-line">${icon('circle-check', 14)}Meta app saved <button class="btn-link" data-delapp="meta" style="margin-left:6px">Replace</button></span>` : '<span></span>'}
        <span class="copyline">Login return address <code id="redir">${esc(S.redirects.meta)}</code>
          <button class="btn btn-ghost btn-icon btn-sm" id="copy-redir" title="Copy" aria-label="Copy the login return address">${icon('copy', 14)}</button></span>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>Posting defaults</h2></div>
      <form class="panel settings" id="sets">
        <div class="set-row"><div><label class="label" for="s-tz">Time zone</label><div class="desc">Times you type and see are in this zone.</div></div>
          <div class="ctl"><input id="s-tz" class="input" name="timezone" value="${esc(s.timezone)}"></div></div>
        <div class="set-row"><div><label class="label" for="s-pd">Clips per day</label><div class="desc">How many clips “Plan for me” puts on each platform per day.</div></div>
          <div class="ctl"><input id="s-pd" class="input num" style="width:90px" name="per_day" type="number" min="1" max="10" value="${s.per_day}"></div></div>
        <div class="set-row"><div><span class="label">Usual times</span><div class="desc">Where “Plan for me” puts each day's first clip.</div></div>
          <div class="ctl"><div class="times">${PLATS.map(p => `<label>${NAMES[p]}<input class="input num" type="time" name="time_${p}" value="${esc((s.times[p] || ['18:00'])[0])}"></label>`).join('')}</div></div></div>
        <div class="set-row"><div><label class="label" for="s-mc">My channels</label><div class="desc">Videos from these channels get no copyright warning. One per line.</div></div>
          <div class="ctl"><textarea id="s-mc" class="textarea" name="my_channels" rows="3">${esc((s.my_channels || []).join('\n'))}</textarea></div></div>
        <div class="set-row"><div><label class="label" for="s-vis">YouTube visibility</label><div class="desc">Unlisted is handy for a quiet test.</div></div>
          <div class="ctl"><select id="s-vis" class="select" name="youtube_visibility">${['public', 'unlisted', 'private'].map(v => opt(v, s.youtube_visibility, v[0].toUpperCase() + v.slice(1))).join('')}</select></div></div>
        <div class="set-row"><div><label class="label" for="s-kids">Made for kids</label><div class="desc">YouTube asks this for every video.</div></div>
          <div class="ctl"><select id="s-kids" class="select" name="youtube_made_for_kids">${opt('false', String(!!s.youtube_made_for_kids), 'No')}${opt('true', String(!!s.youtube_made_for_kids), 'Yes')}</select></div></div>
        <div class="set-row"><div><label class="label" for="s-cat">YouTube category</label></div>
          <div class="ctl"><select id="s-cat" class="select" name="youtube_category">${CATEGORIES.map(([v, n]) => opt(v, s.youtube_category, n)).join('')}</select></div></div>
        <div class="set-row"><div><span class="label">Tell subscribers</span><div class="desc">YouTube notifies subscribers about new Shorts.</div></div>
          <div class="ctl"><label class="switch"><input type="checkbox" name="youtube_notify_subscribers" ${s.youtube_notify_subscribers ? 'checked' : ''} aria-label="Tell subscribers"><span class="track"></span></label></div></div>
        <div class="set-row"><div><span class="label">“Full video” link</span><div class="desc">Add “Full video: link” to new YouTube descriptions.</div></div>
          <div class="ctl"><label class="switch"><input type="checkbox" name="youtube_full_video_line" ${s.youtube_full_video_line ? 'checked' : ''} aria-label="Add the full video link"><span class="track"></span></label></div></div>
        <div class="set-row"><div><label class="label" for="s-late">Instagram, if this computer was off</label><div class="desc">Instagram can't schedule by itself, so PostKaro publishes at the time.</div></div>
          <div class="ctl"><select id="s-late" class="select" name="late">${opt('ask', s.late, 'Ask me')}${opt('post', s.late, 'Post it when the computer is back on')}</select></div></div>
        <div class="set-foot"><button class="btn btn-primary" id="sets-save">Save changes</button></div>
      </form>
    </section>`;
  wireAccounts();
}

function wireAccounts() {
  const gsave = $('#gsave');
  if (gsave) {
    $('#gfile').onchange = async e => { $('#gjson').value = await e.target.files[0].text(); };
    gsave.onclick = async () => {
      try { await busy(gsave, () => api('/apps/google', 'POST', {client: $('#gjson').value})); toast('Google app saved.', 'ok'); accountsPage(); }
      catch (e) { toast(e.message, 'bad'); }
    };
  }
  const msave = $('#msave');
  if (msave) msave.onclick = async () => {
    try { await busy(msave, () => api('/apps/meta', 'POST', {app_id: $('#mid').value, app_secret: $('#msecret').value})); toast('Meta app saved.', 'ok'); accountsPage(); }
    catch (e) { toast(e.message, 'bad'); }
  };
  $$('[data-delapp]').forEach(b => b.onclick = async () => {
    if (!await confirmDialog({title: 'Replace this app?', ok: 'Forget app', danger: true,
      body: 'PostKaro forgets this app\'s ID and secret, so you can save new ones. Connected accounts keep working until you reconnect.'})) return;
    try { await api('/apps/' + b.dataset.delapp, 'DELETE'); accountsPage(); } catch (e) { toast(e.message, 'bad'); }
  });
  $$('[data-connect]').forEach(b => b.onclick = () => connect(b.dataset.connect, b));
  const acct = (attr, action, ask) => $$(`[data-${attr}]`).forEach(b => b.onclick = async () => {
    const [p, ...rest] = b.dataset[attr].split('|');
    const id = rest.join('|');
    if (ask && !await confirmDialog(ask)) return;
    try {
      await busy(b, () => api(`/account/${p}/${encodeURIComponent(id)}/${action}`, 'POST', {}));
      if (action === 'check') toast('Connection checked.', 'ok');
      accountsPage();
    } catch (e) { toast(e.message, 'bad'); }
  });
  acct('check', 'check');
  acct('activate', 'activate');
  acct('disconnect', 'disconnect', {title: 'Disconnect this account?', ok: 'Disconnect', danger: true,
    body: 'PostKaro forgets its login and asks the platform to cancel its access. Scheduled posts for it fail until you connect again.'});
  $('#copy-redir').onclick = async () => {
    try { await navigator.clipboard.writeText($('#redir').textContent); toast('Copied.', 'ok'); }
    catch { getSelection().selectAllChildren($('#redir')); toast('Selected: press Ctrl+C to copy.'); }
  };
  $('#sets').onsubmit = async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = {
      timezone: f.get('timezone').trim(), per_day: Number(f.get('per_day')) || 1,
      times: Object.fromEntries(PLATS.map(p => [p, [f.get('time_' + p) || '18:00']])),
      my_channels: f.get('my_channels').split('\n').map(x => x.trim()).filter(Boolean),
      youtube_made_for_kids: f.get('youtube_made_for_kids') === 'true',
      youtube_visibility: f.get('youtube_visibility'), youtube_category: f.get('youtube_category'),
      youtube_notify_subscribers: f.get('youtube_notify_subscribers') === 'on',
      youtube_full_video_line: f.get('youtube_full_video_line') === 'on', late: f.get('late'),
    };
    try { await busy($('#sets-save'), () => api('/settings', 'PUT', body)); toast('Saved.', 'ok'); loadState(); }
    catch (err) { toast(err.message, 'bad'); }
  };
}

async function connect(name, btn) {
  const before = JSON.stringify(S.accounts);
  try {
    const r = await busy(btn, () => api('/connect/' + name, 'POST', {}));
    window.open(r.url, '_blank', 'noopener');
    toast('Finish the login in the new tab. This page updates by itself.', 'info', 10000);
    for (let i = 0; i < 90; i++) {                        // up to 3 minutes
      await new Promise(res => setTimeout(res, 2000));
      await loadState();
      if (JSON.stringify(S.accounts) !== before) { accountsPage(); toast('Connected.', 'ok'); return; }
      if (location.hash !== '#/accounts') return;
    }
  } catch (e) { toast(e.message, 'bad'); }
}

// ---------------------------------------------------------------- start

(async () => {
  try { await loadState(); } catch (e) {
    $('#main').innerHTML = `<div class="notice warn">${icon('circle-alert')}<span>${esc(e.message)}</span></div>`;
    return;
  }
  route();
  setInterval(() => loadState().catch(() => {}), 30000);
})();
