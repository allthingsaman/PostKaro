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
function accountsOf(platform) {
  return (S?.accounts || []).filter(a => a.platform === platform);
}
function postAcc(p) {                       // the account a post goes to: its own pick, else the default
  return p.account ? accountsOf(p.platform).find(a => a.account_id === p.account) : acc(p.platform);
}
function accountLine(p, draft) {
  const list = accountsOf(p.platform), a = postAcc(p);
  if (!list.length) return `Not connected. <a class="link" href="#/accounts">Connect</a>`;
  if (p.account && !a) return `<span class="to-gone">The account picked for it is no longer connected.</span>`;
  if (list.length < 2 || !draft) return `to <b>${esc(a ? a.name : '')}</b>`;
  const pick = a ? a.account_id : '';
  return `<label class="to-pick"><span>to</span>
    <select class="select select-sm" data-f="account" aria-label="${NAMES[p.platform]} account for this post">
      ${list.map(x => `<option value="${esc(x.account_id)}" ${x.account_id === pick ? 'selected' : ''}>${esc(x.name)}${
        x.active ? ' (default)' : ''}${x.status === 'broken' ? ' (login failed)' : ''}</option>`).join('')}
    </select></label>`;
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
  return local ? `${dayLabel(local)} ${local.slice(11, 16)}` : 'Now';
}
function fromNow(local) {                 // a rough "goes live in …", on this time zone's clock (S.now)
  const mins = (Date.parse(local.slice(0, 16) + ':00Z') - Date.parse((S?.now || '').slice(0, 16) + ':00Z')) / 60000;
  if (!isFinite(mins)) return {text: '', late: false};
  if (mins < 0) return {text: 'This time has passed. Pick a later one, or clear it to post at once.', late: true};
  if (mins < 60) return {text: 'Goes live in under 1 hour', late: false};
  const h = Math.round(mins / 60);
  if (h < 48) return {text: `Goes live in about ${h} hour${h === 1 ? '' : 's'}`, late: false};
  return {text: `Goes live in about ${Math.round(mins / 1440)} days`, late: false};
}
function whenHint(state, when) {
  if (['live', 'cancelled', 'failed'].includes(state)) return {text: '', late: false};
  if (!when) return {text: state === 'draft' ? 'No time: goes live as soon as you press Schedule' : '', late: false};
  return fromNow(when);
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
    case 'scheduled': return `<span class="badge info" title="${p.platform === 'instagram' && p.when ? 'Uploads up to a day before its time: ' : 'Goes out '}${esc(t)}">${icon('clock', 14)}Scheduled</span>`;
    case 'uploading': return `<span class="badge info">${icon('loader-circle', 14, 'spin')}Uploading${p.progress != null ? ' ' + Math.round(p.progress * 100) + '%' : ''}</span>`;
    case 'processing': return `<span class="badge info">${icon('loader-circle', 14, 'spin')}Processing</span>`;
    case 'waiting': return p.platform === 'instagram'
      ? `<span class="badge info" title="PostKaro publishes it at its time. Keep this computer on.">${icon('clock', 14)}Ready, publishes ${esc(time || 'now')}</span>`
      : `<span class="badge info" title="${NAMES[p.platform]} makes it live by itself">${icon('check', 14)}Uploaded, live ${esc(time ? 'at ' + time : 'soon')}</span>`;
    case 'publishing': return `<span class="badge info">${icon('loader-circle', 14, 'spin')}Publishing</span>`;
    case 'live': return `<span class="badge ok">Live</span>`;
    case 'failed': return `<span class="badge bad">${icon('circle-x', 14)}Failed</span>`;
    case 'missed': return `<span class="badge warn" title="This computer was off at its time">${icon('triangle-alert', 14)}Missed</span>`;
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
    return `<span class="mark ${st} ${p}" title="${esc(tip)}">${icon(p, 15)}</span>`;
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
addEventListener('hashchange', () => { if ($('#preview').open) $('#preview').close(); route(); window.scrollTo(0, 0); });
addEventListener('scroll', () => { const s = $('.sticky-head'); if (s) s.classList.toggle('stuck', scrollY > 24); }, {passive: true});

// ---------------------------------------------------------------- Post: the list of videos

async function home() {
  const list = await api('/batches');
  const none = PLATS.every(p => !acc(p));
  // one figure per column; a zero stays on the board, quieter
  const fig = (k, n, label, cls = '') => `<span class="fig f${k} ${n ? cls : 'zero'}"><b class="num">${n || 0}</b><small>${label}</small></span>`;
  $('#main').innerHTML = `
    <div class="page-head"><div><h1>Post</h1>
      <p class="lead">Add a video from ClipKaro, check each platform's title and caption, then schedule it.</p></div></div>
    ${none ? `<div class="notice page-notice">${icon('info')}<span>Connect your accounts first:
      <a class="link" href="#/accounts">open Accounts</a>.</span></div>` : ''}
    <div class="post-home">
    <form id="add" class="add-plate">
      <label class="field-label" for="path">Add a video</label>
      <p class="import-what" id="path-what">ClipKaro project folder or post.json</p>
      <div class="import">
        <div class="input-icon">${icon('folder-open')}<input id="path" class="input" autocomplete="off" spellcheck="false"
          aria-describedby="path-what"></div>
        <button class="btn btn-primary" id="add-btn">${icon('plus')}Add</button>
      </div>
      <p class="import-help">ClipKaro adds finished videos here by itself and ends with a “Post them” link. To add an older
        one, paste its folder, for example <code>…/Claude_Clipper/output/my-video-abc123</code>.</p>
    </form>
    <section class="section videos">
      <div class="section-head"><h2>Videos ${list.length ? `<span class="count-label">${list.length}</span>` : ''}</h2></div>
      ${list.length ? `<div class="vboard">
        <div class="vrow vhead" aria-hidden="true"><span></span><span>Video</span><span>To schedule</span><span>Scheduled</span><span>Live</span><span>Failed</span><span></span></div>
        ${list.map(b => `
        <a class="row vrow" href="#/post/${b.id}">
          ${b.first_clip ? thumb(`/media/thumb/${b.first_clip}`) : '<span class="thumb"></span>'}
          <span class="grow"><span class="title">${esc(b.title || b.project)}</span>
            <span class="sub">${b.channel ? `<span>${esc(b.channel)}</span>` : ''}<span>${b.clips} clip${b.clips === 1 ? '' : 's'}</span>${b.created ? `<span>Added ${esc(dayLabelUtc(b.created))}</span>` : ''}</span></span>
          ${fig(1, b.drafts, 'to schedule')}${fig(2, b.scheduled, 'scheduled')}${fig(3, b.live, 'live', 'live')}${fig(4, b.failed, 'failed', 'bad')}
          <span class="go">${icon('chevron-right')}</span>
        </a>`).join('')}</div>`
      : `<div class="empty">
          <h2>No videos yet</h2>
          <p>Finish a video in ClipKaro and click its “Post them” link, or paste a project folder in Add a video.</p></div>`}
    </section>
    </div>`;
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

let spreadPick = {n: '1', unit: '1440'};               // "Spread over": the last choice (1 day to start)
const SPREAD_UNITS = [['1', 'minutes'], ['60', 'hours'], ['1440', 'days']];

function fmtGap(sec) {                                  // 864 -> "14 min 24 s", 7200 -> "2 h"
  sec = Math.round(sec);
  const d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
  return [d && `${d} d`, h && `${h} h`, m && `${m} min`, s && !d && !h && `${s} s`].filter(Boolean).join(' ') || '0 s';
}

function batchBar(live) {
  // one switch per platform for every clip of the video that is still a draft
  const parts = PLATS.map(p => {
    const d = live.map(c => c.posts[p]).filter(x => x && x.state === 'draft');
    if (!d.length) return '';
    const on = d.filter(x => x.enabled).length;
    return `<label class="switch"><input type="checkbox" data-batch-plat="${p}" ${on === d.length ? 'checked' : ''}
        data-mixed="${on > 0 && on < d.length ? 1 : 0}" aria-label="${NAMES[p]} for every clip"><span class="track"></span>${pf(p)}
        <span class="plat-count">${on} of ${d.length}</span></label>`;
  }).join('');
  return parts ? `<div class="batch-bar"><span class="batch-bar-label">Platforms for all clips</span>${parts}</div>` : '';
}

async function batchPage(id) {
  const b = await api('/batch/' + id);
  const live = b.clips.filter(c => !c.removed), removed = b.clips.filter(c => c.removed);
  clearInterval(timer);                                  // a redraw keeps one refresh timer, not one more each time
  $('#main').innerHTML = `
    <div class="sticky-head">
      <a class="back" href="#/">${icon('arrow-left', 14)}All videos</a>
      <div class="page-head"><div style="min-width:0"><h1>${esc(b.title || b.project)}</h1>
        <div class="meta">${b.channel ? `<span>${esc(b.channel)}</span>` : ''}
          <span>${live.length} clip${live.length === 1 ? '' : 's'}</span>
          ${b.source_url ? `<a class="link" href="${esc(b.source_url)}" target="_blank" rel="noopener">Full video</a>` : ''}</div></div>
        <div class="actions">
          <div class="spread" title="Every clip with a platform on, one even gap apart, #1 first. The first goes when you press Schedule.">
            <label for="sp-n">Spread over</label>
            <input id="sp-n" class="input num" type="number" min="1" max="999" step="1" value="${esc(spreadPick.n)}">
            <select id="sp-unit" class="select" aria-label="Minutes, hours or days">${SPREAD_UNITS.map(([v, l]) =>
              `<option value="${v}" ${spreadPick.unit === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
            <button class="btn" id="spread">${icon('clock', 16)}Spread</button>
          </div>
          <button class="btn" id="plan" title="Fill in times: your usual time on each platform, best clips first">${icon('calendar-clock', 16)}Plan for me</button>
          <button class="btn btn-primary" id="sched">${icon('send', 16)}<span id="sched-label">Schedule</span></button>
        </div></div>
    </div>
    ${batchBar(live)}
    ${b.own ? '' : `<div class="notice warn batch-notice">${icon('triangle-alert')}<span>This video is from
      <b>${esc(b.channel)}</b>, not one of your channels. Clips of other people's videos can get copyright claims or
      less reach. You decide. Your own channels are listed in <a class="link" href="#/accounts">Accounts</a>.</span></div>`}
    <div id="clips">${live.map(c => clipHTML(c)).join('')}</div>
    ${live.length ? '' : `<div class="empty batch-notice"><h2>No clips left</h2>
      <p>Every clip of this video was removed. Restore one below.</p></div>`}
    ${removed.length ? `<section class="removed"><details class="disclose"><summary>${icon('chevron-right', 14)}Removed clips (${removed.length})</summary>
      <div class="list">${removed.map(c => `<div class="row"><span class="grow"><span class="title">#${c.no} ${esc(c.title)}</span></span>
        <button class="btn btn-sm" data-restore="${c.id}">${icon('undo-2', 14)}Restore</button></div>`).join('')}</div></details></section>` : ''}`;
  wireBatch(id);
  $$('[data-batch-plat][data-mixed="1"]').forEach(i => { i.indeterminate = true; });
  $$('[data-batch-plat]').forEach(inp => inp.onchange = async () => {
    try {
      await api(`/batch/${id}/platform`, 'POST', {platform: inp.dataset.batchPlat, enabled: inp.checked});
      await batchPage(id);
    } catch (e) { toast(e.message, 'bad'); }
  });
  updateSchedLabel();
  refreshHints();
  timer = setInterval(() => refreshStates(id), 5000);
}

function clipHTML(c) {
  return `<section class="clip" data-clip="${c.id}">
    <div class="clip-video">${c.exists
      ? `<video src="${c.media}" poster="${c.thumb}" controls preload="none" playsinline aria-label="Clip ${c.no}"></video>
        <button type="button" class="btn preview-btn" data-preview="${c.id}">${icon('maximize-2', 16)}Preview</button>${coverHTML(c)}`
      : '<div class="gone">Video file not found</div>'}</div>
    <div class="clip-body">
      <div class="clip-head"><span class="clip-no num" aria-hidden="true">${c.no}</span><div class="grow">
          <h2><span class="sr-only">Clip ${c.no}: </span>${esc(c.title)}</h2>
          <div class="meta"><span class="num">${fmtDur(c.duration)}</span>${c.score != null ? `<span>Clip score ${c.score}</span>` : ''}
            ${c.deep ? '<span>Deep clip</span>' : ''}</div></div>
        ${Object.values(c.posts).some(p => p.state === 'draft') ? `<button class="btn btn-sm" data-post-now="${c.id}"
          title="Upload this clip now to its ticked platforms; each goes live as soon as it is processed">${icon('send', 15)}Post now</button>` : ''}
        <button class="btn btn-ghost btn-icon btn-sm btn-danger" data-remove="${c.id}" title="Remove from this video" aria-label="Remove clip ${c.no}">${icon('trash-2', 16)}</button>
      </div>
      ${c.warnings.length ? `<div>${c.warnings.map(w => `<div class="notice warn">${icon('triangle-alert')}<span>${esc(w)}</span></div>`).join('')}</div>` : ''}
      ${PLATS.filter(p => c.posts[p]?.state === 'draft').length > 1 ? `<div class="clip-when">
        <label class="field-label" for="m${c.id}">Time for all platforms</label>
        <div class="clip-when-row"><input id="m${c.id}" class="input num" type="datetime-local" data-clip-when="${c.id}"
          aria-describedby="mh${c.id}"><span class="hint" id="mh${c.id}"></span></div>
        <p class="clip-when-help">Sets the same time on every platform below. Change one box to give that platform its own time.</p>
      </div>` : ''}
      <div class="lanes">${PLATS.map(p => c.posts[p] ? postHTML(c.posts[p]) : '').join('')}</div>
    </div>
  </section>`;
}

function coverHTML(c) {
  const kind = c.cover ? (c.cover_kind === 'frame' ? 'Frame' : 'Image') : 'Automatic';
  return `<div class="cover" data-cover="${c.id}">
    <div class="cover-head"><span>Thumbnail</span><span class="faint">${kind}</span></div>
    <button class="btn btn-sm" data-cover-frame="${c.id}" title="Pause the video on the frame you want, then press this">${icon('scan-eye', 14)}Use this frame</button>
    <label class="btn btn-sm">${icon('image', 14)}Upload image<input type="file" class="sr-only" accept="image/jpeg,image/png,image/webp"
      data-cover-file="${c.id}" aria-label="Upload a thumbnail image for clip ${c.no}"></label>
    ${c.cover ? `<button class="btn btn-ghost btn-sm btn-danger" data-cover-remove="${c.id}">${icon('x', 14)}Remove</button>` : ''}
    <p class="cover-text">${esc(c.cover_text)}</p>
  </div>`;
}
function showCover(clipEl, cv) {
  const v = $('video', clipEl);
  if (v) v.poster = cv.thumb;
  const box = $('.cover', clipEl);
  const tmp = document.createElement('div');
  tmp.innerHTML = coverHTML(cv);
  box.replaceWith(tmp.firstElementChild);
}
async function uploadCover(cid, file) {
  const r = await fetch(`/api/clip/${cid}/cover`, {method: 'PUT', body: file,
                                                   headers: {'X-PostKaro': KEY, 'Content-Type': file.type || 'application/octet-stream'}});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `${r.status} ${r.statusText}`);
  return j;
}

function counterText(p) {
  if (p.platform === 'youtube') return {title: `${p.title_chars}/100`, body: `${p.desc_bytes}/5000 bytes`};
  if (p.platform === 'instagram') return {body: `${p.chars}/2200, ${p.hashtags}/5 hashtags`};
  return {body: `${p.chars} characters`};
}
function postHTML(p) {
  const draft = p.state === 'draft', locked = p.state === 'live';
  const cnt = counterText(p);
  const ro = locked ? 'readonly' : '';
  const fields = p.platform === 'youtube' ? `
      <div class="field"><label class="field-label" for="t${p.id}"><span>Title</span>
        <span class="counter ${p.title_chars > 100 ? 'over' : ''}" data-cnt="title">${cnt.title}</span></label>
        <textarea id="t${p.id}" class="textarea title-box" data-f="title" rows="2" maxlength="140" ${ro}>${esc(p.title)}</textarea></div>
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
      <div class="to">${accountLine(p, draft)}</div>
      <div class="st">${stateBadge(p)}</div>
    </div>
    <div class="plat-off">Not posting to ${NAMES[p.platform]}.</div>
    <div class="plat-main">
      ${fields}
      <div class="plat-foot">
        <div class="when"><label class="sr-only" for="w${p.id}">When to post on ${NAMES[p.platform]}</label>
          <input id="w${p.id}" class="input num" type="datetime-local" data-f="when" value="${esc(p.when)}" ${ro}>
          <span class="hint${whenHint(p.state, p.when).late ? ' late' : ''}">${esc(whenHint(p.state, p.when).text)}</span></div>
        <div class="plat-actions">${actionButtons(p)}</div>
      </div>
      <ul class="msgs">${msgsHTML(p)}</ul>
    </div>
  </div>`;
}
function msgsHTML(p) {
  return p.errors.map(e => `<li class="err">${icon('circle-alert', 14)}<span>${esc(e)}</span></li>`).join('') +
    p.warnings.map(w => `<li class="warn">${icon('triangle-alert', 14)}<span>${esc(w)}</span></li>`).join('') +
    (p.error && p.state !== 'live' ? `<li class="err">${icon('circle-x', 14)}<span>${esc(p.error)}</span></li>` : '') +
    (p.note ? `<li class="warn">${icon('info', 14)}<span>${esc(p.note)}</span></li>` : '');
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
      refreshHints();
      updateSchedLabel();
      return v;
    } catch (e) { toast(e.message, 'bad'); }
  };
  clips.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.dataset.f === 'title') e.preventDefault(); });
  clips.addEventListener('input', e => {
    const f = e.target.dataset.f, row = e.target.closest('.plat');
    if (!row || !['title', 'body'].includes(f)) return;
    if (f === 'title' && /[\r\n]/.test(e.target.value)) e.target.value = e.target.value.replace(/\s*[\r\n]+\s*/g, ' ');
    liveCount(row, f, e.target.value);
    const k = row.dataset.post + f;
    (savers[k] ||= debounce(save, 700))(row, f, e.target.value);
  });
  clips.addEventListener('change', async e => {
    if (e.target.dataset.coverFile) {
      const file = e.target.files[0], clipEl = e.target.closest('.clip');
      if (!file) return;
      try { showCover(clipEl, await uploadCover(e.target.dataset.coverFile, file)); toast('Thumbnail saved.', 'ok'); }
      catch (err) { toast(err.message, 'bad'); }
      return;
    }
    if (e.target.dataset.clipWhen) {                          // the clip's main time: every draft takes it
      const value = e.target.value, rows = $$('.plat[data-state="draft"]', e.target.closest('.clip'));
      rows.forEach(r => { $('[data-f="when"]', r).value = value; });
      refreshHints();
      await Promise.all(rows.map(r => save(r, 'when', value)));
      return;
    }
    const f = e.target.dataset.f, row = e.target.closest('.plat');
    if (!row) return;
    if (f === 'enabled') { row.classList.toggle('off', !e.target.checked); updateSchedLabel(); refreshHints(); save(row, 'enabled', e.target.checked); }
    if (f === 'when') { refreshHints(); save(row, 'when', e.target.value); }
    if (f === 'account') {                                   // the default stays '' so it follows the default
      const def = acc(row.dataset.plat);
      save(row, 'account', def && def.account_id === e.target.value ? '' : e.target.value);
    }
  });
  clips.addEventListener('click', async e => {
    const pvb = e.target.closest('[data-preview]');
    if (pvb) { previewClip(pvb.dataset.preview); return; }
    const pn = e.target.closest('[data-post-now]');
    if (pn) { postClipNow(bid, pn); return; }
    const act = e.target.closest('[data-act]');
    if (act && await postAct(act.dataset.id, act.dataset.act, act)) batchPage(bid);
    const fr = e.target.closest('[data-cover-frame]');
    if (fr) {
      const clipEl = fr.closest('.clip'), v = $('video', clipEl);
      const t = v ? v.currentTime : 0;
      try {
        const cv = await busy(fr, () => api(`/clip/${fr.dataset.coverFrame}/cover-frame`, 'POST', {t}));
        showCover(clipEl, cv);
        toast(`Thumbnail set to the frame at ${fmtDur(t)}.`, 'ok');
      } catch (err) { toast(err.message, 'bad'); }
      return;
    }
    const cr = e.target.closest('[data-cover-remove]');
    if (cr) {
      try { showCover(cr.closest('.clip'), await busy(cr, () => api(`/clip/${cr.dataset.coverRemove}/cover`, 'DELETE'))); toast('Back to the automatic thumbnail.', 'ok'); }
      catch (err) { toast(err.message, 'bad'); }
      return;
    }
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
  $('#spread').onclick = async e => {
    const n = Number($('#sp-n').value), unit = $('#sp-unit').value;
    spreadPick = {n: $('#sp-n').value, unit};
    if (!(n > 0)) { $('#sp-n').focus(); return toast('Type how many minutes, hours or days to spread the clips over.', 'bad'); }
    try {
      const r = await busy(e.currentTarget, () => api(`/batch/${bid}/spread`, 'POST', {minutes: n * Number(unit)}));
      await batchPage(bid);
      const word = {1: 'minute', 60: 'hour', 1440: 'day'}[unit] + (n === 1 ? '' : 's');
      toast(`${r.clips} clips over ${n} ${word}: one every ${fmtGap(r.gap)}, #1 first (it goes when you press ` +
            `Schedule). Check the times, then press Schedule.${r.instagram && n * Number(unit) > 60
              ? ' Instagram posts need this computer on at their times.' : ''}`, 'ok', 12000);
      r.warnings.forEach(w => toast(w, 'bad', 20000));
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
    el.textContent = `${value.length}/2200, ${tags}/5 hashtags`;
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

// "Post now" on one clip: its ticked platforms upload at once, whatever time they had, and each goes
// live as soon as the platform has processed it
async function postClipNow(bid, btn) {
  const clipEl = btn.closest('.clip');
  const rows = $$('.plat[data-state="draft"]', clipEl).filter(r => $('input[data-f="enabled"]', r)?.checked);
  if (!rows.length) return toast('Tick at least one platform of this clip first.', 'bad');
  const where = rows.map(r => {
    const sel = $('select[data-f="account"]', r);
    const name = sel ? sel.selectedOptions[0].textContent.replace(/ \((default|login failed)\)/g, '') : $('.to b', r)?.textContent;
    return `${NAMES[r.dataset.plat]}${name ? ` (${name})` : ''}`;
  }).join(', ');
  if (!await confirmDialog({title: `Post #${$('.clip-no', clipEl).textContent} now?`, ok: 'Post now',
    body: `It uploads to ${where} right away, even where a time is set. Each goes live as soon as the platform ` +
          'has processed it, usually within a few minutes. Keep this computer on until the Queue shows it live.'})) return;
  try {
    const r = await busy(btn, () => api('/schedule', 'POST', {ids: rows.map(x => Number(x.dataset.post)), now: true}));
    await loadState();
    await batchPage(bid);
    if (r.skipped.length) {
      toast(`${r.scheduled} going out now. ${r.skipped.length} skipped: ` +
        r.skipped.map(s => `${NAMES[s.platform]}: ${s.why.join(' ')}`).join(' | '), 'bad', 15000);
    } else {
      toast(`Posting now on ${r.scheduled} platform${r.scheduled === 1 ? '' : 's'}. Follow it in the Queue.`, 'ok');
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
  refreshHints();
}

// "Goes live in about 5 hours" under every time, and the clip's main time kept in step with its boxes
function refreshHints() {
  for (const row of $$('#clips .plat')) {
    const hint = $('.when .hint', row), input = $('[data-f="when"]', row);
    if (!hint || !input) continue;
    const h = whenHint(row.dataset.state, input.value);
    hint.textContent = h.text;
    hint.classList.toggle('late', h.late);
  }
  for (const main of $$('#clips [data-clip-when]')) {
    const clipEl = main.closest('.clip');
    const ticked = $$('.plat[data-state="draft"]', clipEl).filter(r => $('input[data-f="enabled"]', r)?.checked);
    const times = [...new Set(ticked.map(r => $('[data-f="when"]', r).value))];
    if (document.activeElement !== main) main.value = times.length === 1 ? times[0] : '';
    const h = times.length > 1 ? {text: 'Each platform has its own time below', late: false} : whenHint('draft', times[0] || '');
    const hint = $('.clip-when .hint', clipEl);
    hint.textContent = h.text;
    hint.classList.toggle('late', h.late);
  }
}

// ---------------------------------------------------------------- Post: a clip on the big screen

// The preview shows one clip large; Previous / Next (or the arrow keys) step through the video's clips.
let pv = null;                                     // {ids: clip ids in page order, i: the one shown}
function pvClip() { return $(`#clips .clip[data-clip="${pv.ids[pv.i]}"]`); }
function previewClip(cid) {
  const d = $('#preview');
  if (!d.dataset.ready) {
    d.innerHTML = `<div class="pv">
      <div class="pv-head"><span class="pv-no" aria-hidden="true"></span><h2 id="preview-title"></h2>
        <span class="pv-count"></span>
        <button type="button" class="btn btn-icon pv-close" data-pv="close" aria-label="Close preview">${icon('x', 20)}</button></div>
      <div class="pv-stage">
        <button type="button" class="btn btn-icon pv-nav" data-pv="prev" aria-label="Previous clip">${icon('chevron-left', 22)}</button>
        <video class="pv-video" controls playsinline></video>
        <button type="button" class="btn btn-icon pv-nav" data-pv="next" aria-label="Next clip">${icon('chevron-right', 22)}</button>
      </div>
      <div class="pv-foot"><button type="button" class="btn" data-pv="frame" title="Pause on the frame you want, then press this">${icon('scan-eye', 16)}<span>Use this frame as thumbnail</span></button></div>
    </div>`;
    d.dataset.ready = '1';
    d.addEventListener('click', async e => {
      if (e.target === d) return d.close();                    // a click on the dark area around it
      const b = e.target.closest('[data-pv]');
      if (!b) return;
      if (b.dataset.pv === 'close') return d.close();
      if (b.dataset.pv === 'prev' || b.dataset.pv === 'next') return pvStep(b.dataset.pv === 'next' ? 1 : -1);
      const v = $('.pv-video', d), el = pvClip(), t = v.currentTime;
      try {
        const cv = await busy(b, () => api(`/clip/${el.dataset.clip}/cover-frame`, 'POST', {t}));
        showCover(el, cv);
        $('span', b).textContent = `Thumbnail set to ${fmtDur(t)}`;    // the label is the feedback
        setTimeout(() => { if (b.isConnected) $('span', b).textContent = 'Use this frame as thumbnail'; }, 2500);
      } catch (err) { toast(err.message, 'bad'); }
    });
    d.addEventListener('keydown', e => {
      if (e.target.tagName === 'VIDEO') return;                  // on the video the arrows move through it
      if (e.key === 'ArrowLeft') pvStep(-1);
      if (e.key === 'ArrowRight') pvStep(1);
    });
    d.addEventListener('close', () => { const v = $('.pv-video', d); v.pause(); v.removeAttribute('src'); v.load(); });
  }
  const ids = $$('#clips .clip').filter(el => $('video', el)).map(el => el.dataset.clip);
  pv = {ids, i: Math.max(0, ids.indexOf(String(cid)))};
  $$('#clips video').forEach(v => v.pause());
  pvShow();
  d.showModal();
  $('[data-pv="close"]', d).focus();
}
function pvStep(n) {
  if (!pv || pv.i + n < 0 || pv.i + n >= pv.ids.length) return;
  pv.i += n;
  pvShow();
}
function pvShow() {
  const d = $('#preview'), el = pvClip(), small = $('video', el), v = $('.pv-video', d);
  v.src = small.getAttribute('src');
  v.poster = small.poster;
  v.play().catch(() => {});
  $('.pv-no', d).textContent = $('.clip-no', el).textContent;
  $('#preview-title').textContent = $('.clip-head h2', el).textContent.replace(/^Clip \d+: /, '');
  $('.pv-count', d).textContent = `${pv.i + 1} of ${pv.ids.length}`;
  $('[data-pv="prev"]', d).disabled = pv.i === 0;
  $('[data-pv="next"]', d).disabled = pv.i === pv.ids.length - 1;
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
    ${groups.length ? `<div class="board">${QHEAD}${groups.map(g => `<section class="board-day"><h2 class="board-date">${esc(g.d)}</h2>
      <div class="list">${g.items.map(p => qRow(p, p.when ? p.when.slice(11, 16) : 'Now')).join('')}</div></section>`).join('')}</div>`
      : `<div class="empty"><h2>Nothing waiting</h2>
          <p>Scheduled posts show up here until they go live.</p>
          <a class="btn" href="#/">${icon('arrow-left', 14)}Go to Post</a></div>`}`;
  timer = setInterval(async () => {
    if (location.hash === '#/queue' && !$('#modal').open && !$('#main').contains(document.activeElement)) {
      await loadState(); queuePage();
    }
  }, 8000);
}

const QHEAD = '<div class="q-row qhead" aria-hidden="true"><span class="time">Time</span><span class="thumb-col"></span>' +
  '<span class="info">Clip</span><span class="pfcell">Platform</span><span class="status">Status</span><span class="acts"></span></div>';
function qRow(p, timeText) {
  // "#1 Short title" names the clip (the same number on its YouTube, Instagram and Facebook rows);
  // under it, what actually goes out: the YouTube title or the first line of the caption
  const first = (p.platform === 'youtube' ? p.title : p.body || '').split('\n')[0];
  let preview = first && first !== p.clip_title ? first : (p.video || '');
  if (preview.length > 72) preview = preview.slice(0, 70).trimEnd() + '…';   // one short line under the title
  return `<div class="q-row ${esc(p.state)}" data-post="${p.id}">
    <span class="time">${esc(timeText)}</span>
    ${thumb(p.thumb || `/media/thumb/${p.clip_id}`)}
    <div class="info"><a href="#/post/${p.batch}">#${p.no} ${esc(p.clip_title)}</a>
      <div class="sub">${esc(preview)}</div>
      ${p.error && p.state !== 'live' ? `<div class="why">${esc(p.error)}</div>` : ''}</div>
    <span class="pfcell">${pf(p.platform)}${accountsOf(p.platform).length > 1 && postAcc(p)
      ? `<small class="pf-to">to ${esc(postAcc(p).name)}</small>` : ''}</span>
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
    ${shown.length ? `<div class="list posted">${QHEAD}${shown.map(p => qRow(p, whenText(p.posted || p.updated))).join('')}</div>`
      : `<div class="empty">
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
        <div class="setup-acts"><label class="btn">${icon('upload', 16)}Choose file
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
        ${S.apps.meta ? `<span class="ok-line">${icon('circle-check', 14)}Meta app saved <button class="btn-link" data-delapp="meta">Replace</button></span>` : '<span></span>'}
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
          <div class="ctl"><input id="s-pd" class="input num" name="per_day" type="number" min="1" max="10" value="${s.per_day}"></div></div>
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
