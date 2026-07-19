import os
from datetime import datetime
from pathlib import Path
from typing import List
from pydantic import BaseModel
import docx
import docx.text.paragraph
import docx.table


class DocumentInput(BaseModel):
    file_path: str
    file_type: str  # "docx", "md", "txt"
    title: str  # extracted from filename or first heading
    content_markdown: str  # the document body as markdown
    section_count: int  # number of top-level sections detected
    loaded_at: datetime


class Section(BaseModel):
    heading: str
    level: int  # 1 = #, 2 = ##, etc.
    content: str  # text under this heading
    line_start: int
    line_end: int


def _table_to_markdown(table: docx.table.Table) -> str:
    rows_data = []
    for row in table.rows:
        row_cells = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
        rows_data.append(row_cells)
    if not rows_data or not rows_data[0]:
        return ""
    headers = rows_data[0]
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body_lines = ["| " + " | ".join(row) + " |" for row in rows_data[1:]]
    return "\n".join([header_line, separator_line] + body_lines)


def _load_docx_markdown(path: Path) -> tuple[str, str]:
    doc = docx.Document(str(path))
    markdown_parts = []
    detected_title = ""

    for child in doc.element.body:
        if child.tag.endswith('p'):
            p = docx.text.paragraph.Paragraph(child, doc)
            text = p.text.strip()
            if not text:
                continue
            style_name = p.style.name if p.style else ""
            
            if style_name == "Title":
                markdown_parts.append(f"# {text}")
                if not detected_title:
                    detected_title = text
            elif style_name.startswith("Heading"):
                try:
                    level = int(style_name.split()[-1])
                except (ValueError, IndexError):
                    level = 1
                prefix = "#" * level
                markdown_parts.append(f"{prefix} {text}")
            elif style_name == "List Paragraph":
                markdown_parts.append(f"- {text}")
            else:
                markdown_parts.append(text)
                
        elif child.tag.endswith('tbl'):
            tbl = docx.table.Table(child, doc)
            table_md = _table_to_markdown(tbl)
            if table_md:
                markdown_parts.append(table_md)

    content_md = "\n\n".join(markdown_parts)
    if not detected_title:
        detected_title = path.stem.replace("-", " ").replace("_", " ").title()
        
    return content_md, detected_title


def detect_sections(content_markdown: str) -> List[Section]:
    lines = content_markdown.splitlines()
    sections: List[Section] = []
    current_heading = None
    current_level = 0
    current_lines: List[str] = []
    start_line = 1

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            hash_count = len(stripped) - len(stripped.lstrip("#"))
            if hash_count > 0 and (len(stripped) == hash_count or stripped[hash_count] == " "):
                heading_text = stripped.lstrip("#").strip()
                if current_heading is not None:
                    sections.append(Section(
                        heading=current_heading,
                        level=current_level,
                        content="\n".join(current_lines).strip(),
                        line_start=start_line,
                        line_end=i - 1
                    ))
                current_heading = heading_text
                current_level = hash_count
                current_lines = []
                start_line = i
                continue
        if current_heading is not None:
            current_lines.append(line)

    if current_heading is not None:
        sections.append(Section(
            heading=current_heading,
            level=current_level,
            content="\n".join(current_lines).strip(),
            line_start=start_line,
            line_end=len(lines)
        ))

    return sections


def load_document(path: str) -> DocumentInput:
    file_path_obj = Path(path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"Document not found at {path}")

    ext = file_path_obj.suffix.lower()

    if ext == ".docx":
        file_type = "docx"
        content_markdown, title = _load_docx_markdown(file_path_obj)
    elif ext == ".md":
        file_type = "md"
        with open(file_path_obj, "r", encoding="utf-8") as f:
            content_markdown = f.read()
        title = file_path_obj.stem
        for line in content_markdown.splitlines():
            if line.strip().startswith("# "):
                title = line.strip().lstrip("#").strip()
                break
    elif ext == ".txt":
        file_type = "txt"
        with open(file_path_obj, "r", encoding="utf-8") as f:
            content_markdown = f.read()
        title = file_path_obj.stem
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

    sections = detect_sections(content_markdown)
    top_level_count = sum(1 for s in sections if s.level == 1)
    if top_level_count == 0:
        top_level_count = len(sections)

    return DocumentInput(
        file_path=str(file_path_obj),
        file_type=file_type,
        title=title,
        content_markdown=content_markdown,
        section_count=top_level_count,
        loaded_at=datetime.now()
    )
