# Submission checklist

**Chosen workflow: Lecturer Result Submission.** The full portal, with all four roles, is included so the workflow can be tested end to end.

- **Repository:** https://github.com/Clintonkes/university-education-management-portal
- **Live app:** *(your Render URL)*

---

## Submission form answers

| Form field | Link to give |
|---|---|
| Source code | https://github.com/Clintonkes/university-education-management-portal |
| Technical documentation (architecture, database, stack, security, setup) | https://github.com/Clintonkes/university-education-management-portal#readme. The README has the setup and links to [ARCHITECTURE.md](ARCHITECTURE.md), which covers the stack, architecture, database, RBAC and security. |
| Database design (schema or ER diagram) | https://github.com/Clintonkes/university-education-management-portal/blob/main/docs/DATABASE.md: the ER diagram, every table and column, keys, constraints, and how the design supports the lecturer workflow |
| Demonstration (short video) | Record it yourself (see the script at the end), upload it to YouTube (unlisted), Loom or Google Drive (anyone with the link), and paste the link |

---

## Deliverables (§7)

| # | Deliverable | Where |
|---|---|---|
| 1 | Functional web-based portal | The live Render URL, or locally with `python run.py` |
| 2 | Working dashboards for all four roles | Student `/student/`, Lecturer `/lecturer/`, Department Admin `/admin/`, Super Admin `/super/` |
| 3 | Source code | GitHub repository |
| 4 | Database schema or ER diagram | [DATABASE.md](DATABASE.md): ER diagram, all 14 tables, keys and constraints |
| 5 | README with installation and setup | [README.md §1 Quick start](../README.md), §5 Configuration, §6 Deployment, and [DEPLOYMENT.md](DEPLOYMENT.md) |
| 6 | Test login credentials for each role | [README.md §2](../README.md) and the login page (one-click demo accounts for every role) |
| 7 | Technical documentation (architecture, database, permission logic) | [ARCHITECTURE.md](ARCHITECTURE.md) §2 architecture, §3 database, §4 RBAC, §5 security |
| 8 | Short demonstration | The video (script below) and [LECTURER_WORKFLOW.md](LECTURER_WORKFLOW.md) |
| — | Sample data | Loaded by `flask --app run seed`: 3 faculties, 4 departments, 13 courses, 24 students, 5 lecturers, two sessions of results |

---

## Assessment areas

| Area (weight) | What covers it | Where to look |
|---|---|---|
| **System architecture and database design (15%)** | Flask app factory with blueprints per role; a service layer for business rules; 14 related tables with foreign keys and unique constraints | [ARCHITECTURE.md §2–3](ARCHITECTURE.md) |
| **Role-based access control and security (20%)** | Three layers: permission per role, department scope, and ownership. Plus hashed passwords, CSRF, lockout, session expiry and secure headers. Every route is tested against every role (460 checks). | [ARCHITECTURE.md §4–5](ARCHITECTURE.md), `uemp/security/`, `tests/test_req_8_endpoint_matrix.py` |
| **Student and course management (15%)** | Department admins manage students, lecturers, courses, programmes and allocations. The lecturer sees class lists. | `/admin/students`, `/admin/courses`, `/admin/allocations`; lecturer **Class list** tab |
| **Course registration workflow (10%)** | Students register for courses offered to their programme, level and semester, with a unit limit and no duplicates | Student `/student/courses`; README Workflow 1 |
| **Result entry and approval workflow (15%)** | **The chosen workflow**: score entry, draft, submit, department approve or return, correction requests, students see only approved results | [LECTURER_WORKFLOW.md](LECTURER_WORKFLOW.md) |
| **Super Admin functionality (10%)** | Faculties, departments, sessions and semesters, user accounts and roles, university reports, audit trail | `/super/`; README Workflow 4 |
| **UI/UX and responsiveness (5%)** | Bootstrap 5; works at phone width (tested at 390 px); fast page changes without full reloads; confirmation dialogs; toasts | Browser tests in `tests/e2e/` |
| **Code quality and documentation (5%)** | Each file starts with a plain-English explanation; rules live in services, not pages; ruff lint in CI | `uemp/services/`, `docs/` |
| **Testing and problem-solving (5%)** | 241 automated tests on SQLite and PostgreSQL, plus 15 real-browser tests; bugs found and fixed are listed | [TEST_REPORT.md](TEST_REPORT.md) |

---

## Technical requirements (§5)

| Requirement | How it is met | Where |
|---|---|---|
| Proper RBAC | Permission table per role; every area of the app is protected as a whole, so new routes are covered too | `uemp/security/permissions.py`, `decorators.py`, `scope.py` |
| Secure authentication and session management | scrypt password hashing, sessions that expire after 30 minutes, a 15-minute lockout after repeated wrong passwords, HttpOnly/SameSite cookies (also Secure in production), and logout only by POST, after a confirmation dialog | `uemp/blueprints/auth/`, `config.py` |
| Backend validation of permissions | Every check happens on the server. Hiding a button is never the only protection; changed URLs or form IDs return 403. | `tests/test_req_2c_dept_admin.py`, endpoint matrix |
| Relationships between students, lecturers, courses, departments and results | Foreign keys from users, profiles, departments, programmes, courses, allocations, registrations, result sheets and result entries | ER diagram, `uemp/models/` |
| Data validation and duplicate prevention | Form and service validation (score ranges, unit limits, required reasons), backed up by database `UNIQUE` constraints | [ARCHITECTURE.md "Duplicate prevention"](ARCHITECTURE.md) |
| Secure storage and handling of academic records | Totals and grades are always calculated on the server; results lock after submission; only approved results are visible to students; deletes are blocked for records in use | `uemp/services/results.py` |
| Audit trails for submissions and approvals | Every submission, approval, return, reopening, correction and score change is recorded with who, what, when and IP | Super Admin **Audit Trail**; the lecturer's **Overview** history |
| Responsive interface | Phone, tablet and desktop layouts; tested for no sideways scroll at phone width on 20 pages | `tests/e2e/test_browser.py` |
| Error handling and user feedback | Friendly 403, 404 and 500 pages; success and error messages; inline form errors; confirmation dialogs | `uemp/templates/errors/`, `app.js` |
| Clean, maintainable code | Routes → services → models; configuration in one file | [ARCHITECTURE.md §2](ARCHITECTURE.md) |
| Explained technical decisions | Why each tool was chosen | [ARCHITECTURE.md §1](ARCHITECTURE.md) |

Business rules 1–8 and the GPA calculation are mapped to tests in [TEST_REPORT.md](TEST_REPORT.md) (`tests/test_req_6_business_rules.py`).

---

## Demonstration video script (about 5 minutes)

1. **Login page (20 s).** Show the one-click demo accounts for every role.
2. **Lecturer (2½ min).** Sign in as `lecturer@uemp.edu.ng`:
   - Show the dashboard, then CSC 201's **Class list**, including CSV and print.
   - **Enter scores**: show the live grades, try typing 45 in CA (the 5 is refused with a message), then **Save draft**.
   - **Submit**: show the checklist blocking submission while scores are missing; fill them in, then submit.
   - Show the **Performance** tab.
   - Show a 403 when opening `/lecturer/courses/7`.
3. **Department admin (1 min).** Sign in as `csc.admin@uemp.edu.ng`:
   - **Result Approval** → CSC 201 → **Return for correction** with a comment.
   - Switch to the lecturer: show the feedback, fix a score, and resubmit.
   - Back as the admin: **Approve & publish**.
4. **Student (30 s).** Sign in as `csc25002@uemp.edu.ng` → **Semester Results**: CSC 201 now shows, with the GPA.
5. **Traceability (30 s).** As `admin@uemp.edu.ng` → **Audit Trail**: every step above is listed.
6. **Log out (10 s).** Show the confirmation dialog.
