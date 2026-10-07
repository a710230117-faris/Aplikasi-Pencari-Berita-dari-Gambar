# Ringkasan Tinjauan Keamanan

Tanggal tinjauan: 2026-10-07

## Temuan

| # | Severity | File | Lines | Kerentanan | Confidence |
|---|----------|------|-------|------------|------------|
| 1 | 🟠 HIGH | [main.py](main.py#L50) | 50, 264-269 | Kunci admin default yang diketahui publik dapat mengizinkan akses ke endpoint admin jika `ADMIN_KEY` tidak dikonfigurasi. | 9/10 |

### Status remediasi

Temuan 1 telah diperbaiki. Tidak ada lagi kunci default; bila `ADMIN_KEY` kosong atau tidak tersedia, endpoint admin mengembalikan HTTP 503. Kunci yang diberikan dibandingkan dengan `hmac.compare_digest`.

## Catatan deployment

- Aplikasi harus dijalankan di belakang HTTPS saat digunakan di lingkungan produksi agar header autentikasi terlindungi saat transit.
- Versi dependency di `requirements.txt` belum dikunci. Tinjau dan perbarui dependency secara berkala.
- Repository melacak `berita.db` dan sebuah berkas PDF unggahan. Isi dan sensitivitas data tersebut tidak dinilai dalam tinjauan ini; pastikan keduanya memang layak dipublikasikan.

## Verifikasi

Tes API yang relevan dijalankan: 45 passed.
