// Shared pieces: rendering, API calls, routing, and small UI atoms.
import { html, render, useState, useEffect, useRef, useMemo, useCallback } from '/static/vendor/htm-preact.js';
export { html, render, useState, useEffect, useRef, useMemo, useCallback };

// ---- who is this tab? The link decides: /join/<token> is a participant, /m/<token> a moderator.
export function scope(path = location.pathname) {
  let m = /^\/join\/([^/]+)/.exec(path);
  if (m) return { role: 'participant', token: 'p.' + m[1], base: '/join/' + m[1] };
  m = /^\/m\/([^/]+)/.exec(path);
  if (m) return { role: 'moderator', token: 'm.' + m[1], base: '/m/' + m[1] };
  let token = null;
  try { token = localStorage.getItem('dp_org'); } catch (e) { /* storage blocked */ }
  return { role: 'organiser', token, base: '' };
}
export function setOrganiserToken(t) { try { t ? localStorage.setItem('dp_org', t) : localStorage.removeItem('dp_org'); } catch (e) { /* ignore */ } }

export async function api(method, path, body) {
  const s = scope();
  const opts = { method, headers: {} };
  if (s.token) opts.headers.Authorization = 'Bearer ' + s.token;
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const res = await fetch('/api' + path, opts);
  if (res.status === 401 && s.role === 'organiser' && path !== '/auth/login') { setOrganiserToken(null); navigate('/login'); }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch (e) { /* not JSON */ }
  if (!res.ok) {
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = msg.map(x => (x.loc ? x.loc[x.loc.length - 1] + ': ' : '') + x.msg).join('. ');
    const err = new Error(msg || 'Something went wrong (' + res.status + ').');
    err.status = res.status;
    throw err;
  }
  return data;
}
// POST a form with upload progress (fetch cannot report it). onProgress gets 0..1 as bytes leave the browser.
export function upload(path, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const s = scope();
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api' + path);
    if (s.token) xhr.setRequestHeader('Authorization', 'Bearer ' + s.token);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total); };
    xhr.upload.onload = () => onProgress && onProgress(1);
    xhr.onerror = () => reject(new Error('The upload did not reach the server. Check your connection and try again.'));
    xhr.onload = () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch (e) { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data);
      const detail = data && data.detail;
      reject(new Error(typeof detail === 'string' ? detail : xhr.status === 413 ? 'That upload is too large for the server.' : 'The upload failed (' + xhr.status + ').'));
    };
    xhr.send(formData);
  });
}
export const get = (p) => api('GET', p);
export const post = (p, b) => api('POST', p, b === undefined ? {} : b);

// ---- routing (history API)
const listeners = new Set();
export function navigate(path) { if (path !== location.pathname) history.pushState({}, '', path); listeners.forEach(f => f()); window.scrollTo(0, 0); }
window.addEventListener('popstate', () => listeners.forEach(f => f()));
export function usePath() {
  const [p, setP] = useState(location.pathname);
  useEffect(() => { const f = () => setP(location.pathname); listeners.add(f); return () => listeners.delete(f); }, []);
  return p;
}
export function Link({ href, children, ...rest }) {
  return html`<a href=${href} ...${rest} onClick=${(e) => { if (e.metaKey || e.ctrlKey || e.button) return; e.preventDefault(); navigate(href); }}>${children}</a>`;
}

// ---- data loading
export function useLoad(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const reload = useCallback(() => fn().then(data => setState({ data, error: null, loading: false }), error => setState(s => ({ ...s, error, loading: false }))), deps);
  useEffect(() => { setState(s => ({ ...s, loading: true })); reload(); }, [reload]);
  return { ...state, reload, set: (data) => setState({ data, error: null, loading: false }) };
}

// ---- toast
let toastSet = null;
export function toast(msg) { if (toastSet) toastSet(msg); }
export function Toast() {
  const [msg, setMsg] = useState('');
  toastSet = setMsg;
  useEffect(() => { if (!msg) return; const t = setTimeout(() => setMsg(''), 4500); return () => clearTimeout(t); }, [msg]);
  return msg ? html`<div class="toast" role="status">${msg}</div>` : null;
}
// Run an action, show any error as a toast, and return the result (or undefined on failure).
export async function attempt(fn) { try { return await fn(); } catch (e) { toast(e.message); return undefined; } }

// ---- labels and formatting
export const STAGES = [
  { id: 'none', label: 'No action taken', cls: '', bar: '#9A9E96' },
  { id: 'invited', label: 'Invites sent to participants', cls: 'blue', bar: '#3B73A8' },
  { id: 'scheduled', label: 'Deliberation scheduled', cls: 'teal', bar: '#2E8273' },
  { id: 'in_progress', label: 'Deliberation in progress', cls: 'purple', bar: '#6B4FA0' },
  { id: 'pending_debrief', label: 'Pending debrief', cls: 'amber', bar: '#C98A2E' },
  { id: 'complete', label: 'Complete', cls: 'green', bar: '#3F8A3F' },
];
export const stageIndex = (id) => STAGES.findIndex(s => s.id === id);
export function StageBadge({ stage }) { const s = STAGES[stageIndex(stage)] || STAGES[0]; return html`<span class=${'badge ' + s.cls}>${s.label}</span>`; }
export function fmtDate(iso, withTime = true) {
  if (!iso) return 'Not set';
  const d = new Date(iso);
  const date = d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
  return withTime ? date + ', ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : date;
}
export const fmtTime = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
const PALETTE = ['#2E8273', '#3B73A8', '#A8553B', '#6B4FA0', '#8C6D1F', '#1F6F8C', '#8C3B6B', '#4F7A2E'];
export function colorFor(key) { let h = 0; for (const ch of String(key || '')) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return PALETTE[h % PALETTE.length]; }
export function initials(name) {
  const parts = String(name || '?').replace(/\./g, '').split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : (parts[0] || '?').slice(0, 2)).toUpperCase();
}
export function Avatar({ name, id, size = 30 }) {
  return html`<span class="avatar" aria-hidden="true" style=${`width:${size}px;height:${size}px;background:${colorFor(id || name)};font-size:${Math.round(size * 0.4)}px`}>${initials(name)}</span>`;
}
export function Field({ label, help, children }) { return html`<label class="field">${label}${help && html`<span class="help">${help}</span>`}${children}</label>`; }
export function Logo() {
  return html`<svg width="28" height="28" viewBox="0 0 28 28" fill="none" stroke="#1F5A8C" stroke-width="2" aria-hidden="true"><circle cx="10" cy="12" r="7"></circle><circle cx="18" cy="16" r="7"></circle></svg>`;
}
export function Loading({ error }) { return error ? html`<div class="notice err" role="alert">${error.message}</div>` : html`<p class="muted">Loading.</p>`; }
export async function copyText(text, what = 'Link') {
  try { await navigator.clipboard.writeText(text); toast(what + ' copied.'); } catch (e) { window.prompt('Copy this ' + what.toLowerCase() + ':', text); }
}
export const absolute = (path) => location.origin + path;
