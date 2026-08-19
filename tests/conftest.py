from __future__ import annotations

import socket
from pathlib import Path

import pytest

from refcheck.models import ADSRecord, SourceEntry


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def reject_connection(*args, **kwargs):
        raise AssertionError("Tests must not open network connections")

    monkeypatch.setattr(socket, "create_connection", reject_connection)


@pytest.fixture
def fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "ads"


@pytest.fixture
def source_factory():
    def make(**updates: object) -> SourceEntry:
        values: dict[str, object] = {
            "key": "Ouyang2025",
            "raw": "Ouyang, Y., Ding, F., Yang, J., 2025, ApJL, 985, L43",
            "authors": ["Ouyang, Y.", "Ding, F.", "Yang, J."],
            "year": 2025,
            "journal": "ApJL",
            "volume": "985",
            "page": "L43",
        }
        values.update(updates)
        return SourceEntry(**values)

    return make


@pytest.fixture
def record_factory():
    def make(**updates: object) -> ADSRecord:
        values: dict[str, object] = {
            "bibcode": "2025ApJ...985L..43O",
            "title": [
                "Retention of Surface Water on Tidally Locked Rocky Planets "
                "in the Venus Zone around M Dwarfs"
            ],
            "author": ["Ouyang, Yueyun", "Ding, Feng", "Yang, Jun"],
            "first_author": "Ouyang, Yueyun",
            "year": "2025",
            "pub": "The Astrophysical Journal Letters",
            "volume": "985",
            "page": ["L43"],
            "doi": ["10.3847/2041-8213/adda4b"],
            "identifier": ["arXiv:2505.13066"],
            "pubdate": "2025-06-00",
        }
        values.update(updates)
        return ADSRecord(**values)

    return make
