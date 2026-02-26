"""Data models for DSB API."""
from datetime import datetime
from typing import List, Dict, Optional, Any


class Picture:
    """Represents a picture/document attachment."""

    def __init__(self, photo: str, title: str, preview_url: str):
        self.photo: str = photo
        self.title: str = title
        self.preview_url: str = (
            "https://light.dsbcontrol.de/DSBlightWebsite/Data/" + preview_url
        )


class Entry:
    """Represents a single substitution plan entry."""

    def __init__(
        self,
        raw_data: dict,
        date: datetime,
        plan_mapping: Optional[dict] = None,
    ):
        self._raw_data: dict = raw_data
        self._plan_mapping: dict = plan_mapping or {}
        self.date: datetime = date

    def __getattr__(self, item: str):
        """Allow attribute-style access to raw data fields."""
        if item.startswith("_"):
            raise AttributeError(item)

        if item in self._raw_data.keys():
            return self._raw_data[item]

        if item in self._plan_mapping.keys():
            if self._plan_mapping[item] in self._raw_data.keys():
                return self._raw_data[self._plan_mapping[item]]

        raise AttributeError(f"Entry has no attribute '{item}'")

    def to_dict(self) -> Dict[str, Any]:
        """Convert entry to dictionary."""
        result = {}
        for key, value in self._raw_data.items():
            result[key] = value
        result["_date"] = self.date.isoformat() if self.date else None
        return result

    def __repr__(self) -> str:
        return f"Entry({self._raw_data})"


class Day:
    """Represents a day with substitution entries."""

    def __init__(self, date: datetime, entries: List[Entry]):
        self.date: datetime = date
        self.entries: List[Entry] = entries

    def __repr__(self) -> str:
        return f"Day({self.date.strftime('%Y-%m-%d')}, {len(self.entries)} entries)"