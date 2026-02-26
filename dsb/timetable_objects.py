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

        self.days = self._parse_links(self._links)

    def _parse_links(self, links: List[str]) -> List[Day]:
        """Parse all plan links and group entries by date."""
        plans = defaultdict(list)

        for link in links:
            try:
                entries = self._extract_entries(link)
                if entries:
                    plans[entries[0].date].extend(entries)
            except Exception as e:
                _LOGGER.error("Error parsing link %s: %s", link, e)

        days = []
        for day in sorted(plans.keys()):
            days.append(Day(day, plans[day]))

        return days

    def _extract_entries(self, link: str) -> List[Entry]:
        """Extract entries from a plan HTML page."""
        try:
            request = Request(link, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(
                urlopen(request, timeout=30),
                features="html.parser",
            )
        except Exception as e:
            _LOGGER.error("Failed to fetch %s: %s", link, e)
            return []

        # Find the main table
        tables = soup.find_all(class_="mon_list")
        if not tables:
            _LOGGER.warning("No mon_list table found in %s", link)
            return []

        table = tables[0]

        # Parse date from page title
        date = self._parse_date(soup)

        # Extract column headers from first "list" row (contains th or td headers)
        headers = self._extract_headers(table)

        # Extract data rows (skip header row and class separator rows)
        data_rows = self._extract_data_rows(table)

        # Parse each data row
        entries: List[Entry] = []
        for row in data_rows:
            entry_data = self._parse_row(row, headers)
            if entry_data and self._is_valid_entry(entry_data):
                entries.append(Entry(entry_data, date, self.plan_mapping))

        return entries

    def _parse_date(self, soup: BeautifulSoup) -> datetime:
        """Parse date from the page title."""
        try:
            mon_title = soup.find("div", {"class": "mon_title"})
            if mon_title:
                text = mon_title.get_text(strip=True)
                match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
                if match:
                    day, month, year = match.groups()
                    return datetime(int(year), int(month), int(day))
        except Exception as e:
            _LOGGER.debug("Could not parse date: %s", e)

        return datetime(1900, 1, 1)

    def _extract_headers(self, table) -> List[str]:
        """Extract column headers from the table."""
        # Method 1: Look for th elements
        for row in table.find_all("tr"):
            th_cells = row.find_all("th")
            if th_cells:
                headers = [th.get_text(strip=True) for th in th_cells]
                if len(headers) > 1:
                    return headers

        # Method 2: First "list" row might be the header
        rows = table.find_all("tr", {"class": "list"})
        if rows:
            first_row = rows[0]
            children = first_row.findChildren(recursive=False)
            if children:
                potential_headers = [
                    child.get_text(strip=True) for child in children
                ]
                # Check if these look like headers (contain known header names)
                known = {"Klasse(n)", "Stunde", "Vertreter", "Fach", "Raum"}
                if any(h in known for h in potential_headers):
                    return potential_headers

        # Fallback
        return self.DEFAULT_HEADERS.copy()

    def _extract_data_rows(self, table) -> list:
        """Extract data rows, skipping headers and class separators."""
        all_rows = table.find_all("tr", {"class": "list"})

        if not all_rows:
            return []

        data_rows = []
        first_row = True

        for row in all_rows:
            # Get direct children (td or th)
            cells = row.findChildren(recursive=False)

            if first_row:
                # Check if first row is a header row
                first_row = False
                if cells:
                    text_vals = [c.get_text(strip=True) for c in cells]
                    known = {"Klasse(n)", "Stunde", "Vertreter", "Fach"}
                    if any(t in known for t in text_vals):
                        # This is the header row, skip it
                        continue

            # Skip class separator rows (only 1 cell, usually with colspan)
            if len(cells) <= 1:
                continue

            # Skip rows where first cell has colspan (class group headers)
            first_cell = cells[0] if cells else None
            if first_cell and first_cell.get("colspan"):
                try:
                    if int(first_cell.get("colspan", 1)) > 1:
                        continue
                except (ValueError, TypeError):
                    pass

            data_rows.append(row)

        return data_rows

    def _parse_row(self, row, headers: List[str]) -> Optional[Dict[str, Any]]:
        """Parse a single table row into a dictionary."""
        cells = row.findChildren(recursive=False)

        if len(cells) < 2:
            return None

        entry_data: Dict[str, Any] = {}

        for i, header in enumerate(headers):
            if i < len(cells):
                text = cells[i].get_text(strip=True)
                entry_data[header] = text if text and text != "\xa0" else None
            else:
                entry_data[header] = None

        return entry_data

    def _is_valid_entry(self, entry_data: Dict[str, Any]) -> bool:
        """Check if entry has meaningful data (not just a class header)."""
        non_none = sum(1 for v in entry_data.values() if v is not None)
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
            picture = Picture(child._detail, child._title, child._preview)
            self.pictures.append(picture)