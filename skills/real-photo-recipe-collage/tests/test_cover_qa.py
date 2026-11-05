"""Regression tests for the 3:4 cover gate; use synthetic images only."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cover_qa


class CoverQATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "original.jpg"
        Image.new("RGB", (650, 900), (175, 160, 140)).save(self.source)
        self.out = self.root / "cover.png"
        Image.new("RGB", (1200, 1600), (190, 185, 180)).save(self.out)

    def checked_review(self):
        data = cover_qa.review_template(
            cover_qa.sha256(self.out), cover_qa.sha256(self.source))
        data["checks"] = {key: True for key in cover_qa.VISUAL_CHECKS}
        path = self.root / "review.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_exact_3_by_4_is_not_auto_approved_without_review(self):
        qa = cover_qa.inspect(self.out, self.source)
        self.assertEqual(qa["actual_size"], [1200, 1600])
        self.assertTrue(qa["exact_ratio_3_4"])
        self.assertEqual(qa["status"], "review_required")
        self.assertFalse(qa["manual_review_confirmed"])

    def test_four_by_five_is_rejected(self):
        Image.new("RGB", (1122, 1402), (180, 180, 180)).save(self.out)
        qa = cover_qa.inspect(self.out, self.source)
        self.assertFalse(qa["exact_ratio_3_4"])
        self.assertEqual(qa["status"], "fail")
        self.assertIn("FINAL_RATIO_NOT_EXACT_3_4", qa["hard_failures"])

    def test_non_png_is_rejected_even_with_3_by_4(self):
        jpg = self.root / "result.jpg"
        Image.new("RGB", (900, 1200)).save(jpg)
        qa = cover_qa.inspect(jpg, self.source)
        self.assertEqual(qa["status"], "fail")
        self.assertIn("FINAL_IMAGE_NOT_PNG", qa["hard_failures"])

    def test_subject_touching_edges_is_rejected(self):
        maskfile = self.root / "mask.png"
        mask = Image.new("L", (1200, 1600), 0)
        ImageDraw.Draw(mask).rectangle((0, 100, 1140, 1450), fill=255)
        mask.save(maskfile)
        qa = cover_qa.inspect(self.out, self.source, maskfile)
        self.assertEqual(qa["status"], "fail")
        self.assertIn("SUBJECT_TOUCHES_CANVAS_EDGE", qa["hard_failures"])

    def test_safe_mask_requires_review_and_then_can_pass(self):
        maskfile = self.root / "safe_mask.png"
        mask = Image.new("L", (1200, 1600), 0)
        ImageDraw.Draw(mask).rectangle((48, 80, 1151, 1519), fill=255)
        mask.save(maskfile)
        qa = cover_qa.inspect(self.out, self.source, maskfile)
        self.assertEqual(qa["status"], "review_required")
        reviewed = cover_qa.inspect(self.out, self.source, maskfile,
                                    self.checked_review())
        self.assertEqual(reviewed["status"], "pass_manual_checked")
        self.assertGreaterEqual(reviewed["subject_margins"]["left"], 0.03)

    def test_review_is_bound_to_actual_final_image_sha(self):
        review = self.checked_review()
        Image.new("RGB", (1200, 1600), (0, 0, 0)).save(self.out)
        qa = cover_qa.inspect(self.out, self.source, review_path=review)
        self.assertEqual(qa["status"], "fail")
        self.assertIn("VISUAL_REVIEW_HASH_MISMATCH", qa["hard_failures"])

    def test_review_with_unchecked_items_cannot_pass(self):
        data = cover_qa.review_template(
            cover_qa.sha256(self.out), cover_qa.sha256(self.source))
        path = self.root / "review_empty.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        qa = cover_qa.inspect(self.out, self.source, review_path=path)
        self.assertEqual(qa["status"], "review_required")
        self.assertIn("VISUAL_REVIEW_INCOMPLETE", qa["warnings"])


if __name__ == "__main__":
    unittest.main()
