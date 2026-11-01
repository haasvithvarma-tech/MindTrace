import sqlite3
from pathlib import Path

# Resolve the database path relative to this file, regardless of
# where the application is launched from.
DB_PATH = Path(__file__).parent / "mindtrace.db"


def get_db():
    """Return a sqlite3 connection to mindtrace.db.

    Every connection has:
      - PRAGMA foreign_keys = ON   : enforce FK constraints
      - PRAGMA recursive_triggers = ON : ensure REPLACE-fired DELETEs pass
                                         through append-only triggers
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA recursive_triggers = ON")
    return conn


def init_db():
    """Create all tables and append-only triggers if they do not exist.

    Tables are created in dependency order (parents before children).
    Triggers are registered after all tables.
    This function is idempotent — safe to call on every request.
    """
    conn = get_db()

    # ── EXISTING ──────────────────────────────────────────────────────────────

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    NOT NULL UNIQUE,
            password TEXT    NOT NULL,
            role     TEXT    NOT NULL CHECK(role IN ('teacher', 'student'))
        )
    """)

    # ── ORGANISATIONAL ────────────────────────────────────────────────────────

    conn.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT    NOT NULL UNIQUE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT    NOT NULL UNIQUE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL REFERENCES classes(id),
            name     TEXT    NOT NULL,
            UNIQUE (class_id, name)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS student_sections (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER NOT NULL REFERENCES users(id),
            section_id  INTEGER NOT NULL REFERENCES sections(id),
            enrolled_at TEXT    NOT NULL,
            UNIQUE (student_id, section_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS seat_positions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES users(id),
            section_id INTEGER NOT NULL REFERENCES sections(id),
            row_num    INTEGER NOT NULL,
            col_num    INTEGER NOT NULL,
            UNIQUE (section_id, row_num, col_num),
            UNIQUE (student_id, section_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS teacher_assignments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id  INTEGER NOT NULL REFERENCES users(id),
            section_id  INTEGER NOT NULL REFERENCES sections(id),
            subject_id  INTEGER NOT NULL REFERENCES subjects(id),
            assigned_at TEXT    NOT NULL,
            UNIQUE (teacher_id, section_id, subject_id)
        )
    """)

    # ── TEXTBOOK CONTENT ──────────────────────────────────────────────────────

    conn.execute("""
        CREATE TABLE IF NOT EXISTS textbooks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL REFERENCES subjects(id),
            title      TEXT    NOT NULL,
            edition    TEXT,
            UNIQUE (subject_id, title, edition)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chapters (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            textbook_id INTEGER NOT NULL REFERENCES textbooks(id),
            number      INTEGER NOT NULL,
            title       TEXT    NOT NULL,
            UNIQUE (textbook_id, number)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS concepts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id  INTEGER NOT NULL REFERENCES chapters(id),
            name        TEXT    NOT NULL,
            description TEXT,
            UNIQUE (chapter_id, name)
        )
    """)

    # One row per physical page — content stored exactly once.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS textbook_pages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            textbook_id  INTEGER NOT NULL REFERENCES textbooks(id),
            page_number  INTEGER NOT NULL,
            content_text TEXT    NOT NULL,
            UNIQUE (textbook_id, page_number)
        )
    """)

    # Many-to-many: pages <-> concepts. Content lives only in textbook_pages.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS page_concepts (
            page_id    INTEGER NOT NULL REFERENCES textbook_pages(id),
            concept_id INTEGER NOT NULL REFERENCES concepts(id),
            PRIMARY KEY (page_id, concept_id)
        )
    """)

    # Directed prerequisite graph (self-join). No self-loops.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS concept_prerequisites (
            concept_id      INTEGER NOT NULL REFERENCES concepts(id),
            prerequisite_id INTEGER NOT NULL REFERENCES concepts(id),
            PRIMARY KEY (concept_id, prerequisite_id),
            CHECK (concept_id != prerequisite_id)
        )
    """)

    # ── LESSON COVERAGE ───────────────────────────────────────────────────────

    conn.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id  INTEGER NOT NULL REFERENCES users(id),
            section_id  INTEGER NOT NULL REFERENCES sections(id),
            subject_id  INTEGER NOT NULL REFERENCES subjects(id),
            lesson_date TEXT    NOT NULL,
            notes       TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS lesson_concepts (
            lesson_id  INTEGER NOT NULL REFERENCES lessons(id),
            concept_id INTEGER NOT NULL REFERENCES concepts(id),
            PRIMARY KEY (lesson_id, concept_id)
        )
    """)

    # ── STUDENT CHECK-INS ─────────────────────────────────────────────────────
    # lesson_id and concept_id are both nullable; at least one must be non-null.
    # SQLite UNIQUE treats NULLs as distinct — application must guard
    # against duplicate lesson-only check-ins (concept_id IS NULL case).

    conn.execute("""
        CREATE TABLE IF NOT EXISTS student_checkins (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id    INTEGER NOT NULL REFERENCES users(id),
            lesson_id     INTEGER REFERENCES lessons(id),
            concept_id    INTEGER REFERENCES concepts(id),
            understanding INTEGER NOT NULL CHECK(understanding BETWEEN 1 AND 5),
            confidence    INTEGER NOT NULL CHECK(confidence BETWEEN 1 AND 5),
            note          TEXT,
            checked_in_at TEXT    NOT NULL,
            CHECK (lesson_id IS NOT NULL OR concept_id IS NOT NULL),
            UNIQUE (student_id, lesson_id, concept_id)
        )
    """)

    # ── TEACHER OBSERVATIONS ──────────────────────────────────────────────────

    conn.execute("""
        CREATE TABLE IF NOT EXISTS teacher_observations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id  INTEGER NOT NULL REFERENCES users(id),
            student_id  INTEGER NOT NULL REFERENCES users(id),
            concept_id  INTEGER NOT NULL REFERENCES concepts(id),
            observation TEXT    NOT NULL,
            observed_at TEXT    NOT NULL
        )
    """)

    # ── DIAGNOSTICS ───────────────────────────────────────────────────────────
    # Questions are generated for a specific student. is_correct is computed
    # on the backend from correct_option — never supplied by the client.

    conn.execute("""
        CREATE TABLE IF NOT EXISTS diagnostic_questions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id     INTEGER NOT NULL REFERENCES users(id),
            student_id     INTEGER NOT NULL REFERENCES users(id),
            concept_id     INTEGER NOT NULL REFERENCES concepts(id),
            question_text  TEXT    NOT NULL,
            option_a       TEXT    NOT NULL,
            option_b       TEXT    NOT NULL,
            option_c       TEXT    NOT NULL,
            option_d       TEXT    NOT NULL,
            correct_option TEXT    NOT NULL CHECK(correct_option IN ('a','b','c','d')),
            created_at     TEXT    NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS diagnostic_responses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id     INTEGER NOT NULL REFERENCES diagnostic_questions(id),
            student_id      INTEGER NOT NULL REFERENCES users(id),
            selected_option TEXT    NOT NULL CHECK(selected_option IN ('a','b','c','d')),
            is_correct      INTEGER NOT NULL CHECK(is_correct IN (0,1)),
            responded_at    TEXT    NOT NULL,
            UNIQUE (question_id, student_id)
        )
    """)

    # ── ASSESSMENTS ───────────────────────────────────────────────────────────
    # Defined before learning_evidence so test_result_id FK resolves cleanly.

    conn.execute("""
        CREATE TABLE IF NOT EXISTS class_tests (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER NOT NULL REFERENCES sections(id),
            subject_id INTEGER NOT NULL REFERENCES subjects(id),
            title      TEXT    NOT NULL,
            test_date  TEXT    NOT NULL,
            max_score  REAL    NOT NULL CHECK(max_score > 0),
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT    NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_concepts (
            test_id    INTEGER NOT NULL REFERENCES class_tests(id),
            concept_id INTEGER NOT NULL REFERENCES concepts(id),
            PRIMARY KEY (test_id, concept_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id     INTEGER NOT NULL REFERENCES class_tests(id),
            student_id  INTEGER NOT NULL REFERENCES users(id),
            concept_id  INTEGER NOT NULL REFERENCES concepts(id),
            score       REAL    NOT NULL CHECK(score >= 0),
            max_score   REAL    NOT NULL CHECK(max_score > 0),
            recorded_by INTEGER NOT NULL REFERENCES users(id),
            recorded_at TEXT    NOT NULL,
            UNIQUE (test_id, student_id, concept_id),
            CHECK (score <= max_score)
        )
    """)

    # ── LEARNING EVIDENCE (append-only) ──────────────────────────────────────
    # Exactly one of the four source FK columns must be non-null.
    # (col IS NOT NULL) evaluates to 0 or 1 in SQLite arithmetic — valid CHECK.
    # NEVER UPDATE or DELETE rows — enforced by triggers below.

    conn.execute("""
        CREATE TABLE IF NOT EXISTS learning_evidence (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id             INTEGER NOT NULL REFERENCES users(id),
            concept_id             INTEGER NOT NULL REFERENCES concepts(id),
            checkin_id             INTEGER REFERENCES student_checkins(id),
            diagnostic_response_id INTEGER REFERENCES diagnostic_responses(id),
            test_result_id         INTEGER REFERENCES test_results(id),
            teacher_observation_id INTEGER REFERENCES teacher_observations(id),
            evidence_value         REAL    NOT NULL CHECK(evidence_value BETWEEN 0.0 AND 1.0),
            recorded_at            TEXT    NOT NULL,
            CHECK (
                (checkin_id             IS NOT NULL) +
                (diagnostic_response_id IS NOT NULL) +
                (test_result_id         IS NOT NULL) +
                (teacher_observation_id IS NOT NULL)
                = 1
            )
        )
    """)

    # ── LEARNING CONCERNS ─────────────────────────────────────────────────────
    # suspected_prerequisite_id and gap_confidence are either both NULL
    # (root cause unknown) or both non-NULL (prerequisite identified).
    # The range CHECK on gap_confidence applies only when it is non-NULL.
    # Whether suspected_prerequisite_id exists in concept_prerequisites must
    # be validated at the application layer before INSERT.

    conn.execute("""
        CREATE TABLE IF NOT EXISTS learning_concerns (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id                INTEGER NOT NULL REFERENCES users(id),
            concept_id                INTEGER NOT NULL REFERENCES concepts(id),
            suspected_prerequisite_id INTEGER REFERENCES concepts(id),
            gap_confidence            REAL    CHECK(gap_confidence BETWEEN 0.0 AND 1.0),
            raised_by                 INTEGER NOT NULL REFERENCES users(id),
            raised_at                 TEXT    NOT NULL,
            description               TEXT    NOT NULL,
            status                    TEXT    NOT NULL DEFAULT 'open'
                                      CHECK(status IN
                                          ('open','investigating','confirmed',
                                           'resolved','dismissed')),
            CHECK (
                (suspected_prerequisite_id IS NULL) = (gap_confidence IS NULL)
            )
        )
    """)

    # Junction: one concern references one or more evidence records.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS concern_evidence (
            concern_id  INTEGER NOT NULL REFERENCES learning_concerns(id),
            evidence_id INTEGER NOT NULL REFERENCES learning_evidence(id),
            PRIMARY KEY (concern_id, evidence_id)
        )
    """)

    # ── CONCERN REVIEWS (append-only) ─────────────────────────────────────────

    conn.execute("""
        CREATE TABLE IF NOT EXISTS concern_reviews (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            concern_id  INTEGER NOT NULL REFERENCES learning_concerns(id),
            reviewed_by INTEGER NOT NULL REFERENCES users(id),
            decision    TEXT    NOT NULL
                        CHECK(decision IN ('noted','resolved','escalated','monitoring')),
            observation TEXT    NOT NULL,
            reviewed_at TEXT    NOT NULL
        )
    """)

    # ── DERIVED / AGGREGATE ───────────────────────────────────────────────────

    conn.execute("""
        CREATE TABLE IF NOT EXISTS student_learning_profiles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id      INTEGER NOT NULL REFERENCES users(id),
            concept_id      INTEGER NOT NULL REFERENCES concepts(id),
            mastery_score   REAL    NOT NULL DEFAULT 0.0
                            CHECK(mastery_score BETWEEN 0.0 AND 1.0),
            status          TEXT    NOT NULL DEFAULT 'not_started'
                            CHECK(status IN
                                ('not_started','gap','developing','mastered')),
            evidence_count  INTEGER NOT NULL DEFAULT 0,
            last_updated_at TEXT    NOT NULL,
            UNIQUE (student_id, concept_id)
        )
    """)

    # One report per section per date across all subjects.
    # report_content is nullable; populated when the report text is generated.
    # This table is an aggregate — never stores individual student records.
    # INSERT OR REPLACE is the correct upsert pattern (no outbound FK references).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS class_daily_reports (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id        INTEGER NOT NULL REFERENCES sections(id),
            report_date       TEXT    NOT NULL,
            avg_understanding REAL,
            avg_confidence    REAL,
            checkin_count     INTEGER NOT NULL DEFAULT 0,
            concern_count     INTEGER NOT NULL DEFAULT 0,
            report_content    TEXT,
            generated_at      TEXT    NOT NULL,
            UNIQUE (section_id, report_date)
        )
    """)

    # ── APPEND-ONLY TRIGGERS ──────────────────────────────────────────────────
    # PRAGMA recursive_triggers = ON (set in get_db()) ensures that the DELETE
    # fired internally by REPLACE also passes through these triggers.

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_evidence_update
        BEFORE UPDATE ON learning_evidence
        BEGIN
            SELECT RAISE(ABORT,
                'learning_evidence is append-only: UPDATE not permitted');
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_evidence_delete
        BEFORE DELETE ON learning_evidence
        BEGIN
            SELECT RAISE(ABORT,
                'learning_evidence is append-only: DELETE not permitted');
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_concern_review_update
        BEFORE UPDATE ON concern_reviews
        BEGIN
            SELECT RAISE(ABORT,
                'concern_reviews is append-only: UPDATE not permitted');
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_concern_review_delete
        BEFORE DELETE ON concern_reviews
        BEGIN
            SELECT RAISE(ABORT,
                'concern_reviews is append-only: DELETE not permitted');
        END
    """)

    conn.commit()
    conn.close()
