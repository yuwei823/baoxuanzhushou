import json
from pathlib import Path

from insurance_audit.rule_names import RULE_DISPLAY_NAMES


def test_every_published_rule_has_a_chinese_display_name():
    root = Path(__file__).resolve().parents[2]
    path = root / "data/corpus/official-v3-2026-10-12/rule_cards.jsonl"
    rule_ids = {
        json.loads(line)["rule_id"] for line in path.read_text(encoding="utf-8").splitlines()
    }

    assert set(RULE_DISPLAY_NAMES) == rule_ids
    assert len(set(RULE_DISPLAY_NAMES.values())) == len(rule_ids) == 46
    assert all(any("\u4e00" <= char <= "\u9fff" for char in name) for name in RULE_DISPLAY_NAMES.values())
