"""Offline, reproducible district model generated from the committed OSM snapshot."""

from pathlib import Path
from .models import Network

VERSION = "kostanay-yubileyny-1"


def make_kostanay():
    return Network.model_validate_json(
        (Path(__file__).parent / "data" / "kostanay-yubileyny-network.json").read_text()
    )
