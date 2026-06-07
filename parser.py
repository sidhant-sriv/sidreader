from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeAlias

import spacy

from loader import load_book, Page, Book

ChunkList: TypeAlias = list[Page]
ChunkCount: TypeAlias = int
ParsingResult: TypeAlias = tuple[ChunkList, ChunkCount]

_SHORT_LINE_RATIO = 0.55
_MODEL = "en_core_web_sm"


@lru_cache(maxsize=1)
def _get_nlp() -> "spacy.language.Language":
    try:
        nlp = spacy.load(_MODEL, disable=["ner", "lemmatizer", "tagger", "attribute_ruler"])
        if "senter" not in nlp.pipe_names and "parser" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")
    except OSError:
        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")
    nlp.max_length = 2_000_000
    return nlp


def normalize(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"\n[ \t]*\n+", "\u0000", text)
    text = text.replace("\n", " ")
    text = text.replace("\u0000", "\n\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n\n *", "\n\n", text)
    return text.strip()


def detect_paragraphs(text: str) -> list[str]:
    normalized = normalize(text)
    if not normalized:
        return []
    blocks = [b.strip() for b in normalized.split("\n\n") if b.strip()]
    if len(blocks) > 1:
        return blocks
    return _recover_paragraphs_from_lines(text)


def _recover_paragraphs_from_lines(raw_text: str) -> list[str]:
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    if not lines:
        return []

    median = sorted(len(ln) for ln in lines)[len(lines) // 2]
    threshold = max(1, int(median * _SHORT_LINE_RATIO))

    paragraphs: list[str] = []
    current: list[str] = []

    for i, line in enumerate(lines):
        current.append(line)
        is_last = i == len(lines) - 1
        ends_sentence = line.rstrip().endswith((".", "!", "?", '"', "”"))
        is_short = len(line) <= threshold
        next_is_cap = (not is_last) and lines[i + 1][:1].isupper()

        if (is_short and ends_sentence and next_is_cap) or is_last:
            joined = re.sub(r"(\w)-\s(\w)", r"\1\2", " ".join(current))
            paragraphs.append(re.sub(r"\s+", " ", joined).strip())
            current = []

    if current:
        paragraphs.append(re.sub(r"\s+", " ", " ".join(current)).strip())

    return [p for p in paragraphs if p]


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    doc = _get_nlp()(text)
    return [s.text.strip() for s in doc.sents if s.text.strip()]


@dataclass
class _Para:
    text: str
    page_number: int


def _pack(paragraphs: list[_Para], max_chars: int) -> ChunkList:
    chunks: ChunkList = []
    cur: list[str] = []
    cur_len = 0
    cur_page: int | None = None

    def flush() -> None:
        nonlocal cur, cur_len, cur_page
        if cur:
            chunks.append(Page(text="\n\n".join(cur), page_number=cur_page))
            cur, cur_len, cur_page = [], 0, None

    for para in paragraphs:
        if len(para.text) > max_chars:
            flush()
            sent_buf: list[str] = []
            sent_len = 0
            for sentence in split_sentences(para.text):
                add = len(sentence) + (1 if sent_buf else 0)
                if sent_buf and sent_len + add > max_chars:
                    chunks.append(Page(text=" ".join(sent_buf), page_number=para.page_number))
                    sent_buf, sent_len = [], 0
                sent_buf.append(sentence)
                sent_len += add
            if sent_buf:
                chunks.append(Page(text=" ".join(sent_buf), page_number=para.page_number))
            continue

        add = len(para.text) + (2 if cur else 0)
        if cur and cur_len + add > max_chars:
            flush()
        if cur_page is None:
            cur_page = para.page_number
        cur.append(para.text)
        cur_len += add

    flush()
    return chunks


def parse_page(book: Book, page_num: int, max_chars: int = 1000) -> ParsingResult:
    page = book.get_page(page_num)
    if not page:
        return [], 0
    paras = [_Para(text=p, page_number=page_num) for p in detect_paragraphs(page.text)]
    chunks = _pack(paras, max_chars)
    return chunks, len(chunks)


def parse_book(
    book: Book,
    start_page: int = 1,
    end_page: int | None = None,
    max_chars: int = 1000,
) -> ParsingResult:
    if end_page is None:
        end_page = book.last_page_num

    paras: list[_Para] = []
    for page_num in range(start_page, end_page + 1):
        page = book.get_page(page_num)
        if not page:
            continue
        page_paras = detect_paragraphs(page.text)
        if not page_paras:
            continue

        if paras and page_paras:
            prev = paras[-1].text.rstrip()
            nxt = page_paras[0].lstrip()
            prev_open = not prev.endswith((".", "!", "?", '"', "”", ":"))
            nxt_cont = bool(nxt) and not nxt[:1].isupper()
            if prev_open and nxt_cont:
                paras[-1].text = f"{prev} {nxt}".strip()
                page_paras = page_paras[1:]

        paras.extend(_Para(text=p, page_number=page_num) for p in page_paras)

    chunks = _pack(paras, max_chars)
    return chunks, len(chunks)