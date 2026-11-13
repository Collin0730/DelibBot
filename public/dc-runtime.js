// Minimal runtime for the Deliberation Partner demo.
//
// The page markup lives in <template id="dc-template"> and uses a small
// template language:
//   {{ path }}                      value lookup (dotted path, no expressions)
//   attr="{{ path }}"               raw value (function, boolean, number...)
//   attr="text {{ path }} text"     interpolated string
//   <sc-for list="{{ xs }}" as="x"> repeat children for each item ($index in scope)
//   <sc-if value="{{ cond }}">      render children only when cond is truthy
//   onClick / onChange / ...        event handlers (functions from renderVals)
//
// The app logic (app.js) defines `class Component extends DCLogic` with
// renderVals(); this file renders that template through Preact, so DOM
// updates are diffed and inputs keep focus and caret position.

import { h, render, Component, Fragment } from './vendor/preact.mjs';

const WHOLE = /^\s*\{\{\s*([^}]+?)\s*\}\}\s*$/;
const HOLE = /\{\{\s*([^}]+?)\s*\}\}/g;
const TEXTISH_INPUTS = new Set(['text', 'search', 'email', 'url', 'tel', 'password', 'number', 'range', '']);

let TEMPLATE = null;

function lookup(path, scope) {
  const p = path.trim();
  if (p === 'true') return true;
  if (p === 'false') return false;
  if (p === 'null') return null;
  if (/^-?\d+(\.\d+)?$/.test(p)) return Number(p);
  if (/^(['"]).*\1$/.test(p)) return p.slice(1, -1);
  return p.split('.').reduce((obj, key) => (obj == null ? undefined : obj[key]), scope);
}

function interpolate(text, scope) {
  return text.replace(HOLE, (_, path) => {
    const v = lookup(path, scope);
    return v == null ? '' : String(v);
  });
}

function attrValue(raw, scope) {
  const whole = WHOLE.exec(raw);
  if (whole) return lookup(whole[1], scope);
  return raw.indexOf('{{') >= 0 ? interpolate(raw, scope) : raw;
}

function renderChildren(node, scope) {
  const out = [];
  node.childNodes.forEach((child) => {
    const r = renderNode(child, scope);
    if (Array.isArray(r)) out.push(...r);
    else if (r !== null && r !== undefined) out.push(r);
  });
  return out;
}

function renderNode(node, scope) {
  if (node.nodeType === 3) {
    const t = node.nodeValue;
    return t.indexOf('{{') >= 0 ? interpolate(t, scope) : t;
  }
  if (node.nodeType !== 1) return null;

  const tag = node.localName;
  if (tag === 'sc-for') {
    const list = attrValue(node.getAttribute('list') || '', scope) || [];
    const as = node.getAttribute('as') || 'item';
    return list.map((item, i) =>
      h(Fragment, { key: i }, ...renderChildren(node, Object.assign({}, scope, { [as]: item, $index: i })))
    );
  }
  if (tag === 'sc-if') {
    return attrValue(node.getAttribute('value') || '', scope) ? h(Fragment, null, ...renderChildren(node, scope)) : null;
  }

  const props = {};
  const type = (node.getAttribute('type') || '').toLowerCase();
  for (const attr of Array.from(node.attributes)) {
    const name = attr.name;
    if (name.startsWith('hint-')) continue;
    const value = attrValue(attr.value, scope);
    if (name.startsWith('on')) {
      let evt = name.toLowerCase();
      // React-style onChange on text fields fires per keystroke; map it to input.
      if (evt === 'onchange' && (tag === 'textarea' || (tag === 'input' && TEXTISH_INPUTS.has(type)))) evt = 'oninput';
      if (typeof value === 'function') props[evt] = value;
      continue;
    }
    if (value === false || value === null || value === undefined) continue;
    props[name] = value;
  }
  return h(tag, props, ...renderChildren(node, scope));
}

export class DCLogic extends Component {
  render() {
    const vals = typeof this.renderVals === 'function' ? this.renderVals() : {};
    return h(Fragment, null, ...renderChildren(TEMPLATE, vals));
  }
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = src;
    el.onload = resolve;
    el.onerror = () => reject(new Error('Could not load ' + src));
    document.body.appendChild(el);
  });
}

export async function mount({ templateId, appSrc, target, props }) {
  TEMPLATE = document.getElementById(templateId).content;
  window.DCLogic = DCLogic;
  await loadScript(appSrc);
  const App = window.__DCComponent;
  if (!App) throw new Error('app.js did not define the Component class');
  render(h(App, props || {}), target);
}
