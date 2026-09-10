import unittest
import verify

class VerificationTests(unittest.TestCase):
    def test_mapping_erratum(self):
        r=verify.independent()
        self.assertEqual(r["changed_components"], {"early_same_changed":237,"early_diff_return":137,"early_diff_third":40})
        self.assertEqual(r["excluded_early_diff_keep"],413)
    def test_score_rejects_bad_probability(self):
        with self.assertRaises(ValueError): verify.score([.5,.5,0],0,0)
        with self.assertRaises(ValueError): verify.score([1,0,0,0],1,0)
    def test_frozen_recalculation(self):
        self.assertTrue(verify.independent()["passed"])
    def test_producer_artifacts(self):
        r=verify.audit_artifacts()
        self.assertEqual(r["support_rows"],544)
        self.assertEqual(r["matched_draws"],99999)
