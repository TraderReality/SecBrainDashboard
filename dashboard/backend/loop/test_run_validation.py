import json
import stat
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from loop.run_validation import RunValidationService


class RunValidationServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.state = self.root / "state"
        self.vault.mkdir()
        self.archive = self.vault / "06 Archiv" / "raw.md"
        self.note = self.vault / "08 KI-Wissensbank" / "Raw.md"
        self.proposal = self.vault / "08 KI-Wissensbank" / "_Vorschlaege" / "run.md"
        self.log = self.vault / "08 KI-Wissensbank" / "_Log.md"
        self.graph = self.vault / "08 KI-Wissensbank" / "_index" / "graph.json"
        for path, content in (
            (self.archive, b"abc"),
            (self.note, b"# Raw\n"),
            (self.proposal, b"status: umgesetzt\n"),
            (self.log, b"# Log\n"),
            (self.graph, b'{"nodes": []}\n'),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.service = RunValidationService(self.vault, self.state)

    def finish_inbox(self, run_id="RUN-1"):
        self.service.begin(run_id, "inbox")
        return self.service.finish(run_id, "inbox", {
            "archived": [str(self.archive)], "created": [str(self.note)],
            "proposal_path": str(self.proposal), "log": str(self.log),
            "indexer": {"ok": True, "output": "indexiert"},
            "commit": {"ok": False, "reason": "Kein Git-Repository"},
        }, [{"name": "raw.md", "content": "abc"}], {"path": str(self.proposal)})

    def test_finish_survives_restart(self):
        evidence = self.finish_inbox()
        self.assertEqual(evidence["schema_version"], 1)
        self.assertEqual((evidence["run_id"], evidence["kind"]), ("RUN-1", "inbox"))
        self.assertEqual(evidence["commit"]["reason"], "Kein Git-Repository")
        self.assertTrue(evidence["indexer"]["ok"])
        self.assertEqual(evidence["files"]["06 Archiv/raw.md"],
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertIn("08 KI-Wissensbank/_Vorschlaege/run.md", evidence["files"])
        self.assertEqual(stat.S_IMODE((self.state / "last-run-validation.json").stat().st_mode), 0o600)
        self.assertEqual(RunValidationService(self.vault, self.state).status()["evidence"], evidence)

    def test_abort_keeps_previous_evidence(self):
        previous = self.finish_inbox()
        self.service.begin("RUN-2", "knowledge_radar")
        self.service.abort("RUN-2")
        state = self.service.status()
        self.assertFalse(state["pending"])
        self.assertEqual(state["evidence"], previous)

    def test_pending_marker_suppresses_green(self):
        self.finish_inbox()
        self.service.begin("RUN-2", "knowledge_radar")
        state = RunValidationService(self.vault, self.state).status()
        self.assertTrue(state["pending"])
        self.assertNotEqual(self.service.recheck({"available": True})["overall"], "bestanden")

    def test_new_run_after_crash_preserves_uncertainty_until_success(self):
        previous = self.finish_inbox()
        self.service.begin("RUN-2", "inbox")
        self.service.begin("RUN-3", "inbox")
        self.service.abort("RUN-3")
        self.assertTrue(self.service.status()["pending"])
        self.assertEqual(self.service.status()["evidence"], previous)
        self.service.begin("RUN-4", "inbox")
        newer = self.service.finish("RUN-4", "inbox", {
            "archived": [str(self.archive)], "created": [str(self.note)],
            "proposal_path": str(self.proposal), "log": str(self.log),
            "indexer": {"ok": True}, "commit": {"ok": False, "reason": "Kein Git-Repository"},
        }, [{"name": "raw.md", "content": "abc"}], {"path": str(self.proposal)})
        self.assertEqual(newer["run_id"], "RUN-4")
        self.assertFalse(self.service.status()["pending"])

    def test_recheck_detects_changed_missing_and_new_index(self):
        self.finish_inbox()
        self.archive.write_bytes(b"changed")
        self.note.unlink()
        self.graph.write_text('{"nodes": [1]}\n', encoding="utf-8")
        checked = self.service.recheck({"available": False, "error": "offline"})
        checks = {item.get("path") or item["id"]: item for item in checked["checks"]}
        self.assertEqual(checks["06 Archiv/raw.md"]["status"], "geändert")
        self.assertEqual(checks["08 KI-Wissensbank/Raw.md"]["status"], "fehlt")
        self.assertEqual(checks["graph"]["status"], "geändert")
        self.assertEqual(checks["qmd"]["status"], "nicht prüfbar")
        self.assertNotEqual(checked["overall"], "bestanden")

    def test_recheck_handles_no_commit(self):
        self.finish_inbox()
        checked = self.service.recheck({"available": True})
        commit = next(item for item in checked["checks"] if item["id"] == "commit")
        self.assertEqual(commit["status"], "nicht prüfbar")
        self.assertIn("Kein Git-Repository", commit["detail"])

    def test_recheck_rejects_traversal_and_symlink(self):
        self.finish_inbox()
        outside = self.root / "outside.md"
        outside.write_bytes(b"secret")
        evidence = json.loads(self.service.evidence_path.read_text(encoding="utf-8"))
        evidence["files"] = {"../outside.md": "2bb80d537b1da3e38bd30361aa855686bde0ba98eae16c0cd1c00cde30f1d9"}
        self.service.evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        first = self.service.recheck({"available": True})
        self.assertFalse(first["available"])
        link = self.vault / "link.md"
        link.symlink_to(outside)
        evidence["files"] = {"link.md": "2bb80d537b1da3e38bd30361aa855686bde0ba98eae16c0cd1c00cde30f1d9"}
        self.service.evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        second = self.service.recheck({"available": True})
        self.assertFalse(second["available"])

    def test_recheck_rejects_corrupt_or_future_schema(self):
        self.finish_inbox()
        self.service.evidence_path.write_text("{broken", encoding="utf-8")
        self.assertFalse(self.service.recheck({"available": True})["available"])
        self.service.evidence_path.write_text('{"schema_version": 999}', encoding="utf-8")
        self.assertFalse(self.service.recheck({"available": True})["available"])

    def test_recheck_is_read_only(self):
        self.finish_inbox()
        before = {str(path.relative_to(self.root)): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        checked = self.service.recheck({"available": True})
        after = {str(path.relative_to(self.root)): path.read_bytes()
                 for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(checked["pending"])

    def test_graph_symlink_outside_vault_is_not_read(self):
        self.finish_inbox()
        outside = self.root / "external.json"
        outside.write_bytes(self.graph.read_bytes())
        self.graph.unlink()
        self.graph.symlink_to(outside)
        checked = self.service.recheck({"available": True})
        self.assertNotEqual(checked["overall"], "bestanden")
        self.assertEqual(next(item for item in checked["checks"] if item["id"] == "graph")["status"], "nicht prüfbar")

    def test_corrupt_evidence_fields_and_symlink_loop_do_not_succeed(self):
        self.finish_inbox()
        valid = json.loads(self.service.evidence_path.read_text())
        for change in ({"completed_at": None}, {"indexer": {}}, {"kind": []}):
            self.service.evidence_path.write_text(json.dumps({**valid, **change}))
            self.assertFalse(self.service.recheck({"available": True})["available"])
        self.service.evidence_path.write_text(json.dumps(valid))
        self.archive.unlink()
        self.archive.symlink_to(self.archive)
        self.assertNotEqual(self.service.recheck({"available": True})["overall"], "bestanden")

    def test_new_run_during_recheck_discards_green_result(self):
        self.finish_inbox()
        original = self.service._read_vault_bytes
        triggered = False
        def begin_during_read(relative):
            nonlocal triggered
            if not triggered:
                triggered = True
                self.service.begin("RUN-2", "inbox")
            return original(relative)
        with patch.object(self.service, "_read_vault_bytes", side_effect=begin_during_read):
            checked = self.service.recheck({"available": True})
        self.assertTrue(checked["pending"])
        self.assertNotEqual(checked["overall"], "bestanden")


if __name__ == "__main__":
    unittest.main()
