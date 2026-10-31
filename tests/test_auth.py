import unittest
import sys
import os
from pathlib import Path

# Ensure the project root is on the path so we can import app and database
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test database file — separate from the real mindtrace.db
TEST_DB_PATH = Path(__file__).parent / "test_mindtrace.db"

import database  # noqa: E402 — must come after sys.path insert
from seed import seed


class MindTraceAuthTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Prepare a clean test database once before all tests."""
        # Remove any leftover test database from a previous run
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

        # Redirect all database access to the test file
        cls._original_db_path = database.DB_PATH
        database.DB_PATH = TEST_DB_PATH

        # Import app *after* patching DB_PATH so every request uses the test DB
        from app import app as flask_app
        flask_app.config["TESTING"] = True
        flask_app.config["SECRET_KEY"] = "test-secret-key"
        cls.flask_app = flask_app

        # Initialise schema and seed all 21 accounts into the test database
        database.init_db()
        seed()

        cls.client = flask_app.test_client()

    @classmethod
    def tearDownClass(cls):
        """Remove the test database file and restore the original DB path."""
        database.DB_PATH = cls._original_db_path
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def login(self, username, password):
        return self.client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=False,
        )

    def login_follow(self, username, password):
        return self.client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    # ── Tests ─────────────────────────────────────────────────────────────────

    def test_01_teacher_login_redirects_to_teacher_dashboard(self):
        resp = self.login("teacher1", "Teach@2025")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/teacher", resp.headers["Location"])

    def test_02_all_students_login(self):
        for i in range(1, 21):
            username = f"student{i:02d}"
            with self.subTest(username=username):
                resp = self.login(username, "Study@2025")
                self.assertEqual(
                    resp.status_code, 302,
                    msg=f"{username} did not redirect after login",
                )
                self.assertIn(
                    "/dashboard/student", resp.headers["Location"],
                    msg=f"{username} redirected to wrong dashboard",
                )

    def test_03_invalid_username_rejected(self):
        resp = self.login_follow("nobody", "anything")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Invalid username or password", resp.data)

    def test_04_wrong_password_rejected(self):
        resp = self.login_follow("teacher1", "wrongpassword")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Invalid username or password", resp.data)

    def test_05_teacher_dashboard_returns_200(self):
        with self.flask_app.test_client() as c:
            c.post("/login", data={"username": "teacher1", "password": "Teach@2025"})
            resp = c.get("/dashboard/teacher")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"Teacher", resp.data)

    def test_06_student_dashboard_returns_200(self):
        with self.flask_app.test_client() as c:
            c.post("/login", data={"username": "student01", "password": "Study@2025"})
            resp = c.get("/dashboard/student")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"Student", resp.data)

    def test_07_teacher_cannot_access_student_dashboard(self):
        with self.flask_app.test_client() as c:
            c.post("/login", data={"username": "teacher1", "password": "Teach@2025"})
            resp = c.get("/dashboard/student", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)

    def test_08_logout_clears_session(self):
        with self.flask_app.test_client() as c:
            c.post("/login", data={"username": "teacher1", "password": "Teach@2025"})
            c.get("/logout")
            resp = c.get("/dashboard/teacher", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/login", resp.headers["Location"])

    def test_09_protected_route_without_login_redirects(self):
        with self.flask_app.test_client() as c:
            resp = c.get("/dashboard/teacher", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/login", resp.headers["Location"])


if __name__ == "__main__":
    unittest.main()
