"""
tests/test_database.py — Property-based dan unit tests untuk database.py

# Feature: news-finder-from-image, Property 1
# Validates: Requirements 1.2

Menguji bahwa `init_db()` bersifat idempoten:
- Pemanggilan berulang tidak mengubah skema tabel.
- Pemanggilan berulang tidak menghapus data yang sudah ada.
"""

import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import database

# Kolom yang diharapkan ada pada tabel berita (sesuai CREATE TABLE)
EXPECTED_COLUMNS = {"id", "judul", "tanggal", "foto_file", "pdf_file", "phash", "dhash"}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_columns(db_path: str) -> set:
    """Kembalikan set nama kolom tabel berita dari file database yang diberikan."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("PRAGMA table_info(berita)")
        return {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()


def _table_exists(db_path: str) -> bool:
    """Periksa apakah tabel berita ada di database."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='berita'"
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Deterministic sanity-check test
# ---------------------------------------------------------------------------

def test_init_db_idempotent_basic(tmp_path):
    """
    Test deterministik: panggil init_db() tiga kali, verifikasi skema tabel
    identik dan tidak ada data yang hilang.
    """
    db_file = str(tmp_path / "test_basic.db")

    with patch.object(database, "_DB_PATH", db_file):
        # Panggilan pertama — membuat tabel
        database.init_db()
        assert _table_exists(db_file), "Tabel berita harus ada setelah init_db() pertama"
        assert _get_columns(db_file) == EXPECTED_COLUMNS

        # Masukkan satu baris data
        conn = sqlite3.connect(db_file)
        conn.execute(
            "INSERT INTO berita (judul, tanggal, foto_file, pdf_file, phash, dhash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("Berita Uji", "2024-01-01", "foto.jpg", "berita.pdf", "a" * 64, "b" * 64),
        )
        conn.commit()
        conn.close()

        # Panggilan kedua dan ketiga — harus idempoten
        database.init_db()
        database.init_db()

        # Skema tidak berubah
        assert _get_columns(db_file) == EXPECTED_COLUMNS

        # Data tidak hilang
        conn = sqlite3.connect(db_file)
        cursor = conn.execute("SELECT COUNT(*) FROM berita")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1, "Data yang sudah ada harus tetap ada setelah init_db() berulang"


# ---------------------------------------------------------------------------
# Property-based test — Property 1: Idempotence Inisialisasi Database
# Feature: news-finder-from-image, Property 1
# Validates: Requirements 1.2
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(n_calls=st.integers(min_value=2, max_value=5))
def test_init_db_idempotent_schema(tmp_path, n_calls):
    """
    **Validates: Requirements 1.2**

    Property 1: Memanggil init_db() sebanyak N kali (2 ≤ N ≤ 5) pada database
    yang sama harus menghasilkan skema tabel yang identik — tabel berita ada
    dengan kolom yang persis sama.

    Menggunakan tempfile terpisah per contoh Hypothesis agar isolasi terjaga
    meski fixture tmp_path tidak di-reset antar generated input.
    """
    # Buat file DB sementara yang unik untuk setiap contoh yang di-generate
    with tempfile.NamedTemporaryFile(
        suffix=".db", dir=str(tmp_path), delete=False
    ) as f:
        db_file = f.name

    try:
        with patch.object(database, "_DB_PATH", db_file):
            for _ in range(n_calls):
                database.init_db()

        assert _table_exists(db_file), "Tabel berita harus ada setelah N kali init_db()"
        assert _get_columns(db_file) == EXPECTED_COLUMNS, (
            f"Kolom tabel tidak sesuai setelah {n_calls} pemanggilan init_db(). "
            f"Diharapkan: {EXPECTED_COLUMNS}, Didapat: {_get_columns(db_file)}"
        )
    finally:
        if os.path.exists(db_file):
            os.unlink(db_file)


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(n_calls=st.integers(min_value=2, max_value=5))
def test_init_db_idempotent_data_preserved(tmp_path, n_calls):
    """
    **Validates: Requirements 1.2**

    Property 1 (data preservation): Memanggil init_db() berulang kali setelah
    data dimasukkan tidak boleh menghapus baris yang sudah ada.

    Menggunakan tempfile terpisah per contoh Hypothesis agar isolasi terjaga
    meski fixture tmp_path tidak di-reset antar generated input.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".db", dir=str(tmp_path), delete=False
    ) as f:
        db_file = f.name

    try:
        with patch.object(database, "_DB_PATH", db_file):
            # Inisialisasi pertama
            database.init_db()

            # Masukkan satu baris contoh
            conn = sqlite3.connect(db_file)
            conn.execute(
                "INSERT INTO berita (judul, tanggal, foto_file, pdf_file, phash, dhash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "Judul Contoh",
                    "2024-06-15",
                    "gambar.jpg",
                    "dokumen.pdf",
                    "c" * 64,
                    "d" * 64,
                ),
            )
            conn.commit()
            conn.close()

            # Panggil init_db() sebanyak N kali lagi
            for _ in range(n_calls):
                database.init_db()

        # Data tidak boleh hilang
        conn = sqlite3.connect(db_file)
        cursor = conn.execute("SELECT COUNT(*) FROM berita")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1, (
            f"Data harus tetap ada setelah {n_calls} pemanggilan init_db() tambahan, "
            f"tetapi ditemukan {count} baris."
        )
    finally:
        if os.path.exists(db_file):
            os.unlink(db_file)
