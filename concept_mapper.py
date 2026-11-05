"""
concept_mapper.py — Concept mapping, prerequisite validation, and cycle prevention.
"""

from __future__ import annotations
from database import get_db
from graph import would_create_cycle

def map_concept_to_page(page_id: int, concept_id: int) -> bool:
    """Map an extracted concept to a textbook page idempotently."""
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO page_concepts (page_id, concept_id) VALUES (?, ?)",
            (page_id, concept_id)
        )
        conn.commit()
        success = True
    except Exception:
        conn.rollback()
        success = False
    finally:
        conn.close()
    return success


def add_prerequisite_safely(concept_id: int, prerequisite_id: int) -> bool:
    """Add a prerequisite relationship after validating that it does not create a cycle.

    Returns True if added successfully, False if cycle detected or invalid.
    """
    if concept_id == prerequisite_id:
        return False

    if would_create_cycle(concept_id, prerequisite_id):
        return False

    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO concept_prerequisites (concept_id, prerequisite_id) VALUES (?, ?)",
            (concept_id, prerequisite_id)
        )
        conn.commit()
        success = True
    except Exception:
        conn.rollback()
        success = False
    finally:
        conn.close()
    return success
