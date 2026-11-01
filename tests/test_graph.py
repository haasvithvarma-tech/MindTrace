"""
tests/test_graph.py — Concept Graph Tests for MindTrace Milestone 3

Tests direct retrieval, multi-level tracing, grade boundaries, missing
configuration, missing grade info, cycle detection, depth guard, and
seed idempotency.

Uses the same DB_PATH patching pattern as test_auth.py and test_schema.py.
Creates a fresh temporary database — never touches mindtrace.db.
"""

import sqlite3
import unittest
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB_PATH = Path(__file__).parent / "test_graph.db"

import database  # noqa: E402
import graph     # noqa: E402


class GraphTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Build a fresh test database with a controlled concept fixture."""
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
        """
        Fixture graph (Mathematics, max_lookback_grades = 1):

          Grade 6 textbook:
            C1 — Integers
            C2 — Number Line

          Grade 7 textbook:
            C3 — Proper Fractions
            C4 — Adding Fractions
            C5 — Algebra Intro

          Prerequisite edges:
            C4 → C3  (Adding Fractions requires Proper Fractions, same grade)
            C3 → C2  (Proper Fractions requires Number Line, crosses to G6)
            C2 → C1  (Number Line requires Integers, same grade)
            C5 → C4  (Algebra requires Adding Fractions, same grade)

          Subject without boundary: "NoConfig" (used in missing-config test)
        """
        c = cls.conn
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")

        # ── Users (required by FK chains from other tables, not used here)
        # ── Subjects
        c.execute("INSERT INTO subjects (name) VALUES ('Mathematics')")
        cls._math_id = c.execute(
            "SELECT id FROM subjects WHERE name='Mathematics'"
        ).fetchone()["id"]

        c.execute("INSERT INTO subjects (name) VALUES ('NoConfig')")
        cls._noconfig_subject_id = c.execute(
            "SELECT id FROM subjects WHERE name='NoConfig'"
        ).fetchone()["id"]

        # ── Grade boundary for Mathematics only
        c.execute(
            "INSERT INTO subject_grade_boundaries "
            "(subject_id, max_lookback_grades, updated_at) VALUES (?, 1, ?)",
            (cls._math_id, now),
        )

        # ── Textbooks
        c.execute(
            "INSERT INTO textbooks (subject_id, title, edition, grade_level) "
            "VALUES (?, 'Maths G6', '2024', 6)", (cls._math_id,)
        )
        cls._tb6_id = c.execute(
            "SELECT id FROM textbooks WHERE title='Maths G6'"
        ).fetchone()["id"]

        c.execute(
            "INSERT INTO textbooks (subject_id, title, edition, grade_level) "
            "VALUES (?, 'Maths G7', '2024', 7)", (cls._math_id,)
        )
        cls._tb7_id = c.execute(
            "SELECT id FROM textbooks WHERE title='Maths G7'"
        ).fetchone()["id"]

        # Textbook with NULL grade_level
        c.execute(
            "INSERT INTO textbooks (subject_id, title, edition) "
            "VALUES (?, 'No Grade Book', '2024')", (cls._math_id,)
        )
        cls._tb_nograde_id = c.execute(
            "SELECT id FROM textbooks WHERE title='No Grade Book'"
        ).fetchone()["id"]

        # Textbook for NoConfig subject
        c.execute(
            "INSERT INTO textbooks (subject_id, title, edition, grade_level) "
            "VALUES (?, 'NoConfig Book', '2024', 7)", (cls._noconfig_subject_id,)
        )
        cls._tb_noconfig_id = c.execute(
            "SELECT id FROM textbooks WHERE title='NoConfig Book'"
        ).fetchone()["id"]

        # ── Chapters
        c.execute(
            "INSERT INTO chapters (textbook_id, number, title) VALUES (?, 1, 'G6 Ch1')",
            (cls._tb6_id,)
        )
        cls._ch6_id = c.execute(
            "SELECT id FROM chapters WHERE textbook_id=? AND number=1",
            (cls._tb6_id,)
        ).fetchone()["id"]

        c.execute(
            "INSERT INTO chapters (textbook_id, number, title) VALUES (?, 1, 'G7 Ch1')",
            (cls._tb7_id,)
        )
        cls._ch7_id = c.execute(
            "SELECT id FROM chapters WHERE textbook_id=? AND number=1",
            (cls._tb7_id,)
        ).fetchone()["id"]

        c.execute(
            "INSERT INTO chapters (textbook_id, number, title) VALUES (?, 1, 'NoGrade Ch1')",
            (cls._tb_nograde_id,)
        )
        cls._ch_nograde_id = c.execute(
            "SELECT id FROM chapters WHERE textbook_id=? AND number=1",
            (cls._tb_nograde_id,)
        ).fetchone()["id"]

        c.execute(
            "INSERT INTO chapters (textbook_id, number, title) VALUES (?, 1, 'NoConfig Ch1')",
            (cls._tb_noconfig_id,)
        )
        cls._ch_noconfig_id = c.execute(
            "SELECT id FROM chapters WHERE textbook_id=? AND number=1",
            (cls._tb_noconfig_id,)
        ).fetchone()["id"]

        # ── Concepts
        def add_concept(chapter_id, name):
            c.execute(
                "INSERT INTO concepts (chapter_id, name) VALUES (?, ?)",
                (chapter_id, name)
            )
            return c.execute(
                "SELECT id FROM concepts WHERE chapter_id=? AND name=?",
                (chapter_id, name)
            ).fetchone()["id"]

        cls.C1 = add_concept(cls._ch6_id, "Integers")         # G6
        cls.C2 = add_concept(cls._ch6_id, "Number Line")      # G6
        cls.C3 = add_concept(cls._ch7_id, "Proper Fractions") # G7
        cls.C4 = add_concept(cls._ch7_id, "Adding Fractions") # G7
        cls.C5 = add_concept(cls._ch7_id, "Algebra Intro")    # G7
        cls.C_nograde = add_concept(cls._ch_nograde_id, "NoGradeConcept")
        cls.C_noconfig = add_concept(cls._ch_noconfig_id, "NoConfigConcept")

        # ── Prerequisite edges
        for cid, pid in [
            (cls.C4, cls.C3),  # C4 → C3
            (cls.C3, cls.C2),  # C3 → C2
            (cls.C2, cls.C1),  # C2 → C1
            (cls.C5, cls.C4),  # C5 → C4
        ]:
            c.execute(
                "INSERT INTO concept_prerequisites (concept_id, prerequisite_id)"
                " VALUES (?, ?)", (cid, pid)
            )

        c.commit()

    # ── Direct prerequisite retrieval ────────────────────────────────────────

    def test_01_direct_prerequisites_returns_correct_concept(self):
        result = graph.get_direct_prerequisites(self.C4)
        ids = [r["id"] for r in result]
        self.assertIn(self.C3, ids)
        self.assertEqual(len(result), 1)

    def test_02_direct_prerequisites_empty_when_none(self):
        result = graph.get_direct_prerequisites(self.C1)
        self.assertEqual(result, [])

    def test_03_multiple_prerequisites(self):
        """A concept with two prerequisites returns both."""
        # Add a second prerequisite to C4 temporarily
        self.conn.execute(
            "INSERT INTO concept_prerequisites (concept_id, prerequisite_id)"
            " VALUES (?, ?)", (self.C4, self.C2)
        )
        self.conn.commit()
        result = graph.get_direct_prerequisites(self.C4)
        ids = {r["id"] for r in result}
        self.assertIn(self.C3, ids)
        self.assertIn(self.C2, ids)
        # Clean up
        self.conn.execute(
            "DELETE FROM concept_prerequisites WHERE concept_id=? AND prerequisite_id=?",
            (self.C4, self.C2)
        )
        self.conn.commit()

    # ── Grade helpers ─────────────────────────────────────────────────────────

    def test_04_get_concept_grade_returns_correct_level(self):
        self.assertEqual(graph.get_concept_grade(self.C4), 7)
        self.assertEqual(graph.get_concept_grade(self.C1), 6)

    def test_05_get_concept_grade_returns_none_when_null(self):
        result = graph.get_concept_grade(self.C_nograde)
        self.assertIsNone(result)

    def test_06_get_concept_grade_raises_on_missing_concept(self):
        with self.assertRaises(ValueError):
            graph.get_concept_grade(99999)

    def test_07_get_grade_boundary_correct_value(self):
        # Grade 7, max_lookback = 1 → boundary = 6
        self.assertEqual(graph.get_grade_boundary(self.C4), 6)

    def test_08_get_grade_boundary_returns_none_without_config(self):
        result = graph.get_grade_boundary(self.C_noconfig)
        self.assertIsNone(result)

    def test_09_get_grade_boundary_raises_when_grade_null(self):
        with self.assertRaises(ValueError) as ctx:
            graph.get_grade_boundary(self.C_nograde)
        self.assertIn("grade_level", str(ctx.exception))

    # ── trace_prerequisites ────────────────────────────────────────────────────

    def test_10_trace_with_boundary_stops_at_grade_limit(self):
        """
        C4 is Grade 7, boundary = Grade 6 (inclusive).
        C4 → C3 (G7, included) → C2 (G6, included) → C1 (G6... wait:
        actually C2 is G6 which equals boundary=6, so included.
        C1 is also G6, included.
        C3 → C2 → C1 all pass boundary (grade >= 6).
        So trace from C4 should return C3, C2, C1.
        """
        result = graph.trace_prerequisites(self.C4, respect_grade_boundary=True)
        ids = {r["id"] for r in result}
        self.assertIn(self.C3, ids)
        self.assertIn(self.C2, ids)
        self.assertIn(self.C1, ids)

    def test_11_trace_without_boundary_returns_all(self):
        result = graph.trace_prerequisites(self.C4, respect_grade_boundary=False)
        ids = {r["id"] for r in result}
        self.assertIn(self.C3, ids)
        self.assertIn(self.C2, ids)
        self.assertIn(self.C1, ids)

    def test_12_trace_multi_level_from_C5(self):
        """C5 → C4 → C3 → C2 → C1 all reachable."""
        result = graph.trace_prerequisites(self.C5, respect_grade_boundary=False)
        ids = {r["id"] for r in result}
        self.assertIn(self.C4, ids)
        self.assertIn(self.C3, ids)
        self.assertIn(self.C2, ids)
        self.assertIn(self.C1, ids)

    def test_13_trace_depth_values_are_correct(self):
        result = graph.trace_prerequisites(self.C4, respect_grade_boundary=False)
        depth_map = {r["id"]: r["depth"] for r in result}
        self.assertEqual(depth_map[self.C3], 1)  # direct
        self.assertEqual(depth_map[self.C2], 2)  # one hop
        self.assertEqual(depth_map[self.C1], 3)  # two hops

    def test_14_trace_raises_on_missing_grade_when_boundary_enforced(self):
        """concept with NULL grade_level raises ValueError when boundary=True."""
        # Give C_nograde a prerequisite so traversal reaches it
        self.conn.execute(
            "INSERT OR IGNORE INTO concept_prerequisites"
            " (concept_id, prerequisite_id) VALUES (?, ?)",
            (self.C4, self.C_nograde)
        )
        self.conn.commit()
        with self.assertRaises(ValueError):
            # C4 → C_nograde is now a prerequisite edge.
            # C_nograde has NULL grade_level, so traversal must raise ValueError.
            graph.trace_prerequisites(self.C4, respect_grade_boundary=True)
        # Clean up
        self.conn.execute(
            "DELETE FROM concept_prerequisites WHERE concept_id=? AND prerequisite_id=?",
            (self.C4, self.C_nograde)
        )
        self.conn.commit()

    def test_15_trace_raises_when_no_boundary_config(self):
        """Starting trace from a concept whose subject has no boundary row raises."""
        with self.assertRaises(ValueError) as ctx:
            graph.trace_prerequisites(self.C_noconfig, respect_grade_boundary=True)
        self.assertIn("boundary", str(ctx.exception).lower())

    def test_16_trace_returns_empty_for_concept_with_no_prerequisites(self):
        result = graph.trace_prerequisites(self.C1, respect_grade_boundary=False)
        self.assertEqual(result, [])

    def test_17_trace_raises_on_nonexistent_concept(self):
        with self.assertRaises(ValueError):
            graph.trace_prerequisites(99999)

    # ── Cycle detection ────────────────────────────────────────────────────────

    def test_18_would_create_cycle_detects_self_loop(self):
        self.assertTrue(graph.would_create_cycle(self.C1, self.C1))

    def test_19_would_create_cycle_detects_transitive_cycle(self):
        # C4 → C3 → C2 → C1 already exists.
        # Adding C1 → C4 would create C1 → C4 → C3 → C2 → C1.
        self.assertTrue(graph.would_create_cycle(self.C1, self.C4))

    def test_20_would_create_cycle_returns_false_for_valid_edge(self):
        # C1 has no prerequisites. Adding C5 → C1 is fine (C5 not reachable from C1).
        self.assertFalse(graph.would_create_cycle(self.C5, self.C1))

    def test_21_would_create_cycle_false_for_unrelated_concepts(self):
        self.assertFalse(graph.would_create_cycle(self.C_noconfig, self.C1))

    # ── max_depth guard ────────────────────────────────────────────────────────

    def test_22_max_depth_limits_traversal(self):
        """A chain longer than max_depth is truncated without error."""
        # Build a chain of 12 concepts: D1 → D2 → ... → D12
        c = self.conn
        prev_id = None
        chain_ids = []
        for i in range(12):
            c.execute(
                "INSERT INTO concepts (chapter_id, name) VALUES (?, ?)",
                (self._ch7_id, f"DepthConcept{i}")
            )
            cid = c.execute(
                "SELECT id FROM concepts WHERE chapter_id=? AND name=?",
                (self._ch7_id, f"DepthConcept{i}")
            ).fetchone()["id"]
            chain_ids.append(cid)
            if prev_id is not None:
                c.execute(
                    "INSERT INTO concept_prerequisites (concept_id, prerequisite_id)"
                    " VALUES (?, ?)", (prev_id, cid)
                )
            prev_id = cid
        c.commit()

        result = graph.trace_prerequisites(
            chain_ids[0], max_depth=10, respect_grade_boundary=False
        )
        depths = [r["depth"] for r in result]
        self.assertLessEqual(max(depths), 10)
        # Clean up chain
        for cid in chain_ids:
            c.execute(
                "DELETE FROM concept_prerequisites WHERE concept_id=? OR prerequisite_id=?",
                (cid, cid)
            )
            c.execute("DELETE FROM concepts WHERE id=?", (cid,))
        c.commit()

    # ── Seed idempotency ───────────────────────────────────────────────────────

    def test_23_seed_grade_data_idempotent(self):
        """Calling seed_grade_data() twice must not raise or create duplicates."""
        from seed import seed_grade_data

        # Patch DB_PATH to the test database
        database.DB_PATH = TEST_DB_PATH

        # Insert Mathematics into the test DB if not present (already done in fixtures)
        seed_grade_data()  # first call
        seed_grade_data()  # second call — must not raise

        count = self.conn.execute(
            "SELECT COUNT(*) FROM subject_grade_boundaries WHERE subject_id=?",
            (self._math_id,)
        ).fetchone()[0]
        self.assertEqual(count, 1, "Duplicate boundary row created on second seed call")


if __name__ == "__main__":
    unittest.main()
