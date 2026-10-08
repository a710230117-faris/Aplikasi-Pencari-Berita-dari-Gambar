"""
database.py — Koneksi SQLite dan inisialisasi skema untuk aplikasi Pencari Berita dari Gambar.

Requirements: 1.1, 1.2, 11.2
"""

import os
import sqlite3
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent
_DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(_BASE_DIR))).resolve()
_DB_PATH = os.fspath(_DATA_DIR / "berita.db")


def get_connection() -> sqlite3.Connection:
    """
    Kembalikan koneksi SQLite baru ke berita.db dengan row_factory=sqlite3.Row.

    Setiap pemanggil bertanggung jawab menutup koneksi setelah selesai.
    Tidak ada connection pooling — SQLite cukup untuk beban single-user.
    """
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Buat tabel 'berita' jika belum ada (CREATE TABLE IF NOT EXISTS).

    Fungsi ini idempoten: aman dipanggil berulang kali tanpa mengubah
    struktur tabel atau data yang sudah ada (Requirements 1.1 dan 1.2).

    Skema tabel:
        id        INTEGER PRIMARY KEY AUTOINCREMENT
        judul     TEXT    NOT NULL  -- maksimal 255 karakter
        tanggal   TEXT    NOT NULL  -- format YYYY-MM-DD
        foto_file TEXT    NOT NULL  -- nama file, e.g. "uuid4.jpg"
        pdf_file  TEXT    NOT NULL  -- nama file, e.g. "uuid4.pdf"
        phash     TEXT    NOT NULL  -- 64-char lowercase hex (hash_size=16)
        dhash     TEXT    NOT NULL  -- 64-char lowercase hex (hash_size=16)
    """
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS berita (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                judul     TEXT    NOT NULL,
                tanggal   TEXT    NOT NULL,
                foto_file TEXT    NOT NULL,
                pdf_file  TEXT    NOT NULL,
                phash     TEXT    NOT NULL,
                dhash     TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS berita_pdf_hashes (
                berita_id   INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                phash       TEXT    NOT NULL,
                dhash       TEXT    NOT NULL,
                PRIMARY KEY (berita_id, page_number),
                FOREIGN KEY (berita_id) REFERENCES berita(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS berita_pdf_image_hashes (
                berita_id   INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                image_xref  INTEGER NOT NULL,
                phash       TEXT    NOT NULL,
                dhash       TEXT    NOT NULL,
                PRIMARY KEY (berita_id, image_xref),
                FOREIGN KEY (berita_id) REFERENCES berita(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS berita_pdf_index_state (
                berita_id INTEGER PRIMARY KEY,
                version   INTEGER NOT NULL,
                FOREIGN KEY (berita_id) REFERENCES berita(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
