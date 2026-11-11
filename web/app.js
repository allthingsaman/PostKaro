// PostKaro page: Post (batches and the clip editor), Queue, Posted, Accounts (⚙). Plain JavaScript.
'use strict';

const KEY = document.querySelector('meta[name=pk-key]').content;
const NAMES = {youtube: 'YouTube', instagram: 'Instagram', facebook: 'Facebook'};
const ICONS = {youtube: '▶', instagram: '◎', facebook: 'f'};
const PLATS = ['youtube', 'instagram', 'facebook'];
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
let S = null;                  // /api/state
let timer = null;              // page refresh timer

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
function toast(text, bad = false, ms = 5000) {
  const t = $('#toast');
  t.textContent = text;
  t.className = 'show' + (bad ? ' bad' : '');
  clearTimeout(t._h);
  t._h = setTimeout(() => t.className = '', ms);
}
function fmtDur(s) {
  s = Math.round(s || 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
function niceTime(local) {        // '2026-11-12T18:00' -> 'Wed 12 Nov · 18:00'
  if (!local) return 'now';
  const d = new Date(local);
  return d.toLocaleDateString(undefined, {weekday: 'short', day: 'numeric', month: 'short'}) + ' · ' + local.slice(11, 16);
}
function acc(platform) {
  return (S?.accounts || []).find(a => a.platform === platform && a.active);
}
function debounce(fn, ms) {
  let h;
  return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); };
}

// ---------- top bar ----------

async function loadState() {
  S = await api('/state');
  $('#dots').innerHTML = PLATS.map(p => {
    const a = acc(p);
    const cls = !a ? 'off' : a.status;
    const tip = !a ? `${NAMES[p]}: not connected` : `${NAMES[p]}: ${a.name}${a.problem ? ' · ' + a.problem : ''}`;
    return `<a href="#/accounts" class="dot ${cls}" title="${esc(tip)}">${ICONS[p]}</a>`;
  }).join('');
  const n = ['scheduled', 'uploading', 'processing', 'waiting', 'publishing', 'missed']
    .reduce((t, k) => t + (S.counts[k] || 0), 0);
  $('#qcount').textContent = n ? n : '';
}

// ---------- router ----------

const ROUTES = [
  [/^#?\/?$/, home], [/^#\/post\/(\d+)$/, batchPage], [/^#\/queue$/, queuePage],
  [/^#\/posted$/, postedPage], [/^#\/accounts$/, accountsPage],
];
async function route() {
  clearInterval(timer);
  const h = location.hash || '#/';
  $$('[data-nav]').forEach(a => a.classList.toggle('on',
    h.startsWith('#/' + a.dataset.nav) || (a.dataset.nav === 'post' && (h === '#/' || h.startsWith('#/post')))));
  for (const [re, fn] of ROUTES) {
    const m = h.match(re);
    if (m) {
      try { await fn(...m.slice(1)); } catch (e) { $('#main').innerHTML = `<p class="err">${esc(e.message)}</p>`; }
      return;
    }
  }
  location.hash = '#/';
}
addEventListener('hashchange', route);

// ---------- Post: the list of videos ----------

async function home() {
  const list = await api('/batches');
  const notConnected = PLATS.filter(p => !acc(p));
  $('#main').innerHTML = `
    ${notConnected.length === 3 ? `<div class="note">Start on the <a href="#/accounts">⚙ page</a>: connect your
      YouTube channel and your Facebook Page with Instagram.</div>` : ''}
    <h1>Post</h1>
    <form class="add" id="add">
      <input id="path" placeholder="Path of a ClipKaro project folder or a post.json"
             autocomplete="off" spellcheck="false">
      <button>Add</button>
    </form>
    <p class="muted small">ClipKaro opens its clips here by itself. To add an older ClipKaro video, paste its folder,
      for example <code>…/Claude_Clipper/output/my-video-abc123</code>.</p>
    <div class="batches">${list.map(b => `
      <a class="batch" href="#/post/${b.id}">
        <b>${esc(b.title || b.project)}</b>
        <span class="muted">${esc(b.channel || '')}</span>
        <span>${b.clips} clip${b.clips === 1 ? '' : 's'} · ${b.drafts || 0} to schedule · ${b.live || 0} live</span>
      </a>`).join('') || '<p class="muted">Nothing here yet.</p>'}</div>`;
  $('#add').onsubmit = async e => {
    e.preventDefault();
    try {
      const r = await api('/import', 'POST', {path: $('#path').value});
      location.hash = '#/post/' + r.id;
    } catch (err) { toast(err.message, true); }
  };
}

// ---------- Post: one video's clips ----------

async function batchPage(id) {
  const b = await api('/batch/' + id);
  const removed = b.clips.filter(c => c.removed);
  $('#main').innerHTML = `
    <div class="bar">
      <div><a href="#/" class="muted">Post</a> › <b>${esc(b.title || b.project)}</b>
        <span class="muted">· ${b.clips.length - removed.length} clips</span></div>
      <div class="actions">
        <button id="plan" title="Fill in times: your usual time for each platform, best clips first">Plan for me</button>
        <button id="sched" class="primary">Schedule all</button>
      </div>
    </div>
    ${b.own ? '' : `<div class="note warn">⚠ This video is from <b>${esc(b.channel)}</b>, not one of your channels.
      Clips of other people's videos may get a copyright claim or less reach. You decide what to post.
      (Your own channels are listed on the <a href="#/accounts">⚙ page</a>.)</div>`}
    <div id="clips">${b.clips.filter(c => !c.removed).map(clipCard).join('')}</div>
    ${removed.length ? `<details class="removed"><summary>Removed clips (${removed.length})</summary>
      ${removed.map(c => `<div class="row"><span>#${c.no} ${esc(c.title)}</span>
        <button data-restore="${c.id}">Restore</button></div>`).join('')}</details>` : ''}`;
  wireClips(b, id);
  $('#plan').onclick = async () => {
    try { await api(`/batch/${id}/plan`, 'POST', {}); await batchPage(id); toast('Times filled in. Change any you like, then press Schedule all.'); }
    catch (e) { toast(e.message, true); }
  };
  $('#sched').onclick = () => scheduleAll(b, id);
  $$('[data-restore]').forEach(el => el.onclick = async () => {
    await api(`/clip/${el.dataset.restore}/restore`, 'POST', {}); batchPage(id);
  });
  timer = setInterval(() => refreshStates(id), 5000);
}

function clipCard(c) {
  return `<section class="clip" data-clip="${c.id}">
    <div class="vid">${c.exists ? `<video src="${c.media}" poster="${c.thumb}" controls preload="none" playsinline></video>`
                                : '<div class="gone">video file not found</div>'}</div>
    <div class="body">
      <div class="head">
        <h2>#${c.no} ${esc(c.title)}</h2>
        <span class="muted">${fmtDur(c.duration)}${c.score != null ? ` · score ${c.score}` : ''}${c.deep ? ' · deep clip' : ''}</span>
        <button class="icon" data-remove="${c.id}" title="Remove this clip from the batch">🗑</button>
      </div>
      ${c.warnings.map(w => `<p class="warn">⚠ ${esc(w)}</p>`).join('')}
      ${PLATS.map(p => c.posts[p] ? postBox(c.posts[p]) : '').join('')}
    </div>
  </section>`;
}

function stateText(p) {
  const t = niceTime(p.when);
  return {
    draft: '', scheduled: p.platform === 'instagram' && p.when ? `scheduled for ${t} (uploads up to a day before)`
      : `scheduled for ${t}`,
    uploading: `uploading${p.progress != null ? ' ' + Math.round(p.progress * 100) + '%' : ''}…`,
    processing: `${NAMES[p.platform]} is processing the video…`,
    waiting: p.platform === 'instagram' ? `uploaded · PostKaro publishes it at ${t} (keep the laptop on)`
      : `uploaded · goes live at ${t} by itself`,
    publishing: 'publishing…', live: 'live', failed: 'failed', missed: 'missed its time (the laptop was off)',
    cancelled: 'cancelled',
  }[p.state] ?? p.state;
}

function postBox(p) {
  const a = acc(p.platform);
  const locked = p.state !== 'draft';
  const counter = p.platform === 'youtube' ? '' : p.platform === 'instagram'
    ? `<span class="cnt ${p.chars > 2200 || p.hashtags > 5 ? 'over' : ''}">${p.chars}/2200 · ${p.hashtags} of 5 hashtags</span>`
    : `<span class="cnt">${p.chars} characters</span>`;
  let fields;
  if (p.platform === 'youtube') {
    fields = `<label>Title <span class="cnt ${p.title_chars > 100 ? 'over' : ''}" data-cnt="title">${p.title_chars}/100</span>
        <input data-f="title" value="${esc(p.title)}" maxlength="140" ${locked && p.state !== 'scheduled' ? '' : ''}></label>
      <details ${p.body ? '' : ''}><summary>Description (optional)</summary>
        <textarea data-f="body" rows="4">${esc(p.body)}</textarea>
        <span class="cnt ${p.desc_bytes > 5000 ? 'over' : ''}" data-cnt="body">${p.desc_bytes}/5000 bytes</span></details>`;
  } else {
    fields = `<label>Caption ${counter}<textarea data-f="body" rows="3">${esc(p.body)}</textarea></label>`;
  }
  const actions = {
    scheduled: ['cancel'], processing: ['cancel'], waiting: ['cancel'], failed: ['retry', 'draft'],
    missed: ['now', 'newtime', 'skip'], cancelled: ['draft'],
  }[p.state] || [];
  const LABEL = {cancel: 'Cancel', retry: 'Retry', draft: 'Back to drafts', now: 'Post now',
                 newtime: 'New time', skip: 'Skip'};
  return `<div class="post ${p.platform} ${p.enabled ? '' : 'off'} st-${p.state}" data-post="${p.id}" data-plat="${p.platform}">
    <div class="phead">
      <label class="tick"><input type="checkbox" data-f="enabled" ${p.enabled ? 'checked' : ''} ${locked ? 'disabled' : ''}>
        <span class="pi">${ICONS[p.platform]}</span> ${NAMES[p.platform]}</label>
      ${a ? '' : `<span class="muted small">not connected · <a href="#/accounts">connect</a></span>`}
      <span class="state">${p.state === 'live' && p.url ? `✅ <a href="${esc(p.url)}" target="_blank" rel="noopener">live</a>`
        : esc(stateText(p))}</span>
    </div>
    <div class="pbody">
      ${fields}
      <label class="when">When <input type="datetime-local" data-f="when" value="${esc(p.when)}">
        <span class="muted small">${p.when ? '' : 'empty = as soon as you press Schedule'}</span></label>
      <ul class="msgs">${p.errors.map(e => `<li class="err">${esc(e)}</li>`).join('')}
        ${p.warnings.map(w => `<li class="warn">${esc(w)}</li>`).join('')}
        ${p.error && p.state !== 'live' ? `<li class="err">${esc(p.error)}</li>` : ''}</ul>
      ${actions.length ? `<div class="pact">${actions.map(x => `<button data-act="${x}">${LABEL[x]}</button>`).join('')}</div>` : ''}
    </div>
  </div>`;
}

function wireClips(b, bid) {
  $$('[data-remove]').forEach(el => el.onclick = async () => {
    if (!confirm('Remove this clip from the batch? Its scheduled posts are cancelled. You can restore it later.')) return;
    try { await api(`/clip/${el.dataset.remove}/remove`, 'POST', {}); batchPage(bid); } catch (e) { toast(e.message, true); }
  });
  $$('.post').forEach(box => {
    const pid = box.dataset.post;
    const save = async (field, value) => {
      try {
        const v = await api('/post/' + pid, 'PATCH', {[field]: value});
        replacePost(box, v);
      } catch (e) { toast(e.message, true); }
    };
    const later = debounce(save, 700);
    $$('[data-f]', box).forEach(inp => {
      const f = inp.dataset.f;
      if (f === 'enabled') inp.onchange = () => save('enabled', inp.checked);
      else if (f === 'when') inp.onchange = () => save('when', inp.value);
      else inp.oninput = () => { liveCount(box, f, inp.value); later(f, inp.value); };
    });
    $$('[data-act]', box).forEach(btn => btn.onclick = () => postAct(pid, btn.dataset.act, bid));
  });
}

function liveCount(box, field, value) {
  const plat = box.dataset.plat;
  if (plat === 'youtube') {
    const el = $(`[data-cnt="${field}"]`, box);
    if (field === 'title') { el.textContent = `${value.length}/100`; el.classList.toggle('over', value.length > 100); }
    else { const n = new TextEncoder().encode(value).length; el.textContent = `${n}/5000 bytes`; el.classList.toggle('over', n > 5000); }
  } else {
    const el = $('.cnt', box);
    if (plat !== 'instagram') { el.textContent = `${value.length} characters`; return; }
    const tags = (value.match(/(^|[^\w#])#[^\s#.,!?;:()\[\]{}"'।]+/g) || []).length;
    el.textContent = `${value.length}/2200 · ${tags} of 5 hashtags`;
    el.classList.toggle('over', value.length > 2200 || tags > 5);
  }
}

function replacePost(box, v) {
  // keep what the user is typing: only refresh messages, state and counters
  $('.msgs', box).innerHTML = v.errors.map(e => `<li class="err">${esc(e)}</li>`).join('') +
    v.warnings.map(w => `<li class="warn">${esc(w)}</li>`).join('') +
    (v.error && v.state !== 'live' ? `<li class="err">${esc(v.error)}</li>` : '');
  box.classList.toggle('off', !v.enabled);
  $('.state', box).innerHTML = v.state === 'live' && v.url ? `✅ <a href="${esc(v.url)}" target="_blank" rel="noopener">live</a>`
    : esc(stateText(v));
  const hint = $('.when .muted', box);
  if (hint) hint.textContent = v.when ? '' : 'empty = as soon as you press Schedule';
}

async function postAct(pid, act, bid) {
  try {
    if (act === 'newtime') {
      const when = prompt('New time (YYYY-MM-DD HH:MM, your time zone):', S.now.replace('T', ' '));
      if (!when) return;
      await api(`/post/${pid}/time`, 'POST', {when: when.trim().replace(' ', 'T')});
    } else {
      if (act === 'cancel' && !confirm('Cancel this post? If it is already uploaded, PostKaro removes it from the platform.')) return;
      await api(`/post/${pid}/${act}`, 'POST', {});
    }
    await loadState();
    bid ? batchPage(bid) : route();
  } catch (e) { toast(e.message, true); }
}

async function scheduleAll(b, bid) {
  const drafts = b.clips.filter(c => !c.removed).flatMap(c => PLATS.map(p => c.posts[p]))
    .filter(p => p && p.state === 'draft' && p.enabled);
  if (!drafts.length) return toast('Nothing ticked to schedule.');
  const now = drafts.filter(p => !p.when).length;
  if (!confirm(`Schedule ${drafts.length} post${drafts.length === 1 ? '' : 's'}?` +
               (now ? `\n${now} of them have no time and go out right away.` : ''))) return;
  try {
    const r = await api('/schedule', 'POST', {batch: Number(bid)});
    await loadState();
    await batchPage(bid);
    let msg = `${r.scheduled} scheduled${r.now ? ` (${r.now} going out now)` : ''}.`;
    if (r.skipped.length) msg += ` ${r.skipped.length} skipped: ` +
      r.skipped.map(s => `#${s.clip} ${NAMES[s.platform]}: ${s.why.join(' ')}`).join(' | ');
    toast(msg, r.skipped.length > 0, r.skipped.length ? 15000 : 5000);
  } catch (e) { toast(e.message, true); }
}

async function refreshStates(bid) {
  if (!location.hash.startsWith('#/post/')) return;
  const b = await api('/batch/' + bid).catch(() => null);
  if (!b) return;
  for (const c of b.clips) for (const p of Object.values(c.posts)) {
    const box = $(`.post[data-post="${p.id}"]`);
    if (!box) continue;
    const shown = [...box.classList].find(k => k.startsWith('st-'));
    if (shown !== 'st-' + p.state) {                 // state changed: redraw this platform's box
      const tmp = document.createElement('div');
      tmp.innerHTML = postBox(p);
      box.replaceWith(tmp.firstElementChild);
      wireClips(b, bid);
    } else if (p.state === 'uploading') {
      $('.state', box).textContent = stateText(p);
    }
  }
}

// ---------- Queue ----------

async function queuePage() {
  const list = await api('/queue');
  let day = '';
  const rows = list.map(p => {
    const d = p.when ? new Date(p.when).toLocaleDateString(undefined, {weekday: 'short', day: 'numeric', month: 'short'}) : 'Now';
    const head = d !== day ? `<h3>${esc(d)}</h3>` : '';
    day = d;
    const acts = p.state === 'missed' ? ['now', 'newtime', 'skip'] : ['cancel'];
    const LABEL = {cancel: 'Cancel', now: 'Post now', newtime: 'New time', skip: 'Skip'};
    return head + `<div class="qrow st-${p.state}" data-post="${p.id}">
      <span class="t">${p.when ? p.when.slice(11, 16) : 'now'}</span>
      <span class="pi ${p.platform}" title="${NAMES[p.platform]}">${ICONS[p.platform]}</span>
      <a href="#/post/${p.batch}" class="ttl">#${p.no} ${esc(p.clip_title)} <span class="muted">· ${esc(p.video)}</span></a>
      <span class="state">${esc(stateText(p))}${p.error ? ` <span class="err small">(${esc(p.error)})</span>` : ''}</span>
      <span class="acts">${acts.map(a => `<button data-act="${a}">${LABEL[a]}</button>`).join('')}</span>
    </div>`;
  }).join('');
  $('#main').innerHTML = `<h1>Queue</h1>${rows || '<p class="muted">Nothing waiting. Schedule clips on the Post page.</p>'}
    <p class="muted small">YouTube and Facebook posts are uploaded right away and go live by themselves, even with
    the laptop off. Instagram can't schedule on its side: PostKaro publishes those at their time, so the laptop
    must be on then.</p>`;
  $$('.qrow').forEach(r => $$('[data-act]', r).forEach(b => b.onclick = () => postAct(r.dataset.post, b.dataset.act)));
  timer = setInterval(async () => { if (location.hash === '#/queue') { await loadState(); queuePage(); } }, 8000);
}

// ---------- Posted ----------

async function postedPage() {
  const list = await api('/posted');
  $('#main').innerHTML = `<h1>Posted</h1>${list.map(p => `
    <div class="qrow st-${p.state}" data-post="${p.id}">
      <span class="t">${esc((p.posted || p.updated).replace('T', ' '))}</span>
      <span class="pi ${p.platform}" title="${NAMES[p.platform]}">${ICONS[p.platform]}</span>
      <a href="#/post/${p.batch}" class="ttl">#${p.no} ${esc(p.clip_title)} <span class="muted">· ${esc(p.video)}</span></a>
      <span class="state">${p.state === 'live' ? (p.url ? `✅ <a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.url.replace(/^https?:\/\/(www\.)?/, ''))}</a>` : '✅ live')
        : p.state === 'failed' ? `❌ ${esc(p.error || 'failed')}` : 'cancelled'}</span>
      <span class="acts">${p.state === 'failed' ? '<button data-act="retry">Retry</button><button data-act="draft">Back to drafts</button>'
        : p.state === 'cancelled' ? '<button data-act="draft">Back to drafts</button>' : ''}</span>
    </div>`).join('') || '<p class="muted">Nothing posted yet.</p>'}`;
  $$('.qrow').forEach(r => $$('[data-act]', r).forEach(b => b.onclick = () => postAct(r.dataset.post, b.dataset.act)));
}

// ---------- Accounts and settings (⚙) ----------

async function accountsPage() {
  await loadState();
  const s = S.settings;
  const list = p => S.accounts.filter(a => a.platform === p);
  const accRow = a => `<div class="acc ${a.status}">
      <span class="dot ${a.status}">${ICONS[a.platform]}</span>
      <b>${esc(a.name)}</b>${a.username ? ` <span class="muted">@${esc(a.username)}</span>` : ''}
      ${a.active ? '' : `<button data-activate="${a.platform}|${a.account_id}">Use this one</button>`}
      <span class="muted small">${a.problem ? esc(a.problem) : 'login OK'}${a.checked ? ' · checked ' + esc(a.checked.slice(0, 16).replace('T', ' ')) + ' UTC' : ''}</span>
      <span class="acts"><button data-check="${a.platform}|${a.account_id}">Check now</button>
        <button data-disconnect="${a.platform}|${a.account_id}">Disconnect</button></span>
    </div>`;
  $('#main').innerHTML = `
    <h1>Accounts</h1>
    <p class="muted small">Logins are kept in: <b>${esc(S.vault.where)}</b>. ${S.vault.ok ? '' : `<span class="err">${esc(S.vault.problem || '')}</span>`}
      They never leave this laptop. The step-by-step guide is <code>docs/connect-accounts.md</code> in the PostKaro folder.</p>

    <section class="card">
      <h2>▶ YouTube</h2>
      ${S.apps.google ? `<p class="ok small">✓ Your Google app is saved. <button class="link" data-delapp="google">Replace it</button></p>`
        : `<p>First, your own Google app (one time, about 10 minutes, guide part A). Then paste the downloaded
           <code>client_secret_….json</code> here, or pick the file:</p>
           <textarea id="gjson" rows="3" placeholder='{"installed":{"client_id":"…","client_secret":"…"}}'></textarea>
           <input type="file" id="gfile" accept=".json,application/json"> <button id="gsave">Save</button>`}
      ${list('youtube').map(accRow).join('')}
      <button class="primary" data-connect="google" ${S.apps.google ? '' : 'disabled'}>${list('youtube').length ? 'Reconnect / add a channel' : 'Connect YouTube'}</button>
    </section>

    <section class="card">
      <h2>◎ Instagram and f Facebook Page</h2>
      ${S.apps.meta ? `<p class="ok small">✓ Your Meta app is saved. <button class="link" data-delapp="meta">Replace it</button></p>`
        : `<p>First, your own Meta app (one time, about 20 minutes, guide part B). Then paste its App ID and App Secret:</p>
           <div class="row"><input id="mid" placeholder="App ID" inputmode="numeric">
           <input id="msecret" placeholder="App Secret" type="password" autocomplete="off"><button id="msave">Save</button></div>`}
      <p class="muted small">In the Meta app, the login redirect must be exactly <code>${esc(S.redirects.meta)}</code></p>
      ${[...list('instagram'), ...list('facebook')].map(accRow).join('')}
      <button class="primary" data-connect="meta" ${S.apps.meta ? '' : 'disabled'}>${list('facebook').length ? 'Reconnect' : 'Connect Facebook and Instagram'}</button>
      <p class="muted small">One Meta login connects both. Your Instagram must be a Creator or Business account linked to your Facebook Page.</p>
    </section>

    <section class="card"><h2>𝕏 X</h2><p class="muted">Coming later.</p></section>

    <h1>Posting defaults</h1>
    <form class="card settings" id="sets">
      <label>Time zone <input name="timezone" value="${esc(s.timezone)}"></label>
      <label>Clips per day on each platform <input name="per_day" type="number" min="1" max="10" value="${s.per_day}"></label>
      <div class="row">${PLATS.map(p => `<label>${NAMES[p]} usual time
        <input type="time" name="time_${p}" value="${esc((s.times[p] || ['18:00'])[0])}"></label>`).join('')}</div>
      <label>My channels (no "not your video" warning; one per line)
        <textarea name="my_channels" rows="2">${esc((s.my_channels || []).join('\n'))}</textarea></label>
      <div class="row">
        <label>YouTube: made for kids <select name="youtube_made_for_kids"><option value="false">No</option>
          <option value="true" ${s.youtube_made_for_kids ? 'selected' : ''}>Yes</option></select></label>
        <label>YouTube visibility <select name="youtube_visibility">${['public', 'unlisted', 'private'].map(v =>
          `<option ${s.youtube_visibility === v ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
        <label>YouTube category <select name="youtube_category">${[['24', 'Entertainment'], ['22', 'People & Blogs'],
          ['27', 'Education'], ['20', 'Gaming'], ['25', 'News & Politics'], ['23', 'Comedy'], ['28', 'Science & Technology'],
          ['1', 'Film & Animation']].map(([v, n]) => `<option value="${v}" ${s.youtube_category === v ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
      </div>
      <label class="tick"><input type="checkbox" name="youtube_notify_subscribers" ${s.youtube_notify_subscribers ? 'checked' : ''}> YouTube: tell subscribers about new Shorts</label>
      <label class="tick"><input type="checkbox" name="youtube_full_video_line" ${s.youtube_full_video_line ? 'checked' : ''}> Add "Full video: link" to new YouTube descriptions</label>
      <label>Instagram, when the laptop was off at posting time <select name="late">
        <option value="ask" ${s.late === 'ask' ? 'selected' : ''}>Ask me</option>
        <option value="post" ${s.late === 'post' ? 'selected' : ''}>Post it as soon as the laptop is back on</option></select></label>
      <button class="primary">Save</button>
    </form>`;
  wireAccounts();
}

function wireAccounts() {
  const gsave = $('#gsave');
  if (gsave) {
    $('#gfile').onchange = async e => { $('#gjson').value = await e.target.files[0].text(); };
    gsave.onclick = async () => {
      try { await api('/apps/google', 'POST', {client: $('#gjson').value}); toast('Google app saved.'); accountsPage(); }
      catch (e) { toast(e.message, true); }
    };
  }
  const msave = $('#msave');
  if (msave) msave.onclick = async () => {
    try { await api('/apps/meta', 'POST', {app_id: $('#mid').value, app_secret: $('#msecret').value}); toast('Meta app saved.'); accountsPage(); }
    catch (e) { toast(e.message, true); }
  };
  $$('[data-delapp]').forEach(b => b.onclick = async () => {
    if (!confirm('Forget this app\'s ID and secret? Connected accounts keep working until you reconnect.')) return;
    await api('/apps/' + b.dataset.delapp, 'DELETE'); accountsPage();
  });
  $$('[data-connect]').forEach(b => b.onclick = () => connect(b.dataset.connect));
  const acct = (attr, action, ask) => $$(`[data-${attr}]`).forEach(b => b.onclick = async () => {
    if (ask && !confirm(ask)) return;
    const [p, id] = b.dataset[attr].split('|');
    try { await api(`/account/${p}/${encodeURIComponent(id)}/${action}`, 'POST', {}); accountsPage(); }
    catch (e) { toast(e.message, true); }
  });
  acct('check', 'check');
  acct('activate', 'activate');
  acct('disconnect', 'disconnect', 'Disconnect this account? PostKaro forgets its login and asks the platform to cancel its access. Scheduled posts for it will fail until you connect again.');
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
    try { await api('/settings', 'PUT', body); toast('Saved.'); loadState(); } catch (err) { toast(err.message, true); }
  };
}

async function connect(name) {
  const before = JSON.stringify(S.accounts);
  try {
    const r = await api('/connect/' + name, 'POST', {});
    window.open(r.url, '_blank', 'noopener');
    toast('Finish the login in the new tab. This page updates when it is done.', false, 10000);
    for (let i = 0; i < 90; i++) {                        // up to 3 minutes
      await new Promise(res => setTimeout(res, 2000));
      await loadState();
      if (JSON.stringify(S.accounts) !== before) { accountsPage(); toast('Connected.'); return; }
      if (location.hash !== '#/accounts') return;
    }
  } catch (e) { toast(e.message, true); }
}

// ---------- start ----------

(async () => {
  try { await loadState(); } catch (e) { $('#main').innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
  route();
  setInterval(() => loadState().catch(() => {}), 30000);
})();
