"""Timetable objects for DSB API."""
import logging
import re
from datetime import datetime
from typing import List, Dict, Optional, Any
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.error import URLError

from bs4 import BeautifulSoup

from .models import Picture, Day, Entry

_LOGGER = logging.getLogger(__name__)


class TimetableObject:
    """Base class for timetable objects."""

    def __init__(self, raw_data: dict):
        self._id: str = raw_data["Id"]
        self._title: str = raw_data["Title"]
        self._detail: str = raw_data["Detail"]
        self._tags: str = raw_data["Tags"]
        self._preview: str = raw_data["Preview"]
        self._content_type = int(raw_data["ConType"])
        self._priority = int(raw_data["Prio"])
        self._index = int(raw_data["Index"])
        self._date_published = datetime.strptime(
            raw_data["Date"], "%d.%m.%Y %H:%M"
        )


class Plan(TimetableObject):
    """Represents a substitution plan."""

    DEFAULT_HEADERS = [
        "Klasse(n)", "Stunde", "Vertreter", "Fach", "Raum",
        "(Lehrer)", "(Le.) nach", "Art", "Text",
    ]

    def __init__(self, raw_data: dict, plan_mapping: dict = None):
        super().__init__(raw_data)
        self.plan_mapping = plan_mapping if plan_mapping else {}
        self._children: List[TimetableObject] = []
        self._links: List[str] = []

        for child in raw_data["Childs"]:
            self._children.append(Plan(child))
            self._links.append(child["Detail"])

        # Parse results
        self.days: List[Day] = []
        self.raw_tables: List[Dict[str, Any]] = []

        self._parse_all_links()

    def _parse_all_links(self) -> None:
        """Parse all plan links, populate days and raw_tables."""
        plans = defaultdict(list)

        for link in self._links:
            try:
                result = self._extract_from_link(link)
                if result:
                    entries, raw_table = result
                    self.raw_tables.append(raw_table)
                    if entries:
                        plans[entries[0].date].extend(entries)
            except Exception as e:
                _LOGGER.error("Error parsing link %s: %s", link, e)

        for day in sorted(plans.keys()):
            self.days.append(Day(day, plans[day]))

    def _extract_from_link(
        self, link: str
    ) -> Optional[tuple]:
        """Extract entries AND raw table data from a plan HTML page.

        Returns:
            Tuple of (parsed_entries, raw_table_dict) or None on error.
        """
        try:
            request = Request(
                link, headers={"User-Agent": "Mozilla/5.0"}
            )
            html_content = urlopen(request, timeout=30).read()
            soup = BeautifulSoup(html_content, features="html.parser")
        except Exception as e:
            _LOGGER.error("Failed to fetch %s: %s", link, e)
            return None

        # Parse date
        date = self._parse_date(soup)

        # Find the main table
        tables = soup.find_all(class_="mon_list")

        # ── Build raw table data (EVERYTHING, unfiltered) ──
        raw_table = self._extract_raw_table(
            soup, tables, link, date
        )

        if not tables:
            _LOGGER.warning(
                "No mon_list table found in %s", link
            )
            return [], raw_table

        table = tables[0]

        # ── Extract parsed entries (filtered, for student sensor) ──
        headers = self._extract_headers(table)
        data_rows = self._extract_data_rows(table)

        entries: List[Entry] = []
        for row in data_rows:
            entry_data = self._parse_row(row, headers)
            if entry_data and self._is_valid_entry(entry_data):
                entries.append(
                    Entry(entry_data, date, self.plan_mapping)
                )

        return entries, raw_table

    def _extract_raw_table(
        self,
        soup: BeautifulSoup,
        tables: list,
        link: str,
        date: datetime,
    ) -> Dict[str, Any]:
        """Extract complete raw table data – no filtering at all.

        Captures EVERYTHING: headers, separators, class groups,
        info sections, and all rows regardless of content.
        """
        raw: Dict[str, Any] = {
            "url": link,
            "date": date.isoformat() if date else None,
            "title": "",
            "info": [],
            "headers": [],
            "all_rows": [],
            "class_groups": [],
            "table_count": len(tables),
        }

        # ── Page title ──
        mon_title = soup.find("div", {"class": "mon_title"})
        if mon_title:
            raw["title"] = mon_title.get_text(strip=True)

        # ── Info section (announcements above the table) ──
        info_table = soup.find("table", {"class": "info"})
        if info_table:
            for row in info_table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                raw["info"].append(
                    [c.get_text(strip=True) for c in cells]
                )

        # ── All mon_head elements (date headers, subtitles) ──
        for head in soup.find_all(class_="mon_head"):
            text = head.get_text(strip=True)
            if text:
                raw.setdefault("mon_heads", []).append(text)

        if not tables:
            return raw

        table = tables[0]

        # ── Every single row in the table ──
        row_index = 0
        for tr in table.find_all("tr"):
            row_data: Dict[str, Any] = {
                "index": row_index,
                "cells": [],
                "css_classes": tr.get("class", []),
                "is_header": False,
                "is_class_group": False,
                "is_data": False,
            }

            children = tr.findChildren(recursive=False)

            for cell in children:
                cell_data = {
                    "text": cell.get_text(strip=True),
                    "tag": cell.name,
                    "colspan": cell.get("colspan"),
                    "css_classes": cell.get("class", []),
                    "title": cell.get("title"),
                }
                row_data["cells"].append(cell_data)

            # Classify the row
            if children:
                # Header row (th elements)
                if children[0].name == "th":
                    row_data["is_header"] = True
                    raw["headers"] = [
                        c["text"] for c in row_data["cells"]
                    ]

                # Class group separator (single cell with colspan)
                elif len(children) == 1:
                    colspan = children[0].get("colspan")
                    if colspan:
                        row_data["is_class_group"] = True
                        group_text = children[0].get_text(strip=True)
                        raw["class_groups"].append(group_text)
                    else:
                        row_data["is_data"] = True

                # Regular data row
                else:
                    first_cell = children[0]
                    try:
                        if (
                            first_cell.get("colspan")
                            and int(first_cell.get("colspan", 1)) > 1
                        ):
                            row_data["is_class_group"] = True
                            raw["class_groups"].append(
                                first_cell.get_text(strip=True)
                            )
                        else:
                            row_data["is_data"] = True
                    except (ValueError, TypeError):
                        row_data["is_data"] = True

            raw["all_rows"].append(row_data)
            row_index += 1

        raw["total_rows"] = row_index

        return raw

    def _parse_date(self, soup: BeautifulSoup) -> datetime:
        """Parse date from the page title."""
        try:
            mon_title = soup.find("div", {"class": "mon_title"})
            if mon_title:
                text = mon_title.get_text(strip=True)
                match = re.search(
                    r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text
                )
                if match:
                    day, month, year = match.groups()
                    return datetime(
                        int(year), int(month), int(day)
                    )
        except Exception as e:
            _LOGGER.debug("Could not parse date: %s", e)
        return datetime(1900, 1, 1)

    def _extract_headers(self, table) -> List[str]:
        """Extract column headers from the table."""
        for row in table.find_all("tr"):
            th_cells = row.find_all("th")
            if th_cells:
                headers = [
                    th.get_text(strip=True) for th in th_cells
                ]
                if len(headers) > 1:
                    return headers

        rows = table.find_all("tr", {"class": "list"})
        if rows:
            first_row = rows[0]
            children = first_row.findChildren(recursive=False)
            if children:
                potential_headers = [
                    child.get_text(strip=True)
                    for child in children
                ]
                known = {
                    "Klasse(n)", "Stunde", "Vertreter",
                    "Fach", "Raum",
                }
                if any(h in known for h in potential_headers):
                    return potential_headers

        return self.DEFAULT_HEADERS.copy()

    def _extract_data_rows(self, table) -> list:
        """Extract data rows, skipping headers and separators."""
        all_rows = table.find_all("tr", {"class": "list"})
        if not all_rows:
            return []

        data_rows = []
        first_row = True

        for row in all_rows:
            cells = row.findChildren(recursive=False)

            if first_row:
                first_row = False
                if cells:
                    text_vals = [
                        c.get_text(strip=True) for c in cells
                    ]
                    known = {
                        "Klasse(n)", "Stunde", "Vertreter", "Fach",
                    }
                    if any(t in known for t in text_vals):
                        continue

            if len(cells) <= 1:
                continue

            first_cell = cells[0] if cells else None
            if first_cell and first_cell.get("colspan"):
                try:
                    if int(first_cell.get("colspan", 1)) > 1:
                        continue
                except (ValueError, TypeError):
                    pass

            data_rows.append(row)

        return data_rows

    def _parse_row(
        self, row, headers: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Parse a single table row into a dictionary."""
        cells = row.findChildren(recursive=False)
        if len(cells) < 2:
            return None

        entry_data: Dict[str, Any] = {}
        for i, header in enumerate(headers):
            if i < len(cells):
                text = cells[i].get_text(strip=True)
                entry_data[header] = (
                    text if text and text != "\xa0" else None
                )
            else:
                entry_data[header] = None

        return entry_data

    def _is_valid_entry(self, entry_data: Dict[str, Any]) -> bool:
        """Check if entry has meaningful data."""
        non_none = sum(
            1 for v in entry_data.values() if v is not None
        )
        return non_none > 1


class News(TimetableObject):
    """Represents a news entry."""

    def __init__(self, raw_data: dict):
        super().__init__(raw_data)
        self.title: str = self._title
        self.content: str = self._detail
        self._children: List[TimetableObject] = []
        for child in raw_data["Childs"]:
            self._children.append(News(child))


class Posting(TimetableObject):
    """Represents a posting/document."""

    def __init__(self, raw_data: dict):
        super().__init__(raw_data)
        self.title: str = self._title
        self._children: List[TimetableObject] = []
        for child in raw_data["Childs"]:
            self._children.append(Posting(child))
        self.pictures: List[Picture] = []
        for child in self._children:
            picture = Picture(
                child._detail, child._title, child._preview
            )
            self.pictures.append(picture)