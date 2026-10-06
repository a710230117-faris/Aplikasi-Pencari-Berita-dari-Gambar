"""Generate perceptual hashes for rendered PDF pages."""

from __future__ import annotations

import logging
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image

import matcher

MAX_PDF_PAGES = 100
PDF_INDEX_VERSION = 1
MAX_EMBEDDED_IMAGE_PIXELS = 20_000_000
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfPageIndex:
    page_number: int
    phash: str
    dhash: str
    embedded_images: tuple[tuple[int, str, str], ...]


def index_pdf_pages(pdf_source: bytes | Path) -> list[PdfPageIndex]:
    """Hash rendered pages and embedded images on the first 100 PDF pages.

    The returned page numbers are 1-based. PDF parsing and image-decoding
    errors are raised to the caller for explicit handling.
    """
    if isinstance(pdf_source, bytes):
        document = pymupdf.open(stream=pdf_source, filetype="pdf")
    else:
        document = pymupdf.open(pdf_source)

    try:
        if document.is_encrypted:
            raise ValueError("PDF terenkripsi tidak dapat diindeks.")
        if document.page_count == 0:
            raise ValueError("PDF tidak memiliki halaman.")

        indexed_pages = []
        seen_image_xrefs: set[int] = set()
        for page_index in range(min(document.page_count, MAX_PDF_PAGES)):
            page = document.load_page(page_index)
            page_rect = page.rect
            longest_edge = max(page_rect.width, page_rect.height)
            if longest_edge <= 0:
                raise ValueError(f"Ukuran halaman PDF ke-{page_index + 1} tidak valid.")
            scale = min(1.5, 1600 / longest_edge)
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale),
                alpha=False,
            )
            with Image.open(BytesIO(pixmap.tobytes("png"))) as page_image:
                phash, dhash = matcher.compute_hashes_from_image(page_image)

            embedded_images = []
            for image_info in page.get_images(full=True):
                xref = image_info[0]
                if xref <= 0 or xref in seen_image_xrefs:
                    continue
                seen_image_xrefs.add(xref)

                try:
                    image_bytes = document.extract_image(xref)["image"]
                    with Image.open(BytesIO(image_bytes)) as source_image:
                        if source_image.width * source_image.height > MAX_EMBEDDED_IMAGE_PIXELS:
                            logger.warning(
                                "Gambar PDF xref=%s halaman=%s dilewati karena dimensi terlalu besar.",
                                xref,
                                page_index + 1,
                            )
                            continue
                        source_image.thumbnail((1024, 1024))
                        image = source_image.convert("RGB")
                        try:
                            image_phash, image_dhash = matcher.compute_hashes_from_image(image)
                        finally:
                            image.close()
                    embedded_images.append((xref, image_phash, image_dhash))
                except Exception:
                    logger.exception(
                        "Gagal mengindeks gambar tersemat xref=%s halaman=%s.",
                        xref,
                        page_index + 1,
                    )

            indexed_pages.append(
                PdfPageIndex(
                    page_number=page_index + 1,
                    phash=phash,
                    dhash=dhash,
                    embedded_images=tuple(embedded_images),
                )
            )

        return indexed_pages
    finally:
        document.close()
