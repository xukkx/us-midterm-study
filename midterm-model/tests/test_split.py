import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from midterms.split import RollingFold, assert_fold_valid, expanding_window_splits  # noqa: E402


def row(cycle, number, office="HOUSE", horizon="8_weeks"):
    return {
        "race_id": f"R-{cycle}-{number}",
        "cycle": cycle,
        "office": office,
        "forecast_horizon": horizon,
    }


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.rows = [row(cycle, number) for cycle in (2002, 2006, 2010, 2014) for number in range(3)]

    def test_expanding_window_only_uses_past(self):
        folds = expanding_window_splits(self.rows, min_train_cycles=2)
        self.assertEqual([fold.test_cycle for fold in folds], [2010, 2014])
        for fold in folds:
            self.assertLess(max(item["cycle"] for item in fold.train), fold.test_cycle)

    def test_complete_cycle_is_held_out(self):
        folds = expanding_window_splits(self.rows, min_train_cycles=2)
        self.assertEqual(len(folds[0].test), 3)
        self.assertEqual({item["cycle"] for item in folds[0].test}, {2010})

    def test_future_cycle_never_enters_earlier_fold(self):
        first = expanding_window_splits(self.rows, min_train_cycles=2)[0]
        self.assertNotIn(2014, {item["cycle"] for item in first.train})

    def test_house_and_senate_must_be_separate(self):
        with self.assertRaisesRegex(ValueError, "分轨"):
            expanding_window_splits(self.rows + [row(2014, 9, office="SENATE")], 2)

    def test_horizons_must_be_separate(self):
        with self.assertRaisesRegex(ValueError, "forecast_horizon"):
            expanding_window_splits(self.rows + [row(2014, 9, horizon="1_week")], 2)

    def test_too_few_cycles_rejected(self):
        with self.assertRaises(ValueError):
            expanding_window_splits(self.rows[:6], min_train_cycles=2)

    def test_manual_leaking_fold_rejected(self):
        leaking = RollingFold(
            test_cycle=2010,
            train_cycles=(2006, 2010),
            train=(row(2006, 1), row(2010, 1)),
            test=(row(2010, 2),),
        )
        with self.assertRaisesRegex(ValueError, "泄漏"):
            assert_fold_valid(leaking)

    def test_empty_input_rejected(self):
        with self.assertRaises(ValueError):
            expanding_window_splits([], 1)


if __name__ == "__main__":
    unittest.main()

