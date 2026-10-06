import pymupdf

import pdf_indexer


def test_index_pdf_pages_returns_hashes_for_rendered_pages():
    document = pymupdf.open()
    document.new_page(width=100, height=100)
    document.new_page(width=100, height=100)
    pdf_bytes = document.tobytes()
    document.close()

    pages = pdf_indexer.index_pdf_pages(pdf_bytes)

    assert [page.page_number for page in pages] == [1, 2]
    assert all(len(page.phash) == 64 and len(page.dhash) == 64 for page in pages)


def test_index_pdf_pages_caps_index_at_100_pages():
    document = pymupdf.open()
    for _ in range(101):
        document.new_page(width=32, height=32)
    pdf_bytes = document.tobytes()
    document.close()

    pages = pdf_indexer.index_pdf_pages(pdf_bytes)

    assert len(pages) == 100
    assert pages[-1].page_number == 100
