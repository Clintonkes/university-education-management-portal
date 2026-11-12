# UEMP — University Education Management Portal

A web-based university management system with **four user roles** (Student, Lecturer, Department Admin, Super Admin), **role-based access control**, course registration, result entry and a **departmental result-approval workflow**.

Built for the *Lead Web Praxis Media Limited — Practical Software Development Test*.

> ## Submitted workflow: **Lecturer Result Submission**
> A lecturer signs in, sees their allocated courses, opens a course to see the registered students, enters CA and exam scores, lets the system calculate totals and grades, saves a draft, and submits the results for departmental approval. The lecturer also gets status and feedback, a performance summary, and correction requests after submission.
>
> - **Sign in as:** `lecturer@uemp.edu.ng` / `Lecturer@1234` and open **CSC 201** (11 students, ready for scores).
> - **Submission checklist** (deliverables, assessment areas, technical requirements, and where each is shown): **[docs/SUBMISSION.md](docs/SUBMISSION.md)**
> - **Full test guide**, covering every lecturer capability and the end-to-end workflow, with expected results: **[docs/LECTURER_WORKFLOW.md](docs/LECTURER_WORKFLOW.md)**
>
> The Student and Administrator areas are included only to support this workflow: students register for the course, and the department approves the results.

| | |
|---|---|
| **Language** | Python 3.12 |
| **Framework** | Flask 3 (application factory + blueprints) |
| **Database** | SQLAlchemy 2 ORM — SQLite locally, PostgreSQL in production |
| **Auth** | Flask-Login sessions, scrypt password hashing, CSRF protection (Flask-WTF) |
| **UI** | Server-rendered Jinja templates, Bootstrap 5, responsive (mobile → desktop) |
| **Tests** | 241 pytest tests (passing on SQLite **and** PostgreSQL) + 15 real-browser tests — see [docs/TEST_REPORT.md](docs/TEST_REPORT.md) |

Lecturer workflow test guide: **[docs/LECTURER_WORKFLOW.md](docs/LECTURER_WORKFLOW.md)**
Database design (ER diagram, every table): **[docs/DATABASE.md](docs/DATABASE.md)**
Technical documentation (architecture, database / ER diagram, permission logic, security): **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**
Deployment (GitHub + Neon + Render): **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** · Test report: **[docs/TEST_REPORT.md](docs/TEST_REPORT.md)**

---

## 1. Quick start (about 2 minutes)

```bash
# 1. Get the code and enter the folder
git clone <your-repo-url> uemp && cd uemp

# 2. Create a virtual environment and install packages
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Create the database and load demo data
flask --app run seed

# 4. Start the app
python run.py
```

Open **http://127.0.0.1:5000** and sign in with one of the accounts below. The login page also has clickable demo accounts that fill in the form for you.

> Prefer `uv`? `uv venv && uv pip install -r requirements.txt` works the same way.

### Useful commands

| Command | What it does |
|---|---|
| `flask --app run seed` | Create tables and load demo data (only if the database is empty) |
| `flask --app run seed --reset` | **Delete everything** and reload demo data |
| `flask --app run init-db` | Create empty tables only |
| `flask --app run create-superadmin` | Create your own Super Admin (for a clean production database) |
| `pytest` | Run the automated tests |

---

## 2. Test login credentials

| Role | Email | Password | What to try |
|---|---|---|---|
| Role | Email | Password | Use in the lecturer workflow |
|---|---|---|---|
| **Lecturer (main account)** | `lecturer@uemp.edu.ng` | `Lecturer@1234` | **CSC 201 is ready for score entry and submission**; CSC 101 (last session) is approved |
| Another lecturer | `bakare@uemp.edu.ng` | `Lecturer@1234` | Owns CSC 203, so it shows a lecturer cannot open someone else's course |
| **Department Admin** (Computer Science) | `csc.admin@uemp.edu.ng` | `Admin@1234` | Approves or returns the lecturer's results; allows or refuses correction requests |
| Student in CSC 201 | `csc25002@uemp.edu.ng` | `Student@1234` | Sees CSC 201 results only after approval |
| Student (not registered yet) | `student@uemp.edu.ng` | `Student@1234` | Supporting area: course registration |
| Super Admin | `admin@uemp.edu.ng` | `Admin@1234` | Supporting area: university set-up, audit trail |
| Department Admin (Economics) | `eco.admin@uemp.edu.ng` | `Admin@1234` | Shows that a department admin only sees their own department |

Other demo lecturers (`musa@`, `eze@`, `adeyemi@` …`uemp.edu.ng`) use `Lecturer@1234`; all other demo students use `Student@1234`. All of this is fictitious test data.

### What the demo data contains

- 3 faculties, 4 departments, 4 programmes, 13 courses (100 and 200 Level)
- Session **2025/2026** (finished, all results approved) and **2026/2027** (current: First Semester, registration **open**)
- 24 students: twelve 200-Level Computer Science students with approved 100-Level results (so GPA/CGPA work immediately), plus 100-Level CSC and Economics students

---

## 3. Demonstration script

### The lecturer workflow (submitted)

A quick run-through follows. The step-by-step checklist with expected results is in **[docs/LECTURER_WORKFLOW.md](docs/LECTURER_WORKFLOW.md)**.

1. Sign in as `lecturer@uemp.edu.ng`. The **Dashboard** shows this semester's courses, students taught, and results submitted or returned.
2. Open **CSC 201**. Its tabs are **Overview, Class list, Enter scores, Submit, Performance, Request correction**.
3. **Class list**: the 11 registered students, with **CSV** download and **Print**.
4. **Enter scores**: CA (max 40) and exam (max 60). The total and grade appear as you type. **Save draft** as often as you like; out-of-range or non-numeric scores are refused.
5. **Submit**: a checklist blocks submission until every student has both scores. Then **Submit for approval**, and the results lock.
6. **Performance**: average, median, pass rate, grade distribution, top students, and students who may need support.
7. Sign in as `csc.admin@uemp.edu.ng` → **Result Approval** → CSC 201 → **Return for correction** with a comment. The lecturer sees the feedback on their dashboard, fixes the score and resubmits. Every change is recorded (e.g. `Exam 45→50`).
8. The admin clicks **Approve & publish**. `csc25002@uemp.edu.ng` now sees CSC 201 in **Semester Results**.
9. After submitting, the lecturer uses **Request correction** to ask permission to edit. The department allows or refuses it.
10. Security: as the lecturer, open `/lecturer/courses/7` (another lecturer's course) or `/admin/` → **403 Access denied**.

### Supporting workflows (also built)

**Workflow 1 — Student course registration**
1. Sign in as `student@uemp.edu.ng`.
2. Go to **Course Registration**. Only 200-Level, First-Semester courses offered to Computer Science appear.
3. Tick courses and watch the unit counter; press **Register selected courses**.
4. Try to tamper: registering the same course again is refused (duplicate prevention).
5. Click **Print slip** for a printable registration form.

**Workflow 3 — Departmental result approval**
1. Sign in as `csc.admin@uemp.edu.ng` → **Result Approval**.
2. Open **CSC 203** (or the CSC 201 sheet you just submitted).
3. Either **Approve & publish**, or write a comment and **Return for correction**. **Reports → Department report** gives a one-page department report, with the formula behind every figure.
   - If returned, the lecturer sees the feedback on their dashboard, corrects and resubmits. Every changed score is recorded in the audit trail (e.g. `Exam 45→40`).
4. Sign in as a student in that class: the approved results and the updated GPA/CGPA now appear.

**Workflow 4 — Super Admin management**
1. Sign in as `admin@uemp.edu.ng`.
2. **Faculties & Departments** → create a faculty and a department.
3. **Sessions & Semesters** → create `2027/2028` (both semesters are created), make one current, and open or close registration. Mark semesters and sessions **completed**, edit dates, or add and delete semesters. Click a session or semester to see everything that happened in it.
4. **User Accounts** → create a Department Admin, change a lecturer's role, and suspend, unsuspend or unlock accounts. Delete people, programmes, departments and faculties; anything still in use is protected.
5. **Department Dashboard** → choose a department to see its full report, or leave it on "All" to compare departments.
6. **Registrations** → open any registration to change its course or type (regular, carry-over or elective), or add a remark.
7. **Roles & Permissions** shows the exact permission table the server enforces. **Audit Trail** shows every important action in plain English ("Results approved · by Dr. … (Department Admin)"), grouped by day and filterable by kind, person, role and date.

**Try the security**
- While signed in as a student, open `/admin/` or `/super/` in the address bar → **403 Access denied**.
- As `eco.admin@uemp.edu.ng`, open a CSC student's URL → **403**.

---

## 4. Project structure

```
.
├── run.py                  # starts the app (python run.py / gunicorn run:app)
├── config.py               # all settings: security, database, grading scale, limits
├── requirements.txt        # packages the live app needs
├── requirements-dev.txt    # + lint and browser-test tools
├── render.yaml / Procfile  # deployment (Render web service, Neon database)
├── .github/workflows/      # GitHub Actions: lint + tests on SQLite, PostgreSQL, browser
├── docs/                   # LECTURER_WORKFLOW (test guide), SUBMISSION, DATABASE, ARCHITECTURE (+ ER diagram), DEPLOYMENT, TEST_REPORT
├── tests/                  # 241 pytest tests; tests/e2e = browser tests
└── uemp/
    ├── __init__.py         # app factory: wires everything together
    ├── extensions.py       # database, login manager, CSRF objects
    ├── models/             # database tables (one file per area)
    ├── security/           # RBAC: permissions, route guards, department scope
    ├── services/           # business rules (registration, results, grading, …)
    ├── blueprints/         # web pages, one folder per area
    │   ├── auth/  main/  student/  lecturer/  admin/  superadmin/
    ├── templates/          # HTML (Jinja) – one folder per area
    ├── static/             # CSS and a small JS helper
    ├── navigation.py       # sidebar menu, filtered by permission
    ├── seed.py             # demo data
    └── cli.py              # flask commands (seed, init-db, create-superadmin)
```

Every Python file starts with a plain-English description of what it does, and functions explain their purpose and rules.

---

## 5. Configuration

Settings are read from environment variables (or a `.env` file — copy `.env.example`).

| Variable | Purpose | Default |
|---|---|---|
| `UEMP_ENV` | `development` or `production` | `development` |
| `SECRET_KEY` | Signs session cookies. **Required in production.** | dev-only value |
| `DATABASE_URL` | PostgreSQL URL. `postgres://` URLs are accepted. | SQLite file in `instance/` |
| `AUTO_SEED` | `1` = create demo data on first start (demo use only) | `0` |

Academic rules live in `config.py` and are documented there: **grading scale**, maximum CA (40) and exam (60) scores, maximum units per semester (24), academic levels.

### Grading scale (configurable in `config.py → GRADING_SCALE`)

| Total | Grade | Point |
|---|---|---|
| 70–100 | A | 5 |
| 60–69 | B | 4 |
| 50–59 | C | 3 |
| 45–49 | D | 2 |
| 40–44 | E | 1 |
| 0–39 | F | 0 |

**GPA** = Σ(course units × grade point) ÷ Σ(course units), using one semester's **approved** results. **CGPA** uses all approved results.

---

## 6. Deployment

The live setup is **GitHub** (code + automatic tests) → **Render** (runs the app) → **Neon** (PostgreSQL database).
Step-by-step guide, with troubleshooting: **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

In short:
1. Push the repository to GitHub.
2. Create a Neon project and copy its **pooled** connection string.
3. In Render, choose **New → Blueprint** and select the repository. Paste the Neon string when asked for `DATABASE_URL`. `render.yaml` sets everything else: it generates a `SECRET_KEY`, initializes and verifies the database tables at startup without inserting demo accounts, and sets the `/health` check.
4. Keep the free service awake: add a repository variable `APP_URL` (your Render URL) so `.github/workflows/keepalive.yml` pings `/health` every 10 minutes, and/or add a free UptimeRobot monitor. See [DEPLOYMENT.md, Step 6](docs/DEPLOYMENT.md#step-6--keep-the-app-awake-no-slow-first-load).

### Any other host (Railway, Fly.io, a VPS…)
```bash
export UEMP_ENV=production
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export DATABASE_URL="postgresql://user:pass@host:5432/uemp?sslmode=require"
pip install -r requirements.txt
flask --app run seed                # or: flask --app run init-db && flask --app run create-superadmin
gunicorn run:app --preload --workers 2 --bind 0.0.0.0:8000
```
Put the app behind HTTPS (the production config only sends cookies over HTTPS).

---

## 7. Running the tests

```bash
pip install -r requirements-dev.txt
pytest -q                                                          # 241 tests, in-memory SQLite
TEST_DATABASE_URL=postgresql://user:pass@localhost/uemp_test pytest -q   # same tests on PostgreSQL
playwright install --with-deps chromium && RUN_E2E=1 pytest tests/e2e -v  # real-browser tests
```

Only the lecturer workflow: `pytest -q tests/test_req_2b_lecturer.py tests/test_results.py tests/test_req_4_workflows.py`

Each test gets a fresh database with the demo data. The tests are organised by the brief's sections, so each requirement can be traced to its test:
- `test_req_2a…2d`: every ability and restriction of the four roles;
- `test_req_4_workflows`: workflows 1–4, step by step;
- `test_req_5_technical`: hashing, sessions, CSRF, DB-level duplicate prevention, audit, error pages;
- `test_req_6_business_rules`: rules 1–8 and GPA;
- `test_req_8_endpoint_matrix`: **every route in the app** called as anonymous and as each role (460 access checks);
- `tests/e2e`: Chromium clicks through the workflows and checks phone layouts and JavaScript errors.

Full requirement-to-test map and the bugs found: [docs/TEST_REPORT.md](docs/TEST_REPORT.md). GitHub Actions runs all of this on every push.

---

## 8. Out of scope (as stated in the brief)

Fee payments, accommodation, admissions, biometric attendance, SMS/email gateways, mobile apps, transcript certification and external integrations are not implemented. The service layer was designed so these could be added as new services and blueprints without changing existing code — see *Scaling* in the architecture document.
