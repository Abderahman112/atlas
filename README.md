# Atlas: a multi-agent personal assistant on Telegram

Atlas is a personal assistant you text from your phone. An orchestrator agent talks to you and
hands work to five specialist agents, each with its own tools. It also reaches out on its own:
a morning brief, reminders before classes and deadlines, alerts for important email, an evening
check-in and a Sunday weekly review.

```mermaid
flowchart LR
  you((You on Telegram)) <--> bot[Telegram bot]
  bot <--> atlas[Atlas orchestrator]
  jobs[Scheduler: brief, reminders, inbox watch, check-ins] --> atlas
  atlas -->|ask_schedule| sch[Schedule agent]
  atlas -->|ask_inbox| inb[Inbox agent]
  atlas -->|ask_school| scl[School agent]
  atlas -->|ask_coop| coop[Co-op agent]
  atlas -->|ask_planner| pln[Planner agent]
  atlas --- db[(SQLite: history, to-dos, moods)]
  sch & scl & pln --> cal[Timetable + Google Calendar + ICS feeds]
  inb & scl & coop --> gmail[Gmail, read-only]
  coop --> xlsx[Co-op Tracker.xlsx]
  pln --> ch[30-day challenge plan]
```

| Agent | Answers | Tools |
|---|---|---|
| **Atlas** (orchestrator) | Everything you send; decides who to ask | `ask_*` for each specialist, to-dos, mood log |
| Schedule | "What do I have today?", free time, conflicts | merged calendar |
| Inbox | Email summaries, what needs a reply | Gmail search/read |
| School | Assignments, quizzes, midterms, time left | calendar, deadlines, to-dos, Gmail |
| Co-op | Application progress, what to apply to next, follow-ups | tracker spreadsheet, Gmail |
| Planner | A day plan adjusted to your energy (1–5) | calendar, deadlines, to-dos, moods, challenge |

## What happens automatically (Toronto time)

| When | What |
|---|---|
| Every 5 min | Reminders 20 min before class, 30 min before work and events. Deadlines at 3 days, 24 h and 3 h |
| Every 30 min | New unread email checked; you're only pinged for things that need you |
| 7:15 AM Sun–Thu, 9:00 AM Fri–Sat | Morning brief |
| 9:00 PM daily | Evening check-in: tomorrow's preview and how you're feeling |
| Sunday 11:30 AM | Weekly review |

No messages between 11 PM and 7 AM. Anything that came up overnight is sent after 7.

Commands: `/today /tomorrow /week /inbox /deadlines /coop /plan /tasks`, or just type normally:
"I'm wiped today, energy 2", "remind me to email my TA Friday at noon", "anything from recruiters?"

## Setup

### 1. Keys
- **Telegram:** message [@BotFather](https://t.me/BotFather), send `/newbot`, and copy the token.
- **Claude:** create an API key at console.anthropic.com. Set a monthly spend limit there.
- `cp .env.example .env` and fill both in.

### 2. Google (Gmail + Calendar, read-only)
1. At console.cloud.google.com, create a project and enable the **Gmail API** and **Google Calendar API**.
2. Under **OAuth consent screen**, choose External and add yourself as a test user.
3. Then **publish the app** (set it to "In production"). While it's in Testing mode, Google expires the login after 7 days and Atlas loses access. Since the app is only for you, the "unverified app" warning is fine to click through.
4. Under **Credentials**, create an OAuth client ID of type **Desktop app**, download the JSON and save it as `secrets/client_secret.json`.
5. On your Mac, run `python -m atlas.setup_google`. Sign in and `secrets/token.json` appears.

### 3. School and Apple calendars (ICS feeds in `ICS_FEEDS`)
- **Avenue to Learn:** Calendar → Subscribe → copy the feed link.
- **School Outlook calendar:** Outlook web → Settings → Calendar → Shared calendars → Publish → ICS link.
- **iCloud calendar:** Calendar app → right-click the calendar → Share → Public Calendar → copy the link.

### 4. Your profile and timetable
`cp data/profile.example.md data/profile.md` and `cp data/timetable.example.json data/timetable.json`,
then fill in who you are and your classes. Both files are git-ignored, so your personal details stay
off GitHub. Atlas falls back to the examples when they're missing.

### 5. Co-op tracker
Copy `Co-op Tracker.xlsx` into `data/`. After deploying, keep the server's copy up to date with
`deploy/sync_tracker.sh`, run from your Mac (hourly with cron is enough).

### 6. Run it
```bash
uv venv && uv pip install -r requirements-dev.txt
python -m pytest            # 14 tests, no network needed
python -m atlas             # then send /start to your bot and paste the id into TELEGRAM_OWNER_ID
```

### 7. Deploy (VPS, ~$5/month)
Any small Ubuntu VPS works (Hetzner, DigitalOcean, Lightsail). Clone the repo and create the venv,
then copy `.env`, `secrets/` and `data/Co-op Tracker.xlsx` over with rsync. Finally:
```bash
pm2 start deploy/ecosystem.config.js && pm2 save && pm2 startup
```

## Known limits
- **University email:** Microsoft 365 at universities usually blocks third-party apps. Atlas reads school mail if you set Outlook to **forward to Gmail**; if your school blocks forwarding, that mail isn't readable yet.
- **Apple Reminders** can't be read from a Linux server. Tell Atlas "remind me…" and it keeps its own to-do list with due-time pings.
- Atlas can **read** email and calendars but **can't send or change** anything. Replies are drafted as text for you to send.
- Email and calendar text is untrusted. The prompts tell every agent to report it, never obey it, and the tools are read-only, so a malicious email can't make Atlas act.

## Cost
Every agent runs on `claude-opus-5`: the orchestrator at medium effort, specialists at low, with prompt caching and server-side refusal fallback turned on. Expect a few cents per question plus the scheduled briefs. Set `ATLAS_MODEL=claude-sonnet-5` in `.env` to cut costs, and watch actual spend in the Claude Console.

## Roadmap
- [ ] Voice notes: transcribe Telegram voice messages (faster-whisper) and optionally reply with audio
- [ ] Apple Reminders sync through an iOS Shortcut webhook
- [ ] Update co-op statuses from chat (writes to the tracker)
- [ ] Morning phone call (Twilio Voice)
- [ ] Eval set of 30 real questions with expected answers, to catch regressions when prompts change
