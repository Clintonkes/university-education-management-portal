# Test report

How the portal was tested against the assessment brief, and what was found.

> **Submitted workflow: Lecturer Result Submission.** The tests that prove it are listed below, in the rows for §2B Lecturer, Workflows 2 and 3, `test_results`, and browser tests 3, 4 and 11. The manual checklist with expected results is in [LECTURER_WORKFLOW.md](LECTURER_WORKFLOW.md). Run only these tests with:
> `pytest -q tests/test_req_2b_lecturer.py tests/test_results.py tests/test_req_4_workflows.py`

## Summary

| Run | Result |
|---|---|
| Automated suite on **SQLite** | **241 passed** |
| Same suite on **PostgreSQL 18** (the same engine as Neon) | **241 passed** |
| **Browser tests** (headless Chromium, real CSRF + JavaScript, htmx page swaps) | **15 passed** |
| Upgrade of a database made by the previous version (13 columns missing) on PostgreSQL | Columns added on startup, all 93 registrations kept, every page loads |
| Production rehearsal: gunicorn `--preload`, `UEMP_ENV=production`, empty PostgreSQL, `AUTO_SEED=1` | Started, seeded once, login and RBAC work, cookie `Secure; HttpOnly; SameSite=Lax` |
| Lint (`ruff --select F,E9,B`) | Clean |

## How to run the tests

```bash
pip install -r requirements-dev.txt

pytest -q                                   # 241 tests on an in-memory SQLite database (~40 s)

# Same tests on PostgreSQL (use an EMPTY throwaway database; tables are created and dropped)
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/uemp_test pytest -q

# Browser tests (opt-in; need Chromium)
playwright install --with-deps chromium
RUN_E2E=1 pytest tests/e2e -v
RUN_E2E=1 E2E_SCREENSHOTS=shots pytest tests/e2e   # also save a screenshot of each step
```

All four runs happen automatically on GitHub for every push (`.github/workflows/tests.yml`).

## Requirement → test map

Test files named `test_req_*` follow the brief's section numbers. Inside each file, the test names read like the brief's bullet points (e.g. `test_students_cannot_register_other_students`).

| Brief section | Where it is tested | Tests |
|---|---|---|
| §2A Student: 12 abilities + 4 restrictions | `tests/test_req_2a_student.py` | 16 |
| §2B Lecturer: abilities + restrictions (only own courses, no editing after submission, cannot approve) | `tests/test_req_2b_lecturer.py` | 17 |
| §2C Department Admin: students, lecturers, courses, allocation, programmes/levels, registrations, approvals, reports; **blocked outside own department**, including by tampering with form IDs | `tests/test_req_2c_dept_admin.py` | 27 |
| §2D Super Admin: faculties, departments, sessions, semesters, all accounts, roles, approvals, reports, audit | `tests/test_req_2d_super_admin.py` | 17 |
| §4 Workflows 1–4, step by step (comments `# 1.`, `# 2.` … match the brief) | `tests/test_req_4_workflows.py` | 4 |
| §5 Technical: RBAC table, password hashing, session expiry, CSRF, production secret check, DB relationships, **database-level duplicate prevention**, audit (who/what/when/IP), friendly 403/404/500, HTML escaping, mobile viewport, security headers | `tests/test_req_5_technical.py` | 23 |
| §6 Business rules 1–8, GPA weighting, configurable scale | `tests/test_req_6_business_rules.py` | 14 |
| §8 "Unauthorized users cannot access restricted pages or backend endpoints" | `tests/test_req_8_endpoint_matrix.py` | 6 |
| Unit and feature tests (grading boundaries, login lockout, RBAC, registration, results, super admin) | `test_grading`, `test_auth`, `test_rbac`, `test_registration`, `test_results`, `test_superadmin` | 86 |
| Second-round features: lecturer tabs, correction requests (ask / allow / refuse, from any semester), unsuspend and unlock, deletes with safety checks, complete/reopen/edit/add/delete sessions and semesters, activity pages, registration filter and Super Admin edits, department report, academic report, plain-English audit trail, schema upgrade | `tests/test_new_features.py` | 28 |
| Real browser: workflows 1–4 by clicking, live grade preview, unit counter, confirmation dialogs, 403 page, log-out confirmation (cancel and confirm); **no sideways scroll at phone width (390 px) on 20 main pages**; **no JavaScript console errors**; **the sidebar stays loaded while pages change** (no full reloads) and Back works; lecturer tabs and correction request; completing a semester and reading the audit trail | `tests/e2e/test_browser.py` | 15 |

### The endpoint matrix (§8) in more detail
The matrix test does **not** use a hand-written list of URLs. It reads every route registered in the app and calls each one, with GET and POST:

- **92 route/method pairs** are called as an anonymous visitor and as each of the 4 roles, which is **460 access checks**.
- Account status, delete and registration-edit actions under `/admin/` are Super Admin only; the test checks that department admins get 403 for them.
- The test fails if any role reaches another role's area, if a role is wrongly blocked from its own area, or if any route returns a 500.
- Any route added later is checked automatically.

## Problems found by testing, and fixed

| # | Problem | How it was found | Fix |
|---|---|---|---|
| 1 | On PostgreSQL, the app failed to connect in some situations: a SQLite-only setting (`check_same_thread`) leaked into the PostgreSQL connection settings. A settings dictionary was shared between app instances, and Flask-SQLAlchemy modified it. | Running the suite against PostgreSQL | Engine settings are now built fresh for each app in `create_app` |
| 2 | **Sessions & Semesters** page scrolled sideways by 80 px on phones, and **Faculties & Departments** by 20 px. | Browser test at 390 px width | Tables wrapped in `table-responsive`, and action buttons can wrap. The same wrapper was added to every other data table that lacked it. |
| 4 | **Confirmed buttons lost their value.** After "Submit for approval → Continue" the scores were only saved as a draft, and "Allow correction" sent no decision. htmx remembers the pressed button from focus events, and the confirmation dialog takes focus away. | Browser test of workflow 2 | `app.js` copies the button's `name=value` into a hidden field before submitting |
| 5 | Correction requests for an earlier semester did not appear in the department's results queue (it only listed the selected semester). | Browser test after the current semester changed | The "Correction requested" filter lists requests from every semester, with the semester name |
| 3 | Test infrastructure: two test clients shared one app context, so one user's login leaked into another client's requests. This could hide permission bugs. | Lecturer tests failing for the wrong reason | Each test request now runs in its own app context (`IsolatedClient` in `tests/conftest.py`) |

## Manual checks also done
- Every page rendered for every role on desktop and phone; screenshots reviewed.
- A form posted without a CSRF token is refused (400) with a friendly message.
- Production mode refuses to start with the default `SECRET_KEY`.
- Results stay hidden from students until approved, and are hidden again when reopened.
