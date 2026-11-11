# Submitted workflow: Lecturer Result Submission

This is the workflow submitted for the assessment. A lecturer:
1. signs in;
2. sees the courses allocated to them;
3. opens a course and sees the students registered for it;
4. enters CA and exam scores;
5. lets the system calculate totals and grades;
6. saves a draft or submits the results for approval.

The department then approves or returns the results. Approved results become visible to students.

The Student and Administrator areas are also in the application. Here they are used only to support this workflow: students register for the course, and the department admin approves the results.

This document has three parts:
- **Part A**: test every lecturer capability, one at a time.
- **Part B**: test the full workflow from start to finish.
- **Part C**: how it works in the code, for explaining it in the interview.

---

## Accounts used

All accounts use made-up demo data.

| Who | Email | Password | Role in this workflow |
|---|---|---|---|
| **Dr. Adaeze Okafor** (lecturer) | `lecturer@uemp.edu.ng` | `Lecturer@1234` | **Main tester.** Teaches **CSC 201** this semester (11 students, no scores yet) and taught **CSC 101** last session (results approved). |
| Prof. Tunde Bakare (another lecturer) | `bakare@uemp.edu.ng` | `Lecturer@1234` | Teaches CSC 203. Used to prove Dr. Okafor cannot open his course. |
| Computer Science department admin | `csc.admin@uemp.edu.ng` | `Admin@1234` | Approves or returns the results, and allows or refuses correction requests. |
| Student in the class | `csc25002@uemp.edu.ng` | `Student@1234` | Sees CSC 201 results only after they are approved. |

**Demo IDs on a freshly seeded database:**
- `/lecturer/courses/6` is Dr. Okafor's CSC 201.
- `/lecturer/courses/1` is her CSC 101 from last session.
- `/lecturer/courses/7` is Prof. Bakare's CSC 203.

On another database, use the links on the page instead.

> **Starting again.** Testing changes the data. For example, CSC 201 stays submitted once you submit it. To get back to the starting state:
> - **Locally:** run `flask --app run seed --reset`.
> - **Live database:** run the same command on your computer with `DATABASE_URL` set to the Neon connection string. This **deletes everything** in that database.

---

## What a lecturer can do, and where

| Brief requirement (§2B) | Where in the app |
|---|---|
| Log in to the lecturer dashboard | Sign in, then **Dashboard**: this semester's courses, students taught, results submitted, results returned |
| View assigned courses | **Dashboard** (this semester) and **My Courses** (every semester) |
| View students registered for each course | Course page → **Class list** tab |
| Access class lists | **Class list** → **CSV** (download) or **Print** |
| Enter CA and exam scores | Course page → **Enter scores** tab (CA max 40, exam max 60) |
| Modify scores before final submission | Same tab. Change any box and **Save draft** as often as needed. |
| Submit completed results | **Enter scores** → **Submit for approval**, or the **Submit** tab (shows a checklist first) |
| View submission status and feedback | **Overview** (status, history, feedback), the **Submit** tab, and a red alert on the **Dashboard** when results are returned |
| View course and student performance summaries | **Performance** tab: average, median, highest and lowest, pass rate, grade distribution, top students, and students who may need support |
| Change results after submitting (with permission) | **Request correction** tab. The department allows or refuses. |

| Restriction (§2B) | How it is enforced |
|---|---|
| Only manage courses assigned to them | Every course URL checks that the course belongs to the signed-in lecturer. Otherwise: **403**. |
| Cannot modify courses or students | Lecturers have no admin permissions. Any `/admin/…` or `/super/…` page returns **403**. |
| Cannot edit after submission without reopening | Submitted and approved results are read-only. The server refuses edits even if the form is changed by hand. |
| Cannot approve results | Lecturers have no review permission. Nobody can approve results they submitted themselves. |

---

## Part A — Test each capability

Sign in as **`lecturer@uemp.edu.ng` / `Lecturer@1234`**. Do the steps in order. The expected result is in the right-hand column.

### A1. Sign in and dashboard
| # | Do this | You should see |
|---|---|---|
| 1 | On the login page, click the **Lecturer** demo chip (or type the email and password) and sign in. | The **Lecturer dashboard**: "Welcome, Dr. Adaeze Okafor", Computer Science, First Semester 2026/2027 |
| 2 | Look at the four cards. | Courses this semester **1**, Students taught **11**, Results submitted **0**, Returned to me **0** |
| 3 | Look at the **My courses** table. | **CSC 201 · Data Structures and Algorithms**, 3 units, 200 Level, 11 students, status **Draft**, buttons **Class list** and **Enter scores** |
| 4 | Type a wrong password at sign-in, once. | "Incorrect email or password." After too many wrong tries the account is locked for a few minutes. |

### A2. Assigned courses
| # | Do this | You should see |
|---|---|---|
| 1 | Click **My Courses** in the sidebar. | CSC 201 (this semester) **and CSC 101** (First Semester 2025/2026, Approved). Only her own courses are listed. |
| 2 | Watch the sidebar while you move between pages. | It stays in place; only the main panel changes. |

### A3. Class list
| # | Do this | You should see |
|---|---|---|
| 1 | Open **CSC 201** → **Class list** tab. | 11 students, **CSC/2025/002 … CSC/2025/012**, with name, programme, level, email and date registered |
| 2 | Click **CSV**. | `CSC201_class_list.csv` downloads (matric no, name, level, CA, exam, total, grade) |
| 3 | Click **Print**. | A printable class list opens in a new tab |

### A4. Enter and modify scores (draft)
| # | Do this | You should see |
|---|---|---|
| 1 | Open the **Enter scores** tab. | One row per student with **CA (40)** and **Exam (60)** boxes. The tab shows "11 to do". |
| 2 | Type CA `32` and Exam `45` for the first student. | **Total 77** and grade **A** appear immediately, before saving |
| 3 | Fill in about half the students and click **Save draft**. | "Draft saved." The scores stay after reloading. A partial draft is allowed. |
| 4 | Change one of the saved scores and save again. | The new value is kept. The change is recorded in the history. |
| 5 | Type CA `45` (over 40) and save. | Box turns red; the server refuses: "CA for … must be between 0 and 40." |
| 6 | Type `abc` or `-5` and save. | Refused: "must be a number" or "between 0 and …" |
| 7 | Type a decimal, e.g. CA `32.5`. | Accepted. The total is calculated with the decimal. |

**How grades are worked out** (configurable in `config.py`):

| Total | Grade |
|---|---|
| 70–100 | A |
| 60–69 | B |
| 50–59 | C |
| 45–49 | D |
| 40–44 | E |
| 0–39 | F |

### A5. Submission checks
| # | Do this | You should see |
|---|---|---|
| 1 | With some scores still empty, open the **Submit** tab. | A checklist: "11 student(s) on the class list ✔" and "**N student(s) still missing a CA or exam score** ✘". The submit button is disabled. |
| 2 | Go back to **Enter scores** and click **Submit for approval** with scores missing, then confirm. | Refused: "Enter both CA and exam scores for every student before submitting. Missing: …". What you typed is kept as a draft. |
| 3 | Fill in **every** student and **Save draft**. | Overview shows **Scores entered 11 / 11** |

### A6. Performance summary
| # | Do this | You should see |
|---|---|---|
| 1 | Open the **Performance** tab. | Class average, median, highest and lowest, passed and failed with pass rate, grade distribution bars, top students, and students who may need support (lowest scores) |
| 2 | Read the note under it. | The formula for average, pass rate and spread |

### A7. Restrictions (security)
| # | Do this | You should see |
|---|---|---|
| 1 | In the address bar, open `/lecturer/courses/7` (Prof. Bakare's CSC 203). | **403 Access denied** |
| 2 | Open `/admin/` or `/admin/students`. | **403** (lecturers cannot manage courses or students) |
| 3 | Open `/admin/results`. | **403** (lecturers cannot approve results) |
| 4 | Open `/super/`. | **403** |
| 5 | Sign out, then open `/lecturer/`. | Sent to the login page |

> Part B continues from here, with CSC 201 fully scored but not yet submitted.

---

## Part B — The full workflow, end to end

This follows the brief's Workflow 2 (steps 1–10). It also covers what happens when results are returned and when a correction is needed after approval.

### B1. Submit for approval (lecturer)
1. As the lecturer, open **CSC 201 → Submit**. The checklist should be all green.
2. Click **Submit 11 results for approval** and confirm in the dialog.
3. **Expected:**
   - "Results submitted for departmental review. They are now locked."
   - Status **Submitted**.
   - A yellow banner: "Results are locked while the department reviews them".
   - The **Scores** tab is read-only.
   - The dashboard shows **Results submitted 1**.
4. **Try to edit anyway:** the score boxes are gone. A hand-crafted POST is refused with "can no longer be edited" (covered by automated tests).
5. Sign in as `csc25002@uemp.edu.ng` → **Semester Results**. CSC 201 has **no score** yet; it is only listed under "registered but their results have not been approved yet".

### B2. Department returns the results (department admin)
1. Sign in as `csc.admin@uemp.edu.ng` → **Result Approval**. CSC 201 is listed under **Awaiting review**.
2. Click **Review**. You see every score, the grade distribution and the pass rate.
3. Write a comment, e.g. `Please re-check the exam score for CSC/2025/004`, and click **Return for correction**.
   - A comment is required. Returning without one is refused.

### B3. Lecturer sees the feedback and corrects (lecturer)
1. Sign in as the lecturer. The **Dashboard** shows a red alert: "**CSC 201 was returned for correction.**", with the admin's comment and a **Fix now** button.
2. Click **Fix now**. The feedback is shown at the top, and the scores are editable again.
3. Change CSC/2025/004's exam score, then **Submit for approval** again.
4. **Overview → Submission history** lists every step: submitted, returned (with the comment), each score changed (e.g. `Exam 45→50`), and resubmitted.

### B4. Department approves (department admin)
1. As `csc.admin@uemp.edu.ng`: **Result Approval** → CSC 201 → **Approve & publish**, then confirm.
2. As the lecturer, the course shows **Approved by …**, and the Overview says "Nothing to do".

### B5. Students see the approved results (student)
1. Sign in as `csc25002@uemp.edu.ng` → **Semester Results**.
2. CSC 201 (Data Structures and Algorithms) now appears with its score and grade, and the GPA includes it.

### B6. Correction after submission or approval (authorisation)
1. As the lecturer, open **CSC 201** (or last session's **CSC 101**, already approved) → **Request correction**.
2. Type a reason of at least 10 characters, e.g. `The exam score for CSC/2025/006 was entered as 35 instead of 53.`, and click **Send request to department**.
   - **Expected:** the tab shows "pending", and the dashboard shows "correction requested".
   - Asking twice is refused: "You have already asked".
3. As `csc.admin@uemp.edu.ng`: **Result Approval** → filter **Correction requested**. Requests from any semester are listed. Open the sheet.
   - **Refuse:** a reason is required. The lecturer sees "Correction request refused …", and the results stay locked.
   - **Allow correction** (confirm): the results go back to the lecturer as **Returned**, and students stop seeing an approved sheet until it is approved again.
4. As the lecturer, correct the score and submit again. Then the admin approves it again, as in B4.

**Status flow:**

```
 DRAFT ──submit──▶ SUBMITTED ──approve──▶ APPROVED  (students can see)
   ▲                  │   ▲                   │
   │                return │                reopen / correction allowed
   │                  ▼   │resubmit           ▼
   └──────────────  RETURNED ◀────────────────┘
        (lecturer edits; every change recorded)
```

---

## Part C — How it works (for explaining the code)

**Files involved:**

| Part | File |
|---|---|
| Pages and URLs | `uemp/blueprints/lecturer/routes.py`: the dashboard, course list, course page with tabs, score save/submit, correction request, CSV and print |
| Rules (validation, totals, grades, locking, submit, correction) | `uemp/services/results.py`: `save_scores`, `request_correction`, `sheet_summary`, `get_allocation` |
| Grade calculation | `uemp/services/grading.py` and `GRADING_SCALE` in `config.py` |
| Approval side | `uemp/blueprints/admin/results.py` and `results.approve / reject / grant_correction / decline_correction` |
| Permissions | `uemp/security/permissions.py`: the lecturer role has only `lecturer.portal` and `results.enter` |
| HTML | `uemp/templates/lecturer/`: `dashboard`, `courses`, `course_detail` (the tabs), `print_sheet` |
| Live grade preview | `uemp/static/js/app.js` → `initScoreSheet`. This is only a preview; the server recalculates. |
| Tables | `ResultSheet` (one per course per semester, holds the status) and `ResultEntry` (one per registered student: CA, exam, total, grade, grade point) |

**What happens when the lecturer clicks "Submit for approval":**
1. The browser posts the form to `POST /lecturer/courses/<id>/scores` with `action=submit` and the CSRF token.
2. `protect_blueprint` checks that the user is signed in and has `lecturer.portal`. Otherwise the user gets the login page or a 403.
3. `_my_allocation()` checks that the course is allocated to **this** lecturer. Otherwise: 403.
4. `save_scores(…, submit=True)`:
   - refuses if the sheet is not Draft or Returned;
   - checks each score is a number within range;
   - calculates total, grade and grade point;
   - records every changed score in the audit log;
   - refuses to submit if any student is missing a score;
   - sets the status to **SUBMITTED** and saves the time.
5. The page redirects to the Overview tab with a success message. htmx swaps only the main panel, so the sidebar stays.

**Why the scores are safe:**
- Totals and grades are always calculated on the server.
- Locking is checked on the server, not just by hiding the boxes.
- A lecturer can never approve results; even an admin cannot approve results they submitted.
- Each student can appear only once on a sheet, enforced by a database unique constraint.

---

## Automated tests for this workflow

Run them with:

```bash
pytest -q tests/test_req_2b_lecturer.py tests/test_results.py tests/test_req_4_workflows.py tests/test_new_features.py
```

| File | What it proves |
|---|---|
| `tests/test_req_2b_lecturer.py` (17 tests) | Every §2B ability and restriction: dashboard, own courses only, class list, CSV and print, draft and partial draft, bad, negative and decimal scores, submit, status and feedback, performance, no editing after submission, cannot approve, cannot approve own results, a course moved to another lecturer |
| `tests/test_results.py` | Totals and grades, out-of-range scores, missing scores block submission, locking, students cannot see unapproved results, full cycle (submit → return → correct → resubmit → approve), reopen |
| `tests/test_req_4_workflows.py` | Workflow 2 and Workflow 3 step by step, numbered like the brief |
| `tests/test_new_features.py` | Every tab opens, and correction requests are allowed, refused, need a reason, and work from older semesters |
| `tests/test_req_8_endpoint_matrix.py` | Every URL in the app called as a lecturer: everything outside the lecturer area returns 403 |
| `tests/e2e/test_browser.py` (tests 3, 4, 11) | In a real Chromium browser: live grade preview, draft, submit with the confirmation dialog, admin return and approve, the tabs, and a correction request |
