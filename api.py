from __future__ import annotations

import os
import tempfile
from collections import defaultdict

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from loader import load_book
from parser import parse_book, parse_page

app = FastAPI(title="sidreader", description="Doc parser API")


def _serialize(chunks) -> list[dict]:
    return [{"page_number": c.page_number, "text": c.text} for c in chunks]


def _group_by_page(chunks) -> list[dict]:
    grouped: dict[int | None, list[str]] = defaultdict(list)
    order: list[int | None] = []
    for c in chunks:
        if c.page_number not in grouped:
            order.append(c.page_number)
        grouped[c.page_number].append(c.text)
    return [{"page_number": p, "chunks": grouped[p]} for p in order]


def _paginate(items: list, offset: int, limit: int) -> tuple[list, dict]:
    total = len(items)
    sliced = items[offset : offset + limit]
    return sliced, {
        "total": total,
        "offset": offset,
        "limit": limit,
        "returned": len(sliced),
        "has_more": offset + len(sliced) < total,
    }


@app.post("/parse")
async def parse(
    file: UploadFile = File(...),
    start_page: int = Query(1, ge=1),
    end_page: int | None = Query(None, ge=1),
    max_chars: int = Query(1000, gt=0),
    group_by_page: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, gt=0, le=500),
):
    suffix = os.path.splitext(file.filename or "")[1] or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        book = load_book(tmp_path)
        if book.last_page_num == 0:
            raise HTTPException(status_code=422, detail="No extractable text in document")
        chunks, _ = parse_book(
            book, start_page=start_page, end_page=end_page, max_chars=max_chars
        )
    finally:
        os.unlink(tmp_path)

    return _build_response(chunks, group_by_page, offset, limit)


@app.get("/parse")
def parse_path(
    file_path: str = Query(...),
    start_page: int = Query(1, ge=1),
    end_page: int | None = Query(None, ge=1),
    max_chars: int = Query(1000, gt=0),
    group_by_page: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, gt=0, le=500),
):
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    book = load_book(file_path)
    if book.last_page_num == 0:
        raise HTTPException(status_code=422, detail="No extractable text in document")

    chunks, _ = parse_book(
        book, start_page=start_page, end_page=end_page, max_chars=max_chars
    )
    return _build_response(chunks, group_by_page, offset, limit)


@app.get("/parse/page/{page_num}")
def parse_single_page(
    page_num: int,
    file_path: str = Query(...),
    max_chars: int = Query(1000, gt=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, gt=0, le=500),
):
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    book = load_book(file_path)
    if not book.get_page(page_num):
        raise HTTPException(status_code=404, detail=f"Page {page_num} not found")

    chunks, _ = parse_page(book, page_num, max_chars=max_chars)
    sliced, pagination = _paginate(_serialize(chunks), offset, limit)
    return {"page_number": page_num, "pagination": pagination, "chunks": sliced}


def _build_response(chunks, group_by_page: bool, offset: int, limit: int) -> dict:
    if group_by_page:
        items = _group_by_page(chunks)
        sliced, pagination = _paginate(items, offset, limit)
        return {"pagination": pagination, "pages": sliced}
    items = _serialize(chunks)
    sliced, pagination = _paginate(items, offset, limit)
    return {"pagination": pagination, "chunks": sliced}
