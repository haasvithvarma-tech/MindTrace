"""
graph.py — Concept Graph for MindTrace

Provides prerequisite retrieval and multi-level tracing with configurable,
subject-specific grade boundaries stored in subject_grade_boundaries.

All grade boundary values are read from SQLite — never hardcoded here.

Relationship direction (preserved from Milestone 2):
  concept_prerequisites.concept_id      = the concept that HAS the prerequisite
  concept_prerequisites.prerequisite_id = the concept that must be mastered first

Traversal is deterministic BFS. Cycle detection runs before every INSERT.
"""

from __future__ import annotations
from collections import deque
from database import get_db


# ── Prerequisite retrieval ────────────────────────────────────────────────────

def get_direct_prerequisites(concept_id: int) -> list[dict]:
    """Return the immediate prerequisites of concept_id.

    Each entry: {id, name, chapter_id, description}
    Returns an empty list when no prerequisites exist.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.chapter_id, c.description
        FROM concept_prerequisites cp
        JOIN concepts c ON c.id = cp.prerequisite_id
        WHERE cp.concept_id = ?
        ORDER BY c.id
        """,
        (concept_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Grade helpers ─────────────────────────────────────────────────────────────

def get_concept_grade(concept_id: int) -> int | None:
    """Return the grade_level of the textbook that the concept belongs to.

    Path: concepts → chapters → textbooks.grade_level

    Returns None when grade_level has not been set on the textbook.
    Raises ValueError when concept_id does not exist.
    """
    conn = get_db()
    row = conn.execute(
        """
        SELECT t.grade_level
        FROM concepts c
        JOIN chapters  ch ON ch.id = c.chapter_id
        JOIN textbooks t  ON t.id  = ch.textbook_id
        WHERE c.id = ?
        """,
        (concept_id,),
    ).fetchone()
    conn.close()

    if row is None:
        raise ValueError(f"Concept {concept_id} does not exist.")
    return row["grade_level"]


def get_grade_boundary(concept_id: int) -> int | None:
    """Return the minimum allowed grade for prerequisite tracing from concept_id.

    Boundary = concept's grade_level − max_lookback_grades (read from SQLite).
    Grade boundaries are inclusive: grade >= boundary is permitted.

    Returns None when no boundary row exists for the subject.
    Raises ValueError when concept_id does not exist or grade_level is NULL.
    """
    conn = get_db()
    row = conn.execute(
        """
        SELECT t.grade_level, sgb.max_lookback_grades
        FROM concepts c
        JOIN chapters  ch  ON ch.id  = c.chapter_id
        JOIN textbooks t   ON t.id   = ch.textbook_id
        LEFT JOIN subject_grade_boundaries sgb ON sgb.subject_id = t.subject_id
        WHERE c.id = ?
        """,
        (concept_id,),
    ).fetchone()
    conn.close()

    if row is None:
        raise ValueError(f"Concept {concept_id} does not exist.")

    grade = row["grade_level"]
    lookback = row["max_lookback_grades"]

    if grade is None:
        raise ValueError(
            f"Concept {concept_id} has no grade_level set on its textbook. "
            "Run seed_grade_data() or set the textbook's grade_level before tracing."
        )

    if lookback is None:
        # No boundary configured for this subject
        return None

    return grade - lookback


# ── Graph traversal ───────────────────────────────────────────────────────────

def trace_prerequisites(
    concept_id: int,
    max_depth: int = 10,
    respect_grade_boundary: bool = True,
) -> list[dict]:
    """BFS traversal from concept_id following prerequisite edges.

    Returns a flat list of all reachable prerequisites, each as:
      {id, name, chapter_id, description, grade_level, depth}

    Grade boundary behaviour (respect_grade_boundary=True):
      - Reads the starting concept's grade and the subject's max_lookback_grades
        from SQLite.
      - minimum_grade = grade - max_lookback_grades  (inclusive)
      - A prerequisite with grade_level < minimum_grade is excluded and its
        subtree is not explored.
      - A prerequisite with grade_level IS NULL raises ValueError — missing grade
        data is never silently ignored.
      - A subject with no boundary row in subject_grade_boundaries raises
        ValueError — missing configuration is never silently ignored.

    respect_grade_boundary=False traces the full graph regardless of grades.
      Grade NULLs are permitted in this mode.

    max_depth is an independent safety guard against runaway traversal on
    malformed graphs. It does not substitute for grade boundary enforcement.

    Raises ValueError for missing concept, missing grade data (when enforcing
    boundaries), or missing boundary configuration (when enforcing boundaries).
    """
    conn = get_db()

    # Verify the starting concept exists
    start = conn.execute(
        "SELECT id FROM concepts WHERE id = ?", (concept_id,)
    ).fetchone()
    if start is None:
        conn.close()
        raise ValueError(f"Concept {concept_id} does not exist.")
    conn.close()

    # Determine the grade boundary for the starting concept
    minimum_grade: int | None = None
    if respect_grade_boundary:
        boundary = get_grade_boundary(concept_id)  # raises on missing grade/config
        if boundary is None:
            raise ValueError(
                f"No grade boundary is configured for the subject of concept "
                f"{concept_id}. Add a row to subject_grade_boundaries before "
                "tracing with respect_grade_boundary=True."
            )
        minimum_grade = boundary

    results: list[dict] = []
    visited: set[int] = {concept_id}
    # Queue entries: (prereq_id, depth)
    queue: deque[tuple[int, int]] = deque()

    # Seed queue with direct prerequisites
    for p in _fetch_prerequisites_with_grade(concept_id):
        if p["id"] not in visited:
            queue.append((p["id"], 1))

    while queue:
        current_id, depth = queue.popleft()

        if current_id in visited:
            continue
        visited.add(current_id)

        if depth > max_depth:
            continue  # Safety guard — do not explore beyond max_depth

        # Fetch this concept's details including its grade
        node = _fetch_concept_with_grade(current_id)
        if node is None:
            continue  # Concept deleted since traversal started — skip

        if respect_grade_boundary:
            node_grade = node["grade_level"]
            if node_grade is None:
                raise ValueError(
                    f"Concept {current_id} ('{node['name']}') has no grade_level "
                    "set on its textbook. Set grade_level before tracing with "
                    "respect_grade_boundary=True."
                )
            if node_grade < minimum_grade:
                # This node and its subtree are outside the grade boundary — stop
                continue

        results.append({**node, "depth": depth})

        # Enqueue this concept's prerequisites for the next level
        for p in _fetch_prerequisites_with_grade(current_id):
            if p["id"] not in visited:
                queue.append((p["id"], depth + 1))

    return results


# ── Cycle detection ───────────────────────────────────────────────────────────

def would_create_cycle(concept_id: int, prerequisite_id: int) -> bool:
    """Return True if adding (concept_id → prerequisite_id) would create a cycle.

    Performs a BFS from prerequisite_id following existing prerequisite edges.
    If concept_id is reachable from prerequisite_id, adding the edge would form
    a cycle.

    Note: direct self-loops (concept_id == prerequisite_id) are also caught here
    and return True, consistent with the DB-level CHECK constraint.
    """
    if concept_id == prerequisite_id:
        return True

    visited: set[int] = set()
    queue: deque[int] = deque([prerequisite_id])

    while queue:
        node = queue.popleft()
        if node == concept_id:
            return True
        if node in visited:
            continue
        visited.add(node)
        for p in _fetch_prerequisites_with_grade(node):
            if p["id"] not in visited:
                queue.append(p["id"])

    return False


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetch_concept_with_grade(concept_id: int) -> dict | None:
    """Fetch one concept row joined to its textbook's grade_level."""
    conn = get_db()
    row = conn.execute(
        """
        SELECT c.id, c.name, c.chapter_id, c.description, t.grade_level
        FROM concepts c
        JOIN chapters  ch ON ch.id = c.chapter_id
        JOIN textbooks t  ON t.id  = ch.textbook_id
        WHERE c.id = ?
        """,
        (concept_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _fetch_prerequisites_with_grade(concept_id: int) -> list[dict]:
    """Fetch immediate prerequisite IDs for concept_id (minimal — id only needed)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT prerequisite_id AS id FROM concept_prerequisites WHERE concept_id = ?",
        (concept_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
