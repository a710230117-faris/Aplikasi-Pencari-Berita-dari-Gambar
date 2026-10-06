"""
main.py — Aplikasi FastAPI untuk Pencari Berita dari Gambar.

Server utama yang berisi seluruh rute API.

Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.1–2.5,
              3.1–3.9, 4.1–4.4, 5.1–5.4, 6.1–6.8, 9.1–9.4, 11.1
"""

import glob
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import database
import matcher
import pdf_indexer

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = BASE_DIR / "uploads"
FOTO_DIR = UPLOAD_ROOT / "foto"
PDF_DIR = UPLOAD_ROOT / "pdf"
TMP_DIR = UPLOAD_ROOT / "tmp"
STATIC_DIR = BASE_DIR / "static"

MAX_JARAK: int = 80
ADMIN_KEY: str = os.getenv("ADMIN_KEY", "admin-dev-key")

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


def cleanup_orphan_uploads() -> int:
    """Hapus foto/PDF yang tidak lagi dirujuk oleh baris berita di database."""
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT foto_file, pdf_file FROM berita"
        ).fetchall()
    finally:
        conn.close()

    referenced_files = {
        "foto": {row["foto_file"] for row in rows if row["foto_file"]},
        "pdf": {row["pdf_file"] for row in rows if row["pdf_file"]},
    }
    upload_dirs = {
        "foto": (FOTO_DIR, {".jpg", ".jpeg", ".png"}),
        "pdf": (PDF_DIR, {".pdf"}),
    }
    deleted_count = 0

    for category, (folder, allowed_extensions) in upload_dirs.items():
        for path in folder.iterdir():
            if (
                path.is_symlink()
                or not path.is_file()
                or path.suffix.lower() not in allowed_extensions
                or path.name in referenced_files[category]
            ):
                continue

            try:
                path.unlink()
                deleted_count += 1
                logger.info("File unggahan yatim dihapus: %s", path)
            except OSError as exc:
                logger.error("Gagal menghapus file unggahan yatim %s: %s", path, exc)

    logger.info("Pembersihan file unggahan selesai: %s file dihapus.", deleted_count)
    return deleted_count


def index_missing_pdf_pages() -> int:
    """Create page hashes for PDFs already stored before PDF matching existed."""
    conn = database.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT b.id, b.pdf_file
            FROM berita b
            WHERE COALESCE(b.pdf_file, '') != ''
              AND NOT EXISTS (
                  SELECT 1 FROM berita_pdf_index_state s
                  WHERE s.berita_id = b.id AND s.version = ?
              )
            """,
            (pdf_indexer.PDF_INDEX_VERSION,),
        ).fetchall()
    finally:
        conn.close()

    indexed_count = 0
    for row in rows:
        pdf_file = row["pdf_file"]
        if not isinstance(pdf_file, str) or Path(pdf_file).name != pdf_file:
            logger.error("Nama file PDF tidak valid untuk berita id=%s.", row["id"])
            continue

        pdf_path = PDF_DIR / pdf_file
        if not pdf_path.is_file():
            logger.warning("PDF tidak ditemukan untuk berita id=%s: %s", row["id"], pdf_path)
            continue

        try:
            page_hashes = pdf_indexer.index_pdf_pages(pdf_path)
            conn = database.get_connection()
            try:
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO berita_pdf_hashes
                        (berita_id, page_number, phash, dhash)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (row["id"], page.page_number, page.phash, page.dhash)
                        for page in page_hashes
                    ],
                )
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO berita_pdf_image_hashes
                        (berita_id, page_number, image_xref, phash, dhash)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (row["id"], page.page_number, xref, phash, dhash)
                        for page in page_hashes
                        for xref, phash, dhash in page.embedded_images
                    ],
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO berita_pdf_index_state (berita_id, version)
                    VALUES (?, ?)
                    """,
                    (row["id"], pdf_indexer.PDF_INDEX_VERSION),
                )
                conn.commit()
            finally:
                conn.close()
            indexed_count += 1
            logger.info(
                "PDF berita id=%s diindeks: %s halaman.",
                row["id"],
                len(page_hashes),
            )
        except Exception:
            logger.exception("Gagal mengindeks PDF berita id=%s: %s", row["id"], pdf_path)

    return indexed_count


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Pastikan folder upload ada, bersihkan file sementara dan file yatim,
    lalu inisialisasi database.
    """
    for folder in (FOTO_DIR, PDF_DIR, TMP_DIR):
        folder.mkdir(parents=True, exist_ok=True)
        logger.info("Folder dipastikan ada: %s", folder)

    for tmp_file in glob.glob(str(TMP_DIR / "tmp_*")):
        if os.path.isfile(tmp_file):
            try:
                os.remove(tmp_file)
                logger.info("File tmp dihapus saat startup: %s", tmp_file)
            except OSError as exc:
                logger.error("Gagal menghapus file tmp %s: %s", tmp_file, exc)

    database.init_db()
    logger.info("Database diinisialisasi.")
    cleanup_orphan_uploads()
    index_missing_pdf_pages()
    yield


app = FastAPI(title="Pencari Berita dari Gambar", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Static file mounts  (urutan penting: path lebih spesifik didaftarkan lebih dulu)
# ---------------------------------------------------------------------------

# Sajikan file foto berita → GET /files/foto/{filename}  (Req 1.5, 1.6)
app.mount(
    "/files/foto",
    StaticFiles(directory=str(FOTO_DIR)),
    name="files_foto",
)

# Sajikan file PDF berita → GET /files/pdf/{filename}    (Req 1.7, 1.8)
app.mount(
    "/files/pdf",
    StaticFiles(directory=str(PDF_DIR)),
    name="files_pdf",
)

# CATATAN: uploads/tmp TIDAK di-mount agar akses ke /uploads/tmp/ otomatis 404 (Req 1.9)

# Sajikan aset statis HTML/CSS/JS → GET /static/...      (Req 11.1)
# Mount ini harus didaftarkan SETELAH route-route API agar tidak membayangi mereka.
# Pada aplikasi ini, root page di-render melalui route terpisah agar URL /static/
# tetap valid dan tidak konflik dengan file HTML yang disajikan di /.


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def index_page() -> FileResponse:
    """Sajikan halaman utama aplikasi."""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/admin", include_in_schema=False)
async def admin_page() -> FileResponse:
    """Sajikan halaman admin. (Req 11.1)"""
    return FileResponse(str(STATIC_DIR / "admin.html"))


# ---------------------------------------------------------------------------
# Dependency: verify_admin_key  (Req 2.1, 2.2, 2.3, 2.4, 2.5)
# ---------------------------------------------------------------------------


async def verify_admin_key(x_admin_key: Optional[str] = Header(default=None)) -> None:
    """
    Dependency FastAPI untuk memverifikasi header x-admin-key.

    - Jika header tidak ada (None) atau nilainya tidak cocok secara exact match
      dengan ADMIN_KEY, raise HTTPException 403.
    - Perbandingan bersifat case-sensitive exact match.            (Req 2.5)
    - ADMIN_KEY dibaca dari environment variable saat startup.     (Req 2.1)
    """
    if not x_admin_key or x_admin_key != ADMIN_KEY:
        raise HTTPException(
            status_code=403,
            detail="Autentikasi diperlukan atau kunci tidak valid.",
        )


# ---------------------------------------------------------------------------
# POST /api/cari  (Req 6.1–6.8, 9.1–9.4)
# ---------------------------------------------------------------------------

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


@app.post("/api/cari")
async def cari_berita(file: UploadFile = File(...)):
    """
    Terima unggahan gambar, hitung perceptual hash-nya, lalu cari berita yang
    paling mirip berdasarkan jarak Hamming gabungan (pHash + dHash).

    Returns:
        JSON dengan field ``ditemukan`` (bool) dan ``hasil`` (list, maks 3 item).
    """
    # 1. Validasi MIME type — tolak sebelum membuat file tmp  (Req 6.1)
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Format file tidak didukung. Gunakan JPEG, PNG, atau WebP.",
        )

    # 2. Simpan ke tmp file sementara                         (Req 6.3)
    tmp_path = TMP_DIR / f"tmp_{uuid.uuid4()}"
    try:
        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        # 3. Hitung hash                                      (Req 6.2)
        try:
            query_phash, query_dhash = matcher.compute_hashes(tmp_path)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="File gambar tidak valid atau tidak dapat diproses.",
            )

        # 4. Ambil semua baris berita dari DB                 (Req 6.4)
        try:
            conn = database.get_connection()
            try:
                rows = conn.execute(
                    """
                    SELECT b.id, b.judul, b.tanggal, b.foto_file, b.pdf_file,
                           b.phash, b.dhash,
                           h.phash AS page_phash, h.dhash AS page_dhash
                    FROM berita b
                    LEFT JOIN berita_pdf_hashes h ON h.berita_id = b.id
                    ORDER BY b.id, h.page_number
                    """
                ).fetchall()
                image_rows = conn.execute(
                    """
                    SELECT b.id, b.judul, b.tanggal, b.foto_file, b.pdf_file,
                           b.phash, b.dhash,
                           i.phash AS page_phash, i.dhash AS page_dhash
                    FROM berita b
                    JOIN berita_pdf_image_hashes i ON i.berita_id = b.id
                    ORDER BY b.id, i.page_number, i.image_xref
                    """
                ).fetchall()
                rows = list(rows) + list(image_rows)
            finally:
                conn.close()
        except Exception as exc:
            logger.error("Gagal mengakses database saat cari berita: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Layanan sementara tidak tersedia. Coba lagi nanti.",
            )

        # Gabungkan semua foto/PDF-page candidate per berita, lalu ambil skor
        # terendah agar satu berita tidak muncul berkali-kali.
        berita_candidates = {}
        for row in rows:
            foto_file = row["foto_file"] or ""
            pdf_file = row["pdf_file"] or ""
            if (
                not isinstance(pdf_file, str)
                or not pdf_file
                or Path(pdf_file).name != pdf_file
                or not (PDF_DIR / pdf_file).is_file()
            ):
                continue

            news = berita_candidates.setdefault(
                row["id"],
                {
                    "id": row["id"],
                    "judul": row["judul"],
                    "tanggal": row["tanggal"],
                    "foto_file": "",
                    "pdf_file": pdf_file,
                    "scores": [],
                },
            )

            if (
                isinstance(foto_file, str)
                and foto_file
                and Path(foto_file).name == foto_file
                and (FOTO_DIR / foto_file).is_file()
                and isinstance(row["phash"], str)
                and isinstance(row["dhash"], str)
                and re.fullmatch(r"[0-9a-fA-F]{64}", row["phash"])
                and re.fullmatch(r"[0-9a-fA-F]{64}", row["dhash"])
            ):
                news["foto_file"] = foto_file
                news["scores"].append(
                    matcher.similarity_score(
                        query_phash, query_dhash, row["phash"], row["dhash"]
                    )
                )

            page_phash = row["page_phash"]
            page_dhash = row["page_dhash"]
            if (
                isinstance(page_phash, str)
                and isinstance(page_dhash, str)
                and re.fullmatch(r"[0-9a-fA-F]{64}", page_phash)
                and re.fullmatch(r"[0-9a-fA-F]{64}", page_dhash)
            ):
                news["scores"].append(
                    matcher.similarity_score(
                        query_phash, query_dhash, page_phash, page_dhash
                    )
                )

        # Hitung satu skor terendah per berita, filter, urutkan, ambil top-3.
        hasil = []
        for news in berita_candidates.values():
            if not news["scores"]:
                continue
            score = min(news["scores"])
            if score <= MAX_JARAK:
                hasil.append(
                    {
                        "id": news["id"],
                        "judul": news["judul"],
                        "tanggal": news["tanggal"],
                        "score": score,
                        "foto_url": (
                            f"/files/foto/{news['foto_file']}"
                            if news["foto_file"]
                            else ""
                        ),
                        "pdf_url": f"/files/pdf/{news['pdf_file']}",
                    }
                )

        hasil.sort(key=lambda x: x["score"])
        hasil = hasil[:3]

    finally:
        # 6. Hapus tmp file — selalu dieksekusi                (Req 6.8)
        try:
            os.remove(tmp_path)
        except OSError as e:
            logger.error("Gagal menghapus tmp file %s: %s", tmp_path, e)

    # 7. Kembalikan respons                                   (Req 6.7)
    return {
        "ditemukan": len(hasil) > 0,
        "hasil": hasil,
    }


# ---------------------------------------------------------------------------
# GET /api/admin/berita  (Req 5.1, 5.2, 5.3, 5.4)
# ---------------------------------------------------------------------------


@app.get("/api/admin/berita", dependencies=[Depends(verify_admin_key)])
async def list_berita():
    """
    Kembalikan daftar semua berita diurutkan dari tanggal terbaru ke terlama.

    - Memerlukan header x-admin-key yang valid.             (Req 5.3)
    - Kembalikan daftar kosong jika tidak ada berita.       (Req 5.2)
    - Tangani DB error → HTTP 500.                          (Req 5.4)
    """
    try:
        conn = database.get_connection()
        try:
            rows = conn.execute(
                "SELECT id, judul, tanggal, foto_file, pdf_file FROM berita ORDER BY tanggal DESC"
            ).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Gagal mengakses database saat list berita: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Terjadi kesalahan internal.",
        )

    result = []
    for row in rows:
        foto_file = row["foto_file"] or ""
        pdf_file = row["pdf_file"] or ""
        result.append(
            {
                "id": row["id"],
                "judul": row["judul"],
                "tanggal": row["tanggal"],
                "foto_url": f"/files/foto/{foto_file}" if foto_file else "",
                "pdf_url": f"/files/pdf/{pdf_file}" if pdf_file else "",
            }
        )

    return result


# ---------------------------------------------------------------------------
# DELETE /api/admin/berita/{id}  (Req 4.1, 4.2, 4.3, 4.4)
# ---------------------------------------------------------------------------


@app.delete("/api/admin/berita/{berita_id}", dependencies=[Depends(verify_admin_key)])
async def hapus_berita(berita_id: int):
    """
    Hapus berita beserta file foto dan PDF-nya dari disk.

    - 404 jika id tidak ada di database.                        (Req 4.2)
    - Penghapusan file dilakukan dalam try/except terpisah;
      kegagalan dicatat ke log tetapi respons tetap HTTP 200.   (Req 4.4)
    - Memerlukan header x-admin-key yang valid.                 (Req 4.3)
    """
    # 1. Cari berita berdasarkan id
    try:
        conn = database.get_connection()
        try:
            row = conn.execute(
                "SELECT id, foto_file, pdf_file FROM berita WHERE id = ?", (berita_id,)
            ).fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Berita tidak ditemukan.",
                )

            # 2. Hapus baris dari database
            conn.execute(
                "DELETE FROM berita_pdf_hashes WHERE berita_id = ?", (berita_id,)
            )
            conn.execute(
                "DELETE FROM berita_pdf_image_hashes WHERE berita_id = ?",
                (berita_id,),
            )
            conn.execute(
                "DELETE FROM berita_pdf_index_state WHERE berita_id = ?",
                (berita_id,),
            )
            conn.execute("DELETE FROM berita WHERE id = ?", (berita_id,))
            conn.commit()
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Gagal mengakses database saat hapus berita id=%s: %s", berita_id, exc)
        raise HTTPException(
            status_code=500,
            detail="Terjadi kesalahan internal.",
        )

    # 3. Hapus file foto dari disk (try/except terpisah)
    foto_name = row["foto_file"] or ""
    if foto_name:
        foto_path = FOTO_DIR / foto_name
        try:
            os.remove(foto_path)
            logger.info("File foto dihapus: %s", foto_path)
        except OSError as exc:
            logger.error("Gagal menghapus file foto %s: %s", foto_path, exc)

    # 4. Hapus file PDF dari disk (try/except terpisah)
    pdf_name = row["pdf_file"] or ""
    if pdf_name:
        pdf_path = PDF_DIR / pdf_name
        try:
            os.remove(pdf_path)
            logger.info("File PDF dihapus: %s", pdf_path)
        except OSError as exc:
            logger.error("Gagal menghapus file PDF %s: %s", pdf_path, exc)

    # 5. Selalu return 200 meski penghapusan file gagal          (Req 4.4)
    return {"message": "Berita berhasil dihapus."}


# ---------------------------------------------------------------------------
# POST /api/admin/berita  (Req 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9)
# ---------------------------------------------------------------------------

ALLOWED_FOTO_TYPES = {"image/jpeg", "image/png"}
MAX_FOTO_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_PDF_SIZE  = 30 * 1024 * 1024   # 30 MB
_TANGGAL_RE   = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@app.post("/api/admin/berita", status_code=201, dependencies=[Depends(verify_admin_key)])
async def tambah_berita(
    judul: str = File(...),
    tanggal: str = File(...),
    foto: UploadFile | None = File(default=None),
    pdf: UploadFile = File(...),
):
    """
    Tambah berita baru dengan foto opsional dan PDF wajib.

    Semua validasi dilakukan sebelum file apa pun disimpan ke disk.
    Atomisitas dijaga dengan flag foto_saved/pdf_saved — jika gagal setelah
    menyimpan, file yang sudah tersimpan dihapus sebelum mengembalikan 500.

    Returns HTTP 201 dengan {id, judul, message} jika berhasil.
    """
    # ------------------------------------------------------------------
    # 1. Validasi input — SEBELUM menyimpan file apa pun  (Req 3.6)
    # ------------------------------------------------------------------

    # Judul: tidak kosong, 1–255 karakter                (Req 3.6)
    judul = judul.strip()
    if not judul:
        raise HTTPException(status_code=400, detail="Judul tidak boleh kosong.")
    if len(judul) > 255:
        raise HTTPException(status_code=400, detail="Judul maksimal 255 karakter.")

    # Tanggal: format YYYY-MM-DD                         (Req 3.6)
    if not _TANGGAL_RE.match(tanggal):
        raise HTTPException(
            status_code=400,
            detail="Tanggal harus dalam format YYYY-MM-DD.",
        )

    # Foto: opsional, validasi hanya jika dikirim
    if foto is not None:
        if foto.content_type not in ALLOWED_FOTO_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Format foto tidak didukung. Gunakan JPEG atau PNG.",
            )

        foto_bytes = await foto.read()
        if len(foto_bytes) > MAX_FOTO_SIZE:
            raise HTTPException(
                status_code=400,
                detail="Ukuran foto melebihi batas 10 MB.",
            )
        await foto.seek(0)
    else:
        foto_bytes = b""

    # PDF: MIME type                                     (Req 3.3)
    if pdf.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="File PDF tidak valid. Pastikan mengunggah file PDF.",
        )

    # PDF: baca ukuran, lalu seek kembali                (Req 3.5)
    pdf_bytes = await pdf.read()
    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400,
            detail="Ukuran PDF melebihi batas 30 MB.",
        )
    await pdf.seek(0)

    try:
        pdf_page_hashes = pdf_indexer.index_pdf_pages(pdf_bytes)
    except Exception as exc:
        logger.info("PDF tidak dapat diproses untuk pencocokan visual: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="PDF tidak valid atau halamannya tidak dapat diproses.",
        ) from exc

    # ------------------------------------------------------------------
    # 2. Tentukan nama file output dengan UUID agar tidak konflik
    # ------------------------------------------------------------------
    foto_filename = ""
    phash_hex = ""
    dhash_hex = ""
    foto_path = None
    if foto is not None:
        ext_map = {"image/jpeg": "jpg", "image/png": "png"}
        ext = ext_map[foto.content_type]
        foto_filename = f"{uuid.uuid4()}.{ext}"
        foto_path = FOTO_DIR / foto_filename

    pdf_filename = f"{uuid.uuid4()}.pdf"
    pdf_path = PDF_DIR / pdf_filename

    # ------------------------------------------------------------------
    # 3. Simpan file + hitung hash + INSERT DB (atomik)    (Req 3.1, 3.9)
    # ------------------------------------------------------------------
    foto_saved = False
    pdf_saved = False
    try:
        if foto is not None:
            with open(foto_path, "wb") as f:
                f.write(foto_bytes)
            foto_saved = True
            logger.info("File foto disimpan: %s", foto_path)

        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        pdf_saved = True
        logger.info("File PDF disimpan: %s", pdf_path)

        if foto is not None:
            try:
                phash_hex, dhash_hex = matcher.compute_hashes(foto_path)
            except ValueError as exc:
                raise RuntimeError(f"Hash gagal: {exc}") from exc

        conn = database.get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO berita (judul, tanggal, foto_file, pdf_file, phash, dhash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (judul, tanggal, foto_filename, pdf_filename, phash_hex, dhash_hex),
            )
            new_id = cursor.lastrowid
            conn.executemany(
                """
                INSERT INTO berita_pdf_hashes
                    (berita_id, page_number, phash, dhash)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (new_id, page.page_number, page.phash, page.dhash)
                    for page in pdf_page_hashes
                ],
            )
            conn.executemany(
                """
                INSERT INTO berita_pdf_image_hashes
                    (berita_id, page_number, image_xref, phash, dhash)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (new_id, page.page_number, xref, image_phash, image_dhash)
                    for page in pdf_page_hashes
                    for xref, image_phash, image_dhash in page.embedded_images
                ],
            )
            conn.execute(
                """
                INSERT INTO berita_pdf_index_state (berita_id, version)
                VALUES (?, ?)
                """,
                (new_id, pdf_indexer.PDF_INDEX_VERSION),
            )
            conn.commit()
        finally:
            conn.close()

    except HTTPException:
        if foto_saved:
            try:
                os.remove(foto_path)
            except OSError as e:
                logger.error("Rollback foto gagal %s: %s", foto_path, e)
        if pdf_saved:
            try:
                os.remove(pdf_path)
            except OSError as e:
                logger.error("Rollback PDF gagal %s: %s", pdf_path, e)
        raise
    except Exception as exc:
        logger.error("Gagal menyimpan berita: %s", exc)
        if foto_saved:
            try:
                os.remove(foto_path)
                logger.info("Rollback foto: %s dihapus", foto_path)
            except OSError as e:
                logger.error("Rollback foto gagal %s: %s", foto_path, e)
        if pdf_saved:
            try:
                os.remove(pdf_path)
                logger.info("Rollback PDF: %s dihapus", pdf_path)
            except OSError as e:
                logger.error("Rollback PDF gagal %s: %s", pdf_path, e)
        raise HTTPException(
            status_code=500,
            detail="Terjadi kesalahan internal.",
        )

    logger.info("Berita baru ditambahkan: id=%s judul=%r", new_id, judul)
    return {"id": new_id, "judul": judul, "message": "Berita berhasil ditambahkan."}


# ---------------------------------------------------------------------------
# Mount static root: aset frontend di /static/
# ---------------------------------------------------------------------------

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)