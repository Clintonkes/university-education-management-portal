# Deployment guide — GitHub + Neon (database) + Render (web app)

This guide takes the project from your computer to a live URL in about 20 minutes.

```
 Your computer ──git push──▶ GitHub ──auto-deploy──▶ Render (runs the Python app)
                                                         │
                                                         └──DATABASE_URL──▶ Neon (PostgreSQL)
```

| Piece | What it does | Cost |
|---|---|---|
| **GitHub** | Stores the source code. Runs the automated tests on every push. | Free |
| **Neon** | Hosts the PostgreSQL database. | Free tier is enough |
| **Render** | Builds and runs the web app (gunicorn), gives you an `https://…onrender.com` URL. | Free tier is enough |

You need accounts on all three (sign in to Neon and Render **with GitHub**; it makes linking easier) and `git` on your computer.

---

## Step 1 — Put the code on GitHub

### 1a. Check nothing secret is included
`.gitignore` already excludes `.env`, `.venv/`, `instance/` (local SQLite database) and caches. **Never commit a `.env` file or a database password.**

### 1b. Create the repository and push

On github.com: **New repository** → name it `uemp` → leave *"Add a README"* **unticked** → **Create repository**.
Then, inside the project folder on your computer:

```bash
git init
git add .
git status                 # check: no .env, no .venv, no instance/ folder in the list
git commit -m "University Education Management Portal"
git branch -M main
git remote add origin https://github.com/<your-username>/uemp.git
git push -u origin main
```

> With the GitHub CLI installed you can replace the last two commands with
> `gh repo create uemp --public --source . --push`.

The brief asks for the source code on GitHub, so make the repository **public**, or keep it private and add the reviewers as collaborators (*Settings → Collaborators*).

### 1c. Automated tests on GitHub (already set up)
`.github/workflows/tests.yml` runs on every push. Open the **Actions** tab to watch it. It runs four jobs:

| Job | What it checks |
|---|---|
| `lint` | Code mistakes (unused or undefined names, etc.) |
| `sqlite` | The full test suite on SQLite |
| `postgres` | The full test suite on a real PostgreSQL server (the same engine as Neon) |
| `browser` | Headless Chromium clicks through all four workflows and checks phone layouts. Screenshots are attached to the run. |

A green tick means everything passed. You can add the badge to the README:
`![tests](https://github.com/<your-username>/uemp/actions/workflows/tests.yml/badge.svg)`

---

## Step 2 — Create the database on Neon

1. Go to **https://console.neon.tech** → **New Project**.
2. Fill in:
   - **Project name:** `uemp`
   - **Postgres version:** the default (16 or 17; anything ≥ 14 works).
   - **Region:** pick the one **closest to the Render region** you will choose in Step 3. Every page makes database calls, so distance adds delay.

     | Render region | Neon region |
     |---|---|
     | Frankfurt | AWS Europe Central 1 (Frankfurt) |
     | Virginia / Ohio | AWS US East 1 / US East 2 |
     | Oregon | AWS US West 2 |
     | Singapore | AWS Asia Pacific 1 (Singapore) |

3. Click **Create**. Neon creates a database called `neondb` and a role (user) for you.
4. On the project dashboard click **Connect**. In the dialog:
   - **Branch:** `main`, **Database:** `neondb`, **Role:** the default owner role.
   - Turn **Connection pooling ON**. The host name then contains `-pooler`.
   - Copy the connection string. It looks like:

     ```
     postgresql://neondb_owner:AbC123xyz@ep-cool-name-a1b2c3d4-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
     ```

Keep this string private: it contains the password. You will paste it into Render.

### Pooled or direct connection?

| | Pooled (`-pooler` in host) | Direct (no `-pooler`) |
|---|---|---|
| Use for | The running web app (**recommended**) | One-off admin jobs from your laptop (optional) |
| Why | Handles many short connections from gunicorn workers | Plain session; fine for scripts |

The app supports **both** with no code change. `config.py` does three things:
- Rewrites `postgresql://` to `postgresql+psycopg://`, so the psycopg 3 driver is used.
- Turns off server-side prepared statements (`prepare_threshold=None`), which the Neon pooler (PgBouncer) does not support.
- Sets `pool_pre_ping` and `pool_recycle=300`, so a connection that Neon closed while the database was asleep is replaced silently instead of causing an error.

Keep `?sslmode=require` on the end of the URL; Neon only accepts encrypted connections.

---

## Step 3 — Deploy the web app on Render

### Option A — Blueprint (recommended, uses `render.yaml`)

1. In the Render dashboard: **New → Blueprint**.
2. Connect your GitHub account if asked, then select the `uemp` repository.
3. Render reads `render.yaml` and shows one web service, **uemp**. It asks for the one value it cannot fill in itself:
   - **DATABASE_URL** → paste the Neon connection string from Step 2.
4. Click **Apply**. Render then:
   - Installs the packages (`pip install -r requirements.txt`).
   - Generates a random `SECRET_KEY`.
   - Starts `gunicorn run:app --preload --workers 2 --timeout 60 --bind 0.0.0.0:$PORT`.
   - On first start, creates any missing application tables in Neon and verifies that all model tables exist. It does not insert demo accounts.
   - Checks `/health` before sending traffic to the new version.
5. When the status turns **Live**, create the first administrator as described in Step 4, then sign in with that account.

To use a region other than the default (Oregon), add `region: frankfurt` (or `virginia`, `ohio`, `singapore`) under `name: uemp` in `render.yaml` before creating the Blueprint.

### Option B — Manual web service (without the Blueprint)

**New → Web Service** → pick the repository, then:

| Field | Value |
|---|---|
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn run:app --preload --workers 2 --timeout 60 --bind 0.0.0.0:$PORT` |
| Health check path (Advanced) | `/health` |
| Instance type | Free |

**Environment variables:**

| Key | Value | Notes |
|---|---|---|
| `UEMP_ENV` | `production` | Turns on secure (HTTPS-only) cookies. The app refuses to start without a real `SECRET_KEY`. |
| `SECRET_KEY` | a long random string | Make one with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | your Neon connection string | |
| `AUTO_SEED` | `0` | Keeps demo accounts out of the live database |
| `PYTHON_VERSION` | `3.12.7` | |

### Why `--preload`?
Gunicorn starts 2 worker processes. `--preload` initializes and verifies the schema once before the workers start, rather than having each worker attempt initialization. The app then closes its initialization database connections, so each worker opens its own.

The startup check creates missing tables, but it does not change columns or constraints on existing tables. Use an explicit database migration for future schema changes.

---

## Step 4 — After the first successful deploy

- **Keep `AUTO_SEED=0` for a real installation.** The app initializes and verifies the schema at startup without creating demo users.
- **Reset the demo data** (e.g. before the demo), from your computer:

  ```bash
  pip install -r requirements.txt
  DATABASE_URL="<neon connection string>" UEMP_ENV=production SECRET_KEY=x flask --app run seed --reset
  ```

  This deletes **all** data in that database and reloads the demo data. You can also use Render's **Shell** tab (paid plans) and run `flask --app run seed --reset`.
- **Create the first administrator:** after the service has started and initialized its tables, run this from a trusted local terminal using the Render `DATABASE_URL` and `SECRET_KEY` values:

  ```bash
  DATABASE_URL="<neon url>" UEMP_ENV=production SECRET_KEY="<render secret key>" flask --app run create-superadmin
  ```

  Then sign in and build faculties, departments, sessions and accounts from the Super Admin screens.
- **Redeploying:** every `git push` to `main` redeploys automatically (`autoDeploy: true`). Manual option: **Manual Deploy → Deploy latest commit**.
- **Custom domain:** Render → service → **Settings → Custom Domains**. HTTPS certificates are automatic.

### Optional: a safe copy of the data with Neon branches
In Neon, **Branches → Create branch** makes an instant copy of the database. Two uses:
- Point a second Render service (e.g. `uemp-staging`) at the branch to test changes against real-looking data.
- Create a branch before resetting the demo, so you can go back.

---

## Step 5 — Check the live site

1. `https://<your-app>.onrender.com/health` should return `{"status": "ok"}`.
2. Sign in with the administrator account you created in Step 4, then create the university structure and user accounts.
3. In the browser's developer tools (Application → Cookies), the session cookie should be marked **Secure** and **HttpOnly**.
4. In Neon → **Tables**, you can see the data: `users`, `course_registrations`, `result_sheets`, `audit_logs` and so on.

---

## Step 6 — Keep the app awake (no slow first load)

Render's free plan puts the app to sleep after **15 minutes** with no visitors. The next visitor then waits
about a minute while it starts again. Pinging `/health` regularly prevents this. `/health` does not use the
database, so Neon can still sleep and save its free compute hours.

Set up **one or both** of these:

**A. GitHub Actions (already in the repository: `.github/workflows/keepalive.yml`)**
1. GitHub repository → **Settings → Secrets and variables → Actions → Variables → New repository variable**.
2. Name `APP_URL`, value `https://<your-app>.onrender.com` (no trailing slash).
3. **Actions → Keep Render awake → Run workflow** to test it. It then runs by itself every 10 minutes.

GitHub can delay scheduled runs at busy times, and it pauses them in a repository with no commits for 60 days.

**B. UptimeRobot (free, every 5 minutes, also emails you if the site goes down)**
1. Sign up at <https://uptimerobot.com> → **New monitor**.
2. Monitor type **HTTP(s)**, friendly name `UEMP`, URL `https://<your-app>.onrender.com/health`.
3. Monitoring interval **5 minutes** → **Create monitor**.

Render's free plan includes 750 instance-hours a month, enough for one app awake all the time
(about 730 hours). Don't keep a second free service awake on the same account, or the hours run out before
the month ends.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Deploy fails with `RuntimeError: Set the SECRET_KEY…` | `SECRET_KEY` is missing. Add it under **Environment**. This is a deliberate safety check. |
| `connection … failed: … SSL` or `password authentication failed` | The `DATABASE_URL` was pasted incompletely. Copy it again from Neon → **Connect**, including `?sslmode=require`. If you reset the role password in Neon, update the value in Render. |
| `prepared statement "…" does not exist` | Only possible if the app's engine settings were changed. Keep `prepare_threshold: None` in `config.py`, or use the direct (non-pooler) URL. |
| First page load takes 30–60 s | Render free services sleep after 15 minutes without visits. Neon free databases also suspend when idle, and wake in about a second. Open the site a minute before a demo, or use a paid Render instance. |
| Login works, but you are logged out on every click | `UEMP_ENV=production` makes cookies HTTPS-only. Use the `https://` URL, not `http://`. |
| Login says the credentials are incorrect on a new database | The schema exists, but no account has been created yet. Run `flask --app run create-superadmin` with the Render database and secret-key environment values. |
| Pages show "Something went wrong" | Read **Render → Logs**. The error page hides the details from users, but the full traceback is in the log. |
| Data is missing after a deploy | Each deploy uses the same Neon database, so data persists. If tables are empty, check that `DATABASE_URL` points to the right Neon branch and database. |
| `ModuleNotFoundError` during build | The package is missing from `requirements.txt`. Add it, commit and push. |

---

## Deployment checklist (for the submission)

- [ ] GitHub repository is public, or reviewers are added as collaborators
- [ ] GitHub Actions run is green (lint, SQLite, PostgreSQL, browser)
- [ ] Neon project created, pooled connection string copied
- [ ] Render service is **Live**; `/health` returns `ok`
- [ ] All four test accounts can sign in on the live URL
- [ ] Live URL and test credentials are in the README / submission email
