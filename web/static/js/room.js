// The live discussion room, shared by participants, the moderator and organisers who watch.
import { html, useState, useEffect, useRef, get, post, scope, attempt, toast, StageBadge, fmtTime, Avatar, Loading } from './lib.js';

const POS = { support: 'Supports', dissent: 'Dissents', question: 'Question', clarify: 'Clarifies' };

export function Room({ id, embedded }) {
  const [room, setRoom] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState('flow');
  const [highlight, setHighlight] = useState(null);
  const [online, setOnline] = useState([]);
  const feed = useRef(null);
  const load = () => get(`/deliberations/${id}/room`).then(setRoom, setError);
  const loadFlow = () => get(`/deliberations/${id}/flow`).then(f => setRoom(r => r && { ...r, flow: f.flow, people: f.people }), () => {});

  useEffect(() => { load(); }, [id]);
  // Live updates over a WebSocket, with reconnect.
  useEffect(() => {
    let ws, closed = false, retry = 0, ping;
    const connect = () => {
      ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/ws/deliberations/${id}?token=${encodeURIComponent(scope().token || '')}`);
      ws.onopen = () => { if (retry) load(); retry = 0; ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 25000); };
      ws.onmessage = (ev) => {
        const e = JSON.parse(ev.data);
        if (e.type === 'message') setRoom(r => r && (r.messages.some(x => x.id === e.message.id) ? r : { ...r, messages: [...r.messages, e.message] }));
        else if (e.type === 'flow' || e.type === 'people') loadFlow();
        else if (e.type === 'presence') setOnline(e.online);
        else if (e.type === 'stage') load();
        else if (e.type === 'whisper') setRoom(r => r && { ...r, whispers: [...r.whispers, e.whisper] });
      };
      ws.onclose = (ev) => { clearInterval(ping); if (!closed && ev.code !== 4401) setTimeout(connect, Math.min(8000, 500 * 2 ** retry++)); };
    };
    connect();
    return () => { closed = true; clearInterval(ping); ws && ws.close(); };
  }, [id]);
  const count = room ? room.messages.length : 0;
  useEffect(() => { if (feed.current && !highlight) feed.current.scrollTop = feed.current.scrollHeight; }, [count]);

  if (!room) return html`<${Loading} error=${error} />`;
  const d = room.deliberation;
  const staff = room.me.role !== 'participant';
  const live = d.stage === 'in_progress';
  const names = Object.fromEntries(room.people.map(p => [p.id, p]));
  const jump = (messageId) => {
    setHighlight(messageId);
    const el = feed.current && feed.current.querySelector(`[data-mid="${messageId}"]`);
    if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    setTimeout(() => setHighlight(h => (h === messageId ? null : h)), 2500);
  };
  const act = (fn) => attempt(fn);
  return html`<div class="col" style="gap:14px">
    <div class="row" style="justify-content:space-between;align-items:flex-end">
      <div>${!embedded && html`<div class="small muted">${d.process || 'Deliberation'}</div><h1 style="font-size:24px">${d.title}</h1>`}
        <div class="row small" style="margin-top:4px"><${StageBadge} stage=${d.stage} /><span class="muted">${d.framing_question}</span></div></div>
      <div class="row">
        <div class="chips" role="group" aria-label="View">
          <button class="chip" aria-pressed=${String(view === 'chat')} onClick=${() => setView('chat')}>Chat only</button>
          <button class="chip" aria-pressed=${String(view === 'flow')} onClick=${() => setView('flow')}>Chat and flow</button></div>
        ${staff && d.stage === 'scheduled' && html`<button class="btn primary" onClick=${() => act(() => post(`/deliberations/${id}/start`))}>Start the deliberation</button>`}
        ${staff && live && room.people.some(p => p.simulated) && html`<button class="btn" onClick=${() => act(() => post(`/deliberations/${id}/standins/speak`))}>Let a stand-in speak</button>`}
        ${staff && live && html`<button class="btn danger" onClick=${() => window.confirm('End the deliberation for everyone? Participants will be asked for their reflection.') && act(() => post(`/deliberations/${id}/end`))}>End the deliberation</button>`}
      </div></div>
    ${!live && html`<div class="notice">${d.stage === 'scheduled' ? 'The discussion has not started yet. This page updates by itself when it does.' : ['pending_debrief', 'complete'].includes(d.stage) ? 'The discussion has ended. This is the record of what was said.' : 'The discussion opens once the deliberation is scheduled and started.'}</div>`}
    <div class=${'room' + (view === 'flow' ? ' with-flow' : '')}>
      <section class="card" aria-label="Group chat">
        <div class="people">${room.people.map(p => html`<span class=${'p' + ((p.kind === 'participant' && !p.simulated && !online.includes(p.id) && p.id !== room.me.id) ? ' off' : '')} key=${p.id}>
          <${Avatar} name=${p.name} id=${p.id} size=${22} />${p.name}${p.id === room.me.id ? ' (you)' : ''}${p.kind === 'moderator' ? html` <span class="badge blue">Moderator</span>` : ''}${p.simulated ? html` <span class="badge purple">AI stand-in</span>` : ''}</span>`)}</div>
        <div class="feed" ref=${feed} aria-live="polite">
          ${!room.messages.length && html`<p class="muted" style="margin:auto">No messages yet.</p>`}
          ${room.messages.map(x => x.kind === 'system' ? html`<div class="msg system" key=${x.id}>${x.body}</div>` : html`
            <div class=${'msg' + (highlight === x.id ? ' hl' : '')} data-mid=${x.id} key=${x.id}>
              <${Avatar} name=${(names[x.speaker] || {}).name} id=${x.speaker} />
              <div><div class="who">${(names[x.speaker] || { name: 'Someone' }).name}${x.speaker === room.me.id ? ' (you)' : ''}<span>${fmtTime(x.sent_at)}</span></div><div>${x.body}</div></div></div>`)}
        </div>
        ${room.can_post && live ? html`<${Composer} onSend=${(body) => attempt(() => post(`/deliberations/${id}/messages`, { body }))} />`
          : html`<div class="composer muted small">${live ? 'You are watching this discussion. Only participants and the moderator can post.' : 'The chat is closed.'}</div>`}
      </section>
      ${view === 'flow' && html`<${Flow} room=${room} names=${names} staff=${staff} onJump=${jump} reload=${loadFlow} id=${id} />`}
      ${staff ? html`<${StaffPanel} room=${room} names=${names} id=${id} live=${live} onJump=${jump} />` : html`<${PartnerPanel} room=${room} live=${live} />`}
    </div></div>`;
}

function Composer({ onSend }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const send = async () => { const body = text.trim(); if (!body || busy) return; setBusy(true); const ok = await onSend(body); setBusy(false); if (ok) setText(''); };
  return html`<form class="composer" onSubmit=${(e) => { e.preventDefault(); send(); }}>
    <textarea aria-label="Your message to the group" placeholder="Write to the group" title="Enter sends. Shift+Enter adds a line." value=${text} onInput=${e => setText(e.target.value)}
      onKeyDown=${(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}></textarea>
    <button class="btn primary" disabled=${busy || !text.trim()}>Send</button></form>`;
}

function Flow({ room, names, staff, onJump, id }) {
  const { concepts, entries } = room.flow;
  const cols = room.people.filter(p => p.kind === 'participant' || entries.some(e => e.speaker === p.id));
  const options = concepts.filter(c => c.kind === 'option');
  const rows = options.flatMap(o => [o, ...concepts.filter(c => c.parent_id === o.id)]);
  const me = room.me.role === 'participant' ? room.me.id : null;
  const setStance = (concept_id, value) => value && attempt(() => post(`/deliberations/${id}/stance`, { concept_id, value })).then(ok => ok && toast('Saved. Only you can see this.'));
  return html`<section class="card" aria-label="Discussion flow"><div class="card-head" style="padding:10px 16px"><div><h2 style="font-size:16px">Flow</h2>
      <div class="tiny muted">Rows are the options and sub-points raised. Columns are people. Click an entry to see where it was said.</div></div>
      <div class="legend"><span><i style="background:#3F8A3F"></i>Supports</span><span><i style="background:#B3412F"></i>Dissents</span><span><i style="background:#C98A2E"></i>Question</span><span><i style="background:#3B73A8"></i>Clarifies</span></div></div>
    ${!rows.length ? html`<p class="muted" style="padding:24px 16px">Nothing on the table yet. Rows appear as people raise options.</p>` : html`<div class="flowwrap"><table class="flow">
      <thead><tr><th class="rowh" style="z-index:3;background:#FAFAF8">Option or sub-point</th>${cols.map(p => html`<th key=${p.id}>${p.name}${p.id === me ? ' (you)' : ''}</th>`)}</tr></thead>
      <tbody>${rows.map(c => html`<tr key=${c.id} class=${(c.kind === 'subpoint' ? 'sub ' : '') + (c.status === 'proposed' ? 'proposed' : '')}>
        <th class="rowh" scope="row">${c.label}
          <div class="tiny muted" style="font-weight:400">${c.seeded ? 'Set by the organiser' : c.raised_by && names[c.raised_by] ? 'Raised by ' + names[c.raised_by].name : ''}</div>
          ${c.status === 'proposed' && html`<span class="badge amber">Proposed by the tagger</span>`}
          ${c.unanswered && html`<span class="badge amber" title="Nobody else has responded to this yet">Unanswered</span>`}
          ${me && c.status === 'confirmed' && html`<label class="tiny muted" style="display:block;margin-top:6px;font-weight:400">My private view
            <select style="min-height:30px;padding:2px 6px;font-size:12px" value=${(room.stances[c.id] || {}).value || ''} onChange=${(e) => { room.stances[c.id] = { value: e.target.value }; setStance(c.id, e.target.value); }}>
              <option value="">Not set</option><option value="support">Support</option><option value="oppose">Oppose</option><option value="undecided">Undecided</option></select></label>`}
        </th>
        ${cols.map(p => html`<td key=${p.id}>${entries.filter(e => e.concept_id === c.id && e.speaker === p.id).map(e => html`
          <button key=${e.id} class=${`entry ${e.position} ${e.status}`} onClick=${() => e.message_id && onJump(e.message_id)} title="Show where this was said">
            <small>${POS[e.position]}${e.tag ? ' · ' + e.tag : ''}${e.status === 'proposed' ? ' · proposed' : ''}</small>${e.paraphrase}</button>`)}</td>`)}
      </tr>`)}</tbody></table></div>`}
  </section>`;
}

function StaffPanel({ room, names, id, live, onJump }) {
  const [label, setLabel] = useState('');
  const [parent, setParent] = useState('');
  const [fix, setFix] = useState(null);
  const { concepts, entries } = room.flow;
  const pendingC = concepts.filter(c => c.status === 'proposed');
  const pendingE = entries.filter(e => e.status === 'proposed');
  const review = (kind, x, status) => attempt(() => post(`/${kind}/${x.id}/review`, { status }));
  const conceptLabel = (cid) => (concepts.find(c => c.id === cid) || {}).label;
  const recent = entries.filter(e => e.status === 'confirmed').slice(-6).reverse();
  return html`<aside class="card col" style="gap:0" aria-label="Moderator tools">
    <div class="card-head" style="padding:10px 16px"><div><h2 style="font-size:16px">Tags to review</h2><div class="tiny muted">The tagger proposes; you confirm. Participants only see confirmed rows and entries.</div></div></div>
    <div class="col" style="padding:12px 16px;gap:10px">
      ${!pendingC.length && !pendingE.length && html`<p class="small muted">Nothing waiting.</p>`}
      ${pendingC.map(c => html`<div class="card" style="padding:8px 10px" key=${c.id}><div class="tiny muted">New ${c.kind === 'option' ? 'option' : 'sub-point'}${c.raised_by && names[c.raised_by] ? ', raised by ' + names[c.raised_by].name : ''}</div><b>${c.label}</b>
        <div class="row" style="margin-top:6px"><button class="btn sm primary" onClick=${() => review('concepts', c, 'confirmed')}>Confirm</button><button class="btn sm" onClick=${() => review('concepts', c, 'rejected')}>Reject</button>
          ${c.raised_in_message && html`<button class="btn sm link" onClick=${() => onJump(c.raised_in_message)}>Show message</button>`}</div></div>`)}
      ${pendingE.map(e => html`<div class="card" style="padding:8px 10px" key=${e.id}><div class="tiny muted">${(names[e.speaker] || {}).name} · ${POS[e.position]} · on "${conceptLabel(e.concept_id)}"${e.confidence != null ? ` · ${Math.round(e.confidence * 100)}% sure` : ''}</div>${e.paraphrase}
        <div class="row" style="margin-top:6px"><button class="btn sm primary" onClick=${() => review('entries', e, 'confirmed')}>Confirm</button><button class="btn sm" onClick=${() => review('entries', e, 'rejected')}>Reject</button>
          <button class="btn sm" onClick=${() => setFix({ ...e })}>Fix</button>${e.message_id && html`<button class="btn sm link" onClick=${() => onJump(e.message_id)}>Show message</button>`}</div></div>`)}
      ${fix && html`<form class="card col" style="padding:10px;gap:8px;border-color:var(--blue)" onSubmit=${(ev) => { ev.preventDefault(); attempt(() => post(`/entries/${fix.id}/correct`, { position: fix.position, paraphrase: fix.paraphrase, concept_id: fix.concept_id })).then(ok => ok && setFix(null)); }}>
        <b class="small">Correct this tag</b>
        <select aria-label="Row" value=${fix.concept_id} onChange=${e => setFix({ ...fix, concept_id: e.target.value })}>${concepts.map(c => html`<option value=${c.id}>${c.kind === 'subpoint' ? '· ' : ''}${c.label}</option>`)}</select>
        <select aria-label="Position" value=${fix.position} onChange=${e => setFix({ ...fix, position: e.target.value })}>${Object.entries(POS).map(([k, v]) => html`<option value=${k}>${v}</option>`)}</select>
        <input type="text" aria-label="Paraphrase" value=${fix.paraphrase} onInput=${e => setFix({ ...fix, paraphrase: e.target.value })} />
        <div class="row"><button class="btn sm primary">Save correction</button><button type="button" class="btn sm" onClick=${() => setFix(null)}>Cancel</button></div></form>`}
    </div>
    ${recent.length > 0 && html`<div style="padding:0 16px 12px"><div class="tiny muted" style="margin-bottom:4px">RECENTLY CONFIRMED</div>
      ${recent.map(e => html`<div class="row small" key=${e.id} style="gap:6px;margin-bottom:4px"><span class="grow">${(names[e.speaker] || {}).name}: ${e.paraphrase}</span><button class="btn sm link" onClick=${() => setFix({ ...e })}>Fix</button></div>`)}</div>`}
    <form class="col" style="padding:12px 16px;border-top:1px solid var(--line);gap:8px" onSubmit=${(e) => { e.preventDefault(); if (label.trim()) attempt(() => post(`/deliberations/${id}/concepts`, { label, parent_id: parent || null })).then(ok => ok && setLabel('')); }}>
      <b class="small">Add a row yourself</b>
      <input type="text" aria-label="Row label" placeholder="Short neutral label" value=${label} onInput=${e => setLabel(e.target.value)} />
      <select aria-label="Under" value=${parent} onChange=${e => setParent(e.target.value)}><option value="">A new option</option>${concepts.filter(c => c.kind === 'option' && c.status === 'confirmed').map(c => html`<option value=${c.id}>Sub-point under: ${c.label}</option>`)}</select>
      <button class="btn sm" disabled=${!label.trim()}>Add row</button></form>
  </aside>`;
}

export function PartnerChat({ sessionMode, whispers = [] }) {
  const [msgs, setMsgs] = useState(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const box = useRef(null);
  useEffect(() => { get('/p/partner').then(setMsgs, () => setMsgs([])); }, []);
  const items = [...(msgs || []).map(x => ({ ...x, at: x.created_at })), ...whispers.map(w => ({ id: w.id, role: 'whisper', body: w.body, at: w.shown_at }))].sort((a, b) => a.at < b.at ? -1 : 1);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [items.length, busy]);
  const ask = async (message, mode = 'auto') => {
    if (!message.trim() || busy) return;
    setBusy(true); setText('');
    setMsgs(m => [...(m || []), { id: 'tmp' + Date.now(), role: 'user', body: message, created_at: new Date().toISOString() }]);
    const reply = await attempt(() => post('/p/partner', { message, mode }));
    setBusy(false);
    if (reply) setMsgs(m => [...m, reply]); else setMsgs(m => m.slice(0, -1));
  };
  const quick = sessionMode
    ? [['What are the main views so far?', 'auto'], ['Help me put my point into words', 'auto'], ['What do the materials say about this?', 'tutor']]
    : [['What is this deliberation about?', 'prep'], ['Explain the basics to me', 'tutor'], ['Show me different perspectives', 'perspectives']];
  return html`<div class="pchat" ref=${box} aria-live="polite">
      ${!items.length && html`<p class="small muted">Your partner is private to you. It explains the materials and helps you think, and it will not tell you what to conclude.</p>`}
      ${items.map(x => x.role === 'whisper' ? html`<div class="whisper" key=${x.id}><div class="tiny" style="color:var(--purple);font-weight:600">A nudge from your partner</div>${x.body}</div>`
        : html`<div class=${'bubble ' + x.role} key=${x.id}>${x.body}${x.sources && x.sources.length > 0 && html`<div class="sources">${x.sources.map(s => html`<div title=${s.excerpt}>[${s.label}] ${s.source}</div>`)}</div>`}</div>`)}
      ${busy && html`<div class="bubble assistant muted">Thinking.</div>`}
    </div>
    <div class="row" style="padding:0 16px 8px;gap:6px">${quick.map(([q, mode]) => html`<button class="chip" style="font-size:12px;min-height:28px" disabled=${busy} onClick=${() => ask(q, mode)}>${q}</button>`)}</div>
    <form class="composer" onSubmit=${(e) => { e.preventDefault(); ask(text); }}>
      <input type="text" aria-label="Ask your partner" placeholder="Ask your partner privately" value=${text} onInput=${e => setText(e.target.value)} />
      <button class="btn" disabled=${busy || !text.trim()}>Ask</button></form>`;
}

function PartnerPanel({ room }) {
  return html`<aside class="card" aria-label="Your private partner"><div class="card-head" style="padding:10px 16px"><div><h2 style="font-size:16px">Your partner</h2><div class="tiny muted">Private to you. Nobody else in the room sees this.</div></div></div>
    <${PartnerChat} sessionMode=${true} whispers=${room.whispers} /></aside>`;
}
