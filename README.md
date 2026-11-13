# Deliberation Partner: interactive demo

A clickable demo of the Deliberation Partner, an AI coach for participants in citizens' assemblies, using the Climate Assembly UK materials as the example.

The demo walks through the full participant experience:

1. **Materials**: upload a folder (or use the demo set), build the partner, and see the evaluation health check.
2. **Prepare**: a private chat with the partner before the session, with sourced answers.
3. **Discuss**: a simulated group discussion with three members and a facilitator, viewable as **Chat only**, **Chat and map**, or **Chat and flow**, with the partner's private check-ins throughout.

Everything is simulated in the browser: there is no backend, no API key, and no data leaves the page. Partner answers and the discussion use real figures and speaker names from the Climate Assembly UK materials. Uploaded files are only listed by name; their contents are never read or sent anywhere.

## Run it locally

```powershell
npm install
npm run dev
```

Then open http://localhost:3000. No Node? Any static server works, for example `py -m http.server 3000 -d public`.

## Deploy to Vercel

**From GitHub:** push this folder to a repository, then in Vercel choose **Add New > Project**, import the repo, and keep the framework preset as **Other**. `vercel.json` tells Vercel to serve the `public/` folder. Click **Deploy**.

**From the command line:**

```powershell
npx vercel          # preview deployment
npx vercel --prod   # production
```

## Deploy to Railway

1. Push this folder to a GitHub repository.
2. In Railway, choose **New Project > Deploy from GitHub repo** and pick the repo.
3. Railway detects Node, runs `npm install`, then `npm start`, which serves `public/` on the port Railway provides.
4. Under the service's **Settings > Networking**, click **Generate Domain** to get a public URL.

## How it's built

```
public/
  index.html       page shell, styles, and the page markup inside <template id="dc-template">
  app.js           the demo's logic: state, scripted content, evaluation metrics, partner behaviour
  dc-runtime.js    small renderer that fills the template from app.js (about 120 lines)
  vendor/preact.mjs  Preact 10 (MIT licence in vendor/PREACT-LICENSE.txt), bundled so nothing loads from a CDN
tools/
  build_from_canvas.py  regenerates index.html and app.js from the Design canvas artboard
package.json       `serve` for Railway and local preview
vercel.json        static output settings for Vercel
```

The markup uses a small template syntax: `{{ value }}` placeholders, `<sc-for>` for lists, `<sc-if>` for conditional blocks, and event handlers such as `onClick="{{ handler }}"`. `dc-runtime.js` renders it through Preact, so typing and scroll positions are preserved as the demo updates.

The only external request is Google Fonts (Inter and Space Grotesk). Remove the two font `<link>` tags near the top of `public/index.html` to make the site fully self-contained; it falls back to system fonts.

## Updating the demo

The demo was designed on a Design canvas. To regenerate the site from an updated artboard file:

```powershell
py tools/build_from_canvas.py path\to\FullUX.dc.html
```

Small changes can also be made directly in `public/app.js` (logic and text) and `public/index.html` (layout).
