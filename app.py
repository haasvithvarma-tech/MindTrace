from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from database import init_db, get_db
from datetime import datetime, timezone

app = Flask(__name__)
app.secret_key = "mindtrace-dev-secret-key-change-before-production"


@app.before_request
def setup():
    """Ensure the database and table exist before the first request."""
    init_db()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            error = "Please enter both username and password."
        else:
            conn = get_db()
            user = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            conn.close()

            if user is None or not check_password_hash(user["password"], password):
                error = "Invalid username or password."
            else:
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["role"] = user["role"]

                if user["role"] == "teacher":
                    return redirect(url_for("teacher_dashboard"))
                else:
                    return redirect(url_for("student_dashboard"))

    return render_template("login.html", error=error)


@app.route("/dashboard/teacher")
def teacher_dashboard():
    if session.get("role") != "teacher":
        return redirect(url_for("login"))

    conn = get_db()
    # Fetch sections and textbooks for recording lessons
    sections = conn.execute(
        """SELECT s.id, c.name as class_name, s.name as section_name
           FROM sections s JOIN classes c ON c.id = s.class_id"""
    ).fetchall()
    textbooks = conn.execute(
        """SELECT t.id, t.title, sub.name as subject_name, sub.id as subject_id
           FROM textbooks t JOIN subjects sub ON sub.id = t.subject_id"""
    ).fetchall()

    # Fetch recent lessons recorded by this teacher
    lessons = conn.execute(
        """SELECT l.id, l.lesson_date, l.notes, s.name as section_name, c.name as class_name, sub.name as subject_name, t.title as textbook_title
           FROM lessons l
           JOIN sections s ON s.id = l.section_id
           JOIN classes c ON c.id = s.class_id
           JOIN subjects sub ON sub.id = l.subject_id
           LEFT JOIN teacher_assignments ta ON ta.section_id = l.section_id AND ta.teacher_id = l.teacher_id
           LEFT JOIN textbooks t ON t.subject_id = l.subject_id
           WHERE l.teacher_id = ?
           ORDER BY l.id DESC LIMIT 10""",
        (session["user_id"],)
    ).fetchall()
    conn.close()

    return render_template(
        "teacher_dashboard.html",
        username=session["username"],
        sections=sections,
        textbooks=textbooks,
        lessons=lessons,
    )


@app.route("/lessons/new", methods=["POST"])
def record_lesson():
    if session.get("role") != "teacher":
        return redirect(url_for("login"))

    section_id = request.form.get("section_id")
    textbook_id = request.form.get("textbook_id")
    lesson_date = request.form.get("lesson_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    notes = request.form.get("notes", "").strip()
    selected_concepts = request.form.getlist("concept_ids")

    if not section_id or not textbook_id:
        return redirect(url_for("teacher_dashboard"))

    conn = get_db()
    # Get subject_id from textbook
    tb = conn.execute("SELECT subject_id FROM textbooks WHERE id = ?", (textbook_id,)).fetchone()
    if not tb:
        conn.close()
        return redirect(url_for("teacher_dashboard"))

    subject_id = tb["subject_id"]

    try:
        conn.execute("BEGIN TRANSACTION")
        cursor = conn.execute(
            """INSERT INTO lessons (teacher_id, section_id, subject_id, lesson_date, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (session["user_id"], section_id, subject_id, lesson_date, notes)
        )
        lesson_id = cursor.lastrowid

        for c_id in selected_concepts:
            conn.execute(
                "INSERT OR IGNORE INTO lesson_concepts (lesson_id, concept_id) VALUES (?, ?)",
                (lesson_id, c_id)
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

    return redirect(url_for("teacher_dashboard"))


@app.route("/textbook/<int:textbook_id>/concepts")
def get_textbook_concepts(textbook_id):
    if session.get("role") != "teacher":
        return {"error": "Unauthorized"}, 403

    conn = get_db()
    concepts = conn.execute(
        """SELECT c.id, c.name, ch.title as chapter_title
           FROM concepts c
           JOIN chapters ch ON ch.id = c.chapter_id
           WHERE ch.textbook_id = ?""",
        (textbook_id,)
    ).fetchall()
    conn.close()
    return {"concepts": [dict(c) for c in concepts]}


@app.route("/dashboard/student")
def student_dashboard():
    if session.get("role") != "student":
        return redirect(url_for("login"))
    return render_template("student_dashboard.html", username=session["username"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
