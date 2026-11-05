"""
evidence_consolidation.py — M7 Shared Evidence Consolidation Layer for MindTrace.
Consolidates diagnostic responses, test results, concept check-ins, and lesson check-ins
into append-only learning_evidence and student_learning_profiles.
"""

from __future__ import annotations
from datetime import datetime, timezone
from database import get_db

def consolidate_all_evidence() -> dict[str, int]:
    """Run consolidation across all objective and subjective evidence sources.
    Idempotent and safe to run repeatedly.
    Returns counts of newly processed evidence items.
    """
    conn = get_db()
    counts = {
        "diagnostic_evidence": 0,
        "test_evidence": 0,
        "checkin_evidence": 0,
        "profiles_updated": 0
    }
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")

    try:
        # 1. Diagnostic responses (objective evidence)
        diag_rows = conn.execute(
            """
            SELECT dr.id as resp_id, dr.student_id, dq.concept_id, dr.is_correct, dr.responded_at
            FROM diagnostic_responses dr
            JOIN diagnostic_questions dq ON dq.id = dr.question_id
            WHERE dq.concept_id IS NOT NULL
            """
        ).fetchall()

        for row in diag_rows:
            resp_id = row["resp_id"]
            existing = conn.execute(
                "SELECT id FROM learning_evidence WHERE diagnostic_response_id = ?",
                (resp_id,)
            ).fetchone()

            if not existing:
                evidence_val = 1.0 if row["is_correct"] == 1 else 0.0
                conn.execute(
                    """
                    INSERT INTO learning_evidence
                        (student_id, concept_id, diagnostic_response_id, evidence_value, recorded_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (row["student_id"], row["concept_id"], resp_id, evidence_val, row["responded_at"] or now)
                )
                counts["diagnostic_evidence"] += 1

        # 2. Formal test results (objective evidence, if supported)
        try:
            test_rows = conn.execute(
                """
                SELECT id, student_id, concept_id, score, max_score, recorded_at
                FROM test_results
                WHERE max_score > 0
                """
            ).fetchall()

            for row in test_rows:
                test_res_id = row["id"]
                existing = conn.execute(
                    "SELECT id FROM learning_evidence WHERE test_result_id = ?",
                    (test_res_id,)
                ).fetchone()

                if not existing:
                    max_s = float(row["max_score"])
                    score = float(row["score"])
                    if max_s > 0:
                        ev_val = max(0.0, min(1.0, score / max_s))
                        conn.execute(
                            """
                            INSERT INTO learning_evidence
                                (student_id, concept_id, test_result_id, evidence_value, recorded_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (row["student_id"], row["concept_id"], test_res_id, ev_val, row["recorded_at"] or now)
                        )
                        counts["test_evidence"] += 1
        except Exception:
            pass

        # 3. Concept-level student check-ins (subjective evidence)
        checkin_rows = conn.execute(
            """
            SELECT id, student_id, concept_id, understanding, confidence, checked_in_at
            FROM student_checkins
            WHERE concept_id IS NOT NULL
            """
        ).fetchall()

        for row in checkin_rows:
            chk_id = row["id"]
            existing = conn.execute(
                "SELECT id FROM learning_evidence WHERE checkin_id = ?",
                (chk_id,)
            ).fetchone()

            if not existing:
                und = float(row["understanding"])
                ev_val = max(0.0, min(1.0, und / 5.0))
                conn.execute(
                    """
                    INSERT INTO learning_evidence
                        (student_id, concept_id, checkin_id, evidence_value, recorded_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (row["student_id"], row["concept_id"], chk_id, ev_val, row["checked_in_at"] or now)
                )
                counts["checkin_evidence"] += 1

        conn.commit()

        # 4. Recompute student_learning_profiles based on objective evidence only
        pairs = conn.execute(
            """
            SELECT DISTINCT student_id, concept_id
            FROM learning_evidence
            WHERE diagnostic_response_id IS NOT NULL OR test_result_id IS NOT NULL
            """
        ).fetchall()

        for p in pairs:
            s_id = p["student_id"]
            c_id = p["concept_id"]

            obj_evs = conn.execute(
                """
                SELECT evidence_value FROM learning_evidence
                WHERE student_id = ? AND concept_id = ?
                  AND (diagnostic_response_id IS NOT NULL OR test_result_id IS NOT NULL)
                """,
                (s_id, c_id)
            ).fetchall()

            count = len(obj_evs)
            if count > 0:
                mean_score = sum(row["evidence_value"] for row in obj_evs) / count

                if count >= 3 and mean_score >= 0.8:
                    status = "mastered"
                else:
                    status = "developing"

                conn.execute(
                    """
                    INSERT INTO student_learning_profiles
                        (student_id, concept_id, mastery_score, status, evidence_count, last_updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(student_id, concept_id) DO UPDATE SET
                        mastery_score = excluded.mastery_score,
                        status = excluded.status,
                        evidence_count = excluded.evidence_count,
                        last_updated_at = excluded.last_updated_at
                    """,
                    (s_id, c_id, mean_score, status, count, now)
                )
                counts["profiles_updated"] += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

    return counts


def get_student_objective_evidence(student_id: int, concept_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, student_id, concept_id, diagnostic_response_id, test_result_id, evidence_value, recorded_at
        FROM learning_evidence
        WHERE student_id = ? AND concept_id = ?
          AND (diagnostic_response_id IS NOT NULL OR test_result_id IS NOT NULL)
        """,
        (student_id, concept_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_student_subjective_evidence(student_id: int, concept_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT le.id, le.student_id, le.concept_id, le.checkin_id, le.evidence_value, le.recorded_at,
               sc.understanding, sc.confidence, sc.note
        FROM learning_evidence le
        JOIN student_checkins sc ON sc.id = le.checkin_id
        WHERE le.student_id = ? AND le.concept_id = ? AND le.checkin_id IS NOT NULL
        """,
        (student_id, concept_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_student_lesson_checkin_context(student_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, student_id, lesson_id, understanding, confidence, note, checked_in_at
        FROM student_checkins
        WHERE student_id = ? AND concept_id IS NULL AND lesson_id IS NOT NULL
        """,
        (student_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_student_learning_profiles(student_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, student_id, concept_id, mastery_score, status, evidence_count, last_updated_at
        FROM student_learning_profiles
        WHERE student_id = ?
        """,
        (student_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_section_consolidated_evidence(section_id: int) -> dict[str, Any]:
    """Retrieve section-level consolidated evidence for SOP 4, including:
    - Student profiles (objective mastery & status)
    - Concept-level student check-ins (understanding & confidence)
    - Lesson-level check-ins (contextual evidence)
    Maintains strict separation between objective scores and subjective metrics.
    """
    conn = get_db()
    # 1. Profiles for section students
    profiles = conn.execute(
        """
        SELECT slp.student_id, u.username as student_username, slp.concept_id, c.name as concept_name,
               slp.mastery_score, slp.status, slp.evidence_count, slp.last_updated_at
        FROM student_learning_profiles slp
        JOIN student_sections ss ON ss.student_id = slp.student_id
        JOIN users u ON u.id = slp.student_id
        JOIN concepts c ON c.id = slp.concept_id
        WHERE ss.section_id = ?
        """,
        (section_id,)
    ).fetchall()

    # 2. Concept-level subjective check-ins for section students
    subjective_evidence = conn.execute(
        """
        SELECT sc.student_id, u.username as student_username, sc.concept_id, c.name as concept_name,
               sc.understanding, sc.confidence, sc.note, sc.checked_in_at as recorded_at
        FROM student_checkins sc
        JOIN student_sections ss ON ss.student_id = sc.student_id
        JOIN users u ON u.id = sc.student_id
        JOIN concepts c ON c.id = sc.concept_id
        WHERE ss.section_id = ? AND sc.concept_id IS NOT NULL
        """,
        (section_id,)
    ).fetchall()

    # 3. Lesson-level contextual check-ins for section students
    lesson_checkins = conn.execute(
        """
        SELECT sc.student_id, u.username as student_username, sc.lesson_id, l.lesson_date,
               sc.understanding, sc.confidence, sc.note, sc.checked_in_at as recorded_at
        FROM student_checkins sc
        JOIN student_sections ss ON ss.student_id = sc.student_id
        JOIN users u ON u.id = sc.student_id
        JOIN lessons l ON l.id = sc.lesson_id
        WHERE ss.section_id = ? AND sc.concept_id IS NULL AND sc.lesson_id IS NOT NULL
        """,
        (section_id,)
    ).fetchall()

    conn.close()
    return {
        "profiles": [dict(r) for r in profiles],
        "subjective_evidence": [dict(r) for r in subjective_evidence],
        "lesson_context": [dict(r) for r in lesson_checkins]
    }
