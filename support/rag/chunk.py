"""Lesson 10: documents -> chunks with metadata.

    from support.rag.chunk import load_chunks
    chunks = load_chunks()            # data/kb/*.md, 800 characters per chunk at most
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from support.config import DATA_DIR

KB_DIR = DATA_DIR / "kb"
DEFAULT_MAX_CHARS = 800


@dataclass(frozen=True)
class Chunk:
    id: str        # "povernennya.md#0": file name + number; changes when you re-chunk
    source: str    # file name: what you show the user and what the metadata filter uses
    title: str     # the document title (first line); goes into the text we embed
    text: str

    @property
    def passage(self) -> str:
        """What we embed and search by keyword: the title travels with the text."""
        return f"{self.title}. {self.text}"


def split_doc(text: str, source: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    """By paragraph, with the last sentence of the previous chunk repeated at the start of the next one.

    Expects the first line to be the title (`# Назва`) and paragraphs separated by an empty line."""
    lines = text.strip().split("\n")
    title = lines[0].lstrip("# ").strip()
    paras = [p.strip() for p in "\n".join(lines[1:]).split("\n\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) > max_chars:
            chunks.append(cur)
            cur = re.split(r"(?<=[.!?])\s+", cur)[-1]    # overlap: the last sentence
        cur = (cur + "\n" + p).strip()
    if cur:
        chunks.append(cur)
    return [Chunk(f"{source}#{i}", source, title, c) for i, c in enumerate(chunks)]


def load_chunks(kb_dir: Path | None = None, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    """Every data/kb/*.md (the folder `archive/` is not read: old policy versions stay out of the search)."""
    chunks: list[Chunk] = []
    for path in sorted((kb_dir or KB_DIR).glob("*.md")):
        chunks += split_doc(path.read_text(encoding="utf-8"), path.name, max_chars)
    return chunks
