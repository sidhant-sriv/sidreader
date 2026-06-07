from __future__ import annotations

import hashlib
import os
import tempfile
from collections import defaultdict
from contextlib import asynccontextmanager, closing
from enum import Enum

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

import db
from loader import load_book
from parser import parse_book, parse_book_cards, parse_page, parse_page_cards


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="sidreader", description="Doc parser API", lifespan=lifespan)


class Mode(str, Enum):
    cards = "cards"
    packed = "packed"


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


def _parse_book_for_mode(book, mode: Mode, start_page: int, end_page: int | None, max_chars: int):
    if mode == Mode.cards:
        return parse_book_cards(book, start_page=start_page, end_page=end_page, max_chars=max_chars)
    return parse_book(book, start_page=start_page, end_page=end_page, max_chars=max_chars)


def _parse_page_for_mode(book, mode: Mode, page_num: int, max_chars: int):
    if mode == Mode.cards:
        return parse_page_cards(book, page_num, max_chars=max_chars)
    return parse_page(book, page_num, max_chars=max_chars)


def _build_response(chunks, group_by_page: bool, offset: int, limit: int) -> dict:
    if group_by_page:
        items = _group_by_page(chunks)
        sliced, pagination = _paginate(items, offset, limit)
        return {"pagination": pagination, "pages": sliced}
    items = _serialize(chunks)
    sliced, pagination = _paginate(items, offset, limit)
    return {"pagination": pagination, "chunks": sliced}


@app.post("/parse")
async def parse(
    file: UploadFile = File(...),
    mode: Mode = Query(Mode.cards),
    start_page: int = Query(1, ge=1),
    end_page: int | None = Query(None, ge=1),
    max_chars: int = Query(1500, gt=0),
    group_by_page: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, gt=0, le=5000),
):
    suffix = os.path.splitext(file.filename or "")[1] or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        book = load_book(tmp_path)
        if book.last_page_num == 0:
            raise HTTPException(status_code=422, detail="No extractable text in document")
        chunks, _ = _parse_book_for_mode(book, mode, start_page, end_page, max_chars)
    finally:
        os.unlink(tmp_path)

    return _build_response(chunks, group_by_page, offset, limit)


@app.get("/parse")
def parse_path(
    file_path: str = Query(...),
    mode: Mode = Query(Mode.cards),
    start_page: int = Query(1, ge=1),
    end_page: int | None = Query(None, ge=1),
    max_chars: int = Query(1500, gt=0),
    group_by_page: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, gt=0, le=5000),
):
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    book = load_book(file_path)
    if book.last_page_num == 0:
        raise HTTPException(status_code=422, detail="No extractable text in document")

    chunks, _ = _parse_book_for_mode(book, mode, start_page, end_page, max_chars)
    return _build_response(chunks, group_by_page, offset, limit)


@app.get("/parse/page/{page_num}")
def parse_single_page(
    page_num: int,
    file_path: str = Query(...),
    mode: Mode = Query(Mode.cards),
    max_chars: int = Query(1500, gt=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, gt=0, le=5000),
):
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    book = load_book(file_path)
    if not book.get_page(page_num):
        raise HTTPException(status_code=404, detail=f"Page {page_num} not found")

    chunks, _ = _parse_page_for_mode(book, mode, page_num, max_chars)
    sliced, pagination = _paginate(_serialize(chunks), offset, limit)
    return {"page_number": page_num, "pagination": pagination, "chunks": sliced}


@app.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")

    doc_id = hashlib.sha256(data).hexdigest()[:16]
    path = os.path.join(db.UPLOAD_DIR, f"{doc_id}.pdf")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)

    book = load_book(path)
    if book.last_page_num == 0:
        os.unlink(path)
        raise HTTPException(status_code=422, detail="No extractable text in document")

    with closing(db.get_conn()) as conn:
        row = db.upsert_document(
            conn,
            doc_id=doc_id,
            filename=file.filename or f"{doc_id}.pdf",
            path=path,
            page_count=book.last_page_num,
        )
    return row


@app.get("/documents")
def list_documents():
    with closing(db.get_conn()) as conn:
        return db.list_documents(conn)


@app.get("/documents/current")
def current_document():
    with closing(db.get_conn()) as conn:
        row = db.get_current_document(conn)
    if not row:
        raise HTTPException(status_code=404, detail="No documents uploaded yet")
    return row


@app.get("/documents/{doc_id}")
def get_document(doc_id: str):
    with closing(db.get_conn()) as conn:
        row = db.get_document(conn, doc_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return row


@app.get("/documents/{doc_id}/file")
def get_document_file(doc_id: str):
    with closing(db.get_conn()) as conn:
        row = db.get_document(conn, doc_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    if not os.path.isfile(row["path"]):
        raise HTTPException(status_code=410, detail="Document file is missing on disk")
    return FileResponse(
        row["path"],
        media_type="application/pdf",
        filename=row["filename"],
        content_disposition_type="inline",
    )


@app.patch("/documents/{doc_id}/position")
def update_position(doc_id: str, card_index: int = Body(..., embed=True, ge=0)):
    with closing(db.get_conn()) as conn:
        row = db.set_position(conn, doc_id, card_index)
    if not row:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return row


@app.get("/documents/{doc_id}/cards")
def document_cards(
    doc_id: str,
    start_page: int = Query(1, ge=1),
    end_page: int | None = Query(None, ge=1),
    max_chars: int = Query(1500, gt=0),
    group_by_page: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, gt=0, le=5000),
):
    with closing(db.get_conn()) as conn:
        row = db.touch_document(conn, doc_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    if not os.path.isfile(row["path"]):
        raise HTTPException(status_code=410, detail="Document file is missing on disk")

    book = load_book(row["path"])
    chunks, _ = parse_book_cards(
        book, start_page=start_page, end_page=end_page, max_chars=max_chars
    )
    return {"document": row, **_build_response(chunks, group_by_page, offset, limit)}


@app.get("/documents/{doc_id}/pages/{page_num}/cards")
def document_page_cards(
    doc_id: str,
    page_num: int,
    max_chars: int = Query(1500, gt=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, gt=0, le=5000),
):
    with closing(db.get_conn()) as conn:
        row = db.touch_document(conn, doc_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    if not os.path.isfile(row["path"]):
        raise HTTPException(status_code=410, detail="Document file is missing on disk")

    book = load_book(row["path"])
    if not book.get_page(page_num):
        raise HTTPException(status_code=404, detail=f"Page {page_num} not found")

    chunks, _ = parse_page_cards(book, page_num, max_chars=max_chars)
    sliced, pagination = _paginate(_serialize(chunks), offset, limit)
    return {
        "document": row,
        "page_number": page_num,
        "pagination": pagination,
        "chunks": sliced,
    }
