# Deliberation Partner

A working web app for running small-group deliberations (for example citizens' assembly breakout rooms) with a private AI partner for each participant.

- **Organisers** set up a deliberation, upload briefing materials, check the partner with an evaluation run, invite participants, and review how views moved afterwards.
- **Moderators** run the live discussion and confirm what goes into the flow.
- **Participants** prepare with a private partner, take part in a live group chat, and reflect afterwards.

One service does everything: a FastAPI app serves the API, the live chat (WebSocket) and the web pages. Data lives in Postgres.

## What is in the box

| Path | What it is |
|---|---|
| `app/models.py` | The data model: 19 tables and 3 views |
| `app/routers/` | The API: organiser, participant, live room, review and export |
| `app/ai.py` | The partner, the flow tagger, AI stand-ins, whispers, the evaluation |
| `delib/` | The Phase 1 coach and evaluation package (retrieval, prompts, judge) |
| `web/` | The web app. Plain JavaScript modules, no build step |
| `alembic/` | Database migrations |
| `configs/models.yaml` | Which model plays which role |
| `examples/` | Sample briefing documents to upload |
| `tests/` | An end-to-end API test of a whole deliberation |

## Run it on your computer

You need Python 3.11 or newer and a Postgres database. The quickest route is Docker:

```
docker compose up --build
```

Then open http://localhost:8000 and sign in with `lucy@example.org` and the password `change-me`.

Without Docker (Windows PowerShell shown):

```
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # then edit .env: set DATABASE_URL, SECRET_KEY, ADMIN_PASSWORD
alembic upgrade head
uvicorn app.main:app --reload
```

Keep API keys in `.env` (it is git-ignored). Never commit them.

### Try the whole flow by yourself

1. Sign in, open **Moderators**, add yourself as a moderator and copy the sign-in link.
2. **Create new**, pick that moderator, then upload the files in `examples/riverside_library` on the Materials step and run the evaluation.
3. On Details, add two or three options (these become the first rows of the flow).
4. On Participants, add one person, click **Add AI stand-ins**, then **Send invites**. Copy the person's invite link.
5. Schedule it. Open the moderator link in one browser window and the invite link in a private window.
6. As the participant: accept, answer the pre-survey, ask the partner something.
7. As the moderator: start the deliberation. Chat from both windows. The stand-ins reply, the flow fills in, and proposed tags appear for the moderator to confirm.
8. End the deliberation. The participant window moves to the reflection. Submit it, then open the organiser review.

Each role's link works in its own tab, so one browser can hold an organiser tab, a moderator tab and a participant tab at once.

## Deploy to Railway

1. Push this folder to a new GitHub repository.
2. In Railway: **New Project**, **Deploy from GitHub repo**, and pick the repository. Railway builds it from the `Dockerfile` (see `railway.json`).
3. In the same project, add a **PostgreSQL** database.
4. On the web service, open **Variables** and add:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
   | `SECRET_KEY` | A long random string |
   | `ADMIN_EMAIL` | Your email (the first organiser account) |
   | `ADMIN_PASSWORD` | A strong password |
   | `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` | Optional. Without either, the AI runs on the mock |

5. Under **Settings, Networking**, generate a domain. Open it and sign in.

The service refuses to start on Railway until `SECRET_KEY` and `ADMIN_PASSWORD` are set, so the site is never public with the default password. Migrations run automatically on every deploy. The health check is `/api/health`, which also reports which models are live.

The admin account is created only when no organiser exists. To change the password later, update it in the database or delete the organiser row and redeploy.

## Models

`configs/models.yaml` lists, for each role, the profiles to try in order. The first one whose API key is present is used:

| Role | Does | Default order |
|---|---|---|
| `coach` | The participant-facing partner and whispers | Claude Sonnet, then GPT-6 Luna |
| `tagger` | Turns chat messages into flow rows and entries | Claude Haiku, then GPT-6 Luna |
| `standin` | AI stand-in participants | Claude Haiku, then GPT-6 Luna |
| `participant_sim`, `judge` | Evaluation conversations and scoring | Haiku and Luna |

With only `OPENAI_API_KEY` set, every role uses GPT-6 Luna. With no key, every role uses the offline mock: the partner gives placeholder answers, the tagger uses keyword rules, and evaluation scores are placeholders. The UI says so wherever that matters.

Model IDs and prices in that file change often. Check them against the providers' pricing pages before quoting costs. An evaluation run with real models is 12 short conversations plus judging.

## The data model

The flow is the centre of it:

- `flow_concept` is a row: an option, or a sub-point under one. It records who raised it and in which message.
- `flow_entry` is one person's position on a row (support, dissent, question or clarify), tied to the message where they said it.
- Entries are never overwritten. A change of mind is a new entry. A wrong tag is fixed with a new entry whose `supersedes_id` points at the old one. `topic_parent_id` links an entry to the one it replies to.
- The tagger proposes (`status = proposed`) and the moderator confirms. Tags above `TAG_AUTO_CONFIRM` confidence skip review.

Other choices worth knowing:

- Names and emails live only in `person`. Everything else uses participant ids and pseudonyms.
- What people say in the room (`flow_entry`) is separate from what they privately think (`private_stance`, `survey_response`).
- `survey_response` holds both the pre-survey and the reflection. `reflection_point` links a reflection to the exact entries that moved someone.
- `partner_whisper` logs every unprompted nudge with its model and prompt version, as an audit trail for non-steering.
- Uploaded files are turned into text (`document.content`) and chunks. The original file is not stored, so no file storage is needed.

Views: `v_current_entry`, `v_public_position`, `v_concept_summary`.

## The API

Interactive docs are at `/api/docs` on the running site, and the OpenAPI file is at `/api/openapi.json`.

`GET /api/deliberations/{id}/export` returns everything about one deliberation as JSON. It is pseudonymous by default, leaves out private partner chats, and includes survey and stance data only for people who agreed to research use. Add `?names=true` for an organiser copy with names.

Callers authenticate with `Authorization: Bearer <token>`: organisers with the token from `POST /api/auth/login`, moderators with `m.<their link token>`, participants with `p.<their link token>`.

## Tests

```
pip install -r requirements-dev.txt
$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/delib_test"   # an empty database
pytest
```

The test wipes and recreates every table in that database, so never point it at real data.

## Known limits

- **Email is not connected.** "Send invites" makes the links live; you copy and send them yourself. Links work like passwords.
- **Moderators and participants have no passwords**, only their links. Removing a moderator or cancelling an invite kills the link.
- **Scaling.** Live chat state is held in the web process, so run one replica. To scale out, replace the hub in `app/realtime.py` with Redis pub/sub.
- **Background AI jobs run in-process.** If the service restarts during an evaluation, that run stays "running"; start a new one.
- **Organisers can watch a room but not post.** The moderator speaks from their own link.
- **No map view yet.** The room has "Chat only" and "Chat and flow".
- **Scanned PDFs** need OCR before upload.

## Licences

The app code is yours to license. `web/static/vendor` contains Preact and htm (MIT and Apache 2.0, licence files included).
