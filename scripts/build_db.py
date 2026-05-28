#!/usr/bin/env python3
"""Build docs.sqlite from scraped/*.md using index.json metadata."""

import json
import sqlite3
import sys
from pathlib import Path

SCRAPED_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent.parent / "scraped"
DB_PATH = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "data" / "db" / "docs.sqlite"


def build():
    index_path = SCRAPED_DIR / "index.json"
    if not index_path.exists():
        print(f"ERROR: {index_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(index_path) as f:
        index = json.load(f)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            file TEXT NOT NULL,
            version INTEGER,
            depth INTEGER,
            created_at TEXT,
            content TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE pages_fts USING fts5(
            title, content,
            content='pages',
            content_rowid='id'
        )
    """)
    # triggers to keep FTS in sync
    conn.execute("""
        CREATE TRIGGER pages_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
        END
    """)
    conn.execute("""
        CREATE TRIGGER pages_ad AFTER DELETE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, title, content) VALUES('delete', old.id, old.title, old.content);
        END
    """)
    conn.execute("""
        CREATE TRIGGER pages_au AFTER UPDATE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, title, content) VALUES('delete', old.id, old.title, old.content);
            INSERT INTO pages_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
        END
    """)

    inserted = 0
    skipped = 0
    for entry in index["pages"]:
        md_path = SCRAPED_DIR / entry["file"]
        if not md_path.exists():
            print(f"  SKIP (missing): {entry['file']}")
            skipped += 1
            continue

        content = md_path.read_text(encoding="utf-8")
        conn.execute(
            "INSERT INTO pages (page_id, title, url, file, version, depth, created_at, content) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entry["pageId"], entry["title"], entry.get("url", ""), entry["file"],
             entry.get("version"), entry.get("depth"), entry.get("createdAt"), content),
        )
        inserted += 1

    conn.commit()

    # verify FTS
    count = conn.execute("SELECT count(*) FROM pages").fetchone()[0]
    fts_count = conn.execute("SELECT count(*) FROM pages_fts").fetchone()[0]
    conn.close()

    print(f"Done: {inserted} pages inserted, {skipped} skipped")
    print(f"DB: {count} rows, FTS: {fts_count} rows → {DB_PATH}")


if __name__ == "__main__":
    build()
