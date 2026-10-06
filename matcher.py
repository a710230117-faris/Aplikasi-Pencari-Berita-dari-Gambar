"""
matcher.py — Perhitungan perceptual hash dan jarak kemiripan gambar.

Modul ini murni tanpa side-effect I/O selain membaca file gambar yang diberikan.

Requirements: 3.7, 3.8, 6.2, 11.3
"""

import imagehash
from PIL import Image, UnidentifiedImageError


def compute_hashes(image_path: str) -> tuple[str, str]:
    """
    Buka gambar dari path, hitung pHash (hash_size=16) dan dHash (hash_size=16).
    Kembalikan (phash_hex, dhash_hex) masing-masing sebagai string hex lowercase 64 karakter.

    Raises:
        ValueError: Jika file tidak bisa dibuka sebagai gambar.

    Requirements: 3.7, 3.8
    """
    try:
        with Image.open(image_path) as img:
            img.verify()
        with Image.open(image_path) as img:
            return compute_hashes_from_image(img)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(
            f"File tidak dapat dibuka sebagai gambar: {image_path}"
        ) from exc


def compute_hashes_from_image(image: Image.Image) -> tuple[str, str]:
    """Hitung pHash dan dHash dari gambar Pillow yang sudah terbuka."""
    return (
        str(imagehash.phash(image, hash_size=16)),
        str(imagehash.dhash(image, hash_size=16)),
    )


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """
    Hitung jarak Hamming antara dua string hex hash 64 karakter.
    Kembalikan integer dalam rentang [0, 256] karena 64 karakter hex = 256 bit.

    Cara kerja: XOR kedua nilai integer yang diparsing dari hex,
    lalu hitung jumlah bit '1' (popcount).

    Requirements: 6.2
    """
    int_a = int(hash_a, 16)
    int_b = int(hash_b, 16)
    xor = int_a ^ int_b
    return bin(xor).count("1")


def similarity_score(
    phash_a: str,
    dhash_a: str,
    phash_b: str,
    dhash_b: str,
) -> int:
    """
    Kembalikan hamming_distance(phash_a, phash_b) + hamming_distance(dhash_a, dhash_b).
    Hasilnya berada dalam rentang [0, 512] karena setiap hash 64-char hex (256-bit)
    dapat memiliki jarak Hamming maks 256, sehingga gabungan dua hash maks 512.

    Nilai lebih rendah berarti gambar lebih mirip; 0 berarti identik.

    Requirements: 6.2
    """
    return hamming_distance(phash_a, phash_b) + hamming_distance(dhash_a, dhash_b)
