// The organiser review: how views moved, what persuaded people, and the click-back into the transcript.
import { html, useState, useEffect, useRef, get, Link, useLoad, scope, fmtTime, Avatar, Loading, StageBadge } from './lib.js';

const VIEWS = [['support', 'Support'], ['oppose', 'Oppose'], ['undecided', 'Undecided'], ['none', 'No answer']];
const VLABEL = Object.fromEntries(VIEWS);
const EFFECT = { moved: 'Moved them', reinforced: 'Reinforced their view', not_persuasive: 'Did not persuade them' };
const POS = { support: 'Supports', dissent: 'Dissents', question: 'Question', clarify: 'Clarifies' };

function Stack({ counts, label }) {
  const total = VIEWS.reduce((n, [k]) => n + (counts[k] || 0), 0) || 1;
  return html`<div><div class="row small" style="justify-content:space-between"><b>${label}</b><span class="muted">${VIEWS.filter(([k]) => counts[k]).map(([k, l]) => `${counts[k]} ${l.toLowerCase()}`).join(', ') || 'No answers'}</span></div>
    <div class="stack" role="img" aria-label=${label}>${VIEWS.map(([k]) => counts[k] ? html`<i class=${'v-' + k} style=${`width:${100 * counts[k] / total}%`}></i>` : null)}</div></div>`;
}

export function Review({ id, back }) {
  const { data, error } = useLoad(() => get(`/deliberations/${id}/review`), [id]);
  const [tab, setTab] = useState(0);
  const [pseudo, setPseudo] = useState(false);
  const [openMsg, setOpenMsg] = useState(null);
  if (!data) return html`<main class="page"><${Loading} error=${error} /></main>`;
  const people = Object.fromEntries(data.people.map(p => [p.id, p]));
  const nm = (pid) => { const p = people[pid]; return p ? (pseudo ? p.pseudonym : p.name) : 'Someone'; };
  const d = data.deliberation;
  const topic = data.topics[tab];
  const entryById = Object.fromEntries(data.topics.flatMap(t => t.entries).map(e => [e.id, e]));
  const tabs = [...data.topics.map(t => t.label), 'Process and partner'];
  return html`<main class="page col" style="gap:18px">
    <${Link} href=${back}>← Back to the deliberation<//>
    <div class="row" style="justify-content:space-between;align-items:flex-end">
      <div><div class="small muted">${d.process || 'Independent deliberation'}</div><h1>Organiser review: ${d.title}</h1>
        <div class="row small" style="margin-top:6px"><${StageBadge} stage=${d.stage} /><span class="muted">${d.counts.reflections} of ${d.counts.people} reflections in</span></div></div>
      <div class="chips" role="group" aria-label="How people are shown"><button class="chip" aria-pressed=${String(!pseudo)} onClick=${() => setPseudo(false)}>Names</button><button class="chip" aria-pressed=${String(pseudo)} onClick=${() => setPseudo(true)}>Pseudonyms</button></div>
    </div>
    ${!data.topics.length && html`<div class="notice">No options were on the table in this deliberation, so there are no topic tabs. Process answers are below.</div>`}
    <div class="tabs" role="tablist">${tabs.map((t, i) => html`<button class="tab" role="tab" aria-selected=${String(tab === i)} onClick=${() => setTab(i)}>${t}</button>`)}</div>
    ${topic ? html`<div class="col" style="gap:18px">
      <section class="card pad col"><h2>How views moved</h2><${Stack} label="Before" counts=${topic.before} /><${Stack} label="After" counts=${topic.after} />
        <div class="legend">${VIEWS.map(([k, l]) => html`<span><i class=${'v-' + k}></i>${l}</span>`)}</div>
        ${topic.subpoints.length > 0 && html`<p class="small muted">Sub-points raised: ${topic.subpoints.map(s => `${s.label}${s.raised_by ? ` (${nm(s.raised_by)})` : ''}`).join('; ')}.</p>`}</section>
      <section class="card"><div class="card-head"><h2>Points that mattered</h2><span class="small muted">From participants' reflections. Click a point to see it in the discussion.</span></div>
        ${!topic.entries.length ? html`<p class="muted" style="padding:16px 20px">Nothing was tagged on this topic.</p>` : html`<div style="overflow-x:auto"><table class="grid" style="margin:0"><thead><tr><th style="padding-left:20px">Point</th><th>Said by</th><th>Moved</th><th>Reinforced</th><th>Not persuasive</th></tr></thead><tbody>
          ${[...topic.entries].sort((a, b) => (b.moved + b.reinforced) - (a.moved + a.reinforced)).map(e => html`<tr key=${e.id}>
            <td style="padding-left:20px"><button class="btn link" style="text-align:left;white-space:normal" onClick=${() => setOpenMsg(e.message_id)}>${e.paraphrase}</button><div class="tiny muted">${POS[e.position]}${e.subpoint ? ' · ' + e.subpoint : ''}</div></td>
            <td>${nm(e.speaker)}</td><td><b>${e.moved || ''}</b></td><td>${e.reinforced || ''}</td><td>${e.not_persuasive || ''}</td></tr>`)}</tbody></table></div>`}</section>
      <section class="col"><h2>Each participant</h2><div class="cards">${topic.responses.map(r => html`<article class="card pad col" key=${r.participant_id} style="gap:8px">
        <div class="row"><${Avatar} name=${people[r.participant_id].name} id=${r.participant_id} /><b>${nm(r.participant_id)}</b>${!r.submitted && html`<span class="badge amber">No reflection yet</span>`}</div>
        <div class="row small"><span class=${'badge ' + (r.view_before ? '' : '')}>${VLABEL[r.view_before || 'none']}</span>→<span class="badge blue">${VLABEL[r.view_after || 'none']}</span>
          ${r.view_before && r.view_after && html`<span class="muted">${r.view_before === r.view_after ? 'Unmoved' : 'Changed'}</span>`}${r.certainty_after && html`<span class="muted">certainty ${r.certainty_after} of 5</span>`}</div>
        ${r.moved_note && html`<p class="small"><b>What moved or held them:</b> ${r.moved_note}</p>`}
        ${r.not_persuasive_note && html`<p class="small"><b>Not persuasive:</b> ${r.not_persuasive_note}</p>`}
        ${r.points.length > 0 && html`<div class="small"><b>Points they picked</b><ul style="margin:4px 0 0;padding-left:18px">${r.points.map(pt => { const e = entryById[pt.entry_id]; return e && html`<li>${EFFECT[pt.effect]}: <button class="btn link" style="white-space:normal;text-align:left" onClick=${() => setOpenMsg(e.message_id)}>${nm(e.speaker)}, "${e.paraphrase}"</button></li>`; })}</ul></div>`}
        ${r.said.length > 0 ? html`<div class="small"><b>What they said on this</b><ul style="margin:4px 0 0;padding-left:18px">${r.said.map(eid => { const e = entryById[eid]; return html`<li>${POS[e.position]}: ${e.paraphrase} <button class="btn link" onClick=${() => setOpenMsg(e.message_id)}>Open in discussion</button></li>`; })}</ul></div>` : html`<p class="small muted">Did not speak on this topic.</p>`}
      </article>`)}</div></section></div>`
    : html`<${Process} data=${data} nm=${nm} />`}
    ${openMsg && html`<${Transcript} data=${data} nm=${nm} people=${people} target=${openMsg} onClose=${() => setOpenMsg(null)} />`}
  </main>`;
}

function Process({ data, nm }) {
  const rows = data.surveys;
  const avg = (k) => { const xs = rows.map(r => r.post && Number(r.post[k])).filter(x => x > 0); return xs.length ? (xs.reduce((a, b) => a + b, 0) / xs.length).toFixed(1) + ' of 5' : 'No answers'; };
  const pushed = rows.filter(r => r.post && r.post.partner_pushed === 'yes').length;
  return html`<div class="col" style="gap:18px">
    <div class="tiles" style="grid-template-columns:repeat(auto-fill,minmax(220px,1fr))">
      ${[['Felt heard', avg('felt_heard')], ['Fair to different views', avg('fair')], ['Partner helped', avg('partner_helpful')], ['Said the partner pushed a view', `${pushed} of ${rows.filter(r => r.post).length}`], ['Partner nudges acted on', `${data.whispers.acted_on} of ${data.whispers.shown}`]]
        .map(([k, v]) => html`<div class="card pad"><div class="small muted">${k}</div><div style="font:600 22px 'Space Grotesk',sans-serif">${v}</div></div>`)}</div>
    <section class="card"><div class="card-head"><h2>Each participant</h2></div><div style="overflow-x:auto"><table class="grid"><thead><tr><th style="padding-left:20px">Participant</th><th>Familiarity</th><th>Wanted to understand</th><th>Heard</th><th>Fair</th><th>Partner helped</th><th>Partner pushed</th><th>Follow-up OK</th><th>Comments</th></tr></thead><tbody>
      ${rows.map(r => html`<tr><td style="padding-left:20px"><b>${nm(r.participant_id)}</b></td><td>${(r.pre || {}).knowledge_level || ''}</td><td>${(r.pre || {}).hopes || ''}</td>
        ${r.post ? html`<td>${r.post.felt_heard || ''}</td><td>${r.post.fair || ''}</td><td>${r.post.partner_helpful || ''}</td><td>${r.post.partner_pushed || ''}</td><td>${r.post.follow_up_ok ? 'Yes' : 'No'}</td><td>${r.post.comments || ''}</td>` : html`<td colspan="6" class="muted">No reflection yet</td>`}</tr>`)}
    </tbody></table></div></section></div>`;
}

function Transcript({ data, nm, people, target, onClose }) {
  const box = useRef(null);
  useEffect(() => { const el = box.current && box.current.querySelector(`[data-mid="${target}"]`); if (el) el.scrollIntoView({ block: 'center' }); }, [target]);
  useEffect(() => { const f = (e) => e.key === 'Escape' && onClose(); window.addEventListener('keydown', f); return () => window.removeEventListener('keydown', f); }, []);
  return html`<aside class="drawer" role="dialog" aria-label="Discussion transcript"><div class="card-head"><h2 style="font-size:18px">In the discussion</h2><button class="btn sm" onClick=${onClose}>Close</button></div>
    <div class="feed" ref=${box}>${data.transcript.map(x => x.kind === 'system' ? html`<div class="msg system">${x.body}</div>` : html`<div class=${'msg' + (x.id === target ? ' hl' : '')} data-mid=${x.id}>
      <${Avatar} name=${(people[x.speaker] || {}).name} id=${x.speaker} /><div><div class="who">${nm(x.speaker)}<span>${fmtTime(x.sent_at)}</span></div><div>${x.body}</div></div></div>`)}</div></aside>`;
}
