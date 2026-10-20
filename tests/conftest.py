import json

import pytest

from mockcrowd.util import set_quiet


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCKCROWD_HOME", str(tmp_path / "home"))
    set_quiet(True)
    yield tmp_path / "home"


@pytest.fixture
def voices_file(tmp_path):
    rows = []
    texts = [
        "I keep my whole vinyl collection in a spreadsheet and it is a pain to update every time I buy a record.",
        "Discogs works fine for me, I would never pay for another app to catalog records.",
        "Would love something that scans the barcode and tells me what pressing I have and what it is worth.",
        "Honestly I just buy records I like, I do not care what they are worth.",
        "Every app I tried for this wanted a subscription. Hard pass on another monthly fee.",
        "I lost track of which records I already own and bought a duplicate twice this year.",
        "Price tracking would be nice for selling, but the data is never accurate for rare pressings.",
        "My collection is over 2000 records, any app has to handle bulk import or it is useless.",
    ]
    for i in range(48):
        rows.append({"text": f"{texts[i % len(texts)]} (post {i})", "community": ["r/vinyl", "r/VinylCollectors", "Discogs forum"][i % 3],
                     "url": f"https://example.com/{i}"})
    path = tmp_path / "voices.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path
