import tempfile
import unittest
from pathlib import Path
from offline import inventory, evaluate


class OfflineTest(unittest.TestCase):
    def test_wrong_type_counts_both_sides_and_failed_safe_is_not_correct(self):
        truth = [{"id":"a","types":["reentrancy"]}, {"id":"b","types":[]}]
        predictions = [{"id":"a","status":"COMPLETED","types":["access"]},
                       {"id":"b","status":"FAILED","types":[]}]
        result = evaluate(["reentrancy","access"], truth, predictions)
        self.assertEqual(1, result["per_type"]["reentrancy"]["fn"])
        self.assertEqual(1, result["per_type"]["access"]["fp"])
        self.assertEqual(0, result["correct_completed"])
        self.assertEqual(.5, result["failure_rate"])
        self.assertEqual(1, result["unresolved_negative"])

    def test_missing_positive_is_false_negative(self):
        result = evaluate(["r"], [{"id":"a","types":["r"]}], [])
        self.assertEqual(1, result["missing"])
        self.assertEqual(0, result["micro"]["recall"])
        self.assertIsNone(result["micro"]["precision"])

    def test_rejects_duplicate_unknown_and_failed_predictions(self):
        truth = [{"id":"a","types":["r"]}]
        for predictions in [
            [{"id":"a","status":"COMPLETED","types":[]}] * 2,
            [{"id":"unknown","status":"COMPLETED","types":[]}],
            [{"id":"a","status":"FAILED","types":["r"]}],
            [{"id":"a","status":"COMPLETED","types":["unknown"]}],
        ]:
            with self.assertRaises(ValueError): evaluate(["r"], truth, predictions)

    def test_multilabel_deduplicates_type_predictions(self):
        result = evaluate(["r","a"], [{"id":"x","types":["r","a"]}],
                          [{"id":"x","status":"COMPLETED","types":["r","r","a"]}])
        self.assertEqual(2, result["micro"]["tp"])
        self.assertEqual(1, result["micro"]["f1"])
        self.assertEqual(1, result["macro_f1"])

    def test_partial_undefined_does_not_change_macro_denominator(self):
        result = evaluate(["r", "a"], [{"id":"x", "types":["r"]}],
                          [{"id":"x", "status":"COMPLETED", "types":["r"]}])
        self.assertIsNone(result["macro_f1"])
        self.assertEqual(1, result["macro_f1_defined_only"])
        self.assertEqual(["a"], result["macro_undefined_categories"])

    def test_empty_denominators_are_undefined(self):
        result = evaluate(["r"], [], [])
        self.assertIsNone(result["macro_f1"])
        self.assertIsNone(result["completion_rate"])

    def test_inventory_groups_duplicates_without_assigning_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe").mkdir()
            (root / "safe" / "a.sol").write_text("contract C {}")
            (root / "b.sol").write_text("contract C {}")
            result = inventory(root)
            self.assertEqual(2, result["count"])
            self.assertEqual(1, len(result["duplicate_groups"]))
            self.assertIsNone(result["samples"][0]["types"])
            self.assertEqual(2, len({x["id"] for x in result["samples"]}))
            self.assertEqual(result, inventory(root))


if __name__ == "__main__": unittest.main()
