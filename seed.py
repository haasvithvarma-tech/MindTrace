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

    print(f"Seed complete: {inserted} account(s) inserted, {skipped} already existed.")


if __name__ == "__main__":
    seed()
