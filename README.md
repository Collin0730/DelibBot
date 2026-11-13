# Deliberation Partner: interactive demo

A clickable demo of the Deliberation Partner, an AI coach for participants in citizens' assemblies, using the Climate Assembly UK materials as the example.

The site has two pages, linked by a small bar in the bottom-right corner.

**Participant experience** (`index.html`)

1. **Materials**: upload a folder (or use the demo set), build the partner, and see the evaluation health check.
2. **Prepare**: a quick "where do you stand?" pre-survey, then a private chat with the partner, with sourced answers.
3. **Discuss**: a simulated group discussion with three members and a facilitator, viewable as **Chat only**, **Chat and map**, or **Chat and flow**, with the partner's private check-ins throughout.
4. **Reflect**: a post-deliberation questionnaire. Before and after views per topic (telling apart reinforced, unmoved, and less certain), what moved you and what didn't (picked from the actual points made), plus the discussion process, the AI partner, and follow-ups.

**Organiser review** (`admin.html`)

Submitting the reflection takes you straight here, with your own answers in the fourth seat as "You", next to three simulated participants. The transcript is the discussion you just took part in, including what you said, so "Open in discussion" lands on your actual messages. "Show the simulated room instead" switches back to the fully simulated room. Opened directly, the page shows simulated responses from one breakout room. For each topic: opinion change before and after, the most and least persuasive points, and each participant's answers alongside what they said. Every point has "Open in discussion", which opens the transcript at that moment. Tabs for process, the AI partner (including any reports of steering), and follow-ups, plus a Names / Pseudonyms toggle.

Everything is simulated in the browser: there is no backend, no API key, and no data leaves the page. Partner answers and the discussion use real figures and speaker names from the Climate Assembly UK materials. Uploaded files are only listed by name; their contents are never read or sent anywhere. Questionnaire answers are kept only in your browser (localStorage) to pass them to the organiser page; nothing is sent to a server.

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
  index.html       participant experience: page shell, styles, markup inside <template id="dc-template">
  app.js           its logic: state, scripted content, evaluation metrics, partner behaviour, questionnaire
  admin.html       organiser review page
  admin.js         its logic and the simulated responses
  dc-runtime.js    small renderer that fills the template from app.js (about 120 lines)
  vendor/preact.mjs  Preact 10 (MIT licence in vendor/PREACT-LICENSE.txt), bundled so nothing loads from a CDN
tools/
  build_from_canvas.py  regenerates index.html and app.js from the Design canvas artboard
package.json       `serve` for Railway and local preview (plain static mode, so /admin works)
vercel.json        static output settings for Vercel
```

The markup uses a small template syntax: `{{ value }}` placeholders, `<sc-for>` for lists, `<sc-if>` for conditional blocks, and event handlers such as `onClick="{{ handler }}"`. `dc-runtime.js` renders it through Preact, so typing and scroll positions are preserved as the demo updates.

The only external request is Google Fonts (Inter and Space Grotesk). Remove the two font `<link>` tags near the top of `public/index.html` to make the site fully self-contained; it falls back to system fonts.

## Updating the demo

The demo was designed on a Design canvas. To regenerate the site from updated artboard files:

```powershell
py tools/build_from_canvas.py path\to\FullUX.dc.html path\to\AdminReview.dc.html
```

Small changes can also be made directly in `public/app.js` / `public/admin.js` (logic and text) and the matching `.html` files (layout).
