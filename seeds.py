import json
import sqlite3
import sys
import os
import time


def generate_uuid_v7() -> str:

    # Timestamp-ordered UUID v7.
    
    ts_ms = int(time.time() * 1000)
    rand  = int.from_bytes(os.urandom(10), "big")
    uuid_int = (
        (ts_ms & 0xFFFFFFFFFFFF) << 80 |
        (0x7 << 76) |
        ((rand >> 50) & 0xFFF) << 64 |
        (0b10 << 62) |
        (rand & 0x3FFFFFFFFFFFFFFF)
    )
    h = format(uuid_int, "032x")
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed(filename: str, db_path: str = "profiles.db"):
    # Load JSON
    try:
        with open(filename, "r", encoding="utf-8") as f:
            profiles = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        print("Download it from the Airtable link in the task brief.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Could not parse JSON — {e}")
        sys.exit(1)

    if isinstance(profiles, dict):
        # Find the first list value in the dict
        list_candidates = [v for v in profiles.values() if isinstance(v, list)]

        if len(list_candidates) == 1:
            profiles = list_candidates[0]
        else:
            print("Error: Could not uniquely identify profiles list in JSON.")
            sys.exit(1)

    if not isinstance(profiles, list):
        print("Error: Expected a JSON array at the top level.")
        sys.exit(1)

    # Connect
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Ensure table exists with correct schema
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id                  TEXT PRIMARY KEY,
            name                TEXT UNIQUE NOT NULL,
            gender              TEXT,
            gender_probability  REAL,
            age                 INTEGER,
            age_group           TEXT,
            country_id          TEXT,
            country_name        TEXT,
            country_probability REAL,
            created_at          TEXT
        )
    """)

    inserted = 0
    skipped  = 0
    errors   = 0

    for i, p in enumerate(profiles):
        name = str(p.get("name", "")).strip().lower()
        if not name:
            errors += 1
            continue

        # Skip if name already exists (idempotent)
        existing = conn.execute(
            "SELECT id FROM profiles WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            skipped += 1
            continue

        try:
            conn.execute("""
                INSERT INTO profiles
                    (id, name, gender, gender_probability, age, age_group,
                     country_id, country_name, country_probability, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                generate_uuid_v7(),
                name,
                p.get("gender"),
                p.get("gender_probability"),
                p.get("age"),
                p.get("age_group"),
                p.get("country_id"),
                p.get("country_name"),
                p.get("country_probability"),
                p.get("created_at") or utc_now(),
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
        except Exception as e:
            print(f"  Row {i}: Error — {e}")
            errors += 1

        # Commit in batches of 100 for performance
        if inserted % 100 == 0 and inserted > 0:
            conn.commit()
            print(f"  Progress: {inserted} inserted...")

    conn.commit()
    conn.close()

    print(f"\nSeeding complete.")
    print(f"  Inserted : {inserted}")
    print(f"  Skipped  : {skipped} (already existed)")
    print(f"  Errors   : {errors}")
    print(f"  Total    : {len(profiles)} records in file")


if __name__ == "__main__":
    filename = sys.argv[1] if len(sys.argv) > 1 else "profiles.json"
    seed(filename)
