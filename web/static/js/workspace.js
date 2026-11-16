// The organiser's workspace for one deliberation: details, materials, participants, schedule, session, debrief.
import { html, useState, useEffect, useRef, api, get, post, Link, useLoad, attempt, toast, StageBadge, stageIndex, fmtDate, Avatar, Field, Loading, copyText, absolute } from './lib.js';
import { Shell } from './organiser.js';

const STEPS = [['details', 'Details'], ['materials', 'Materials'], ['participants', 'Participants'], ['schedule', 'Schedule'], ['session', 'Session'], ['debrief', 'Debrief']];
const evalDone = (d) => d.eval && (d.eval.status === 'passed' || d.eval.status === 'below_goal') && !d.eval.stale;
function openStep(d) {
  if (d.stage === 'none') return d.documents.length && evalDone(d) ? 'participants' : 'materials';
  if (d.stage === 'invited') return 'schedule';
  if (d.stage === 'scheduled' || d.stage === 'in_progress') return 'session';
  return 'debrief';
}
function stepDone(d, id) {
  const i = stageIndex(d.stage);
  return { details: true, materials: d.documents.length > 0 && evalDone(d), participants: i >= 1, schedule: i >= 2, session: i >= 4, debrief: i >= 5 }[id];
}

export function Workspace({ id }) {
  const { data: d, error, set, reload } = useLoad(() => get('/deliberations/' + id), [id]);
  const [step, setStep] = useState(null);
  useEffect(() => { if (d && !step) setStep(openStep(d)); }, [d]);
  // Poll while an evaluation runs, and gently while people may be accepting or submitting.
  useEffect(() => {
    if (!d) return;
    const fast = d.eval && d.eval.status === 'running';
    const t = setInterval(reload, fast ? 1500 : 15000);
    return () => clearInterval(t);
  }, [d && d.eval && d.eval.status, id]);
  if (!d) return html`<${Shell} active="home"><${Loading} error=${error} /><//>`;
  const act = async (fn, next) => { const out = await attempt(fn); if (out) { set(out.deliberation || out); if (next) setStep(next); } return out; };
  const props = { d, act, setStep };
  return html`<${Shell} active="home"><div class="col" style="gap:18px">
    <${Link} href="/">← All deliberations<//>
    <div class="row" style="justify-content:space-between;align-items:flex-end">
      <div><div class="small muted">${d.process || 'Independent deliberation'}</div><h1>${d.title}</h1>
        <div class="row small" style="margin-top:6px"><${StageBadge} stage=${d.stage} /><span>Moderator: <b>${d.moderator ? d.moderator.name : 'Not assigned'}</b></span><span class="muted">${d.date ? fmtDate(d.date) : 'No date set'}</span></div></div>
      <a class="btn" href=${`/api/docs`} target="_blank" rel="noopener">API docs</a>
    </div>
    <nav class="steps" aria-label="Deliberation steps">${STEPS.map(([sid, label], i) => html`
      <button class=${'step' + (stepDone(d, sid) ? ' done' : '')} aria-current=${step === sid ? 'step' : null} onClick=${() => setStep(sid)}><i>${stepDone(d, sid) ? '✓' : i + 1}</i>${label}</button>`)}</nav>
    ${step === 'details' && html`<${Details} ...${props} />`}
    ${step === 'materials' && html`<${Materials} ...${props} />`}
    ${step === 'participants' && html`<${Participants} ...${props} />`}
    ${step === 'schedule' && html`<${Schedule} ...${props} />`}
    ${step === 'session' && html`<${SessionStep} ...${props} />`}
    ${step === 'debrief' && html`<${Debrief} ...${props} />`}
  </div><//>`;
}

function Details({ d, act }) {
  const mods = useLoad(() => get('/moderators'), []);
  const [f, setF] = useState({ title: d.title, process: d.process || '', framing_question: d.framing_question, moderator_id: d.moderator ? d.moderator.id : '' });
  const [option, setOption] = useState('');
  const save = (e) => { e.preventDefault(); act(() => api('PATCH', '/deliberations/' + d.id, { ...f, moderator_id: f.moderator_id || null })).then(o => o && toast('Details saved.')); };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const started = stageIndex(d.stage) >= 3;
  const modList = (mods.data || []).slice();
  if (d.moderator && !modList.some(m => m.id === d.moderator.id)) modList.push(d.moderator);
  return html`<div class="split">
    <form class="card pad col main" onSubmit=${save}><h2>Details</h2>
      <${Field} label="Title"><input type="text" value=${f.title} onInput=${set('title')} /><//>
      <${Field} label="Process or assembly"><input type="text" value=${f.process} onInput=${set('process')} /><//>
      <${Field} label="Framing question"><textarea value=${f.framing_question} onInput=${set('framing_question')}></textarea><//>
      <${Field} label="Moderator"><select value=${f.moderator_id} onChange=${set('moderator_id')}><option value="">Not assigned</option>${modList.map(m => html`<option value=${m.id}>${m.name}</option>`)}</select><//>
      <div><button class="btn primary">Save details</button></div>
    </form>
    <div class="card side"><div class="card-head"><div><h2 style="font-size:18px">Options on the table</h2>
      <div class="small muted">These become the first rows of the flow and the questions in the pre-survey. More rows appear as people raise them.</div></div></div>
      <ul class="plain rows">${d.options.map(o => html`<li key=${o.id}><span class="grow">${o.label}</span>
        ${!started && html`<button class="btn sm danger" aria-label=${'Remove ' + o.label} onClick=${() => act(() => api('DELETE', '/concepts/' + o.id))}>Remove</button>`}</li>`)}
        ${!d.options.length && html`<li class="muted">None yet. Add the main options people will weigh up.</li>`}</ul>
      <form class="row" style="padding:12px 20px;background:#FAFAF8;border-radius:0 0 14px 14px" onSubmit=${(e) => { e.preventDefault(); if (option.trim()) act(() => post(`/deliberations/${d.id}/concepts`, { label: option })).then(o => o && setOption('')); }}>
        <input class="grow" type="text" aria-label="New option" placeholder="e.g. A frequent flyer levy" value=${option} onInput=${e => setOption(e.target.value)} style="width:auto" />
        <button class="btn">Add option</button></form>
    </div></div>`;
}

const pct = (x) => Math.round(x * 100) + '%';
const size = (n) => n < 1000 ? `${n} characters` : `${Math.round(n / 1000)}k characters`;
const fmtMetric = (m, v) => m.metric.endsWith('_rate') ? (v * 100).toFixed(1) + '%' : Number(v).toFixed(2);

function Materials({ d, act, setStep }) {
  const [busy, setBusy] = useState(false);
  const [skipped, setSkipped] = useState([]);
  const upload = async (e) => {
    const files = Array.from(e.target.files || []).filter(f => !/(^|\/)\./.test(f.webkitRelativePath || f.name));
    e.target.value = '';
    if (!files.length) return;
    setBusy(true);
    const fd = new FormData();
    files.forEach(f => fd.append('files', f, f.name));
    const out = await act(() => post(`/deliberations/${d.id}/documents`, fd));
    setBusy(false);
    if (out) { setSkipped(out.skipped); toast(`${out.added.length} document${out.added.length === 1 ? '' : 's'} added${out.skipped.length ? `, ${out.skipped.length} skipped` : ''}.`); }
  };
  const ev = d.eval;
  const running = ev && ev.status === 'running';
  const done = ev && (ev.status === 'passed' || ev.status === 'below_goal');
  const below = done ? ev.metrics.filter(m => m.attainment < 1) : [];
  const ring = done ? (ev.health >= 90 ? '#2D7A4F' : ev.health >= 75 ? '#C98A2E' : '#B3412F') : '#C9CBC4';
  const mock = !d.models.coach.live;
  const run = () => act(() => post(`/deliberations/${d.id}/eval`));
  return html`<div class="split">
    <div class="card main"><div class="card-head"><div><h2>Materials</h2><div class="small muted">${d.documents.length ? `${d.documents.length} document${d.documents.length === 1 ? '' : 's'} uploaded` : 'Nothing uploaded yet'}. PDF, Word, text, Markdown, HTML and captions.</div></div>
      <div class="row">
        <label class="btn">${busy ? 'Uploading.' : 'Upload a folder'}<input class="sr" type="file" webkitdirectory="true" multiple onChange=${upload} disabled=${busy} /></label>
        <label class="btn">Upload files<input class="sr" type="file" multiple accept=".pdf,.docx,.txt,.md,.html,.htm,.vtt,.srt" onChange=${upload} disabled=${busy} /></label>
      </div></div>
      ${skipped.length > 0 && html`<div class="notice warn" style="margin:12px 20px 0"><b>Skipped:</b><ul style="margin:4px 0 0;padding-left:18px">${skipped.map(s => html`<li>${s.reason}</li>`)}</ul></div>`}
      ${!d.documents.length && html`<div class="muted" style="padding:32px 20px;text-align:center">No documents yet. Upload the briefings, transcripts or readings participants were given.</div>`}
      <ul class="plain rows" style="max-height:440px;overflow-y:auto">${d.documents.map(f => html`<li key=${f.id}>
        <span class="ext">${f.ext || 'file'}</span><span class="grow" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${f.file_name}</span>
        <span class="tiny muted">${size(f.chars)}, indexed</span>
        <button class="btn sm danger" aria-label=${'Remove ' + f.file_name} onClick=${() => act(() => api('DELETE', '/documents/' + f.id))}>Remove</button></li>`)}</ul>
    </div>
    <aside class="card pad col side"><h2 style="font-size:18px">Partner readiness</h2>
      ${mock && html`<div class="notice warn small">No model API key is set, so the partner and the evaluation run on the built-in mock. Scores here are placeholders until you add a key.</div>`}
      ${!ev && html`<p class="small">Run the evaluation suite against these documents before inviting anyone. It checks that the partner stays neutral, grounded and non-steering.</p>
        <button class="btn primary" disabled=${!d.documents.length} onClick=${run}>Build partner and run evaluation</button>`}
      ${running && html`<div class="row small muted" style="justify-content:space-between"><span>Running simulated conversations and judging them.</span><span>${ev.progress}%</span></div>
        <div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow=${ev.progress}><i style=${`width:${ev.progress}%`}></i></div>`}
      ${ev && ev.status === 'failed' && html`<div class="notice err small" role="alert">The evaluation failed. ${ev.error}</div><button class="btn primary" onClick=${run}>Run it again</button>`}
      ${done && html`
        ${ev.stale && html`<div class="notice warn small">Documents changed since this evaluation. Re-run it so the score reflects the current materials.</div>`}
        <div class="row" style="gap:14px"><div class="ring" role="img" aria-label=${`Health score ${Math.round(ev.health)} percent`} style=${`background:conic-gradient(${ring} 0 ${ev.health}%, #ECECE7 ${ev.health}% 100%)`}><b>${Math.round(ev.health)}%</b></div>
          <div class="col" style="gap:4px"><span class=${'badge ' + (below.length ? 'amber' : 'green')} style="align-self:flex-start">${below.length ? `${below.length} metric${below.length === 1 ? '' : 's'} below goal` : 'All metrics at goal'}</span>
            <span class="small muted">Health is the average of ${ev.metrics.length} metrics against their goals.</span></div></div>
        <table class="grid"><thead><tr><th>Metric</th><th>Result</th><th>Goal</th><th>Attained</th></tr></thead><tbody>
          ${ev.metrics.map(m => html`<tr><td>${m.label}</td><td>${fmtMetric(m, m.result)}</td><td>${m.higher_is_better ? '≥ ' : '≤ '}${fmtMetric(m, m.goal)}</td><td style=${m.attainment < 1 ? 'color:var(--red);font-weight:600' : ''}>${pct(m.attainment)}</td></tr>`)}</tbody></table>
        <p class="tiny muted">Coach ${ev.coach_model}, judge ${ev.judge_model}, prompt ${ev.prompt_version}${ev.cost_usd ? `, cost $${ev.cost_usd.toFixed(2)}` : ''}.</p>
        <div class="row"><button class="btn sm" onClick=${run}>Re-run evaluation</button>${d.stage === 'none' && html`<button class="btn primary" onClick=${() => setStep('participants')}>Next: participants</button>`}</div>`}
    </aside></div>`;
}

const STATUS = { not_invited: ['Not invited', ''], invited: ['Invited', 'amber'], accepted: ['Accepted', 'green'], cancelled: ['Invite cancelled', 'red'], declined: ['Declined', 'red'] };
function personStatus(d, p) {
  const i = stageIndex(d.stage);
  if (p.simulated) return ['AI stand-in', 'purple'];
  if (p.status === 'cancelled') return STATUS.cancelled;
  if (i >= 4) return p.post_done ? ['Reflection submitted', 'green'] : p.joined ? ['Reflection pending', 'amber'] : ['Did not take part', ''];
  if (i === 3) return p.joined ? ['In the discussion', 'green'] : p.status === 'accepted' ? ['Accepted, not yet in', 'amber'] : STATUS[p.status];
  return p.status === 'accepted' && p.pre_done ? ['Accepted, pre-survey done', 'green'] : STATUS[p.status];
}

function Participants({ d, act }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const i = stageIndex(d.stage);
  const open = d.stage === 'invited' || d.stage === 'scheduled';
  const ended = i >= 4;
  const c = d.counts;
  const add = (e) => { e.preventDefault(); act(() => post(`/deliberations/${d.id}/participants`, { name, email })).then(o => { if (o) { setName(''); setEmail(''); } }); };
  const canInvite = c.people > 0 && d.eval && (d.eval.status === 'passed' || d.eval.status === 'below_goal');
  return html`<div class="card" style="max-width:980px"><div class="card-head"><div><h2>Participants</h2>
      <div class="small muted">${!d.participants.length ? 'Nobody added yet' : i === 0 ? `${c.participants} added, not invited yet` : `${c.participants} invited, ${c.accepted} accepted${c.cancelled ? `, ${c.cancelled} cancelled` : ''}`}</div>
      ${i >= 1 && html`<div class="tiny muted">Email is not connected yet, so nothing is sent automatically. Copy each person's link and send it to them yourself.</div>`}</div>
      <div class="row">
        ${!ended && html`<button class="btn" disabled=${c.standins >= 4} onClick=${() => act(() => post(`/deliberations/${d.id}/standins`, { count: 3 }))} title="AI stand-ins fill empty seats so one person can try the discussion alone">Add AI stand-ins</button>`}
        ${d.stage === 'none' && html`<button class="btn primary" disabled=${!canInvite} onClick=${() => act(() => post(`/deliberations/${d.id}/invites`), 'schedule')}>Send invites${c.people ? ` to ${c.people}` : ''}</button>`}
      </div></div>
    ${d.stage === 'none' && c.people > 0 && !canInvite && html`<div class="notice warn small" style="margin:12px 20px 0">Run the evaluation on the Materials step before inviting anyone.</div>`}
    <ul class="plain rows">${d.participants.map(p => { const [label, cls] = personStatus(d, p); return html`<li key=${p.id}>
      <${Avatar} name=${p.name} id=${p.id} /><span class="grow" style="min-width:180px"><b>${p.name}</b> <span class="muted">${p.email || ''}</span> <span class="tiny muted">${p.pseudonym}</span></span>
      <span class=${'badge ' + cls}>${label}</span>
      ${p.link && i >= 1 && p.status !== 'cancelled' && html`<button class="btn sm" onClick=${() => copyText(absolute(p.link), 'Invite link')}>Copy invite link</button>`}
      ${open && !p.simulated && p.status !== 'cancelled' && html`<button class="btn sm danger" aria-label=${'Cancel invite for ' + p.name} onClick=${() => act(() => post(`/participants/${p.id}/cancel`))}>Cancel invite</button>`}
      ${open && p.status === 'cancelled' && html`<button class="btn sm" aria-label=${'Re-invite ' + p.name} onClick=${() => act(() => post(`/participants/${p.id}/reinvite`))}>Re-invite</button>`}
      ${(i === 0 || (p.simulated && !p.joined && !ended)) && html`<button class="btn sm danger" aria-label=${'Remove ' + p.name} onClick=${() => act(() => api('DELETE', '/participants/' + p.id))}>Remove</button>`}
    </li>`; })}</ul>
    ${!ended && html`<form class="row" onSubmit=${add} style="padding:14px 20px;background:#FAFAF8;align-items:flex-end;border-radius:0 0 14px 14px">
      <div class="grow"><${Field} label="Name"><input type="text" required value=${name} onInput=${e => setName(e.target.value)} /><//></div>
      <div class="grow"><${Field} label="Email"><input type="email" required value=${email} onInput=${e => setEmail(e.target.value)} /><//></div>
      <button class="btn">Add participant</button></form>`}
  </div>`;
}

function Schedule({ d, act }) {
  const s = d.session;
  const local = s && s.scheduled_start ? new Date(s.scheduled_start) : null;
  const pad = (n) => String(n).padStart(2, '0');
  const [date, setDate] = useState(local ? `${local.getFullYear()}-${pad(local.getMonth() + 1)}-${pad(local.getDate())}` : '');
  const [time, setTime] = useState(local ? `${pad(local.getHours())}:${pad(local.getMinutes())}` : '10:00');
  const [duration, setDuration] = useState(s && s.duration_minutes ? s.duration_minutes : 120);
  const [format, setFormat] = useState(s ? s.format : 'online');
  const i = stageIndex(d.stage);
  const locked = i >= 3;
  const submit = () => act(() => post(`/deliberations/${d.id}/schedule`, { scheduled_start: new Date(`${date}T${time}`).toISOString(), duration_minutes: Number(duration), format }), 'session').then(o => o && toast('Schedule saved.'));
  return html`<div class="card pad col narrow"><h2>Schedule</h2>
    ${i === 0 && html`<div class="notice warn small">Send invites to participants first, so they hear about the date from you.</div>`}
    ${locked && html`<div class="notice small">This deliberation has started, so the schedule is fixed.</div>`}
    <div class="row" style="align-items:flex-start">
      <div class="grow"><${Field} label="Date"><input type="date" value=${date} onInput=${e => setDate(e.target.value)} disabled=${locked} /><//></div>
      <div class="grow"><${Field} label="Start time"><input type="time" value=${time} onInput=${e => setTime(e.target.value)} disabled=${locked} /><//></div>
      <div class="grow"><${Field} label="Length"><select value=${duration} onChange=${e => setDuration(e.target.value)} disabled=${locked}><option value="60">1 hour</option><option value="90">90 minutes</option><option value="120">2 hours</option><option value="240">Half day</option></select><//></div>
      <div class="grow"><${Field} label="Where"><select value=${format} onChange=${e => setFormat(e.target.value)} disabled=${locked}><option value="online">Online</option><option value="in_person">In person</option><option value="hybrid">Hybrid</option></select><//></div>
    </div>
    ${!locked && html`<div class="row"><button class="btn primary" disabled=${i === 0 || !date || !time} onClick=${submit}>${d.stage === 'scheduled' ? 'Save changes' : 'Schedule deliberation'}</button>
      <span class="small muted">Times are in your local time zone.</span></div>`}
  </div>`;
}

function SessionStep({ d, act }) {
  const i = stageIndex(d.stage);
  const c = d.counts;
  const s = d.session;
  let text = 'Schedule the deliberation first. Once it is scheduled you can start it from here on the day.';
  if (d.stage === 'scheduled') text = `Scheduled for ${fmtDate(s.scheduled_start)}. ${c.accepted} of ${c.participants} participants have accepted${c.standins ? `, including ${c.standins} AI stand-in${c.standins === 1 ? '' : 's'}` : ''}. Moderator: ${d.moderator ? d.moderator.name : 'not assigned'}.`;
  if (d.stage === 'in_progress') text = `Live since ${fmtDate(s.started_at)}. Each participant has a private partner on the side. End the deliberation to open reflections and the debrief.`;
  if (i >= 4) text = `This deliberation ran from ${fmtDate(s.started_at)} to ${fmtDate(s.ended_at)}.`;
  return html`<div class="card pad col narrow"><h2>Session</h2><p>${text}</p>
    ${d.stage === 'scheduled' && !d.moderator && html`<div class="notice warn small">No moderator is assigned. You can still start the session, but nobody will be able to confirm flow tags or speak as moderator. Assign one on the Details step.</div>`}
    <div class="row">
      ${d.stage === 'scheduled' && html`<button class="btn primary" onClick=${() => act(() => post(`/deliberations/${d.id}/start`))}>Start the deliberation</button>`}
      ${i >= 3 && html`<${Link} href=${`/d/${d.id}/room`} class=${'btn' + (d.stage === 'in_progress' ? ' primary' : '')}>${d.stage === 'in_progress' ? 'Watch the discussion' : 'Open the transcript and flow'}<//>`}
      ${d.stage === 'in_progress' && html`<button class="btn" onClick=${() => act(() => post(`/deliberations/${d.id}/end`), 'debrief')}>End the deliberation</button>`}
    </div>
    <p class="small muted">Organisers watch and review tags. The moderator runs the room from their own link, and participants join from theirs.</p>
  </div>`;
}

function Debrief({ d, act }) {
  const i = stageIndex(d.stage);
  const c = d.counts;
  const download = async () => {
    const data = await attempt(() => get(`/deliberations/${d.id}/export`));
    if (!data) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    a.download = d.title.toLowerCase().replace(/[^a-z0-9]+/g, '-') + '-export.json';
    a.click(); URL.revokeObjectURL(a.href);
  };
  return html`<div class="card pad col narrow"><h2>Debrief</h2>
    <p>${i < 4 ? 'The debrief opens when the deliberation ends. Participants then get the reflection questionnaire, and their answers appear here.'
      : d.stage === 'pending_debrief' ? `${c.reflections} of ${c.people} participants have submitted their reflection. Review how views moved and what persuaded people, then mark the debrief complete.`
      : `Debrief complete. ${c.reflections} reflection${c.reflections === 1 ? ' was' : 's were'} submitted. The review stays available.`}</p>
    ${i >= 4 && html`<div class="row">
      <${Link} href=${`/d/${d.id}/review`} class="btn primary">Open the organiser review<//>
      <button class="btn" onClick=${download}>Download data (JSON)</button>
      ${d.stage === 'pending_debrief' && html`<button class="btn" onClick=${() => act(() => post(`/deliberations/${d.id}/complete`))}>Mark debrief complete</button>`}
    </div><p class="small muted">The download is pseudonymous: names and emails are left out, and survey answers are included only for people who agreed to research use.</p>`}
  </div>`;
}
