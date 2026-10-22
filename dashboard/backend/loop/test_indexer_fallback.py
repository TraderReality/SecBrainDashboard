"""Real subprocess contracts for the package fallback and Vault-owned indexer."""

import json
import importlib.util
import subprocess
from contextlib import contextmanager

import pytest

from loop import vault_loop_executor
from loop.vault_loop_executor import VaultLoopExecutor
from scanner.write_guard import VaultWriteGuard


@pytest.fixture
def executor(tmp_path, monkeypatch):
    vault = tmp_path.resolve() / "vault"
    vault.mkdir()
    guard = VaultWriteGuard(vault, tmp_path.resolve() / "state", model=lambda: "unused", chat=lambda **_: None)
    monkeypatch.setenv("SECBRAIN_QMD", "0")
    monkeypatch.setenv("SECBRAIN_VAULT", str(tmp_path / "wrong-vault"))
    return VaultLoopExecutor(vault, guard)


def test_missing_vault_indexer_builds_compatible_outputs_without_installing_script(executor):
    (executor.vault / "Note.md").write_text(
        "---\nid: note\ntitel: Note\ntyp: wissen\nstatus: aktiv\nerstellt: 2026-08-23\ntags: [test]\n---\nNormal body [[Target]]\n",
        encoding="utf-8",
    )
    (executor.vault / "Target.md").write_text("# Target\n", encoding="utf-8")

    result = executor._run_indexer()

    assert result["ok"] is True
    assert "Dateien indexiert: 2" in result["output"]
    output = executor.knowledge / "_index"
    graph = json.loads((output / "graph.json").read_text())
    assert graph["vault_root"] == str(executor.vault)
    assert graph["dateien_indexiert"] == graph["dateien_gesamt"] == 2
    assert graph["edges"] == [{"from": "note", "to": "target", "typ": "wikilink"}]
    note = next(node for node in graph["nodes"] if node["id"] == "note")
    assert note["erstellt"] == "2026-08-23"
    assert note["outgoing_links"] == ["target"]
    search = json.loads((output / "search_index.json").read_text())
    assert search["dateien"][0]["text"] == "Normal body [[Target]]\n"
    manifest = json.loads((output / "qmd-manifest.json").read_text())
    assert manifest["pfad_zu_id"] == {"Note.md": "note", "Target.md": "target"}
    stats = json.loads((output / "statistics.json").read_text())
    assert stats["relationen_gesamt"] == 1
    assert stats["qmd"]["ausgefuehrt"] is False
    assert stats["qmd"]["grund"] == "per SECBRAIN_QMD abgeschaltet"
    assert stats["timestamp"] == graph["timestamp"] == search["timestamp"] == manifest["generated"]
    assert json.loads((output / "cache/metadaten.json").read_text())["note"]["pfad"] == "Note.md"
    assert json.loads((output / "cache/wikilinks.json").read_text()) == {"note": ["Target"], "target": []}
    assert json.loads((output / "cache/broken-links.json").read_text()) == {"note": [], "target": []}
    assert json.loads((output / "cache/waisen.json").read_text()) == []
    assert not (executor.vault / "09 Werkzeuge/indexer.py").exists()


def test_report_folder_excludes_json_and_markdown_from_every_generated_view(executor):
    files = {
        "09 Werkzeuge/Scanner-Berichte/scan.json": '{"report": "private report"}',
        "09 Werkzeuge/Scanner-Berichte/nested/decoy.md": "# Report decoy\nprivate report",
        "09 Werkzeuge/Scanner-Berichte-old/normal.md": "# Neighbor\n",
        "Other/Scanner-Berichte/normal.md": "# Ordinary folder\n",
    }
    for relative, content in files.items():
        path = executor.vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    assert executor._run_indexer()["ok"] is True

    output = executor.knowledge / "_index"
    graph = json.loads((output / "graph.json").read_text())
    search = json.loads((output / "search_index.json").read_text())
    manifest = json.loads((output / "qmd-manifest.json").read_text())
    included = {"09 Werkzeuge/Scanner-Berichte-old/normal.md", "Other/Scanner-Berichte/normal.md"}
    assert {node["pfad"] for node in graph["nodes"]} == included
    assert {doc["pfad"] for doc in search["dateien"]} == included
    assert {doc["pfad"] for doc in manifest["dokumente"]} == included
    assert set(manifest["pfad_zu_id"]) == included
    assert manifest["dokumente_gesamt"] == 2
    for exported in output.rglob("*.json"):
        text = exported.read_text()
        assert "private report" not in text
        assert "decoy" not in text
        assert "scan.json" not in text
    for relative, content in files.items():
        assert (executor.vault / relative).read_text() == content


def test_crlf_markdown_preserves_frontmatter_ids_and_graph_search_outputs(executor):
    source = executor.vault / "Filename differs.md"
    original = (
        b"---\r\nid: explicit-id\r\ntitel: Explicit title\r\n"
        b"typ: wissen\r\nstatus: aktiv\r\ntags: [crlf, metadata]\r\n---\r\n"
        b"# Heading\r\nBody with [[target-id]]\r\n"
    )
    source.write_bytes(original)
    (executor.vault / "Target filename.md").write_bytes(
        b"---\r\nid: target-id\r\ntitel: Target title\r\n---\r\nTarget body\r\n"
    )

    assert executor._run_indexer()["ok"] is True

    output = executor.knowledge / "_index"
    graph = json.loads((output / "graph.json").read_text())
    note = next((node for node in graph["nodes"] if node["id"] == "explicit-id"), None)
    assert note is not None, "CRLF frontmatter must preserve the explicit identifier"
    assert note["titel"] == "Explicit title"
    assert note["tags"] == ["crlf", "metadata"]
    assert note["typ"] == "wissen"
    assert note["status"] == "aktiv"
    assert graph["edges"] == [{"from": "explicit-id", "to": "target-id", "typ": "wikilink"}]
    search = json.loads((output / "search_index.json").read_text())
    indexed = next(doc for doc in search["dateien"] if doc["id"] == "explicit-id")
    assert indexed["titel"] == "Explicit title"
    assert indexed["tags"] == ["crlf", "metadata"]
    assert indexed["text"] == "# Heading\nBody with [[target-id]]\n"
    assert source.read_bytes() == original


def test_vault_owned_indexer_keeps_precedence_and_active_environment(executor):
    script = executor.vault / "09 Werkzeuge/indexer.py"
    script.parent.mkdir()
    script.write_text(
        "import os\nfrom pathlib import Path\n"
        "assert Path(os.environ['SECBRAIN_VAULT']) == Path(__file__).parents[1]\n"
        "assert os.environ['SECBRAIN_QMD_EMBED'] == '0'\n"
        "print('Vault-owned indexer')\n",
        encoding="utf-8",
    )
    assert executor._run_indexer() == {"ok": True, "output": "Vault-owned indexer\n"}
    assert not (executor.knowledge / "_index").exists()


def test_failed_vault_owned_indexer_does_not_silently_use_fallback(executor):
    script = executor.vault / "09 Werkzeuge/indexer.py"
    script.parent.mkdir()
    script.write_text("raise RuntimeError('Vault indexer failure')\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Vault indexer failure"):
        executor._run_indexer()
    assert not (executor.knowledge / "_index").exists()


def test_missing_both_indexers_reports_both_paths(executor, tmp_path, monkeypatch):
    missing = tmp_path / "missing-package-indexer.py"
    monkeypatch.setattr(vault_loop_executor, "BUNDLED_INDEXER", missing, raising=False)
    with pytest.raises(RuntimeError) as error:
        executor._run_indexer()
    assert str(executor.vault / "09 Werkzeuge/indexer.py") in str(error.value)
    assert str(missing) in str(error.value)
    assert "Fallback" in str(error.value)


def test_new_qmd_collection_uses_explicit_markdown_mask(monkeypatch, tmp_path):
    # Only the external QMD process is replaced; no real QMD config is touched.
    from loop import vault_indexer

    calls = []

    def qmd_process(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setenv("SECBRAIN_QMD", "1")
    monkeypatch.setenv("SECBRAIN_QMD_EMBED", "0")
    monkeypatch.setattr(vault_indexer, "VAULT_ROOT", tmp_path)
    monkeypatch.setattr(vault_indexer, "QMD_COLLECTION", "isolated-test")
    monkeypatch.setattr(vault_indexer.shutil, "which", lambda _: "/fake/qmd")
    monkeypatch.setattr(vault_indexer.subprocess, "run", qmd_process)

    result = vault_indexer.qmd_auffrischen(1)

    assert result["ausgefuehrt"] is True
    assert calls == [
        ["qmd", "collection", "list"],
        ["qmd", "collection", "add", str(tmp_path), "--name", "isolated-test", "--mask", "**/*.md"],
        ["qmd", "update"],
    ]


@pytest.mark.parametrize("target", ["graph.json", "cache", "index-parent"])
def test_fallback_rejects_output_symlink_after_executor_snapshot(executor, tmp_path, target):
    (executor.vault / "Note.md").write_text("# Note\n")
    output = executor.knowledge / "_index"
    (output / "cache").mkdir(parents=True)
    (output / "graph.json").write_text("old graph")
    executor._snapshot_index(output)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "graph.json"
    sentinel.write_bytes(b"external sentinel")
    if target == "graph.json":
        (output / target).unlink()
        (output / target).symlink_to(sentinel)
    elif target == "cache":
        (output / target).rmdir()
        (output / target).symlink_to(outside, target_is_directory=True)
    else:
        output.rename(output.with_name("original-index"))
        output.symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError):
        executor._run_indexer()

    assert sentinel.read_bytes() == b"external sentinel"
    assert list(outside.iterdir()) == [sentinel]


def load_isolated_indexer(executor, monkeypatch):
    monkeypatch.setenv("SECBRAIN_VAULT", str(executor.vault))
    spec = importlib.util.spec_from_file_location("isolated_vault_indexer", vault_loop_executor.BUNDLED_INDEXER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("replacement", ["symlink", "identity", "bytes", "parent-symlink"])
def test_fallback_rejects_source_replacement_after_inventory(executor, tmp_path, monkeypatch, replacement):
    folder = executor.vault / "Notes"
    folder.mkdir()
    source = folder / "Note.md"
    source.write_text("# Authorized note\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / "Note.md"
    external.write_text("# External secret\n")
    module = load_isolated_indexer(executor, monkeypatch)
    scan = module.scan_vault

    def swap_after_scan():
        result = scan()
        if replacement == "parent-symlink":
            folder.rename(folder.with_name("original"))
            folder.symlink_to(outside, target_is_directory=True)
        elif replacement == "bytes":
            source.write_text("# Changed bytes\n")
        else:
            source.rename(folder / "original")
            if replacement == "symlink":
                source.symlink_to(external)
            else:
                source.write_text("# Authorized note\n")
        return result

    monkeypatch.setattr(module, "scan_vault", swap_after_scan)
    with pytest.raises((RuntimeError, OSError)):
        module.build_index()
    assert not (executor.knowledge / "_index/search_index.json").exists()
    assert external.read_text() == "# External secret\n"


def test_fallback_never_reads_initial_markdown_symlink(executor, tmp_path):
    external = tmp_path / "secret.md"
    external.write_text("# External secret\n")
    (executor.vault / "Note.md").symlink_to(external)
    with pytest.raises(RuntimeError):
        executor._run_indexer()
    assert not (executor.knowledge / "_index/search_index.json").exists()


@pytest.mark.parametrize("replacement", ["symlink", "identity", "bytes", "parent-symlink"])
def test_fallback_rejects_output_replacement_after_its_own_snapshot(executor, tmp_path, monkeypatch, replacement):
    (executor.vault / "Note.md").write_text("# Note\n")
    output = executor.knowledge / "_index"
    output.mkdir(parents=True)
    graph = output / "graph.json"
    graph.write_text("original graph")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "graph.json"
    sentinel.write_text("external sentinel")
    module = load_isolated_indexer(executor, monkeypatch)
    scan = module.scan_vault

    def swap_after_scan():
        result = scan()
        if replacement == "parent-symlink":
            output.rename(output.with_name("original-index"))
            output.symlink_to(outside, target_is_directory=True)
        elif replacement == "bytes":
            graph.write_text("foreign modification")
        else:
            graph.rename(output / "original-graph")
            if replacement == "symlink":
                graph.symlink_to(sentinel)
            else:
                graph.write_text("original graph")
        return result

    monkeypatch.setattr(module, "scan_vault", swap_after_scan)
    with pytest.raises((RuntimeError, OSError)):
        module.build_index()
    assert sentinel.read_text() == "external sentinel"
    assert list(outside.iterdir()) == [sentinel]
    if replacement == "bytes":
        assert graph.read_text() == "foreign modification"


def test_fallback_rejects_parent_swap_after_output_descriptor_open(executor, tmp_path, monkeypatch):
    from scanner import safe_files

    (executor.vault / "Note.md").write_text("# Note\n")
    output = executor.knowledge / "_index"
    output.mkdir(parents=True)
    (output / "graph.json").write_text("original graph")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "graph.json"
    sentinel.write_text("external sentinel")
    module = load_isolated_indexer(executor, monkeypatch)
    stage = safe_files._staged_bytes
    swapped = False

    @contextmanager
    def swap_after_open(directory, content):
        nonlocal swapped
        if not swapped:
            swapped = True
            output.rename(output.with_name("original-index"))
            output.symlink_to(outside, target_is_directory=True)
        with stage(directory, content) as temporary:
            yield temporary

    monkeypatch.setattr(safe_files, "_staged_bytes", swap_after_open)
    with pytest.raises((RuntimeError, OSError)):
        module.build_index()
    assert swapped
    assert sentinel.read_text() == "external sentinel"
    assert list(outside.iterdir()) == [sentinel]
