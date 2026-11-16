// Organiser pages: sign-in, home tiles, create, moderators.
import { html, useState, api, get, post, navigate, Link, useLoad, attempt, toast, setOrganiserToken, scope, STAGES, stageIndex, StageBadge, fmtDate, Avatar, Field, Logo, Loading, copyText, absolute } from './lib.js';

export function Shell({ active, children }) {
  const signOut = () => { setOrganiserToken(null); navigate('/login'); };
  return html`
    <header class="top"><div class="top-in">
      <${Link} href="/" class="brand"><${Logo} /><span><b>Deliberation Partner</b><span class="small muted">Organiser workspace</span></span><//>
      <nav class="nav" aria-label="Organiser sections">
        <${Link} href="/" aria-current=${active === 'home' ? 'page' : null}>Deliberations<//>
        <${Link} href="/moderators" aria-current=${active === 'mods' ? 'page' : null}>Moderators<//>
      </nav>
      <button class="btn sm" onClick=${signOut}>Sign out</button>
    </div></header>
    <main class="page">${children}</main>`;
}

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('');
    try { const r = await post('/auth/login', { email, password }); setOrganiserToken(r.token); navigate('/'); }
    catch (err) { setError(err.message); }
    setBusy(false);
  };
  return html`<main class="page" style="max-width:440px;padding-top:72px">
    <form class="card pad col" onSubmit=${submit}>
      <div class="row"><${Logo} /><h1 style="font-size:22px">Deliberation Partner</h1></div>
      <p class="muted">Sign in as an organiser. Participants and moderators use the personal link they were sent.</p>
      ${error && html`<div class="notice err" role="alert">${error}</div>`}
      <${Field} label="Email"><input type="email" required autocomplete="username" value=${email} onInput=${e => setEmail(e.target.value)} /><//>
      <${Field} label="Password"><input type="password" required autocomplete="current-password" value=${password} onInput=${e => setPassword(e.target.value)} /><//>
      <button class="btn primary" disabled=${busy}>Sign in</button>
    </form></main>`;
}

export function nextAction(d) {
  const c = d.counts;
  if (d.stage === 'none') {
    if (!c.documents) return 'Next: add materials';
    if (!d.eval_status || d.eval_stale || d.eval_status === 'failed') return 'Next: run the evaluation';
    if (d.eval_status === 'running') return 'Evaluation running';
    if (!c.people) return 'Next: add participants';
    return 'Next: send invites';
  }
  if (d.stage === 'invited') return `Next: schedule (${c.accepted} of ${c.participants} accepted)`;
  if (d.stage === 'scheduled') return 'Next: start on ' + fmtDate(d.date, false);
  if (d.stage === 'in_progress') return 'Live now: open the session';
  if (d.stage === 'pending_debrief') return `Next: review reflections (${c.reflections} of ${c.people} in)`;
  return 'Open the debrief';
}

export function Tile({ d, href }) {
  const idx = stageIndex(d.stage);
  const mod = d.moderator ? d.moderator.name : 'Not assigned';
  return html`<${Link} href=${href} class="card tile" aria-label=${`${d.title}. ${STAGES[idx].label}. ${d.counts.documents} documents. Moderator ${mod}.`}>
    <div><div class="tiny muted">${d.process || 'Independent deliberation'}</div><h3 style="font-size:18px">${d.title}</h3></div>
    <div><${StageBadge} stage=${d.stage} /><div class="segs" aria-hidden="true">${STAGES.map((s, i) => html`<i style=${i <= idx ? 'background:' + STAGES[idx].bar : ''}></i>`)}</div></div>
    <div class="facts">
      <div><span>Documents</span><b>${d.counts.documents || 'None yet'}</b></div>
      <div><span>Participants</span><b>${d.counts.participants || 'None yet'}</b></div>
      <div><span>Moderator</span><b>${mod}</b></div>
      <div><span>Date</span><b>${d.date ? fmtDate(d.date, false) : 'Not set'}</b></div>
    </div>
    <div class="next">${nextAction(d)}</div>
  <//>`;
}

export function Home() {
  const { data, error } = useLoad(() => get('/deliberations'), []);
  const [filter, setFilter] = useState('all');
  if (!data) return html`<${Shell} active="home"><${Loading} error=${error} /><//>`;
  const shown = filter === 'all' ? data : data.filter(d => d.stage === filter);
  const live = data.filter(d => d.stage === 'in_progress').length;
  return html`<${Shell} active="home"><div class="col" style="gap:20px">
    <div class="row" style="gap:16px">
      <${Link} href="/new" class="btn primary">+ Create new<//>
      <h1>Deliberations</h1>
      <span class="muted small">${data.length} deliberation${data.length === 1 ? '' : 's'}${live ? `, ${live} live now` : ''}</span>
    </div>
    <div class="chips" role="group" aria-label="Filter by stage">
      ${[{ id: 'all', label: 'All' }, ...STAGES].map(s => html`<button class="chip" aria-pressed=${String(filter === s.id)} onClick=${() => setFilter(s.id)}>${s.label} <span style="opacity:.7">${s.id === 'all' ? data.length : data.filter(d => d.stage === s.id).length}</span></button>`)}
    </div>
    ${!data.length && html`<div class="card pad muted" style="text-align:center">No deliberations yet. Create your first one to add materials and invite participants.</div>`}
    ${data.length > 0 && !shown.length && html`<div class="card pad muted" style="text-align:center">No deliberations at this stage.</div>`}
    <div class="tiles">${shown.map(d => html`<${Tile} key=${d.id} d=${d} href=${'/d/' + d.id} />`)}</div>
  </div><//>`;
}

export function Create() {
  const mods = useLoad(() => get('/moderators'), []);
  const [f, setF] = useState({ title: '', process: '', framing_question: '', moderator_id: '', date: '' });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const valid = f.title.trim() && f.framing_question.trim();
  const submit = async (e) => {
    e.preventDefault(); if (!valid) return; setBusy(true);
    const d = await attempt(() => post('/deliberations', { ...f, moderator_id: f.moderator_id || null, date: f.date || null, process: f.process || null }));
    setBusy(false);
    if (d) navigate('/d/' + d.id);
  };
  return html`<${Shell} active="home"><div class="col narrow">
    <${Link} href="/">← All deliberations<//>
    <div><h1>Create a new deliberation</h1><p class="muted">Start with the basics. You can change any of this later, then add materials and invite participants.</p></div>
    <form class="card pad col" onSubmit=${submit}>
      <${Field} label="Title" help="What participants and moderators will see."><input type="text" value=${f.title} onInput=${set('title')} placeholder="e.g. Transport in our town" /><//>
      <${Field} label="Process or assembly" help="Optional. Groups related sessions together."><input type="text" value=${f.process} onInput=${set('process')} placeholder="e.g. Climate Assembly UK" /><//>
      <${Field} label="Framing question" help="The question the group will deliberate on. The partner uses it to stay on topic."><textarea value=${f.framing_question} onInput=${set('framing_question')}></textarea><//>
      <${Field} label="Moderator" help="You can assign one later.">
        <select value=${f.moderator_id} onChange=${set('moderator_id')}><option value="">Not assigned</option>${(mods.data || []).map(m => html`<option value=${m.id}>${m.name}</option>`)}</select><//>
      <${Field} label="Date (optional)" help="A rough date helps with planning. You confirm it on the Schedule step."><input type="date" value=${f.date} onInput=${set('date')} style="max-width:240px" /><//>
      <div class="row"><button class="btn primary" disabled=${!valid || busy}>Create and add materials</button><${Link} href="/" class="btn">Cancel<//>
        ${!valid && html`<span class="small muted">Add a title and a framing question to continue.</span>`}</div>
    </form></div><//>`;
}

export function Moderators() {
  const { data, error, set } = useLoad(() => get('/moderators'), []);
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ name: '', email: '', organisation: '' });
  const [open, setOpen] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [notice, setNotice] = useState('');
  if (!data) return html`<${Shell} active="mods"><${Loading} error=${error} /><//>`;
  const add = async (e) => {
    e.preventDefault();
    const out = await attempt(() => post('/moderators', f));
    if (out) { set(out); setAdding(false); setNotice(`Added ${f.name}. Copy their personal link and send it to them: it is how they sign in.`); setF({ name: '', email: '', organisation: '' }); }
  };
  const remove = async (m) => {
    const out = await attempt(() => api('DELETE', '/moderators/' + m.id));
    if (out) { set(out.moderators); setConfirm(null); setNotice(`${m.name} is no longer a moderator.` + (out.unassigned ? ` ${out.unassigned} current deliberation${out.unassigned === 1 ? ' is' : 's are'} now unassigned.` : '')); }
  };
  const item = (d) => html`<li><${Link} href=${'/d/' + d.id} class="card" style="display:block;padding:10px 12px;text-decoration:none;color:inherit;margin-bottom:6px">
    <b>${d.title}</b><div class="row tiny muted"><${StageBadge} stage=${d.stage} />${d.date ? fmtDate(d.date) : 'No date set'}</div><//></li>`;
  return html`<${Shell} active="mods"><div class="col" style="gap:20px;max-width:1040px">
    <div class="row" style="gap:16px"><button class="btn primary" onClick=${() => { setAdding(true); setNotice(''); }}>+ Add moderator</button><h1>Moderators</h1>
      <span class="muted small">${data.length} moderator${data.length === 1 ? '' : 's'}, ${data.filter(m => m.current.length).length} with current deliberations</span></div>
    ${notice && html`<div class="notice row" role="status"><span class="grow">${notice}</span><button class="btn link" onClick=${() => setNotice('')}>Dismiss</button></div>`}
    ${adding && html`<form class="card pad col" onSubmit=${add}>
      <div><h2>New moderator</h2><p class="small muted">They sign in with a personal link. Assign them to a deliberation from its Details step.</p></div>
      <div class="row" style="align-items:flex-start">
        <div class="grow"><${Field} label="Full name"><input type="text" required value=${f.name} onInput=${e => setF({ ...f, name: e.target.value })} /><//></div>
        <div class="grow"><${Field} label="Email"><input type="email" required value=${f.email} onInput=${e => setF({ ...f, email: e.target.value })} /><//></div>
        <div class="grow"><${Field} label="Organisation (optional)"><input type="text" value=${f.organisation} onInput=${e => setF({ ...f, organisation: e.target.value })} /><//></div>
      </div>
      <div class="row"><button class="btn primary">Add moderator</button><button type="button" class="btn" onClick=${() => setAdding(false)}>Cancel</button></div>
    </form>`}
    ${!data.length && html`<div class="card pad muted" style="text-align:center">No moderators yet. Add one to start assigning deliberations.</div>`}
    <ul class="plain col">${data.map(m => html`<li class="card" key=${m.id}>
      <div class="row" style="padding:16px 18px;gap:14px">
        <${Avatar} name=${m.name} id=${m.id} size=${44} />
        <div class="grow"><b style="font-size:16px">${m.name}</b><div class="small muted">${m.email}${m.organisation ? ' · ' + m.organisation : ''}</div></div>
        <span class="badge purple">${m.current.length} current</span><span class="badge">${m.past.length} past</span>
        <button class="btn sm" aria-expanded=${String(open === m.id)} onClick=${() => setOpen(open === m.id ? null : m.id)}>${open === m.id ? 'Hide deliberations' : 'Show deliberations'}</button>
        <button class="btn sm" onClick=${() => copyText(absolute(m.link), 'Moderator link')}>Copy sign-in link</button>
        <button class="btn sm danger" onClick=${() => setConfirm(m.id)}>Remove as moderator</button>
      </div>
      ${confirm === m.id && html`<div class="notice err col" role="alertdialog" style="margin:0 18px 16px">
        <span>Remove ${m.name} as a moderator? ${m.current.length ? `${m.current.length} current deliberation${m.current.length === 1 ? '' : 's'} (${m.current.map(d => `"${d.title}"`).join(', ')}) will become unassigned.` : 'They have no current deliberations.'}${m.past.length ? ` Their name stays on ${m.past.length} past deliberation${m.past.length === 1 ? '' : 's'}.` : ''} Their sign-in link stops working.</span>
        <div class="row"><button class="btn sm solid-danger" onClick=${() => remove(m)}>Remove ${m.name}</button><button class="btn sm" onClick=${() => setConfirm(null)}>Keep</button></div></div>`}
      ${open === m.id && html`<div class="split" style="border-top:1px solid var(--line2);padding:14px 18px">
        <div class="grow"><h3 class="tiny muted" style="margin-bottom:8px">CURRENT</h3>${m.current.length ? html`<ul class="plain">${m.current.map(item)}</ul>` : html`<p class="small muted">No current deliberations.</p>`}</div>
        <div class="grow"><h3 class="tiny muted" style="margin-bottom:8px">PAST</h3>${m.past.length ? html`<ul class="plain">${m.past.map(item)}</ul>` : html`<p class="small muted">No past deliberations.</p>`}</div>
      </div>`}
    </li>`)}</ul>
  </div><//>`;
}

// A moderator's own home, reached through their personal link.
export function ModeratorHome() {
  const s = scope();
  const me = useLoad(() => get('/me'), []);
  const { data, error } = useLoad(() => get('/deliberations'), []);
  if (!data) return html`<main class="page"><${Loading} error=${error && new Error('This moderator link is not valid any more. Ask the organiser for a new one.')} /></main>`;
  return html`<header class="top"><div class="top-in"><span class="brand"><${Logo} /><span><b>Deliberation Partner</b><span class="small muted">Moderator workspace</span></span></span>
      <span class="right">${me.data ? me.data.name + ', moderator' : ''}</span></div></header>
    <main class="page col" style="gap:20px"><h1>Your deliberations</h1>
    ${!data.length && html`<div class="card pad muted">You have not been assigned to a deliberation yet.</div>`}
    <div class="tiles">${data.map(d => html`<${Tile} key=${d.id} d=${d} href=${`${s.base}/d/${d.id}`} />`)}</div></main>`;
}
