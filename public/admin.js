// Generated from the Design canvas by tools/build_from_canvas.py. Edit the canvas, then rebuild.
// Simulated post-deliberation data for one breakout room, consistent with the scripted discussion.
const PEOPLE = {
  river: { name: 'River', pseudo: 'Facilitator', initials: 'R', color: '#3D4651' },
  priya: { name: 'Priya', pseudo: 'P1', initials: 'P', color: '#6B4FA0' },
  gary: { name: 'Gary', pseudo: 'P2', initials: 'G', color: '#2F6B4F' },
  okafor: { name: 'Mr. Okafor', pseudo: 'P3', initials: 'O', color: '#A3532A' },
  dana: { name: 'Dana', pseudo: 'P4', initials: 'D', color: '#1F5A8C' }
};
const PARTICIPANTS = ['priya', 'gary', 'okafor', 'dana'];

const TRANSCRIPT = [
  { who: 'river', text: "Welcome back, everyone. This session is about air travel: how should the UK reduce emissions from flying? Let's start with first reactions. Who'd like to go first?" },
  { who: 'priya', text: "I'll go. Dr Cairns said 15% of people take 70% of flights. If that's right, it seems fairer for frequent flyers to pay more than for everyone to give up their one holiday." },
  { who: 'gary', text: 'I see that, but some of us fly for work. I visit suppliers a couple of times a month. A levy on frequent flyers could hit small businesses like mine, not just people with second homes abroad.' },
  { who: 'okafor', text: 'For me it is about family. My relatives live overseas. A flight every year or two is how we stay a family. I worry the rules will be written by people who do not have that situation.' },
  { who: 'river', text: "Thank you. So we're hearing fairness from three directions: who flies most, people who fly for work, and families spread across countries. Priya, what would a fair levy look like to you?" },
  { who: 'priya', text: "Leo Murray's version had no tax on your first flight each year, then it rises with every extra flight. That would protect Mr. Okafor's visits." },
  { who: 'gary', text: 'And business trips? If my flights cost more, that goes straight into what I charge my customers.' },
  { who: 'okafor', text: 'Could business travel be treated separately? Although I suppose then everyone would call their trip business.' },
  { who: 'dana', text: "On business travel: could companies have to document trips, so an exemption can't just be gamed?" },
  { who: 'river', text: 'Thank you for adding that. Would anyone like to respond?' },
  { who: 'river', text: "Let's bring in the other view we heard. Rachael Everard from Rolls Royce argued that cleaner engines and sustainable fuels could cut emissions while keeping people connected. How does that sit with people?" },
  { who: 'gary', text: "That's my preference. Fix the planes, not the people." },
  { who: 'priya', text: "But Owen Bellamy said planes last 20 to 30 years, and we only have about 30 years until 2050. I'm not sure the technology arrives in time on its own." },
  { who: 'okafor', text: 'And Ms Everard said the cleaner fuels are not yet available in the quantities needed. Perhaps we need both: invest in better planes, and ask those who fly most to do more now.' },
  { who: 'river', text: "We haven't heard from everyone yet. Would you like to add anything? A question counts too." },
  { who: 'dana', text: "I'm not sure a tax changes how often people fly. I'd want to see evidence that it works before supporting it." },
  { who: 'gary', text: "One more thing: trains. If a train to Edinburgh cost less than the flight, I'd take it." },
  { who: 'priya', text: 'Agreed. Professor Larkin talked about rail and video calls as alternatives. Making those easier feels less like a punishment.' },
  { who: 'river', text: "Let's capture where we are: some support for a frequent flyer levy with protections for occasional flyers, interest in cleaner technology, and making alternatives like rail cheaper. We'll take five minutes, then each say how strongly each option should feature." }
];

const TOPICS = [
  { id: 'A', title: 'Frequent flyer levy' },
  { id: 'B', title: 'Cleaner engines and sustainable fuels' },
  { id: 'C', title: 'Alternatives: rail, ferry, video calls' },
  { id: 'D', title: 'Combining options', duringOnly: true }
];

// Points from the discussion flow; msg is the transcript index where the point was made.
const POINTS = [
  { id: 'p1', topic: 'A', who: 'priya', msg: 1, tag: 'Raises', text: 'Frequent flyers should pay more, rather than everyone giving up a holiday' },
  { id: 'p2', topic: 'A', who: 'priya', msg: 1, tag: 'Raises', text: '15% of people take 70% of flights (Dr Cairns)' },
  { id: 'p3', topic: 'A', who: 'gary', msg: 2, tag: 'Challenges', text: 'Could hit small businesses whose owners fly for work' },
  { id: 'p4', topic: 'A', who: 'okafor', msg: 3, tag: 'Raises', text: 'Occasional flights keep families abroad together' },
  { id: 'p5', topic: 'A', who: 'priya', msg: 5, tag: 'Responds', text: "No tax on the first flight each year protects family visits (Leo Murray's design)" },
  { id: 'p6', topic: 'A', who: 'gary', msg: 6, tag: 'Challenges', text: 'Higher costs get passed on to customers' },
  { id: 'p7', topic: 'A', who: 'okafor', msg: 7, tag: 'Asks', text: 'Treat business travel separately? It could be gamed' },
  { id: 'p8', topic: 'A', who: 'dana', msg: 8, tag: 'Responds', text: "Companies could document trips so an exemption can't be gamed" },
  { id: 'p9', topic: 'A', who: 'dana', msg: 15, tag: 'Challenges', text: 'Not sure a tax changes how often people fly; wants evidence first' },
  { id: 'p10', topic: 'B', who: 'river', msg: 10, tag: 'Raises', text: "Rachael Everard's case: cleaner engines and fuels cut emissions while keeping people connected" },
  { id: 'p11', topic: 'B', who: 'gary', msg: 11, tag: 'Supports', text: '"Fix the planes, not the people"' },
  { id: 'p12', topic: 'B', who: 'priya', msg: 12, tag: 'Challenges', text: 'Planes last 20 to 30 years; the technology may not arrive in time (Owen Bellamy)' },
  { id: 'p13', topic: 'B', who: 'okafor', msg: 13, tag: 'Challenges', text: 'Cleaner fuels are not yet available in the quantities needed (Rachael Everard)' },
  { id: 'p14', topic: 'C', who: 'gary', msg: 16, tag: 'Raises', text: 'Would take the train if it cost less than the flight' },
  { id: 'p15', topic: 'C', who: 'priya', msg: 17, tag: 'Supports', text: 'Rail and video calls feel less like a punishment (Professor Larkin)' },
  { id: 'p16', topic: 'D', who: 'okafor', msg: 13, tag: 'Raises', text: 'Do both: invest in better planes, and ask frequent flyers to do more now' }
];

const RESPONSES = {
  priya: {
    topics: {
      A: { before: 'For', now: 'For', certainty: 'More sure', moved: ['p4'], notp: ['p3', 'p6'], movedNote: 'Hearing Mr. Okafor made me sure the levy needs a free first flight.', notNote: 'Business costs matter, but frequent business flying is exactly what the levy is meant to reduce.' },
      B: { before: 'Leaning against', now: 'Against', moved: ['p13'], notp: ['p11'], movedNote: "If the fuel doesn't exist at scale, it can't be the main plan.", notNote: '' },
      C: { before: 'Leaning for', now: 'For', moved: ['p14'], notp: [], movedNote: '', notNote: '' },
      D: { now: 'Leaning for', moved: ['p16'], notp: [], movedNote: '', notNote: '' }
    },
    heard: 'Completely', fair: 'Completely', wanted: '', issues: '',
    helpful: 'Mostly', pushed: 'No', pushedWhen: '', used: ['Preparation chat', 'Flow view'],
    openQs: [], updates: ["The assembly's final recommendations"], contact: 'Email'
  },
  gary: {
    topics: {
      A: { before: 'Against', now: 'Leaning against', moved: ['p5', 'p2'], notp: ['p1'], movedNote: 'The first-flight-free idea is better than I expected.', notNote: 'Still hits people like me who fly for work.' },
      B: { before: 'For', now: 'For', certainty: 'More sure', moved: ['p10'], notp: ['p12'], movedNote: '', notNote: 'Then build them faster. Waiting is not a plan either.' },
      C: { before: 'Unsure', now: 'Leaning for', moved: ['p15'], notp: [], movedNote: 'Cheaper trains would change what I do.', notNote: '' },
      D: { now: 'Unsure', moved: [], notp: ['p16'], movedNote: '', notNote: '"Both" sounds like paying twice.' }
    },
    heard: 'Mostly', fair: 'Mostly', wanted: '', issues: '',
    helpful: 'A little', pushed: 'Once or twice', pushedWhen: "It kept pointing me to Mr. Okafor's business travel question. It felt like it wanted me to answer it.", used: ['Whispers in the chat'],
    openQs: ['How would business travel be defined?'], updates: ["The assembly's final recommendations", 'Answers to my open questions'], contact: 'Email'
  },
  okafor: {
    topics: {
      A: { before: 'Unsure', now: 'Leaning for', moved: ['p5'], notp: ['p3'], movedNote: 'If family visits are protected, I can support it.', notNote: '' },
      B: { before: 'Unsure', now: 'Unsure', certainty: 'Less sure', moved: ['p12'], notp: ['p11'], movedNote: 'The timing point made me doubt it.', notNote: '' },
      C: { before: 'Leaning for', now: 'Leaning for', certainty: 'About the same', moved: [], notp: [], movedNote: '', notNote: '' },
      D: { now: 'For', moved: [], notp: [], movedNote: 'This was my own suggestion, and I still think it is the fairest path.', notNote: '' }
    },
    heard: 'Somewhat', fair: 'Mostly', wanted: '', issues: 'Sometimes two people spoke a lot before others could come in.',
    helpful: 'Mostly', pushed: 'No', pushedWhen: '', used: ['Preparation chat', 'Starter drafts', 'Map view'],
    openQs: ['Would the first flight be free for each person or each household?'], updates: ["The assembly's final recommendations"], contact: 'Text message'
  },
  dana: {
    topics: {
      A: { before: 'Leaning against', now: 'Leaning against', certainty: 'About the same', moved: [], notp: ['p2'], movedNote: '', notNote: "I understand the numbers, but I'm not sure a tax changes behaviour." },
      B: { before: 'Leaning for', now: 'For', moved: ['p11', 'p10'], notp: ['p12'], movedNote: '', notNote: '' },
      C: { before: 'Leaning for', now: 'For', moved: ['p14'], notp: [], movedNote: '', notNote: '' },
      D: { now: 'Leaning for', moved: ['p16'], notp: [], movedNote: '', notNote: '' }
    },
    heard: 'A little', fair: 'Somewhat', wanted: 'I wanted to answer the timing point about planes, but the group moved on to trains.', issues: 'It moved quickly. More time before the vote would help.',
    helpful: 'Completely', pushed: 'Not sure', pushedWhen: "The starter draft used my own words, but I'm not sure I would have spoken without it.", used: ['Preparation chat', 'Whispers in the chat', 'Starter drafts', 'Points list'],
    openQs: ['Would a levy actually reduce how often people fly?'], updates: ['Answers to my open questions', 'Future sessions'], contact: 'Email'
  }
};

const STANCES = ['Against', 'Leaning against', 'Unsure', 'Leaning for', 'For'];
const TAG_STYLES = {
  Raises: ['#E8F0F8', '#1F4E79'], Supports: ['#E4F1E8', '#24543D'], Challenges: ['#FBEBDD', '#8A4B0F'],
  Responds: ['#E1F0EF', '#1D5C5C'], Asks: ['#ECEEF1', '#3D4651']
};
const TONES = {
  gray: ['#ECEEF1', '#3D4651'], blue: ['#E8F0F8', '#1F4E79'], green: ['#E4F1E8', '#24543D'],
  amber: ['#FDF3E4', '#6B4310'], purple: ['#EEE9F6', '#5B3F8C']
};
function badgeStyle(tone) {
  const c = TONES[tone] || TONES.gray;
  return 'justify-self: start; display: inline-block; font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 99px; background: ' + c[0] + '; color: ' + c[1];
}
function tagStyle(tag) {
  const c = TAG_STYLES[tag] || TAG_STYLES.Asks;
  return 'font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 99px; background: ' + c[0] + '; color: ' + c[1];
}
function changeOf(topic, before, now, certainty) {
  if (!now) return { label: 'No answer', tone: 'gray', key: 'none' };
  if (topic.duringOnly) return { label: 'New in the discussion', tone: 'blue', key: 'new' };
  const b = STANCES.indexOf(before), n = STANCES.indexOf(now);
  if (b < 0 && n >= 0) return { label: 'Formed a view', tone: 'blue', key: 'moved' };
  if (n > b) return { label: 'Moved toward For', tone: 'purple', key: 'moved' };
  if (n < b) return { label: 'Moved toward Against', tone: 'purple', key: 'moved' };
  if (certainty === 'More sure') return { label: 'Reinforced', tone: 'green', key: 'reinforced' };
  if (certainty === 'Less sure') return { label: 'Less certain', tone: 'amber', key: 'less' };
  return { label: 'Unmoved', tone: 'gray', key: 'unmoved' };
}
const SCALE_TONE = { 'Not at all': '#8A2A22', 'A little': '#8A4B0F', 'Somewhat': '#6B4310', 'Mostly': '#24543D', 'Completely': '#24543D' };

class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { tab: props.startTab || 'A', names: (props.identity || 'names') === 'names', selectedMsg: null, drawer: false };
  }
  componentDidUpdate(prevProps, prevState) {
    if (prevProps.startTab !== this.props.startTab) this.setState({ tab: this.props.startTab || 'A' });
    if (prevProps.identity !== this.props.identity) this.setState({ names: (this.props.identity || 'names') === 'names' });
    // Scroll the drawer (not the page) so the selected message sits near the top third.
    const s = this.state, ps = prevState || {};
    if (s.drawer && s.selectedMsg !== null && (!ps.drawer || ps.selectedMsg !== s.selectedMsg)) {
      const box = document.getElementById('drawer-scroll');
      const el = document.getElementById('d-msg-' + s.selectedMsg);
      if (box && el) box.scrollTop = Math.max(0, el.offsetTop - box.clientHeight / 3);
    }
  }

  renderVals() {
    const s = this.state;
    const who = (k) => (s.names ? PEOPLE[k].name : PEOPLE[k].pseudo);
    const initials = (k) => (s.names ? PEOPLE[k].initials : PEOPLE[k].pseudo);
    const avatar = (k) => 'flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 50%; color: #FFFFFF; font-size: 12px; font-weight: 600; background: ' + PEOPLE[k].color;
    const link = (msg) => ({ href: '#msg-' + msg, go: (e) => { if (e && e.preventDefault) e.preventDefault(); this.setState({ selectedMsg: msg, drawer: true }); } });
    const pointRef = (pid) => { const p = POINTS.find(x => x.id === pid); return Object.assign({ text: p.text, who: who(p.who) }, link(p.msg)); };

    const tabDefs = TOPICS.map(t => ({ id: t.id, label: t.id + '. ' + t.title })).concat([
      { id: 'process', label: 'Process' }, { id: 'partner', label: 'AI partner' }, { id: 'follow', label: 'Follow-ups' }
    ]);
    const tabs = tabDefs.map(t => {
      const on = s.tab === t.id;
      return {
        label: t.label, selected: on ? 'true' : 'false', pick: () => this.setState({ tab: t.id }),
        style: 'min-height: 44px; padding: 0 14px; border: 0; border-bottom: 3px solid ' + (on ? '#1F5A8C' : 'transparent') + '; background: transparent; font: inherit; font-size: 14px; cursor: pointer; color: ' + (on ? '#1B1F24' : '#5B6169') + '; font-weight: ' + (on ? '600' : '500')
      };
    });

    const topic = TOPICS.find(t => t.id === s.tab);
    const vals = { topicNum: '', topicTitle: '', topicNote: '', changeCounts: [], chartRows: [], chartAria: '', chartFootnote: '', topMoved: [], topNot: [], noTopMoved: true, noTopNot: true, personCards: [] };
    if (topic) {
      const counts = { moved: 0, reinforced: 0, unmoved: 0, less: 0, new: 0 };
      const chartRows = PARTICIPANTS.map(k => {
        const a = RESPONSES[k].topics[topic.id];
        const ch = changeOf(topic, a.before, a.now, a.certainty);
        counts[ch.key] = (counts[ch.key] || 0) + 1;
        const b = topic.duringOnly ? -1 : STANCES.indexOf(a.before), n = STANCES.indexOf(a.now);
        const pos = (i) => 10 + i * 20;
        const lo = b >= 0 ? Math.min(pos(b), pos(n)) : pos(n), hi = b >= 0 ? Math.max(pos(b), pos(n)) : pos(n);
        const c = PEOPLE[k].color;
        return {
          name: who(k), change: ch.label, badgeStyle: badgeStyle(ch.tone),
          hasBefore: b >= 0, hasNow: n >= 0,
          lineStyle: 'position: absolute; top: 14px; height: 3px; border-radius: 2px; left: ' + lo + '%; width: ' + (hi - lo) + '%; background: ' + c + '; opacity: .5',
          beforeStyle: 'position: absolute; top: 7px; width: 16px; height: 16px; margin-left: -8px; border-radius: 50%; box-sizing: border-box; border: 2.5px solid ' + c + '; background: #FFFFFF; left: ' + (b >= 0 ? pos(b) : 0) + '%',
          nowStyle: 'position: absolute; top: 7px; width: 16px; height: 16px; margin-left: -8px; border-radius: 50%; background: ' + c + '; left: ' + pos(n) + '%',
          aria: who(k) + ': ' + (topic.duringOnly ? '' : (a.before + ' to ')) + a.now
        };
      });
      const countDefs = topic.duringOnly ? [['new', 'answered', 'blue']] : [['moved', 'moved', 'purple'], ['reinforced', 'reinforced', 'green'], ['unmoved', 'unmoved', 'gray'], ['less', 'less certain', 'amber']];
      const tally = (field) => {
        const t = {};
        PARTICIPANTS.forEach(k => RESPONSES[k].topics[topic.id][field].forEach(pid => { t[pid] = (t[pid] || 0) + 1; }));
        return Object.keys(t).sort((x, y) => t[y] - t[x]).map(pid => Object.assign({ count: t[pid] }, pointRef(pid)));
      };
      const topMoved = tally('moved'), topNot = tally('notp');
      const personCards = PARTICIPANTS.map(k => {
        const a = RESPONSES[k].topics[topic.id];
        const ch = changeOf(topic, a.before, a.now, a.certainty);
        const said = POINTS.filter(p => p.topic === topic.id && p.who === k).map(p => Object.assign({ text: p.text, tag: p.tag, tagStyle: tagStyle(p.tag) }, link(p.msg)));
        const spokeAtAll = TRANSCRIPT.some(m => m.who === k);
        return {
          name: who(k), initials: initials(k), avatarStyle: avatar(k), change: ch.label, badgeStyle: badgeStyle(ch.tone),
          beforeNow: topic.duringOnly ? 'After: ' + a.now + (a.certainty ? ' · ' + a.certainty : '') : 'Before: ' + a.before + '  →  After: ' + a.now + (a.certainty ? ' · ' + a.certainty : ''),
          moved: a.moved.map(pointRef), notp: a.notp.map(pointRef), noMoved: !a.moved.length, noNot: !a.notp.length,
          movedNote: a.movedNote, notNote: a.notNote, hasMovedNote: !!a.movedNote, hasNotNote: !!a.notNote,
          said: said, silent: !said.length,
          silentNote: spokeAtAll ? "Didn't speak on this topic." : "Didn't speak in the discussion."
        };
      });
      Object.assign(vals, {
        topicNum: topic.id, topicTitle: topic.title,
        topicNote: topic.duringOnly ? 'This option came up during the discussion, so there is no pre-survey baseline. Only views after the discussion are shown.' : 'Before comes from the pre-survey each participant took in Prepare; after comes from their reflection.',
        changeCounts: countDefs.map(d => ({ label: (counts[d[0]] || 0) + ' ' + d[1], style: badgeStyle(d[2]) })),
        chartRows: chartRows, chartAria: 'Opinion before and after: ' + chartRows.map(r => r.aria).join('; '),
        chartFootnote: topic.duringOnly ? 'No pre-survey for this topic' : 'Self-reported on a 5-point scale',
        topMoved: topMoved, topNot: topNot, noTopMoved: !topMoved.length, noTopNot: !topNot.length,
        personCards: personCards
      });
    }

    const processCards = PARTICIPANTS.map(k => {
      const r = RESPONSES[k];
      const n = TRANSCRIPT.filter(m => m.who === k).length;
      return {
        name: who(k), initials: initials(k), avatarStyle: avatar(k), messages: n + (n === 1 ? ' message' : ' messages') + ' in the discussion',
        heard: r.heard, fair: r.fair, heardStyle: 'color: ' + (SCALE_TONE[r.heard] || '#1B1F24'), fairStyle: 'color: ' + (SCALE_TONE[r.fair] || '#1B1F24'),
        wanted: r.wanted, issues: r.issues, hasWanted: !!r.wanted, hasIssues: !!r.issues, nothingRaised: !r.wanted && !r.issues
      };
    });
    const steer = PARTICIPANTS.filter(k => RESPONSES[k].pushed !== 'No');
    const partnerCards = PARTICIPANTS.map(k => {
      const r = RESPONSES[k];
      return { name: who(k), initials: initials(k), avatarStyle: avatar(k), helpful: r.helpful, pushed: r.pushed, used: r.used.join(', ') || 'nothing',
        pushedStyle: 'color: ' + (r.pushed === 'No' ? '#24543D' : '#8A4B0F') };
    });
    const followCards = PARTICIPANTS.map(k => {
      const r = RESPONSES[k];
      return { name: who(k), initials: initials(k), avatarStyle: avatar(k), contact: r.contact, questions: r.openQs.join('; ') || 'None', updates: r.updates.join('; ') || 'None' };
    });

    const topicMsgs = {};
    if (topic) POINTS.filter(p => p.topic === topic.id).forEach(p => { topicMsgs[p.msg] = true; });
    const transcript = TRANSCRIPT.map((m, i) => {
      const sel = s.selectedMsg === i;
      return {
        anchor: 'msg-' + i, drawerAnchor: 'd-msg-' + i, n: i + 1, name: who(m.who), color: PEOPLE[m.who].color, text: m.text,
        onTopic: !!topicMsgs[i], topicLabel: topic ? 'Topic ' + topic.id : '',
        style: 'scroll-margin-top: 12px; border-radius: 10px; padding: 8px 10px; ' + (sel ? 'background: #FFF4D6; border: 2px solid #D9A400' : m.who === 'river' ? 'background: #F3F5F8; border: 2px solid transparent' : 'background: #FFFFFF; border: 2px solid transparent')
      };
    });
    const segOn = 'min-height: 38px; padding: 0 14px; border: 0; font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; background: #1F5A8C; color: #FFFFFF';
    const segOff = 'min-height: 38px; padding: 0 14px; border: 0; font: inherit; font-size: 14px; cursor: pointer; background: #FFFFFF; color: #1B1F24';

    return Object.assign({
      tabs: tabs, isTopic: !!topic, isProcess: s.tab === 'process', isPartner: s.tab === 'partner', isFollow: s.tab === 'follow',
      responseCount: PARTICIPANTS.length + ' of ' + PARTICIPANTS.length + ' participants responded',
      namesPressed: s.names ? 'true' : 'false', pseudoPressed: s.names ? 'false' : 'true',
      namesBtnStyle: s.names ? segOn : segOff, pseudoBtnStyle: s.names ? segOff : segOn,
      showNames: () => this.setState({ names: true }), showPseudonyms: () => this.setState({ names: false }),
      processCards: processCards, partnerCards: partnerCards, followCards: followCards,
      hasSteerReports: steer.length > 0,
      steerTitle: steer.length + (steer.length === 1 ? ' participant' : ' participants') + ' said the partner may have pushed them',
      steerReports: steer.map(k => ({ name: who(k), pushed: RESPONSES[k].pushed, text: RESPONSES[k].pushedWhen || 'No details given.' })),
      transcript: transcript,
      drawerOpen: s.drawer, closeDrawer: () => this.setState({ drawer: false }),
      drawerHint: s.selectedMsg === null ? '' : 'Message #' + (s.selectedMsg + 1) + ' is highlighted. The full discussion is shown for context.',
      transcriptHint: s.selectedMsg === null ? 'Click "Open in discussion" on any response to see that moment in context.' : 'Showing message #' + (s.selectedMsg + 1) + ', highlighted.'
    }, vals);
  }
}

window.__DCComponent = Component;
