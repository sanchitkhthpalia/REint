"""The committed snapshot: serving (CSV) and archive (parquet) copies must hold the same data.

Uses pyarrow (a dev dependency) to read the parquet archive; the app itself never does.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from app.snapshot import SERVING_FILES, load_snapshot, read_serving_table

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.mark.parametrize("serving_name", sorted(SERVING_FILES))
def test_serving_copy_matches_parquet_archive(serving_name):
    archive_name = serving_name.replace(".csv.gz", ".parquet")
    serving = read_serving_table(DATA_DIR / serving_name, SERVING_FILES[serving_name])
    archive = pd.read_parquet(DATA_DIR / archive_name)

    pd.testing.assert_frame_equal(
        serving,
        archive,
        check_dtype=False,  # timestamp resolution may differ (ns vs us); values must not
        check_exact=True,
    )
    for column in SERVING_FILES[serving_name]:
        assert str(serving[column].dt.tz) == "UTC"


def test_manifest_describes_every_file_with_matching_row_counts():
    manifest = json.loads((DATA_DIR / "manifest.json").read_text())
    snapshot = load_snapshot(DATA_DIR)

    files = manifest["files"]
    assert {files[n]["role"] for n in files} == {"archive", "serving"}
    assert files["actuals.csv.gz"]["rows"] == files["actuals.parquet"]["rows"]
    assert files["forecasts.csv.gz"]["rows"] == files["forecasts.parquet"]["rows"]
    assert len(snapshot.actuals) == files["actuals.csv.gz"]["rows"]
    assert len(snapshot.forecasts) == files["forecasts.csv.gz"]["rows"]
