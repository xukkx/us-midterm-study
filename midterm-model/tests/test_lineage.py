import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from midterms.lineage import (  # noqa: E402
    LineageValidationError,
    SourceLineage,
    build_cycle_lineage,
    lineage_bytes,
    validate_lineage,
)


def row(cycle, office="HOUSE", race_id="race"):
    return {"cycle": cycle, "office": office, "race_id": f"{race_id}-{cycle}"}


class LineageTests(unittest.TestCase):
    def test_valid_lineage_is_sorted_deterministically(self):
        records = validate_lineage(
            [
                {"office": "HOUSE", "source_cycle": 2002},
                {"office": "HOUSE", "source_cycle": 1998},
            ],
            test_cycle=2006,
            expected_office="HOUSE",
        )
        self.assertEqual([item.source_cycle for item in records], [1998, 2002])

    def test_equal_or_future_source_cycle_is_rejected(self):
        for source_cycle in (2006, 2010):
            with self.subTest(source_cycle=source_cycle):
                with self.assertRaisesRegex(LineageValidationError, "不早于"):
                    validate_lineage(
                        [{"office": "HOUSE", "source_cycle": source_cycle}],
                        test_cycle=2006,
                    )

    def test_boolean_source_cycle_is_rejected(self):
        with self.assertRaisesRegex(LineageValidationError, "整数周期"):
            validate_lineage(
                [{"office": "HOUSE", "source_cycle": True}], test_cycle=2006
            )

    def test_expected_office_mismatch_is_rejected(self):
        with self.assertRaisesRegex(LineageValidationError, "院别"):
            validate_lineage(
                [{"office": "SENATE", "source_cycle": 2002}],
                test_cycle=2006,
                expected_office="HOUSE",
            )

    def test_duplicate_lineage_is_rejected(self):
        duplicate = {"office": "HOUSE", "source_cycle": 2002}
        with self.assertRaisesRegex(LineageValidationError, "重复来源"):
            validate_lineage([duplicate, duplicate], test_cycle=2006)

    def test_empty_lineage_is_rejected(self):
        with self.assertRaisesRegex(LineageValidationError, "不能为空"):
            validate_lineage([], test_cycle=2006)

    def test_build_cycle_lineage_collapses_rows_within_cycle(self):
        records = build_cycle_lineage(
            [row(1998, race_id="a"), row(1998, race_id="b"), row(2002)],
            test_cycle=2006,
            office="HOUSE",
        )
        self.assertEqual(
            records,
            (
                SourceLineage("HOUSE", 1998),
                SourceLineage("HOUSE", 2002),
            ),
        )

    def test_build_cycle_lineage_rejects_mixed_chambers(self):
        with self.assertRaisesRegex(LineageValidationError, "不得混合"):
            build_cycle_lineage(
                [row(1998, "HOUSE"), row(2002, "SENATE")],
                test_cycle=2006,
                office="HOUSE",
            )

    def test_lineage_bytes_do_not_depend_on_input_order(self):
        left = [
            {"office": "HOUSE", "source_cycle": 2002},
            {"office": "HOUSE", "source_cycle": 1998},
        ]
        right = list(reversed(left))
        self.assertEqual(lineage_bytes(left), lineage_bytes(right))


if __name__ == "__main__":
    unittest.main()

