// Entry point: pick the page from the URL.
import { html, render, useEffect, usePath, scope, navigate, Link, Toast, Logo } from './lib.js';
import { Login, Home, Create, Moderators, ModeratorHome, Shell } from './organiser.js';
import { Workspace } from './workspace.js';
import { Room } from './room.js';
import { Review } from './review.js';
import { Participant } from './participant.js';

function Page() {
  const path = usePath();
  const s = scope(path);
  const needsLogin = s.role === 'organiser' && !s.token && path !== '/login';
  useEffect(() => { if (needsLogin) navigate('/login'); }, [needsLogin]);
  let m;
  if (s.role === 'participant') return html`<${Participant} />`;
  if (s.role === 'moderator') {
    const rest = path.slice(s.base.length);
    if ((m = /^\/d\/([^/]+)\/review$/.exec(rest))) return html`<${Review} id=${m[1]} back=${`${s.base}/d/${m[1]}`} />`;
    if ((m = /^\/d\/([^/]+)$/.exec(rest))) return html`<header class="top"><div class="top-in"><${Link} href=${s.base} class="brand"><${Logo} /><span><b>Deliberation Partner</b><span class="small muted">Moderator workspace</span></span><//>
        <span class="right row"><${Link} href=${s.base}>All my deliberations<//><${Link} href=${`${s.base}/d/${m[1]}/review`}>Review<//></span></div></header><main class="page"><${Room} id=${m[1]} /></main>`;
    return html`<${ModeratorHome} />`;
  }
  if (path === '/login') return html`<${Login} />`;
  if (needsLogin) return null;
  if (path === '/') return html`<${Home} />`;
  if (path === '/new') return html`<${Create} />`;
  if (path === '/moderators') return html`<${Moderators} />`;
  if ((m = /^\/d\/([^/]+)\/review$/.exec(path))) return html`<${Review} id=${m[1]} back=${'/d/' + m[1]} />`;
  if ((m = /^\/d\/([^/]+)\/room$/.exec(path))) return html`<${Shell} active="home"><div class="col"><${Link} href=${'/d/' + m[1]}>← Back to the deliberation<//><${Room} id=${m[1]} /></div><//>`;
  if ((m = /^\/d\/([^/]+)$/.exec(path))) return html`<${Workspace} id=${m[1]} key=${m[1]} />`;
  return html`<${Shell}><div class="card pad"><h1>Page not found</h1><p><${Link} href="/">Back to your deliberations<//></p></div><//>`;
}

const root = document.getElementById('app');
root.textContent = '';
render(html`<${Page} /><${Toast} />`, root);
