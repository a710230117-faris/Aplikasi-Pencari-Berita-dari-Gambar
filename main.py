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
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import database
import matcher

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

MAX_JARAK: int = 80
ADMIN_KEY: str = os.getenv("ADMIN_KEY", "admin-dev-key")

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="Pencari Berita dari Gambar")

# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup_event() -> None:
    """
    Jalankan saat server pertama kali start:
    1. Buat folder uploads jika belum ada.                      (Req 1.3)
    2. Hapus semua file tmp_* di uploads/tmp/.                  (Req 1.4)
    3. Inisialisasi database.                                   (Req 1.1)
    """
    # 1. Buat direktori yang diperlukan
    for folder in ("uploads/foto", "uploads/pdf", "uploads/tmp"):
        os.makedirs(folder, exist_ok=True)
        logger.info("Folder dipastikan ada: %s", folder)

    # 2. Hapus file tmp_* (bukan subdirektori) di uploads/tmp/
    pattern = os.path.join("uploads", "tmp", "tmp_*")
    for tmp_file in glob.glob(pattern):
        if os.path.isfile(tmp_file):
            try:
                os.remove(tmp_file)
                logger.info("File tmp dihapus saat startup: %s", tmp_file)
            except OSError as exc:
                logger.error("Gagal menghapus file tmp %s: %s", tmp_file, exc)

    # 3. Inisialisasi skema database
    database.init_db()
    logger.info("Database diinisialisasi.")


# ---------------------------------------------------------------------------
# Static file mounts  (urutan penting: path lebih spesifik didaftarkan lebih dulu)
# ---------------------------------------------------------------------------

# Sajikan file foto berita → GET /files/foto/{filename}  (Req 1.5, 1.6)
app.mount(
    "/files/foto",
    StaticFiles(directory="uploads/foto"),
    name="files_foto",
)

# Sajikan file PDF berita → GET /files/pdf/{filename}    (Req 1.7, 1.8)
app.mount(
    "/files/pdf",
    StaticFiles(directory="uploads/pdf"),
    name="files_pdf",
)

# CATATAN: uploads/tmp TIDAK di-mount agar akses ke /uploads/tmp/ otomatis 404 (Req 1.9)

# Sajikan aset statis HTML/CSS/JS → GET /...             (Req 11.1)
# Mount ini harus didaftarkan SETELAH route-route API agar tidak membayangi mereka.
# Dilakukan di bagian bawah file setelah semua route didefinisikan.


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@app.get("/admin", include_in_schema=False)
async def admin_page() -> FileResponse:
    """Sajikan halaman admin. (Req 11.1)"""
    return FileResponse("static/admin.html")


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
    tmp_path = f"uploads/tmp/tmp_{uuid.uuid4()}"
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
                    "SELECT id, judul, tanggal, foto_file, pdf_file, phash, dhash FROM berita"
                ).fetchall()
            finally:
                conn.close()
        except Exception as exc:
            logger.error("Gagal mengakses database saat cari berita: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Layanan sementara tidak tersedia. Coba lagi nanti.",
            )

        # 5. Hitung skor kemiripan, filter, urutkan, ambil top-3  (Req 6.5, 6.6)
        hasil = []
        for row in rows:
            score = matcher.similarity_score(
                query_phash, query_dhash, row["phash"], row["dhash"]
            )
            if score <= MAX_JARAK:
                hasil.append(
                    {
                        "id": row["id"],
                        "judul": row["judul"],
                        "tanggal": row["tanggal"],
                        "score": score,
                        "foto_url": f"/files/foto/{row['foto_file']}",
                        "pdf_url": f"/files/pdf/{row['pdf_file']}",
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
        result.append(
            {
                "id": row["id"],
                "judul": row["judul"],
                "tanggal": row["tanggal"],
                "foto_url": f"/files/foto/{row['foto_file']}",
                "pdf_url": f"/files/pdf/{row['pdf_file']}",
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
    foto_path = os.path.join("uploads", "foto", row["foto_file"])
    try:
        os.remove(foto_path)
        logger.info("File foto dihapus: %s", foto_path)
    except OSError as exc:
        logger.error("Gagal menghapus file foto %s: %s", foto_path, exc)

    # 4. Hapus file PDF dari disk (try/except terpisah)
    pdf_path = os.path.join("uploads", "pdf", row["pdf_file"])
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
    foto: UploadFile = File(...),
    pdf: UploadFile = File(...),
):
    """
    Tambah berita baru dengan foto dan PDF.

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

    # Foto: MIME type                                    (Req 3.2)
    if foto.content_type not in ALLOWED_FOTO_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Format foto tidak didukung. Gunakan JPEG atau PNG.",
        )

    # Foto: baca ukuran, lalu seek kembali               (Req 3.4)
    foto_bytes = await foto.read()
    if len(foto_bytes) > MAX_FOTO_SIZE:
        raise HTTPException(
            status_code=400,
            detail="Ukuran foto melebihi batas 10 MB.",
        )
    await foto.seek(0)

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

    # ------------------------------------------------------------------
    # 2. Tentukan nama file output dengan UUID agar tidak konflik
    # ------------------------------------------------------------------
    ext_map = {"image/jpeg": "jpg", "image/png": "png"}
    ext = ext_map[foto.content_type]
    foto_filename = f"{uuid.uuid4()}.{ext}"
    pdf_filename  = f"{uuid.uuid4()}.pdf"
    foto_path = os.path.join("uploads", "foto", foto_filename)
    pdf_path  = os.path.join("uploads", "pdf",  pdf_filename)

    # ------------------------------------------------------------------
    # 3. Simpan file + hitung hash + INSERT DB (atomik)    (Req 3.1, 3.9)
    # ------------------------------------------------------------------
    foto_saved = False
    pdf_saved  = False
    try:
        # Simpan foto
        with open(foto_path, "wb") as f:
            f.write(foto_bytes)
        foto_saved = True
        logger.info("File foto disimpan: %s", foto_path)

        # Simpan PDF
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        pdf_saved = True
        logger.info("File PDF disimpan: %s", pdf_path)

        # Hitung perceptual hash dari foto yang sudah tersimpan  (Req 3.7, 3.8)
        try:
            phash_hex, dhash_hex = matcher.compute_hashes(foto_path)
        except ValueError as exc:
            raise RuntimeError(f"Hash gagal: {exc}") from exc

        # INSERT ke database
        conn = database.get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO berita (judul, tanggal, foto_file, pdf_file, phash, dhash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (judul, tanggal, foto_filename, pdf_filename, phash_hex, dhash_hex),
            )
            conn.commit()
            new_id = cursor.lastrowid
        finally:
            conn.close()

    except HTTPException:
        # Jika HTTPException dilempar dari dalam blok ini (tidak seharusnya terjadi
        # di sini, tapi jaga-jaga), tetap rollback file yang sudah tersimpan.
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
        # Rollback: hapus file yang sudah tersimpan sebelum mengembalikan 500  (Req 3.9)
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
# Mount static root TERAKHIR agar route API tidak tertutupi  (Req 11.1)
# ---------------------------------------------------------------------------

app.mount(
    "/",
    StaticFiles(directory="static", html=True),
    name="static",
)