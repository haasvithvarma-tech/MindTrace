from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from database import init_db, get_db

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
    return render_template("teacher_dashboard.html", username=session["username"])


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
