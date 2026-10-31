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

### Initialise the database and seed all 21 sample accounts

```powershell
python seed.py
```

This creates `mindtrace.db` in the project folder and inserts the sample accounts.
It is safe to run multiple times — it will never create duplicate accounts.

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

All 9 tests should pass. Tests use an in-memory database and do not affect `mindtrace.db`.

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
├── database.py                  # SQLite connection and schema setup
├── seed.py                      # Creates sample accounts
├── requirements.txt             # Pinned dependencies
├── mindtrace.db                 # SQLite database file (created by seed.py)
├── README.md                    # This file
├── templates\
│   ├── base.html                # Shared page layout
│   ├── login.html               # Login form
│   ├── teacher_dashboard.html   # Teacher welcome page
│   └── student_dashboard.html  # Student welcome page
├── static\
│   └── style.css                # Application styles
└── tests\
    └── test_auth.py             # Authentication tests
```

---

## Notes

- `mindtrace.db` is a regular file in the project folder. It persists across restarts.
- The virtual environment folder (`venv\`) is local to your machine. Do not share it.
- `app.secret_key` in `app.py` is a development value. Change it before any public deployment.
- The application runs in debug mode (`debug=True`) during development, which auto-reloads on file changes.
  Set `debug=False` if you ever run this on a shared network.
