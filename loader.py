from dataclasses import dataclass, field
from functools import cache
import logging

import pdfplumber

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class Page:
    text: str
    page_number: int

@dataclass(frozen=True)
class Book:
    filename: str
    pages: dict[int, Page] = field(default_factory=dict)
    
    def get_page(self, page_num: int) -> Page | None:
        """Quickly look up a page by its number."""
        return self.pages.get(page_num)

    @property
    def last_page_num(self) -> int:
        """Compute the last page number based on the pages available."""
        if not self.pages:
            return 0
        return max(self.pages.keys())

@cache
def load_book(file_path: str) -> Book:
    logger.info(f"Loading and caching book: {file_path}")
    
    pages_map = {}
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_map[page.page_number] = Page(text=text, page_number=page.page_number)
                
    return Book(filename=file_path, pages=pages_map)