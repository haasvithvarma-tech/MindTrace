import unittest
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB_PATH = Path(__file__).parent / "test_lesson.db"

import database
from seed import seed, seed_content


class LessonWorkflowTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

        cls._original_db_path = database.DB_PATH
        database.DB_PATH = TEST_DB_PATH

        from app import app as flask_app
        flask_app.config["TESTING"] = True
        flask_app.config["SECRET_KEY"] = "test-secret-key"
        cls.flask_app = flask_app

        database.init_db()
        seed()
        seed_content()

        cls.client = flask_app.test_client()

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls._original_db_path
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def login_teacher(self):
        self.client.post("/login", data={"username": "teacher1", "password": "Teach@2025"})

    def test_01_teacher_can_view_lesson_form(self):
        self.login_teacher()
        resp = self.client.get("/dashboard/teacher")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Record a Lesson", resp.data)

    def test_02_get_textbook_concepts_api(self):
        self.login_teacher()
        resp = self.client.get("/textbook/1/concepts")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("concepts", data)
        self.assertTrue(len(data["concepts"]) > 0)

    def test_03_record_lesson_saves_to_db(self):
        self.login_teacher()
        conn = database.get_db()
        sec = conn.execute("SELECT id FROM sections LIMIT 1").fetchone()["id"]
        tb = conn.execute("SELECT id FROM textbooks LIMIT 1").fetchone()["id"]
        c = conn.execute("SELECT id FROM concepts LIMIT 1").fetchone()["id"]
        conn.close()

        resp = self.client.post(
            "/lessons/new",
            data={
                "section_id": sec,
                "textbook_id": tb,
                "lesson_date": "2026-11-01",
                "notes": "Testing lesson recording",
                "concept_ids": [str(c)]
            },
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        # Verify in DB
        conn = database.get_db()
        lesson = conn.execute("SELECT * FROM lessons WHERE notes = ?", ("Testing lesson recording",)).fetchone()
        self.assertIsNotNone(lesson)

        lc = conn.execute("SELECT * FROM lesson_concepts WHERE lesson_id = ?", (lesson["id"],)).fetchone()
        self.assertIsNotNone(lc)
        self.assertEqual(lc["concept_id"], c)
        conn.close()

    def test_04_student_cannot_record_lesson(self):
        self.client.post("/login", data={"username": "student01", "password": "Study@2025"})
        resp = self.client.post(
            "/lessons/new",
            data={"section_id": 1, "textbook_id": 1, "lesson_date": "2026-11-01"},
            follow_redirects=False
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])


if __name__ == "__main__":
    unittest.main()
