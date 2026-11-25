"""Belege per Checkliste bestätigen (offline)."""
import unittest

from jobwatch.belege import align_cv, apply_to_evidence, branch_of, checklist, parse_boxes
from jobwatch.profile import is_confirmed, parse_evidence

EVIDENCE = """# Belege

## R1 | Engineer | Contoso AG | Zürich | 2022 – heute

- E1 [unbestätigt]: Kundenportal weiterentwickelt. Quelle: Lebenslauf (Entwurf).
- E2 [unbestätigt] [level: basic]: Node.js. Quelle: Lebenslauf (Entwurf).

## Kenntnisse und Sprachen

- E3 [unbestätigt]: Sprachen: TypeScript. Quelle: Lebenslauf (Entwurf).
"""

DRAFT = {"experience": [{"id": "R1", "bullets": [
            {"id": "B1", "text": "Portal", "evidence": ["E1"]},
            {"id": "B2", "text": "Node", "evidence": ["E2"]}]}],
         "skills": [{"category": "Sprachen", "items": "TypeScript", "evidence": ["E3"]}]}


class BelegeTest(unittest.TestCase):
    def test_checklist_roundtrip(self):
        text = checklist(EVIDENCE, "profil/issue-7")
        self.assertEqual(branch_of(text), "profil/issue-7")
        self.assertIn("- [ ] **E1** Kundenportal weiterentwickelt.", text)
        self.assertNotIn("Quelle: Lebenslauf (Entwurf)", text)
        boxes = parse_boxes(text.replace("- [ ] **E2**", "- [x] **E2**"))
        self.assertEqual(boxes, {"E1": False, "E2": True, "E3": False})

    def test_apply_keeps_other_tags(self):
        out = apply_to_evidence(EVIDENCE, {"E1": True, "E2": True, "E3": False})
        items = parse_evidence(out)["items"]
        self.assertTrue(is_confirmed(items["E1"]))
        self.assertTrue(is_confirmed(items["E2"]))
        self.assertIn("level: basic", items["E2"]["tags"])
        self.assertFalse(is_confirmed(items["E3"]))
        back = apply_to_evidence(out, {"E1": False})
        self.assertFalse(is_confirmed(parse_evidence(back)["items"]["E1"]))

    def test_align_drops_and_restores(self):
        import copy
        cv = align_cv(copy.deepcopy(DRAFT), DRAFT, {"E1"})
        self.assertEqual([b["id"] for b in cv["experience"][0]["bullets"]], ["B1"])
        self.assertEqual(cv["skills"], [])
        cv = align_cv(cv, DRAFT, {"E1", "E2", "E3"})
        self.assertEqual([b["id"] for b in cv["experience"][0]["bullets"]], ["B1", "B2"])
        self.assertEqual(len(cv["skills"]), 1)


if __name__ == "__main__":
    unittest.main()
