import unittest
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB_PATH = Path(__file__).parent / "test_student.db"

import database
from seed import seed, seed_content, seed_grade_data, seed_enrolments


class StudentWorkflowTests(unittest.TestCase):

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
        seed_grade_data()
        seed_enrolments()

        cls.client = flask_app.test_client()

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls._original_db_path
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def login_student(self, username="student01"):
        self.client.post("/login", data={"username": username, "password": "Study@2025"})

    def login_teacher(self, username="teacher1"):
        self.client.post("/login", data={"username": username, "password": "Teach@2025"})

    def test_01_student_enrolment_seeded(self):
        conn = database.get_db()
        enrolments = conn.execute(
            """SELECT ss.*, s.name as section_name, c.name as class_name, u.username
               FROM student_sections ss
               JOIN users u ON u.id = ss.student_id
               JOIN sections s ON s.id = ss.section_id
               JOIN classes c ON c.id = s.class_id
               WHERE u.username = 'student01'"""
        .strip()).fetchall()
        conn.close()

        self.assertTrue(len(enrolments) > 0)
        self.assertEqual(enrolments[0]["class_name"], "Grade 7")
        self.assertEqual(enrolments[0]["section_name"], "7-A")

    def test_02_student_dashboard_visibility(self):
        # Teacher records a lesson for Section 7-A
        self.login_teacher()
        conn = database.get_db()
        sec = conn.execute(
            "SELECT s.id FROM sections s JOIN classes c ON c.id = s.class_id WHERE c.name = 'Grade 7' AND s.name = '7-A'"
        ).fetchone()["id"]
        tb = conn.execute("SELECT id FROM textbooks LIMIT 1").fetchone()["id"]
        conn.close()

        self.client.post(
            "/lessons/new",
            data={
                "section_id": sec,
                "textbook_id": tb,
                "lesson_date": "2026-11-02",
                "notes": "Algebra Intro",
                "page_start": 10,
                "page_end": 14
            },
            follow_redirects=True
        )
        self.client.get("/logout")

        # Student01 logs in and views dashboard
        self.login_student("student01")
        resp = self.client.get("/dashboard/student")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Algebra Intro", resp.data)
        self.assertIn(b"Pages 10\xe2\x80\x9314", resp.data) or self.assertIn(b"10", resp.data)

    def test_03_student_checkin_submission(self):
        self.login_teacher()
        conn = database.get_db()
        sec = conn.execute(
            "SELECT s.id FROM sections s JOIN classes c ON c.id = s.class_id WHERE c.name = 'Grade 7' AND s.name = '7-A'"
        ).fetchone()["id"]
        tb = conn.execute("SELECT id FROM textbooks LIMIT 1").fetchone()["id"]
        conn.close()

        resp = self.client.post(
            "/lessons/new",
            data={
                "section_id": sec,
                "textbook_id": tb,
                "lesson_date": "2026-11-03",
                "notes": "Fractions Practice",
                "page_start": 20,
                "page_end": 22
            },
            follow_redirects=True
        )

        conn = database.get_db()
        lesson = conn.execute("SELECT id FROM lessons WHERE notes = 'Fractions Practice'").fetchone()
        lesson_id = lesson["id"]
        conn.close()
        self.client.get("/logout")

        # Student02 submits check-in
        self.login_student("student02")
        resp = self.client.post(
            f"/lessons/{lesson_id}/checkin",
            data={
                "understanding": 4,
                "confidence": 5,
                "note": "Got it completely!"
            },
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Check-in Submitted", resp.data)

        # Verify in DB
        conn = database.get_db()
        checkin = conn.execute(
            "SELECT * FROM student_checkins WHERE lesson_id = ? AND concept_id IS NULL",
            (lesson_id,)
        ).fetchone()
        self.assertIsNotNone(checkin)
        self.assertEqual(checkin["understanding"], 4)
        self.assertEqual(checkin["confidence"], 5)
        self.assertEqual(checkin["note"], "Got it completely!")
        conn.close()

    def test_04_duplicate_checkin_prevented(self):
        # Student02 tries to check in again to the same lesson
        conn = database.get_db()
        lesson = conn.execute("SELECT id FROM lessons WHERE notes = 'Fractions Practice'").fetchone()
        lesson_id = lesson["id"]
        student_id = conn.execute("SELECT id FROM users WHERE username = 'student02'").fetchone()["id"]
        conn.close()

        # Submit via client again
        resp = self.client.post(
            f"/lessons/{lesson_id}/checkin",
            data={
                "understanding": 2,
                "confidence": 2,
                "note": "Second try"
            },
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        # Verify DB still has only 1 check-in for student02 on this lesson
        conn = database.get_db()
        checkins = conn.execute(
            "SELECT * FROM student_checkins WHERE student_id = ? AND lesson_id = ? AND concept_id IS NULL",
            (student_id, lesson_id)
        ).fetchall()
        self.assertEqual(len(checkins), 1)
        self.assertEqual(checkins[0]["understanding"], 4)  # Original value preserved
        conn.close()

    def test_05_unauthorized_section_checkin_rejected(self):
        # Create a new section 7-B where student03 is NOT enrolled
        conn = database.get_db()
        class_id = conn.execute("SELECT id FROM classes LIMIT 1").fetchone()["id"]
        cursor = conn.execute("INSERT OR IGNORE INTO sections (class_id, name) VALUES (?, ?)", (class_id, "7-B"))
        sec_b = conn.execute("SELECT id FROM sections WHERE class_id = ? AND name = '7-B'", (class_id,)).fetchone()["id"]
        teacher_id = conn.execute("SELECT id FROM users WHERE role = 'teacher' LIMIT 1").fetchone()["id"]
        subject_id = conn.execute("SELECT id FROM subjects LIMIT 1").fetchone()["id"]

        cursor = conn.execute(
            """INSERT INTO lessons (teacher_id, section_id, subject_id, lesson_date, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (teacher_id, sec_b, subject_id, "2026-11-04", "Section 7-B Lesson")
        )
        sec_b_lesson_id = cursor.lastrowid
        conn.commit()
        conn.close()

        self.client.get("/logout")
        # student01 is enrolled in 7-A, NOT 7-B. Try to check in to sec_b_lesson_id.
        self.login_student("student01")
        resp = self.client.post(
            f"/lessons/{sec_b_lesson_id}/checkin",
            data={"understanding": 5, "confidence": 5},
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 403)

    def test_06_invalid_ratings_rejected(self):
        conn = database.get_db()
        lesson = conn.execute("SELECT id FROM lessons WHERE notes = 'Algebra Intro'").fetchone()
        lesson_id = lesson["id"]
        conn.close()

        self.login_student("student03")
        # Rating 6 is out of range (1-5)
        resp = self.client.post(
            f"/lessons/{lesson_id}/checkin",
            data={"understanding": 6, "confidence": 3},
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
