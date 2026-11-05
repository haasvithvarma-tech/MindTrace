"""
diagnostics.py — Adaptive diagnostic questions and response grading for MindTrace.
"""

from __future__ import annotations
from datetime import datetime, timezone
from database import get_db

def create_diagnostic_question(
    teacher_id: int,
    student_id: int,
    concept_id: int,
    question_text: str,
    option_a: str,
    option_b: str,
    option_c: str,
    option_d: str,
    correct_option: str
) -> int:
    """Create a diagnostic question for a specific student and concept.

    Returns the created question ID.
    """
    if correct_option not in ('a', 'b', 'c', 'd'):
        raise ValueError("correct_option must be 'a', 'b', 'c', or 'd'")

    conn = get_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    cursor = conn.execute(
        """
        INSERT INTO diagnostic_questions
            (teacher_id, student_id, concept_id, question_text, option_a, option_b, option_c, option_d, correct_option, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (teacher_id, student_id, concept_id, question_text, option_a, option_b, option_c, option_d, correct_option, now)
    )
    q_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return q_id


def submit_diagnostic_response(question_id: int, student_id: int, selected_option: str) -> dict:
    """Submit a student's answer to a diagnostic question and compute is_correct server-side.

    Never trusts client-side correctness evaluation.
    """
    if selected_option not in ('a', 'b', 'c', 'd'):
        raise ValueError("selected_option must be 'a', 'b', 'c', or 'd'")

    conn = get_db()
    q = conn.execute(
        "SELECT * FROM diagnostic_questions WHERE id = ?", (question_id,)
    ).fetchone()

    if not q:
        conn.close()
        raise ValueError(f"Diagnostic question {question_id} does not exist.")

    is_correct = 1 if selected_option.lower() == q["correct_option"].lower() else 0
    responded_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")

    try:
        conn.execute(
            """
            INSERT INTO diagnostic_responses
                (question_id, student_id, selected_option, is_correct, responded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(question_id, student_id) DO UPDATE SET
                selected_option = excluded.selected_option,
                is_correct = excluded.is_correct,
                responded_at = excluded.responded_at
            """,
            (question_id, student_id, selected_option, is_correct, responded_at)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

    conn.close()
    return {"question_id": question_id, "student_id": student_id, "is_correct": is_correct}
