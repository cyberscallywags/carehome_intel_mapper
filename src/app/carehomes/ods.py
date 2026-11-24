"""Read the rows of an OpenDocument spreadsheet (.ods) one at a time, with the standard library
only. CQC's care directory is about 25 MB zipped and several hundred MB of XML, so the sheet is
streamed and never held in memory.

Numbers and dates come from the cell's stored value (`office:value`, `office:date-value`), not
the text shown in the cell, so a latitude keeps every decimal place whatever the cell's format.
"""

import zipfile
from collections.abc import Iterator
from pathlib import Path
from xml.etree.ElementTree import Element, iterparse  # noqa: S405 - see read_sheets

TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"

_TABLE = f"{{{TABLE}}}table"
_ROW = f"{{{TABLE}}}table-row"
_CELLS = (f"{{{TABLE}}}table-cell", f"{{{TABLE}}}covered-table-cell")
_PARAGRAPH = f"{{{TEXT}}}p"
_SPACES = f"{{{TEXT}}}s"
_TAB = f"{{{TEXT}}}tab"
_BREAK = f"{{{TEXT}}}line-break"

# A sheet's last cell and row usually repeat to the edge of the grid; no real row is this wide.
MAX_REPEAT = 2000


def _text(node: Element) -> str:
    """The text of a paragraph, with the spaces and tabs ODF stores as elements."""
    parts = [node.text or ""]
    for child in node:
        if child.tag == _SPACES:
            parts.append(" " * int(child.get(f"{{{TEXT}}}c", "1")))
        elif child.tag == _TAB:
            parts.append("\t")
        elif child.tag == _BREAK:
            parts.append("\n")
        else:
            parts.append(_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _value(cell: Element) -> str:
    kind = cell.get(f"{{{OFFICE}}}value-type")
    if kind in {"float", "currency", "percentage"}:
        return cell.get(f"{{{OFFICE}}}value", "")
    if kind == "date":
        return cell.get(f"{{{OFFICE}}}date-value", "")
    return "\n".join(_text(p) for p in cell.iter(_PARAGRAPH)).strip()


def _row(row: Element) -> list[str]:
    values: list[str] = []
    for cell in row:
        if cell.tag not in _CELLS:
            continue
        value = _value(cell)
        repeat = int(cell.get(f"{{{TABLE}}}number-columns-repeated", "1"))
        if not value and repeat > MAX_REPEAT:
            break  # padding to the edge of the grid
        values.extend([value] * min(repeat, MAX_REPEAT))
    while values and not values[-1]:
        values.pop()
    return values


def read_sheets(path: Path) -> Iterator[tuple[str, list[str]]]:
    """Yield `(sheet name, row)` for every row that has a value, in file order. Each row is a
    list of strings, with trailing empty cells dropped.

    The file is one the operator chose to ingest (CQC's own download); the standard library's
    parser is not hardened against hostile XML, so do not point this at untrusted uploads."""
    with zipfile.ZipFile(path) as archive, archive.open("content.xml") as content:
        sheet = ""
        parents: list[Element] = []
        for event, node in iterparse(content, events=("start", "end")):  # noqa: S314
            if event == "start":
                if node.tag == _TABLE:
                    sheet = node.get(f"{{{TABLE}}}name", "")
                parents.append(node)
                continue
            parents.pop()
            if node.tag != _ROW:
                continue
            if values := _row(node):
                yield sheet, values
            node.clear()
            if parents:
                parents[-1].remove(node)  # keep the tree from growing with the sheet
