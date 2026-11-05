import unittest
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB_PATH = Path(__file__).parent / "test_m6.db"

import database
from seed import seed, seed_content, seed_grade_data, seed_enrolments
from extractor import extract_pdf_pages, store_extracted_pages
from ai_service import analyze_textbook_content, generate_diagnostic_questions
from concept_mapper import map_concept_to_page, add_prerequisite_safely
from diagnostics import create_diagnostic_question, submit_diagnostic_response
from graph import would_create_cycle


class Milestone6Tests(unittest.TestCase):

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

    def test_01_pdf_extraction_and_storage(self):
        # Test extraction simulation for non-existent or simulated PDF path
        pages = extract_pdf_pages("nonexistent.pdf", start_page=10, end_page=12)
        self.assertEqual(len(pages), 3)
        self.assertIn(10, pages)
        self.assertIn(12, pages)

        conn = database.get_db()
        tb = conn.execute("SELECT id FROM textbooks LIMIT 1").fetchone()["id"]
        conn.close()

        stored_count = store_extracted_pages(tb, pages)
        self.assertEqual(stored_count, 3)

        # Verify idempotency / duplicate prevention
        stored_count_again = store_extracted_pages(tb, pages)
        self.assertEqual(stored_count_again, 3)

    def test_02_ai_service_analysis(self):
        analysis = analyze_textbook_content("Mathematics Grade 7", 12, "Integers are whole numbers that can be positive or negative.")
        self.assertIn("concepts", analysis)
        self.assertTrue(len(analysis["concepts"]) > 0)
        self.assertIn("summary", analysis)

    def test_03_diagnostic_question_generation(self):
        questions = generate_diagnostic_questions("Integers", "Whole numbers")
        self.assertTrue(len(questions) > 0)
        self.assertIn("correct_option", questions[0])

    def test_04_concept_mapping_and_cycles(self):
        conn = database.get_db()
        c1 = conn.execute("SELECT id FROM concepts LIMIT 1").fetchone()["id"]
        c2 = conn.execute("SELECT id FROM concepts LIMIT 1 OFFSET 1").fetchone()["id"]
        page = conn.execute("SELECT id FROM textbook_pages LIMIT 1").fetchone()["id"]
        conn.close()

        # Map concept to page
        success = map_concept_to_page(page, c1)
        self.assertTrue(success)

        # Add valid prerequisite
        added = add_prerequisite_safely(c1, c2)
        self.assertTrue(added)

        # Try to create cycle (c2 requires c1, if c1 requires c2)
        cycle_detected = would_create_cycle(c2, c1)
        self.assertTrue(cycle_detected)

        # Adding cyclic prerequisite should be rejected safely
        added_cycle = add_prerequisite_safely(c2, c1)
        self.assertFalse(added_cycle)

    def test_05_diagnostic_question_workflow(self):
        conn = database.get_db()
        teacher = conn.execute("SELECT id FROM users WHERE role = 'teacher' LIMIT 1").fetchone()["id"]
        student = conn.execute("SELECT id FROM users WHERE role = 'student' LIMIT 1").fetchone()["id"]
        concept = conn.execute("SELECT id FROM concepts LIMIT 1").fetchone()["id"]
        conn.close()

        q_id = create_diagnostic_question(
            teacher_id=teacher,
            student_id=student,
            concept_id=concept,
            question_text="What is -5 + 5?",
            option_a="0",
            option_b="10",
            option_c="-10",
            option_d="5",
            correct_option="a"
        )
        self.assertIsNotNone(q_id)

        # Student submits correct answer
        res_correct = submit_diagnostic_response(q_id, student, "a")
        self.assertEqual(res_correct["is_correct"], 1)

        # Student submits incorrect answer
        res_incorrect = submit_diagnostic_response(q_id, student, "b")
        self.assertEqual(res_incorrect["is_correct"], 0)


if __name__ == "__main__":
    unittest.main()
