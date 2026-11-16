// The participant's journey through their invite link: welcome, pre-survey, prepare, discuss, reflect.
import { html, useState, useEffect, get, post, useLoad, attempt, fmtDate, Field, Logo, Loading } from './lib.js';
import { Room, PartnerChat } from './room.js';

const STEPS = [['welcome', 'Welcome'], ['pre', 'Before you start'], ['prepare', 'Prepare'], ['discuss', 'Discuss'], ['reflect', 'Reflect']];
const VIEWS = [['support', 'Support'], ['oppose', 'Oppose'], ['undecided', 'Undecided']];
const SCALE = [1, 2, 3, 4, 5];

function Choice({ name, options, value, onChange }) {
  return html`<div class="choice" role="radiogroup">${options.map(([v, label]) => html`<label><input type="radio" name=${name} checked=${value === v} onChange=${() => onChange(v)} />${label}</label>`)}</div>`;
}

export function Participant() {
  const { data: st, error, set, reload } = useLoad(() => get('/p/state'), []);
  const [step, setStep] = useState(null);
  const stage = st && st.deliberation.stage;
  const pick = (s) => s.status !== 'accepted' ? 'welcome' : !s.pre_done && !['pending_debrief', 'complete'].includes(s.deliberation.stage) ? 'pre'
    : s.deliberation.stage === 'in_progress' ? 'discuss' : ['pending_debrief', 'complete'].includes(s.deliberation.stage) ? 'reflect' : 'prepare';
  useEffect(() => { if (st && !step) setStep(pick(st)); }, [st]);
  useEffect(() => { if (st && step) setStep(pick(st)); }, [stage]);  // move along when the session starts or ends
  useEffect(() => { const t = setInterval(reload, 12000); return () => clearInterval(t); }, []);
  if (!st) return html`<main class="page narrow"><${Loading} error=${error && new Error('This invite link is not valid. It may have been cancelled. Ask the organiser for a new one.')} /></main>`;
  const d = st.deliberation;
  const accepted = st.status === 'accepted';
  const enabled = { welcome: true, pre: accepted, prepare: accepted, discuss: accepted, reflect: accepted };
  const done = { welcome: accepted, pre: st.pre_done, prepare: false, discuss: ['pending_debrief', 'complete'].includes(d.stage), reflect: st.post_done };
  return html`<header class="top"><div class="top-in"><span class="brand"><${Logo} /><span><b>${d.title}</b><span class="small muted">${d.process || 'Deliberation'}</span></span></span>
      <span class="right small">${st.name}</span></div></header>
    <main class="page col" style="gap:18px">
      <nav class="steps" aria-label="Your steps">${STEPS.map(([sid, label], i) => html`<button class=${'step' + (done[sid] ? ' done' : '')} disabled=${!enabled[sid]} aria-current=${step === sid ? 'step' : null} onClick=${() => setStep(sid)}><i>${done[sid] ? '✓' : i + 1}</i>${label}</button>`)}</nav>
      ${step === 'welcome' && html`<${Welcome} st=${st} onDone=${(s) => { set(s); setStep(s.pre_done ? 'prepare' : 'pre'); }} />`}
      ${step === 'pre' && html`<${PreSurvey} st=${st} onDone=${(s) => { set(s); setStep('prepare'); }} />`}
      ${step === 'prepare' && html`<${Prepare} st=${st} />`}
      ${step === 'discuss' && (d.stage === 'in_progress' || ['pending_debrief', 'complete'].includes(d.stage) ? html`<${Room} id=${d.id} embedded=${true} />`
        : html`<div class="card pad narrow col"><h2>The discussion has not started yet</h2><p>${st.session && st.session.scheduled_start ? `It is scheduled for ${fmtDate(st.session.scheduled_start)}.` : 'The organiser has not set a date yet.'} Keep this page open: it moves to the discussion by itself when the moderator starts it.</p>
          <div><button class="btn" onClick=${() => setStep('prepare')}>Keep preparing with your partner</button></div></div>`)}
      ${step === 'reflect' && html`<${Reflect} st=${st} onDone=${reload} />`}
    </main>`;
}

function Welcome({ st, onDone }) {
  const d = st.deliberation;
  const [consent, setConsent] = useState(false);
  const accepted = st.status === 'accepted';
  return html`<div class="card pad col narrow"><h1 style="font-size:24px">Welcome, ${st.name.split(' ')[0]}</h1>
    <p>You have been invited to take part in <b>${d.title}</b>${d.process ? `, part of ${d.process}` : ''}.</p>
    <div class="notice"><b>The question:</b> ${d.framing_question}</div>
    <p class="small muted">${st.session && st.session.scheduled_start ? `Scheduled for ${fmtDate(st.session.scheduled_start)}.` : 'The date will be confirmed soon.'}${d.moderator ? ` Moderator: ${d.moderator}.` : ''}</p>
    <p>You get a private AI partner. It can explain the briefing materials and help you put your thoughts into words. It will not tell you what to think, and nobody else sees what you ask it.</p>
    ${accepted ? html`<p class="badge green" style="align-self:flex-start">You have accepted this invite</p>` : html`
      <label class="row" style="align-items:flex-start;gap:8px"><input type="checkbox" checked=${consent} onChange=${e => setConsent(e.target.checked)} style="margin-top:4px" />
        <span>Optional: my survey answers may be used for research, without my name.</span></label>
      <div><button class="btn primary" onClick=${() => attempt(() => post('/p/accept', { consent_research: consent })).then(s => s && onDone(s))}>Accept and continue</button></div>`}
  </div>`;
}

function PreSurvey({ st, onDone }) {
  const [level, setLevel] = useState(st.knowledge_level || 'some');
  const [hopes, setHopes] = useState('');
  const [views, setViews] = useState({});
  const submit = (e) => {
    e.preventDefault();
    const stances = Object.entries(views).filter(([, v]) => v.value).map(([concept_id, v]) => ({ concept_id, value: v.value, certainty: v.certainty || null }));
    attempt(() => post('/p/pre-survey', { knowledge_level: level, hopes, stances })).then(s => s && onDone(s));
  };
  const setView = (id, patch) => setViews(v => ({ ...v, [id]: { ...(v[id] || {}), ...patch } }));
  return html`<form class="card pad col narrow" onSubmit=${submit}><h2>Before you start</h2>
    <p class="muted">Three quick questions. Your answers are private: other participants never see them, and the moderator does not see them during the discussion.</p>
    ${st.pre_done && html`<div class="notice small">You have already answered. Submitting again updates your answers.</div>`}
    <fieldset style="border:0;padding:0;margin:0" class="col"><legend style="font-weight:600;padding:0">How familiar are you with this topic?</legend>
      <${Choice} name="level" value=${level} onChange=${setLevel} options=${[['novice', 'New to it'], ['some', 'I know a little'], ['informed', 'Well read'], ['expert', 'I work on it']]} /></fieldset>
    ${st.options.length > 0 && html`<div class="col"><b>Where do you stand right now?</b>
      ${st.options.map(o => html`<div class="card" style="padding:12px 14px" key=${o.id}><div style="font-weight:600;margin-bottom:6px">${o.label}</div>
        <${Choice} name=${'v' + o.id} value=${(views[o.id] || {}).value} onChange=${(v) => setView(o.id, { value: v })} options=${VIEWS} />
        <div class="row small" style="margin-top:8px"><span class="muted">How sure are you?</span><${Choice} name=${'c' + o.id} value=${(views[o.id] || {}).certainty} onChange=${(v) => setView(o.id, { certainty: v })} options=${SCALE.map(n => [n, n === 1 ? '1 not sure' : n === 5 ? '5 very sure' : String(n)])} /></div></div>`)}</div>`}
    <${Field} label="What do you most want to understand before the discussion?" help="Optional."><textarea value=${hopes} onInput=${e => setHopes(e.target.value)}></textarea><//>
    <div><button class="btn primary">Save and continue</button></div></form>`;
}

function Prepare({ st }) {
  return html`<div class="split">
    <section class="card main"><div class="card-head"><div><h2>Prepare with your partner</h2><div class="small muted">Ask anything about the materials or the question. Private to you.</div></div></div>
      ${!st.partner_live && html`<div class="notice warn small" style="margin:12px 16px 0">Demo mode: no AI model is connected, so the partner gives placeholder answers.</div>`}
      <${PartnerChat} sessionMode=${false} /></section>
    <aside class="card side"><div class="card-head"><h2 style="font-size:18px">Materials</h2></div>
      <ul class="plain rows">${st.documents.map(x => html`<li><span class="grow">${x.file_name}</span><span class="tiny muted">${x.chars < 1000 ? x.chars : Math.round(x.chars / 1000) + 'k'} characters</span></li>`)}
        ${!st.documents.length && html`<li class="muted">The organiser has not added materials yet.</li>`}</ul>
      <p class="small muted" style="padding:12px 20px">Your partner draws on these documents and shows which one each answer came from.</p></aside></div>`;
}

function Reflect({ st, onDone }) {
  const { data: form, error, reload } = useLoad(() => get('/p/reflection'), [st.deliberation.stage]);
  const [topics, setTopics] = useState({});
  const [answers, setAnswers] = useState({ partner_pushed: 'no', follow_up_ok: false });
  if (!form) return html`<${Loading} error=${error} />`;
  if (!form.open) return html`<div class="card pad narrow"><h2>Reflection</h2><p>The reflection opens when the discussion ends.</p></div>`;
  if (form.submitted) return html`<div class="card pad narrow col"><h2>Thank you</h2><p>Your reflection has been submitted. The organisers will use it, alongside everyone else's, to understand how the discussion went.</p></div>`;
  const setT = (id, patch) => setTopics(t => ({ ...t, [id]: { ...(t[id] || { points: {} }), ...patch } }));
  const setPoint = (id, entry, effect) => setTopics(t => { const cur = t[id] || { points: {} }; return { ...t, [id]: { ...cur, points: { ...cur.points, [entry]: effect } } }; });
  const missing = form.topics.filter(t => !(topics[t.concept_id] || {}).view_after);
  const submit = (e) => {
    e.preventDefault();
    const body = { answers, topics: form.topics.map(t => { const x = topics[t.concept_id] || { points: {} }; return { concept_id: t.concept_id, view_after: x.view_after, certainty_after: x.certainty_after || null, moved_note: x.moved_note || '', not_persuasive_note: x.not_persuasive_note || '',
      points: Object.entries(x.points || {}).filter(([, v]) => v).map(([entry_id, effect]) => ({ entry_id, effect })) }; }) };
    attempt(() => post('/p/reflection', body)).then(ok => { if (ok) { reload(); onDone(); } });
  };
  const label = { support: 'support', oppose: 'oppose', undecided: 'undecided' };
  return html`<form class="col narrow" style="gap:16px" onSubmit=${submit}>
    <div><h2>Your reflection</h2><p class="muted">How did the discussion land for you? Your answers go to the organisers, not to other participants.</p></div>
    ${form.topics.map(t => { const x = topics[t.concept_id] || { points: {} }; return html`<section class="card pad col" key=${t.concept_id}><h3>${t.label}</h3>
      ${t.view_before && html`<p class="small muted">Before the discussion you said: <b>${label[t.view_before]}</b>.</p>`}
      <div><b>Where do you stand now?</b><${Choice} name=${'a' + t.concept_id} value=${x.view_after} onChange=${(v) => setT(t.concept_id, { view_after: v })} options=${VIEWS} /></div>
      <div class="row small"><span class="muted">How sure are you?</span><${Choice} name=${'ca' + t.concept_id} value=${x.certainty_after} onChange=${(v) => setT(t.concept_id, { certainty_after: v })} options=${SCALE.map(n => [n, String(n)])} /></div>
      ${t.points.length > 0 && html`<div class="col" style="gap:6px"><b>Which points mattered to you?</b>
        ${t.points.map(pt => html`<div class="card" style="padding:8px 12px" key=${pt.entry_id}><div><b>${pt.speaker}:</b> ${pt.paraphrase}${pt.subpoint ? html` <span class="tiny muted">(${pt.subpoint})</span>` : ''}</div>
          <${Choice} name=${'p' + pt.entry_id} value=${x.points[pt.entry_id] || ''} onChange=${(v) => setPoint(t.concept_id, pt.entry_id, v)} options=${[['moved', 'Moved me'], ['reinforced', 'Reinforced my view'], ['not_persuasive', 'Did not persuade me'], ['', 'No effect']]} /></div>`)}</div>`}
      <${Field} label="In your own words, what moved you or held you where you were?" help="Optional."><textarea value=${x.moved_note || ''} onInput=${e => setT(t.concept_id, { moved_note: e.target.value })}></textarea><//>
      <${Field} label="What did you hear that did not persuade you, and why?" help="Optional."><textarea value=${x.not_persuasive_note || ''} onInput=${e => setT(t.concept_id, { not_persuasive_note: e.target.value })}></textarea><//>
    </section>`; })}
    <section class="card pad col"><h3>The process and your partner</h3>
      ${[['felt_heard', 'I felt heard in the discussion'], ['fair', 'The discussion was fair to different views'], ['partner_helpful', 'My AI partner helped me take part']].map(([k, q]) => html`<div><b>${q}</b>
        <${Choice} name=${k} value=${answers[k]} onChange=${(v) => setAnswers(a => ({ ...a, [k]: v }))} options=${SCALE.map(n => [n, n === 1 ? '1 disagree' : n === 5 ? '5 agree' : String(n)])} /></div>`)}
      <div><b>Did your partner ever seem to push you towards a view?</b>
        <${Choice} name="pushed" value=${answers.partner_pushed} onChange=${(v) => setAnswers(a => ({ ...a, partner_pushed: v }))} options=${[['no', 'No'], ['unsure', 'Not sure'], ['yes', 'Yes']]} /></div>
      <${Field} label="Anything else you want the organisers to know?" help="Optional."><textarea value=${answers.comments || ''} onInput=${e => setAnswers(a => ({ ...a, comments: e.target.value }))}></textarea><//>
      <label class="row" style="gap:8px"><input type="checkbox" checked=${answers.follow_up_ok} onChange=${e => setAnswers(a => ({ ...a, follow_up_ok: e.target.checked }))} /><span>The organisers may contact me with follow-up questions.</span></label>
    </section>
    <div class="row"><button class="btn primary" disabled=${missing.length > 0}>Submit my reflection</button>
      ${missing.length > 0 && html`<span class="small muted">Say where you stand now on each topic to submit.</span>`}</div>
  </form>`;
}
