"""
tests/test_matcher.py — Property-based dan unit tests untuk matcher.py

# Feature: news-finder-from-image, Property 4
# Validates: Requirements 3.7, 3.8

Menguji bahwa:
- `compute_hashes()` menghasilkan tuple (phash_hex, dhash_hex) dengan panjang tepat
  64 karakter hex lowercase untuk sembarang gambar valid.
- `hamming_distance()` mengembalikan integer non-negatif antara 0 dan 256.
- `similarity_score()` dalam rentang [0, 512] dan bersifat komutatif.
- `ValueError` diangkat jika file tidak bisa dibuka sebagai gambar.
"""

import io
import os
import tempfile

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PIL import Image

import matcher

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_HEX_CHARS = frozenset("0123456789abcdef")


def _make_image_file(mode: str = "RGB", size: tuple = (32, 32), fmt: str = "JPEG") -> str:
    """Buat file gambar sementara di disk dan kembalikan path-nya."""
    img = Image.new(mode, size)
    with tempfile.NamedTemporaryFile(suffix=f".{fmt.lower()}", delete=False) as f:
        img.save(f, format=fmt)
        return f.name


def _make_image_bytes(
    width: int,
    height: int,
    r: int,
    g: int,
    b: int,
    fmt: str = "JPEG",
) -> bytes:
    """Buat bytes gambar valid dari parameter warna dan dimensi yang diberikan."""
    img = Image.new("RGB", (width, height), color=(r, g, b))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Strategi Hypothesis
# ---------------------------------------------------------------------------

@st.composite
def image_file_strategy(draw, fmt: str = "JPEG"):
    """
    Strategy yang menghasilkan path file gambar JPEG valid di disk.
    Dimensi dipilih antara 8–64 pixel untuk memastikan perceptual hash bisa dihitung.
    Warna dipilih acak agar variasi hash cukup representatif.
    """
    width = draw(st.integers(min_value=8, max_value=64))
    height = draw(st.integers(min_value=8, max_value=64))
    r = draw(st.integers(min_value=0, max_value=255))
    g = draw(st.integers(min_value=0, max_value=255))
    b = draw(st.integers(min_value=0, max_value=255))

    image_bytes = _make_image_bytes(width, height, r, g, b, fmt=fmt)

    with tempfile.NamedTemporaryFile(
        suffix=f".{fmt.lower()}", delete=False
    ) as f:
        f.write(image_bytes)
        path = f.name

    return path


@st.composite
def hex_hash_strategy(draw):
    """
    Strategy yang menghasilkan string hex lowercase 64 karakter acak
    sebagai representasi hash yang valid.
    """
    chars = draw(st.lists(
        st.sampled_from("0123456789abcdef"),
        min_size=64,
        max_size=64,
    ))
    return "".join(chars)


# ---------------------------------------------------------------------------
# Unit tests deterministik
# ---------------------------------------------------------------------------

class TestComputeHashesUnit:
    """Unit tests deterministik untuk compute_hashes()."""

    def test_returns_tuple_of_two_strings(self, tmp_path):
        """compute_hashes() harus mengembalikan tuple dua string."""
        path = str(tmp_path / "test.jpg")
        Image.new("RGB", (32, 32)).save(path, format="JPEG")
        result = matcher.compute_hashes(path)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)

    def test_phash_length_64(self, tmp_path):
        """phash harus berupa string hex 64 karakter."""
        path = str(tmp_path / "test.jpg")
        Image.new("RGB", (32, 32)).save(path, format="JPEG")
        phash, _ = matcher.compute_hashes(path)
        assert len(phash) == 64

    def test_dhash_length_64(self, tmp_path):
        """dhash harus berupa string hex 64 karakter."""
        path = str(tmp_path / "test.jpg")
        Image.new("RGB", (32, 32)).save(path, format="JPEG")
        _, dhash = matcher.compute_hashes(path)
        assert len(dhash) == 64

    def test_phash_is_lowercase_hex(self, tmp_path):
        """phash harus terdiri dari karakter hex lowercase saja."""
        path = str(tmp_path / "test.jpg")
        Image.new("RGB", (32, 32)).save(path, format="JPEG")
        phash, _ = matcher.compute_hashes(path)
        assert all(c in _HEX_CHARS for c in phash), (
            f"phash mengandung karakter non-hex: {phash!r}"
        )

    def test_dhash_is_lowercase_hex(self, tmp_path):
        """dhash harus terdiri dari karakter hex lowercase saja."""
        path = str(tmp_path / "test.jpg")
        Image.new("RGB", (32, 32)).save(path, format="JPEG")
        _, dhash = matcher.compute_hashes(path)
        assert all(c in _HEX_CHARS for c in dhash), (
            f"dhash mengandung karakter non-hex: {dhash!r}"
        )

    def test_png_image_supported(self, tmp_path):
        """compute_hashes() harus berhasil untuk file PNG."""
        path = str(tmp_path / "test.png")
        Image.new("RGB", (32, 32)).save(path, format="PNG")
        phash, dhash = matcher.compute_hashes(path)
        assert len(phash) == 64
        assert len(dhash) == 64

    def test_invalid_file_raises_value_error(self, tmp_path):
        """compute_hashes() harus raise ValueError untuk file yang bukan gambar."""
        path = str(tmp_path / "not_an_image.jpg")
        with open(path, "wb") as f:
            f.write(b"ini bukan gambar")
        with pytest.raises(ValueError):
            matcher.compute_hashes(path)

    def test_nonexistent_file_raises_value_error(self, tmp_path):
        """compute_hashes() harus raise ValueError untuk file yang tidak ada."""
        path = str(tmp_path / "tidak_ada.jpg")
        with pytest.raises(ValueError):
            matcher.compute_hashes(path)

    def test_same_image_gives_same_hash(self, tmp_path):
        """Gambar yang sama harus menghasilkan hash yang identik."""
        path = str(tmp_path / "test.jpg")
        Image.new("RGB", (32, 32), color=(100, 150, 200)).save(path, format="JPEG")
        phash1, dhash1 = matcher.compute_hashes(path)
        phash2, dhash2 = matcher.compute_hashes(path)
        assert phash1 == phash2
        assert dhash1 == dhash2


class TestHammingDistanceUnit:
    """Unit tests deterministik untuk hamming_distance()."""

    def test_identical_hashes_zero_distance(self):
        """Hash yang identik harus menghasilkan jarak 0."""
        h = "a" * 64
        assert matcher.hamming_distance(h, h) == 0

    def test_all_zeros_vs_all_ones(self):
        """Hash all-zero vs all-one harus menghasilkan jarak maksimal 256."""
        h_zero = "0" * 64  # 256 bit nol
        h_ones = "f" * 64  # 256 bit satu
        assert matcher.hamming_distance(h_zero, h_ones) == 256

    def test_one_bit_difference(self):
        """Perbedaan satu bit harus menghasilkan jarak 1."""
        h_a = "0" * 64
        h_b = "0" * 63 + "1"  # bit terakhir berbeda 1 bit
        assert matcher.hamming_distance(h_a, h_b) == 1

    def test_result_is_integer(self):
        """Hasil hamming_distance harus berupa integer."""
        result = matcher.hamming_distance("a" * 64, "b" * 64)
        assert isinstance(result, int)

    def test_symmetric(self):
        """hamming_distance(a, b) == hamming_distance(b, a)."""
        h_a = "deadbeef" * 8  # 64 chars
        h_b = "cafebabe" * 8  # 64 chars
        assert matcher.hamming_distance(h_a, h_b) == matcher.hamming_distance(h_b, h_a)


class TestSimilarityScoreUnit:
    """Unit tests deterministik untuk similarity_score()."""

    def test_identical_images_score_zero(self):
        """Hash yang identik harus menghasilkan skor 0."""
        h = "a" * 64
        assert matcher.similarity_score(h, h, h, h) == 0

    def test_result_is_integer(self):
        """Hasil similarity_score harus berupa integer."""
        h = "a" * 64
        result = matcher.similarity_score(h, h, h, h)
        assert isinstance(result, int)

    def test_sum_of_two_hamming_distances(self):
        """similarity_score harus sama dengan jumlah dua hamming_distance."""
        pa = "a" * 64
        da = "b" * 64
        pb = "c" * 64
        db = "d" * 64
        expected = matcher.hamming_distance(pa, pb) + matcher.hamming_distance(da, db)
        assert matcher.similarity_score(pa, da, pb, db) == expected

    def test_commutative(self):
        """similarity_score(A, B) harus sama dengan similarity_score(B, A)."""
        pa, da = "deadbeef" * 8, "cafebabe" * 8
        pb, db = "12345678" * 8, "abcdef01" * 8
        assert matcher.similarity_score(pa, da, pb, db) == matcher.similarity_score(pb, db, pa, da)


# ---------------------------------------------------------------------------
# Property-based test — Property 5: Similarity Score dalam Rentang Valid
# Feature: news-finder-from-image, Property 5
# Validates: Requirements 6.2
# ---------------------------------------------------------------------------

def hex_hash():
    """
    Strategy Hypothesis yang menghasilkan string hex lowercase 64 karakter.
    Merepresentasikan hash gambar yang valid (pHash atau dHash dengan hash_size=16).
    """
    return st.lists(
        st.sampled_from("0123456789abcdef"),
        min_size=64,
        max_size=64,
    ).map("".join)


@given(
    pa=hex_hash(),
    da=hex_hash(),
    pb=hex_hash(),
    db=hex_hash(),
)
@settings(max_examples=100)
def test_similarity_score_range_and_commutativity(pa, da, pb, db):
    """
    **Validates: Requirements 6.2**

    Property 5: Similarity Score dalam Rentang Valid

    Untuk sembarang 4 string hex 64-char, `similarity_score()` harus:
    1. Menghasilkan nilai integer dalam rentang [0, 256].
    2. Bersifat komutatif: score(A, B) == score(B, A).

    # Feature: news-finder-from-image, Property 5
    """
    score_ab = matcher.similarity_score(pa, da, pb, db)
    score_ba = matcher.similarity_score(pb, db, pa, da)

    # Rentang valid: [0, 512] karena setiap hamming distance pada hash 64-char hex
    # (256-bit) dapat bernilai maks 256, sehingga gabungan dua hash maks 512.
    assert 0 <= score_ab <= 512, (
        f"score_ab={score_ab} di luar rentang [0, 512]"
    )

    # Komutatif: score(A, B) == score(B, A)
    assert score_ab == score_ba, (
        f"similarity_score tidak komutatif: score(A,B)={score_ab} != score(B,A)={score_ba}"
    )


# ---------------------------------------------------------------------------
# Property-based test — Property 4: Validasi Format Hash
# Feature: news-finder-from-image, Property 4
# Validates: Requirements 3.7, 3.8
# ---------------------------------------------------------------------------

@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(params=st.fixed_dictionaries({
    "width": st.integers(min_value=8, max_value=64),
    "height": st.integers(min_value=8, max_value=64),
    "r": st.integers(min_value=0, max_value=255),
    "g": st.integers(min_value=0, max_value=255),
    "b": st.integers(min_value=0, max_value=255),
    "fmt": st.sampled_from(["JPEG", "PNG"]),
}))
def test_compute_hashes_format_property(tmp_path, params):
    """
    **Validates: Requirements 3.7, 3.8**

    Property 4: Validasi Format Hash

    Untuk sembarang file gambar valid (JPEG/PNG), `compute_hashes()` harus
    menghasilkan tuple (phash_hex, dhash_hex) di mana keduanya adalah string
    hexadecimal lowercase dengan panjang tepat 64 karakter.

    # Feature: news-finder-from-image, Property 4
    """
    import tempfile as _tempfile

    # Buat gambar valid dengan parameter yang di-generate
    image_bytes = _make_image_bytes(
        width=params["width"],
        height=params["height"],
        r=params["r"],
        g=params["g"],
        b=params["b"],
        fmt=params["fmt"],
    )

    ext = params["fmt"].lower()
    with _tempfile.NamedTemporaryFile(
        suffix=f".{ext}", dir=str(tmp_path), delete=False
    ) as f:
        f.write(image_bytes)
        path = f.name

    try:
        phash, dhash = matcher.compute_hashes(path)

        # Panjang harus tepat 64 karakter
        assert len(phash) == 64, (
            f"phash panjangnya {len(phash)}, diharapkan 64. "
            f"Gambar: {params['width']}x{params['height']} {params['fmt']}"
        )
        assert len(dhash) == 64, (
            f"dhash panjangnya {len(dhash)}, diharapkan 64. "
            f"Gambar: {params['width']}x{params['height']} {params['fmt']}"
        )

        # Harus terdiri dari karakter hex lowercase saja
        assert all(c in _HEX_CHARS for c in phash), (
            f"phash mengandung karakter non-hex: {phash!r}"
        )
        assert all(c in _HEX_CHARS for c in dhash), (
            f"dhash mengandung karakter non-hex: {dhash!r}"
        )

        # Tipe harus string
        assert isinstance(phash, str)
        assert isinstance(dhash, str)
    finally:
        if os.path.exists(path):
            os.unlink(path)
