# MindTrace

A student learning-gap identification web application.

---

## Requirements

- Python 3.8 or later (check with `python --version`)
- Windows PowerShell

---

## Installation

### 1. Open PowerShell and navigate to the project folder

```powershell
cd D:\Projects\MindTrace
```

### 2. One-time fix if virtual environment activation is blocked

If you have never run a PowerShell script before, run this once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. Create and activate the virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Your prompt will show `(venv)` when the environment is active.
You must activate it every time you open a new terminal window.

### 4. Install dependencies

```powershell
pip install flask==3.1.0
```

---

## Database Setup

### Initialise the database and seed all sample accounts and content

```powershell
python seed.py
```

This creates `mindtrace.db`, creates all 28 tables, inserts the 21 sample user
accounts, and seeds a small set of sample content (subject, class, section,
textbook, chapters, concepts, prerequisite, and textbook pages).

It is safe to run multiple times — all inserts use `INSERT OR IGNORE` and will
never create duplicates.

---

## Running the Application

```powershell
python app.py
```

Open your browser and go to: **http://127.0.0.1:5000**

To stop the application press `Ctrl+C` in the terminal.

---

## Running the Tests

```powershell
python -m unittest discover -s tests -v
```

37 tests should pass across two suites:

| Suite | File | Tests | Covers |
|-------|------|-------|--------|
| Authentication | `tests/test_auth.py` | 9 | Login, logout, role routing, session protection |
| Schema | `tests/test_schema.py` | 28 | Table existence, columns, constraints, append-only triggers |

Tests use separate temporary database files and do not affect `mindtrace.db`.

---

## Sample Login Credentials

| Username   | Password   | Role    |
|------------|------------|---------|
| teacher1   | Teach@2025 | Teacher |
| student01  | Study@2025 | Student |
| student02  | Study@2025 | Student |
| student03  | Study@2025 | Student |
| student04  | Study@2025 | Student |
| student05  | Study@2025 | Student |
| student06  | Study@2025 | Student |
| student07  | Study@2025 | Student |
| student08  | Study@2025 | Student |
| student09  | Study@2025 | Student |
| student10  | Study@2025 | Student |
| student11  | Study@2025 | Student |
| student12  | Study@2025 | Student |
| student13  | Study@2025 | Student |
| student14  | Study@2025 | Student |
| student15  | Study@2025 | Student |
| student16  | Study@2025 | Student |
| student17  | Study@2025 | Student |
| student18  | Study@2025 | Student |
| student19  | Study@2025 | Student |
| student20  | Study@2025 | Student |

---

## Project Structure

```
MindTrace\
├── app.py                       # Flask routes and authentication logic
├── database.py                  # SQLite connection, schema setup, and triggers
├── seed.py                      # Creates sample accounts and content
├── requirements.txt             # Pinned dependencies (flask==3.1.0)
├── mindtrace.db                 # SQLite database file (created by seed.py)
├── README.md                    # This file
├── templates\
│   ├── base.html                # Shared page layout
│   ├── login.html               # Login form
│   ├── teacher_dashboard.html   # Teacher welcome page
│   └── student_dashboard.html   # Student welcome page
├── static\
│   └── style.css                # Application styles
└── tests\
    ├── test_auth.py             # Authentication tests
    └── test_schema.py           # Schema and trigger tests
```

---

## Database Schema

The database has 28 tables across 7 groups:

| Group | Tables |
|-------|--------|
| Core | `users` |
| Organisational | `subjects`, `classes`, `sections`, `student_sections`, `seat_positions`, `teacher_assignments` |
| Textbook content | `textbooks`, `chapters`, `concepts`, `textbook_pages`, `page_concepts`, `concept_prerequisites` |
| Lesson coverage | `lessons`, `lesson_concepts` |
| Check-ins and diagnostics | `student_checkins`, `teacher_observations`, `diagnostic_questions`, `diagnostic_responses` |
| Assessments | `class_tests`, `test_concepts`, `test_results` |
| Evidence and concerns | `learning_evidence`, `learning_concerns`, `concern_evidence`, `concern_reviews` |
| Derived aggregates | `student_learning_profiles`, `class_daily_reports` |

**Append-only tables:** `learning_evidence` and `concern_reviews` are protected
by SQLite triggers that reject any `UPDATE`, `DELETE`, or `INSERT OR REPLACE`
on existing rows. These tables can only grow.

Every connection from `get_db()` enables:
- `PRAGMA foreign_keys = ON` — enforces all foreign key constraints
- `PRAGMA recursive_triggers = ON` — ensures `REPLACE` operations cannot bypass triggers

---

## Notes

- `mindtrace.db` is a regular file in the project folder. It persists across restarts.
- The virtual environment folder (`venv\`) is local to your machine. Do not share it.
- `app.secret_key` in `app.py` is a development value. Change it before any public deployment.
- The application runs in debug mode (`debug=True`) during development, which auto-reloads on file changes.
  Set `debug=False` if you ever run this on a shared network.
- All timestamps are stored as ISO 8601 text (`YYYY-MM-DD` for dates,
  `YYYY-MM-DDTHH:MM:SS` for datetimes). The application must supply them in
  this format consistently.
