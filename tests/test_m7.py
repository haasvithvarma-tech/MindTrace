"""
tests/test_m7.py — Automated tests for M7 Evidence Consolidation layer.
"""

import unittest
from pathlib import Path
from datetime import datetime, timezone
import database
import evidence_consolidation

TEST_DB_PATH = Path(__file__).parent / "test_m7.db"

class M7EvidenceConsolidationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._original_db_path = database.DB_PATH
        database.DB_PATH = TEST_DB_PATH
        if TEST_DB_PATH.exists():
            try:
                TEST_DB_PATH.unlink()
            except Exception:
                pass
        database.init_db()

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls._original_db_path
        if TEST_DB_PATH.exists():
            try:
                TEST_DB_PATH.unlink()
            except Exception:
                pass

    def setUp(self):
        conn = database.get_db()
        for t in [
            "concern_evidence", "learning_evidence", "student_learning_profiles",
            "diagnostic_responses", "diagnostic_questions", "student_checkins",
            "lessons", "sections", "classes",
            "concepts", "chapters", "textbooks", "subjects", "users"
        ]:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.commit()
        conn.close()

    def test_01_diagnostic_response_mapping(self):
        conn = database.get_db()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO subjects (id, name) VALUES (1, 'Mathematics')")
        conn.execute("INSERT INTO users (id, username, password, role) VALUES (1, 'student1', 'hash', 'student')")
        conn.execute("INSERT INTO users (id, username, password, role) VALUES (2, 'teacher1', 'hash', 'teacher')")
        conn.execute("INSERT INTO textbooks (id, subject_id, title) VALUES (1, 1, 'Math Book')")
        conn.execute("INSERT INTO chapters (id, textbook_id, number, title) VALUES (1, 1, 1, 'Chapter 1')")
        conn.execute("INSERT INTO concepts (id, chapter_id, name) VALUES (1, 1, 'Fractions')")

        conn.execute(
            """INSERT INTO diagnostic_questions
               (id, teacher_id, student_id, concept_id, question_text, option_a, option_b, option_c, option_d, correct_option, created_at)
               VALUES (1, 2, 1, 1, 'Q1', 'a', 'b', 'c', 'd', 'a', ?)""",
            (now,)
        )
        conn.execute(
            """INSERT INTO diagnostic_responses
               (id, question_id, student_id, selected_option, is_correct, responded_at)
               VALUES (1, 1, 1, 'a', 1, ?)""",
            (now,)
        )
        conn.commit()
        conn.close()

        counts = evidence_consolidation.consolidate_all_evidence()
        self.assertEqual(counts["diagnostic_evidence"], 1)

        objs = evidence_consolidation.get_student_objective_evidence(1, 1)
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0]["evidence_value"], 1.0)
        self.assertEqual(objs[0]["diagnostic_response_id"], 1)

    def test_02_concept_checkin_subjective_mapping_and_confidence(self):
        conn = database.get_db()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO subjects (id, name) VALUES (2, 'Science')")
        conn.execute("INSERT INTO users (id, username, password, role) VALUES (3, 'student2', 'hash', 'student')")
        conn.execute("INSERT INTO textbooks (id, subject_id, title) VALUES (2, 2, 'Science Book')")
        conn.execute("INSERT INTO chapters (id, textbook_id, number, title) VALUES (2, 2, 1, 'Chapter 1')")
        conn.execute("INSERT INTO concepts (id, chapter_id, name) VALUES (2, 2, 'Cells')")

        conn.execute(
            """INSERT INTO student_checkins
               (id, student_id, concept_id, understanding, confidence, checked_in_at)
               VALUES (10, 3, 2, 4, 5, ?)""",
            (now,)
        )
        conn.commit()
        conn.close()

        counts = evidence_consolidation.consolidate_all_evidence()
        self.assertEqual(counts["checkin_evidence"], 1)

        subs = evidence_consolidation.get_student_subjective_evidence(3, 2)
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]["evidence_value"], 0.8)
        self.assertEqual(subs[0]["understanding"], 4)
        self.assertEqual(subs[0]["confidence"], 5)

    def test_03_lesson_level_checkin_isolation_and_no_evidence(self):
        conn = database.get_db()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO subjects (id, name) VALUES (3, 'History')")
        conn.execute("INSERT INTO users (id, username, password, role) VALUES (4, 'student3', 'hash', 'student')")
        conn.execute("INSERT INTO users (id, username, password, role) VALUES (5, 'teacher3', 'hash', 'teacher')")
        conn.execute("INSERT INTO classes (id, name) VALUES (2, 'Class 6')")
        conn.execute("INSERT INTO sections (id, class_id, name) VALUES (2, 2, 'B')")
        conn.execute("INSERT INTO lessons (id, teacher_id, section_id, subject_id, lesson_date) VALUES (10, 5, 2, 3, '2026-11-05')")
        conn.execute("INSERT INTO textbooks (id, subject_id, title) VALUES (3, 3, 'History Book')")
        conn.execute("INSERT INTO chapters (id, textbook_id, number, title) VALUES (5, 3, 1, 'Chapter 1')")
        conn.execute("INSERT INTO concepts (id, chapter_id, name) VALUES (5, 5, 'Revolution')")

        conn.execute(
            """INSERT INTO student_checkins
               (id, student_id, lesson_id, concept_id, understanding, confidence, checked_in_at)
               VALUES (20, 4, 10, NULL, 3, 3, ?)""",
            (now,)
        )
        conn.commit()
        conn.close()

        evidence_consolidation.consolidate_all_evidence()
        lesson_ctx = evidence_consolidation.get_student_lesson_checkin_context(4)
        self.assertTrue(len(lesson_ctx) >= 1)

        # Check no profile created or objective evidence for unassessed concept
        objs = evidence_consolidation.get_student_objective_evidence(4, 5)
        self.assertEqual(len(objs), 0)
        profiles = evidence_consolidation.get_student_learning_profiles(4)
        self.assertEqual(len(profiles), 0)

    def test_04_idempotency_and_append_only_protection(self):
        conn = database.get_db()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO subjects (id, name) VALUES (4, 'Art')")
        conn.execute("INSERT INTO users (id, username, password, role) VALUES (6, 'student4', 'hash', 'student')")
        conn.execute("INSERT INTO users (id, username, password, role) VALUES (7, 'teacher4', 'hash', 'teacher')")
        conn.execute("INSERT INTO textbooks (id, subject_id, title) VALUES (4, 4, 'Art Book')")
        conn.execute("INSERT INTO chapters (id, textbook_id, number, title) VALUES (6, 4, 1, 'Chapter 1')")
        conn.execute("INSERT INTO concepts (id, chapter_id, name) VALUES (6, 6, 'Color')")

        conn.execute(
            """INSERT INTO diagnostic_questions
               (id, teacher_id, student_id, concept_id, question_text, option_a, option_b, option_c, option_d, correct_option, created_at)
               VALUES (100, 7, 6, 6, 'Q2', 'a', 'b', 'c', 'd', 'b', ?)""",
            (now,)
        )
        conn.execute(
            """INSERT INTO diagnostic_responses
               (id, question_id, student_id, selected_option, is_correct, responded_at)
               VALUES (100, 100, 6, 'b', 0, ?)""",
            (now,)
        )
        conn.commit()
        conn.close()

        counts1 = evidence_consolidation.consolidate_all_evidence()
        self.assertEqual(counts1["diagnostic_evidence"], 1)
        counts2 = evidence_consolidation.consolidate_all_evidence()
        self.assertEqual(counts2["diagnostic_evidence"], 0) # Duplicate prevented

        # Test append-only trigger protection on learning_evidence
        conn = database.get_db()
        with self.assertRaises(Exception):
            conn.execute("UPDATE learning_evidence SET evidence_value = 1.0 WHERE diagnostic_response_id = 100")
        with self.assertRaises(Exception):
            conn.execute("DELETE FROM learning_evidence WHERE diagnostic_response_id = 100")
        conn.close()

    def test_05_profile_mastery_status_and_section_retrieval(self):
        conn = database.get_db()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO subjects (id, name) VALUES (5, 'Physics')")
        conn.execute("INSERT INTO users (id, username, password, role) VALUES (8, 'student5', 'hash', 'student')")
        conn.execute("INSERT INTO users (id, username, password, role) VALUES (9, 'teacher5', 'hash', 'teacher')")
        conn.execute("INSERT INTO classes (id, name) VALUES (3, 'Class 7')")
        conn.execute("INSERT INTO sections (id, class_id, name) VALUES (3, 3, 'C')")
        conn.execute("INSERT INTO student_sections (student_id, section_id, enrolled_at) VALUES (8, 3, ?)", (now,))
        conn.execute("INSERT INTO textbooks (id, subject_id, title) VALUES (5, 5, 'Physics Book')")
        conn.execute("INSERT INTO chapters (id, textbook_id, number, title) VALUES (7, 5, 1, 'Chapter 1')")
        conn.execute("INSERT INTO concepts (id, chapter_id, name) VALUES (7, 7, 'Gravity')")

        for q_id, r_id, correct in [(200, 200, 1), (201, 201, 1), (202, 202, 1)]:
            conn.execute(
                """INSERT INTO diagnostic_questions
                   (id, teacher_id, student_id, concept_id, question_text, option_a, option_b, option_c, option_d, correct_option, created_at)
                   VALUES (?, 9, 8, 7, 'Q', 'a', 'b', 'c', 'd', 'a', ?)""",
                (q_id, now)
            )
            conn.execute(
                """INSERT INTO diagnostic_responses
                   (id, question_id, student_id, selected_option, is_correct, responded_at)
                   VALUES (?, ?, 8, 'a', ?, ?)""",
                (r_id, q_id, correct, now)
            )
        conn.commit()
        conn.close()

        evidence_consolidation.consolidate_all_evidence()

        # Test student profile
        profiles = evidence_consolidation.get_student_learning_profiles(8)
        self.assertTrue(len(profiles) >= 1)
        mastered_profile = next((p for p in profiles if p["concept_id"] == 7), None)
        self.assertIsNotNone(mastered_profile)
        self.assertEqual(mastered_profile["mastery_score"], 1.0)
        self.assertEqual(mastered_profile["evidence_count"], 3)
        self.assertEqual(mastered_profile["status"], "mastered")

        # Test section-level consolidated evidence retrieval for SOP 4
        section_data = evidence_consolidation.get_section_consolidated_evidence(3)
        self.assertIn("profiles", section_data)
        self.assertIn("subjective_evidence", section_data)
        self.assertIn("lesson_context", section_data)
        self.assertEqual(len(section_data["profiles"]), 1)


if __name__ == "__main__":
    unittest.main()
