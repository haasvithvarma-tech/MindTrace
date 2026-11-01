from werkzeug.security import generate_password_hash
from database import init_db, get_db

# Sample accounts — teacher1 has a distinct password; all students share one.
ACCOUNTS = [
    {"username": "teacher1", "password": "Teach@2025", "role": "teacher"},
]

for i in range(1, 21):
    ACCOUNTS.append({
        "username": f"student{i:02d}",
        "password": "Study@2025",
        "role": "student",
    })


def seed():
    """Insert sample user accounts. Idempotent — safe to run multiple times."""
    init_db()
    conn = get_db()
    inserted = 0
    skipped = 0

    for account in ACCOUNTS:
        hashed = generate_password_hash(account["password"])
        cursor = conn.execute(
            "INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
            (account["username"], hashed, account["role"]),
        )
        if cursor.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()

    print(f"Seed users: {inserted} inserted, {skipped} already existed.")


def seed_content():
    """Insert minimal sample content to verify the Milestone 2 schema end-to-end.

    Creates:
      - 1 subject: Mathematics
      - 1 class: Grade 7
      - 1 section: 7-A
      - 1 textbook: Mathematics Grade 7
      - 2 chapters: Number Systems, Fractions
      - 4 concepts: Integers, Number Line, Proper Fractions, Adding Fractions
      - 1 prerequisite: Adding Fractions requires Proper Fractions
      - 2 textbook pages with content
      - page-concept mappings

    Idempotent — INSERT OR IGNORE throughout.
    """
    conn = get_db()

    # Subject
    conn.execute("INSERT OR IGNORE INTO subjects (name) VALUES (?)", ("Mathematics",))

    # Class and section
    conn.execute("INSERT OR IGNORE INTO classes (name) VALUES (?)", ("Grade 7",))
    class_id = conn.execute(
        "SELECT id FROM classes WHERE name = ?", ("Grade 7",)
    ).fetchone()["id"]
    conn.execute(
        "INSERT OR IGNORE INTO sections (class_id, name) VALUES (?, ?)",
        (class_id, "7-A"),
    )

    # Textbook
    subject_id = conn.execute(
        "SELECT id FROM subjects WHERE name = ?", ("Mathematics",)
    ).fetchone()["id"]
    conn.execute(
        "INSERT OR IGNORE INTO textbooks (subject_id, title, edition) VALUES (?, ?, ?)",
        (subject_id, "Mathematics Grade 7", "2024"),
    )
    textbook_id = conn.execute(
        "SELECT id FROM textbooks WHERE subject_id = ? AND title = ?",
        (subject_id, "Mathematics Grade 7"),
    ).fetchone()["id"]

    # Chapters
    conn.execute(
        "INSERT OR IGNORE INTO chapters (textbook_id, number, title) VALUES (?, ?, ?)",
        (textbook_id, 1, "Number Systems"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO chapters (textbook_id, number, title) VALUES (?, ?, ?)",
        (textbook_id, 2, "Fractions"),
    )

    ch1_id = conn.execute(
        "SELECT id FROM chapters WHERE textbook_id = ? AND number = ?", (textbook_id, 1)
    ).fetchone()["id"]
    ch2_id = conn.execute(
        "SELECT id FROM chapters WHERE textbook_id = ? AND number = ?", (textbook_id, 2)
    ).fetchone()["id"]

    # Concepts
    for name, desc, ch_id in [
        ("Integers", "Positive and negative whole numbers", ch1_id),
        ("Number Line", "Representing integers on a number line", ch1_id),
        ("Proper Fractions", "Fractions where numerator < denominator", ch2_id),
        ("Adding Fractions", "Adding fractions with like and unlike denominators", ch2_id),
    ]:
        conn.execute(
            "INSERT OR IGNORE INTO concepts (chapter_id, name, description) VALUES (?, ?, ?)",
            (ch_id, name, desc),
        )

    # Prerequisite: Adding Fractions requires Proper Fractions
    adding_id = conn.execute(
        "SELECT id FROM concepts WHERE name = ?", ("Adding Fractions",)
    ).fetchone()["id"]
    proper_id = conn.execute(
        "SELECT id FROM concepts WHERE name = ?", ("Proper Fractions",)
    ).fetchone()["id"]
    conn.execute(
        "INSERT OR IGNORE INTO concept_prerequisites (concept_id, prerequisite_id) VALUES (?, ?)",
        (adding_id, proper_id),
    )

    # Textbook pages
    conn.execute(
        "INSERT OR IGNORE INTO textbook_pages (textbook_id, page_number, content_text)"
        " VALUES (?, ?, ?)",
        (textbook_id, 12,
         "Integers are whole numbers that can be positive, negative, or zero. "
         "They are represented on a number line with zero at the centre."),
    )
    conn.execute(
        "INSERT OR IGNORE INTO textbook_pages (textbook_id, page_number, content_text)"
        " VALUES (?, ?, ?)",
        (textbook_id, 45,
         "A proper fraction has a numerator smaller than its denominator. "
         "To add fractions, first ensure they share a common denominator."),
    )

    p12_id = conn.execute(
        "SELECT id FROM textbook_pages WHERE textbook_id = ? AND page_number = ?",
        (textbook_id, 12),
    ).fetchone()["id"]
    p45_id = conn.execute(
        "SELECT id FROM textbook_pages WHERE textbook_id = ? AND page_number = ?",
        (textbook_id, 45),
    ).fetchone()["id"]

    int_id = conn.execute(
        "SELECT id FROM concepts WHERE name = ?", ("Integers",)
    ).fetchone()["id"]
    nl_id = conn.execute(
        "SELECT id FROM concepts WHERE name = ?", ("Number Line",)
    ).fetchone()["id"]

    # Page-concept mappings
    for page_id, concept_id in [
        (p12_id, int_id),
        (p12_id, nl_id),
        (p45_id, proper_id),
        (p45_id, adding_id),
    ]:
        conn.execute(
            "INSERT OR IGNORE INTO page_concepts (page_id, concept_id) VALUES (?, ?)",
            (page_id, concept_id),
        )

    conn.commit()
    conn.close()
    print("Seed content: sample subject, class, section, textbook, chapters, "
          "concepts, pages inserted (or already existed).")


if __name__ == "__main__":
    seed()
    seed_content()
