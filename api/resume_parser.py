"""Bounded résumé text extraction. Never evaluates macros or follows document links."""
import io
import re
import zipfile
from xml.etree import ElementTree

MAX_BYTES = 512 * 1024
MAX_TEXT = 20000


class ResumeParseError(ValueError):
    """Safe, user-facing parser validation message."""


def extract(kind, data):
    if not data or len(data) > MAX_BYTES:
        raise ResumeParseError("Choose a nonempty file no larger than 512 KB.")
    if kind == "txt":
        text = data.decode("utf-8-sig")
        if "\x00" in text:
            raise ResumeParseError("Choose a UTF-8 text file.")
    elif kind == "docx":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 200 or sum(x.file_size for x in entries) > 8 * 1024 * 1024:
                raise ResumeParseError("This document is too complex. Export a text résumé instead.")
            info = archive.getinfo("word/document.xml")
            if info.file_size > 2 * 1024 * 1024 or info.flag_bits & 1:
                raise ResumeParseError("Choose an unencrypted, simpler DOCX file.")
            xml = archive.read(info)
            if b"\x00" in xml or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                raise ResumeParseError("This document format is unsupported.")
            root = ElementTree.fromstring(xml)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            text = "\n".join("".join(p.itertext()) for p in root.iter(ns + "p"))
    elif kind == "pdf":
        if not data.startswith(b"%PDF-"):
            raise ResumeParseError("This file is not a readable PDF.")
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ResumeParseError("Remove the PDF password before importing it.")
        if len(reader.pages) > 10:
            raise ResumeParseError("Choose a résumé of at most 10 pages.")
        parts = []
        for page in reader.pages:
            content = page.get_contents()
            if content is not None and len(content.get_data()) > 4 * 1024 * 1024:
                raise ResumeParseError("This PDF is too complex. Export a text résumé instead.")
            # Document exports may position each word in a separate graphics state.
            # Layout extraction reconstructs visual rows instead of treating those
            # state changes as semantic paragraph breaks.
            page_text = page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False,
                                          layout_mode_strip_rotated=False) or ""
            if not page_text.strip():
                page_text = page.extract_text() or ""
            parts.append("\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in page_text.splitlines()))
        text = "\n".join(parts)
    else:
        raise ResumeParseError("Choose a PDF, DOCX, or UTF-8 TXT file. Older DOC files are unsupported.")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ResumeParseError("No readable text was found. Scanned PDFs need a text-based export.")
    if len(text) > MAX_TEXT:
        raise ResumeParseError("This résumé has too much text. Choose a shorter version.")
    return text


def suggestions(text):
    result = {"skills": [], "coursework": [], "experience": []}
    headings = {"skills": "skills", "technical skills": "skills", "coursework": "coursework",
                "relevant coursework": "coursework", "experience": "experience",
                "work experience": "experience", "research experience": "experience", "projects": "experience"}
    section = None
    for line in text.splitlines():
        is_bullet = bool(re.match(r"^\s*[•*-]\s+", line))
        line = line.strip().lstrip("•- ").strip()
        title = line.rstrip(":").casefold()
        if title in headings:
            section = headings[title]
            continue
        if title in {"education", "contact", "summary", "interests", "references", "awards"}:
            section = None
            continue
        if not section or not line or "@" in line or "http" in line.casefold():
            continue
        if (section == "experience" and not is_bullet and result[section]
                and (line[0].islower() or result[section][-1].split()[-1].casefold()
                     in {"using", "with", "in", "of", "for", "to", "and", "a", "an", "the", "across"})
                and not result[section][-1].endswith((".", "!", "?", ":"))
                and len(result[section][-1]) + len(line) + 1 <= 250):
            result[section][-1] += " " + line
            continue
        values = re.split(r"[,;|]", line) if section != "experience" else [line]
        for value in values:
            value = value.strip()[:250]
            if value and value not in result[section] and len(result[section]) < 30:
                result[section].append(value)
    return result
