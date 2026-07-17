"""Safe Crossref metadata search used by the optional research Agent."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class CrossrefResearchProvider:
    """Search DOI-backed scholarly metadata without executing remote content."""

    endpoint = "https://api.crossref.org/works"

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._opener = opener or urlopen

    @staticmethod
    def _text(value: object, limit: int = 1200) -> str:
        """Normalize optional Crossref HTML/text fields to bounded plain text."""

        if isinstance(value, list):
            value = " ".join(str(item) for item in value)
        text = re.sub(r"<[^>]+>", " ", str(value or ""))
        text = re.sub(r"\s+", " ", unescape(text)).strip()
        return text[:limit]

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return bounded, normalized metadata for one bibliographic query."""

        query = query.strip()
        if not query:
            raise ValueError("research query cannot be empty")
        if not 1 <= limit <= 10:
            raise ValueError("research limit must be between 1 and 10")
        params = urlencode(
            {
                "query.bibliographic": query,
                "rows": limit,
                "select": (
                    "DOI,title,abstract,URL,published,author,container-title,"
                    "license,is-referenced-by-count,type"
                ),
            }
        )
        request = Request(
            f"{self.endpoint}?{params}",
            headers={
                "Accept": "application/json",
                "User-Agent": "InventoryCapabilityFactory/0.1 (academic metadata research)",
            },
        )
        with self._opener(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        items = payload.get("message", {}).get("items", [])
        records = []
        for item in items[:limit]:
            doi = self._text(item.get("DOI"), 200)
            title = self._text(item.get("title"), 500)
            if not title:
                continue
            authors = []
            for author in item.get("author", [])[:8]:
                name = " ".join(
                    part
                    for part in [author.get("given", ""), author.get("family", "")]
                    if part
                ).strip()
                if name:
                    authors.append(name)
            date_parts = item.get("published", {}).get("date-parts", [[]])
            year = date_parts[0][0] if date_parts and date_parts[0] else None
            records.append(
                {
                    "title": title,
                    "doi": doi,
                    "url": self._text(item.get("URL"), 500)
                    or (f"https://doi.org/{doi}" if doi else ""),
                    "abstract_excerpt": self._text(item.get("abstract")),
                    "authors": authors,
                    "year": year,
                    "venue": self._text(item.get("container-title"), 300),
                    "work_type": self._text(item.get("type"), 100),
                    "citation_count": int(item.get("is-referenced-by-count", 0) or 0),
                    "license_url": self._text(
                        (item.get("license") or [{}])[0].get("URL", ""), 500
                    ),
                    "provider": "crossref",
                }
            )
        return records
