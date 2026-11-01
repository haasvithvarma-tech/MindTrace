import sqlite3
import unittest
import sys
import os
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB_PATH = Path(__file__).parent / "test_schema.db"

import database  # noqa: E402


class SchemaTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Create a clean test database and seed minimal fixtures."""
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

        cls._original_db_path = database.DB_PATH
        database.DB_PATH = TEST_DB_PATH

        database.init_db()

        cls.conn = database.get_db()
        cls._insert_fixtures()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        database.DB_PATH = cls._original_db_path
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    @classmethod
    def _insert_fixtures(cls):
        """Insert the minimal rows needed for trigger and constraint tests."""
        c = cls.conn

        # Users
        c.execute("INSERT INTO users (username, password, role) VALUES "
                  "('t_schema', 'hash', 'teacher')")
        c.execute("INSERT INTO users (username, password, role) VALUES "
                  "('s_schema', 'hash', 'student')")
        cls._teacher_id = c.execute(
            "SELECT id FROM users WHERE username='t_schema'"
        ).fetchone()["id"]
        cls._student_id = c.execute(
            "SELECT id FROM users WHERE username='s_schema'"
        ).fetchone()["id"]

        # Subject, class, section
        c.execute("INSERT INTO subjects (name) VALUES ('TestSubject')")
        cls._subject_id = c.execute(
            "SELECT id FROM subjects WHERE name='TestSubject'"
        ).fetchone()["id"]

        c.execute("INSERT INTO classes (name) VALUES ('TestClass')")
        cls._class_id = c.execute(
            "SELECT id FROM classes WHERE name='TestClass'"
        ).fetchone()["id"]

        c.execute("INSERT INTO sections (class_id, name) VALUES (?, 'A')",
                  (cls._class_id,))
        cls._section_id = c.execute(
            "SELECT id FROM sections WHERE class_id=? AND name='A'",
            (cls._class_id,)
        ).fetchone()["id"]

        # Textbook, chapter, concepts
        c.execute("INSERT INTO textbooks (subject_id, title, edition) VALUES "
                  "(?, 'TestBook', '1st')", (cls._subject_id,))
        cls._textbook_id = c.execute(
            "SELECT id FROM textbooks WHERE title='TestBook'"
        ).fetchone()["id"]

        c.execute("INSERT INTO chapters (textbook_id, number, title) VALUES "
                  "(?, 1, 'Ch1')", (cls._textbook_id,))
        cls._chapter_id = c.execute(
            "SELECT id FROM chapters WHERE textbook_id=? AND number=1",
            (cls._textbook_id,)
        ).fetchone()["id"]

        c.execute("INSERT INTO concepts (chapter_id, name) VALUES (?, 'ConceptA')",
                  (cls._chapter_id,))
        c.execute("INSERT INTO concepts (chapter_id, name) VALUES (?, 'ConceptB')",
                  (cls._chapter_id,))
        cls._concept_a_id = c.execute(
            "SELECT id FROM concepts WHERE name='ConceptA'"
        ).fetchone()["id"]
        cls._concept_b_id = c.execute(
            "SELECT id FROM concepts WHERE name='ConceptB'"
        ).fetchone()["id"]

        # Textbook page
        c.execute("INSERT INTO textbook_pages (textbook_id, page_number, content_text)"
                  " VALUES (?, 1, 'Page one content.')", (cls._textbook_id,))
        cls._page_id = c.execute(
            "SELECT id FROM textbook_pages WHERE textbook_id=? AND page_number=1",
            (cls._textbook_id,)
        ).fetchone()["id"]

        # Lesson + lesson_concept (needed for checkin fixtures)
        c.execute("INSERT INTO lessons (teacher_id, section_id, subject_id, lesson_date)"
                  " VALUES (?, ?, ?, '2026-11-01')",
                  (cls._teacher_id, cls._section_id, cls._subject_id))
        cls._lesson_id = c.execute(
            "SELECT id FROM lessons ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]
        c.execute("INSERT INTO lesson_concepts (lesson_id, concept_id) VALUES (?, ?)",
                  (cls._lesson_id, cls._concept_a_id))

        # Student check-in (source for evidence)
        c.execute("INSERT INTO student_checkins "
                  "(student_id, lesson_id, concept_id, understanding, confidence, checked_in_at)"
                  " VALUES (?, ?, ?, 4, 4, '2026-11-01T09:00:00')",
                  (cls._student_id, cls._lesson_id, cls._concept_a_id))
        cls._checkin_id = c.execute(
            "SELECT id FROM student_checkins ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]

        # Learning concern (needed for concern_reviews)
        c.execute("INSERT INTO learning_concerns "
                  "(student_id, concept_id, raised_by, raised_at, description) "
                  "VALUES (?, ?, ?, '2026-11-01T09:00:00', 'Test concern')",
                  (cls._student_id, cls._concept_a_id, cls._teacher_id))
        cls._concern_id = c.execute(
            "SELECT id FROM learning_concerns ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]

        c.commit()

    # ── TABLE EXISTENCE ───────────────────────────────────────────────────────

    def _table_exists(self, name):
        row = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None

    def test_01_users_table_exists(self):
        self.assertTrue(self._table_exists("users"))

    def test_02_textbook_pages_table_exists(self):
        self.assertTrue(self._table_exists("textbook_pages"))

    def test_03_page_concepts_table_exists(self):
        self.assertTrue(self._table_exists("page_concepts"))

    def test_04_learning_concerns_table_exists(self):
        self.assertTrue(self._table_exists("learning_concerns"))

    def test_05_concern_evidence_table_exists(self):
        self.assertTrue(self._table_exists("concern_evidence"))

    def test_06_class_daily_reports_table_exists(self):
        self.assertTrue(self._table_exists("class_daily_reports"))

    # ── COLUMN PRESENCE ───────────────────────────────────────────────────────

    def _columns(self, table):
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {r["name"] for r in rows}

    def test_07_textbook_pages_has_content_text(self):
        self.assertIn("content_text", self._columns("textbook_pages"))

    def test_08_learning_concerns_has_suspected_prerequisite_id(self):
        self.assertIn("suspected_prerequisite_id", self._columns("learning_concerns"))

    def test_09_learning_concerns_has_gap_confidence(self):
        self.assertIn("gap_confidence", self._columns("learning_concerns"))

    def test_10_learning_concerns_status_accepts_investigating(self):
        self.conn.execute(
            "INSERT INTO learning_concerns "
            "(student_id, concept_id, raised_by, raised_at, description, status) "
            "VALUES (?, ?, ?, '2026-11-01T10:00:00', 'status test', 'investigating')",
            (self._student_id, self._concept_a_id, self._teacher_id),
        )
        self.conn.commit()

    def test_11_learning_concerns_status_rejects_invalid(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO learning_concerns "
                "(student_id, concept_id, raised_by, raised_at, description, status) "
                "VALUES (?, ?, ?, '2026-11-01T10:00:00', 'bad status', 'noted')",
                (self._student_id, self._concept_a_id, self._teacher_id),
            )
            self.conn.commit()

    def test_12_class_daily_reports_has_report_content(self):
        self.assertIn("report_content", self._columns("class_daily_reports"))

    # ── CONSTRAINT TESTS ──────────────────────────────────────────────────────

    def test_13_textbook_pages_unique_per_textbook(self):
        """Duplicate (textbook_id, page_number) must be rejected."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO textbook_pages (textbook_id, page_number, content_text)"
                " VALUES (?, 1, 'duplicate')", (self._textbook_id,)
            )
            self.conn.commit()

    def test_14_page_concepts_pk_rejects_duplicate(self):
        self.conn.execute(
            "INSERT OR IGNORE INTO page_concepts (page_id, concept_id) VALUES (?, ?)",
            (self._page_id, self._concept_a_id),
        )
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO page_concepts (page_id, concept_id) VALUES (?, ?)",
                (self._page_id, self._concept_a_id),
            )
            self.conn.commit()

    def test_15_concern_check_rejects_prerequisite_without_confidence(self):
        """suspected_prerequisite_id set but gap_confidence NULL must fail."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO learning_concerns "
                "(student_id, concept_id, suspected_prerequisite_id, gap_confidence, "
                " raised_by, raised_at, description) "
                "VALUES (?, ?, ?, NULL, ?, '2026-11-01T11:00:00', 'bad pairing')",
                (self._student_id, self._concept_a_id,
                 self._concept_b_id, self._teacher_id),
            )
            self.conn.commit()

    def test_16_concern_check_allows_both_null(self):
        """Both fields NULL (cause unknown) must succeed."""
        self.conn.execute(
            "INSERT INTO learning_concerns "
            "(student_id, concept_id, raised_by, raised_at, description) "
            "VALUES (?, ?, ?, '2026-11-01T11:00:00', 'no prereq yet')",
            (self._student_id, self._concept_a_id, self._teacher_id),
        )
        self.conn.commit()

    def test_17_concern_check_allows_both_populated(self):
        """Both fields non-NULL must succeed."""
        self.conn.execute(
            "INSERT INTO learning_concerns "
            "(student_id, concept_id, suspected_prerequisite_id, gap_confidence, "
            " raised_by, raised_at, description) "
            "VALUES (?, ?, ?, 0.8, ?, '2026-11-01T11:00:00', 'with prereq')",
            (self._student_id, self._concept_a_id,
             self._concept_b_id, self._teacher_id),
        )
        self.conn.commit()

    def test_18_class_daily_reports_unique_section_date(self):
        self.conn.execute(
            "INSERT INTO class_daily_reports "
            "(section_id, report_date, checkin_count, concern_count, generated_at) "
            "VALUES (?, '2026-11-01', 0, 0, '2026-11-01T12:00:00')",
            (self._section_id,),
        )
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO class_daily_reports "
                "(section_id, report_date, checkin_count, concern_count, generated_at)"
                " VALUES (?, '2026-11-01', 0, 0, '2026-11-01T12:00:00')",
                (self._section_id,),
            )
            self.conn.commit()

    def test_19_class_daily_reports_report_content_nullable(self):
        self.conn.execute(
            "INSERT OR REPLACE INTO class_daily_reports "
            "(section_id, report_date, checkin_count, concern_count, "
            " report_content, generated_at) "
            "VALUES (?, '2026-11-02', 0, 0, NULL, '2026-11-02T08:00:00')",
            (self._section_id,),
        )
        self.conn.commit()

    def test_20_test_results_score_must_not_exceed_max(self):
        """score > max_score must be rejected by CHECK."""
        # First create required parent rows
        self.conn.execute(
            "INSERT INTO class_tests "
            "(section_id, subject_id, title, test_date, max_score, created_by, created_at)"
            " VALUES (?, ?, 'T1', '2026-11-01', 100.0, ?, '2026-11-01T08:00:00')",
            (self._section_id, self._subject_id, self._teacher_id),
        )
        test_id = self.conn.execute(
            "SELECT id FROM class_tests WHERE title='T1'"
        ).fetchone()["id"]
        self.conn.execute(
            "INSERT INTO test_concepts (test_id, concept_id) VALUES (?, ?)",
            (test_id, self._concept_a_id),
        )
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO test_results "
                "(test_id, student_id, concept_id, score, max_score, "
                " recorded_by, recorded_at) "
                "VALUES (?, ?, ?, 110.0, 100.0, ?, '2026-11-01T10:00:00')",
                (test_id, self._student_id, self._concept_a_id, self._teacher_id),
            )
            self.conn.commit()

    # ── APPEND-ONLY TRIGGER TESTS ─────────────────────────────────────────────

    def _insert_evidence(self):
        """Insert one learning_evidence row and return its id."""
        self.conn.execute(
            "INSERT INTO learning_evidence "
            "(student_id, concept_id, checkin_id, evidence_value, recorded_at) "
            "VALUES (?, ?, ?, 0.75, '2026-11-01T09:30:00')",
            (self._student_id, self._concept_a_id, self._checkin_id),
        )
        self.conn.commit()
        return self.conn.execute(
            "SELECT id FROM learning_evidence ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]

    def _insert_review(self):
        """Insert one concern_reviews row and return its id."""
        self.conn.execute(
            "INSERT INTO concern_reviews "
            "(concern_id, reviewed_by, decision, observation, reviewed_at) "
            "VALUES (?, ?, 'noted', 'Test observation', '2026-11-01T10:00:00')",
            (self._concern_id, self._teacher_id),
        )
        self.conn.commit()
        return self.conn.execute(
            "SELECT id FROM concern_reviews ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]

    def test_21_learning_evidence_insert_succeeds(self):
        eid = self._insert_evidence()
        self.assertIsNotNone(eid)
        self.__class__._evidence_id = eid

    def test_22_learning_evidence_update_blocked(self):
        if not hasattr(self.__class__, "_evidence_id"):
            self.__class__._evidence_id = self._insert_evidence()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "UPDATE learning_evidence SET evidence_value = 0.9 WHERE id = ?",
                (self.__class__._evidence_id,),
            )
        self.assertIn("append-only", str(ctx.exception))

    def test_23_learning_evidence_delete_blocked(self):
        if not hasattr(self.__class__, "_evidence_id"):
            self.__class__._evidence_id = self._insert_evidence()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "DELETE FROM learning_evidence WHERE id = ?",
                (self.__class__._evidence_id,),
            )
        self.assertIn("append-only", str(ctx.exception))

    def test_24_learning_evidence_replace_blocked(self):
        """INSERT OR REPLACE on an existing row fires DELETE internally — must fail."""
        if not hasattr(self.__class__, "_evidence_id"):
            self.__class__._evidence_id = self._insert_evidence()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT OR REPLACE INTO learning_evidence "
                "(id, student_id, concept_id, checkin_id, evidence_value, recorded_at) "
                "VALUES (?, ?, ?, ?, 0.5, '2026-11-01T09:30:00')",
                (self.__class__._evidence_id,
                 self._student_id, self._concept_a_id, self._checkin_id),
            )
        self.assertIn("append-only", str(ctx.exception))

    def test_25_concern_reviews_insert_succeeds(self):
        rid = self._insert_review()
        self.assertIsNotNone(rid)
        self.__class__._review_id = rid

    def test_26_concern_reviews_update_blocked(self):
        if not hasattr(self.__class__, "_review_id"):
            self.__class__._review_id = self._insert_review()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "UPDATE concern_reviews SET observation = 'edited' WHERE id = ?",
                (self.__class__._review_id,),
            )
        self.assertIn("append-only", str(ctx.exception))

    def test_27_concern_reviews_delete_blocked(self):
        if not hasattr(self.__class__, "_review_id"):
            self.__class__._review_id = self._insert_review()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "DELETE FROM concern_reviews WHERE id = ?",
                (self.__class__._review_id,),
            )
        self.assertIn("append-only", str(ctx.exception))

    def test_28_concern_reviews_replace_blocked(self):
        """INSERT OR REPLACE on an existing review row must fail."""
        if not hasattr(self.__class__, "_review_id"):
            self.__class__._review_id = self._insert_review()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT OR REPLACE INTO concern_reviews "
                "(id, concern_id, reviewed_by, decision, observation, reviewed_at) "
                "VALUES (?, ?, ?, 'resolved', 'replaced', '2026-11-01T11:00:00')",
                (self.__class__._review_id,
                 self._concern_id, self._teacher_id),
            )
        self.assertIn("append-only", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
