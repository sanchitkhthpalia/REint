import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> list[dict[str, Any]]:
    """Fixtures are unmodified slices of real Elexon stream responses."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def fuelhh_wind() -> list[dict[str, Any]]:
    # FUELHH fuelType=WIND, settlementDate 2026-01-03, SP1-4
    return load_fixture("fuelhh_wind_2026-01-03_sp1-4.json")


@pytest.fixture
def fuelhh_all_fuels() -> list[dict[str, Any]]:
    # FUELHH, no fuelType filter, settlementDate 2026-01-03, SP1 (20 fuel types)
    return load_fixture("fuelhh_all_fuels_2026-01-03_sp1.json")


@pytest.fixture
def windfor() -> list[dict[str, Any]]:
    # WINDFOR startTimes 2026-01-16 00:00-02:00Z from the 09:30Z and the late 12:25Z
    # publishes on 2026-01-15
    return load_fixture("windfor_2026-01-15_0930_and_1225.json")
