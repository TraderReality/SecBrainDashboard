"""Rule coverage and untrusted local-model boundary contracts."""
import hashlib
import json

import pytest

from scanner.rules import evaluate_rules, parse_rule_units


AGENTS = b"# Rules\n\nKeep sources.\n\n- No deletion.\n"
SUBJECTS = [{"path": "01 Inbox/note.md", "kind": "markdown", "content": "A researched note with a source."}]


def verdicts(status="erfüllt", subjects=None):
    return [{"rule_id": rule, "path": subject["path"], "status": status, "reason": "Regel geprüft."}
            for rule in ("L1", "L3", "L5") for subject in (SUBJECTS if subjects is None else subjects)]


def chat_reply(rows=None, **extra):
    def chat(messages, model):
        return {"model": model, "message": {"role": "assistant", "content": json.dumps({"findings": verdicts() if rows is None else rows}, ensure_ascii=False)}, **extra}
    return chat


def test_units_preserve_all_headings_paragraphs_bullets_and_code_with_positions():
    markdown = "# Rules\n\nFirst line\ncontinued.\n\n- First bullet\n  detail\n  - Nested bullet\n\nTitle\n-----\n\n```txt\n\n- literal\n```\n"
    assert parse_rule_units(markdown) == [
        {"id": "L1", "line": 1, "text": "# Rules"},
        {"id": "L3", "line": 3, "text": "First line\ncontinued."},
        {"id": "L6", "line": 6, "text": "- First bullet\n  detail"},
        {"id": "L8", "line": 8, "text": "  - Nested bullet"},
        {"id": "L10", "line": 10, "text": "Title\n-----"},
        {"id": "L13", "line": 13, "text": "```txt\n\n- literal\n```"},
    ]


def test_complete_model_coverage_passes_with_source_and_hash():
    result = evaluate_rules(AGENTS, SUBJECTS, "local-model", chat_reply())
    assert result["overall"] == "erfüllt"
    assert result["agents_sha256"] == hashlib.sha256(AGENTS).hexdigest()
    assert result["model"] == "local-model"
    assert [(f["rule_id"], f["source"]) for f in result["findings"]] == [
        ("L1", {"path": "AGENTS.md", "line": 1}),
        ("L3", {"path": "AGENTS.md", "line": 3}),
        ("L5", {"path": "AGENTS.md", "line": 5}),
    ]
    assert all("content" not in f and "text" not in f for f in result["findings"])


def test_full_original_rule_source_subjects_and_operation_reach_model():
    observed = {}
    subjects = [{**SUBJECTS[0], "operation": "delete"}]
    def chat(messages, model):
        observed.update(json.loads(messages[-1]["content"]))
        return chat_reply(verdicts(subjects=subjects))(messages, model)
    assert evaluate_rules(AGENTS, subjects, "local-model", chat)["overall"] == "erfüllt"
    assert observed["agents"] == AGENTS.decode()
    assert observed["subjects"] == subjects
    assert [u["id"] for u in observed["rules"]] == ["L1", "L3", "L5"]


def test_partial_coverage_is_unclear_and_preserves_violation():
    rows = verdicts("verletzt")[:1]
    result = evaluate_rules(AGENTS, SUBJECTS, "local-model", chat_reply(rows))
    assert result["overall"] == "unklar"
    assert [f["rule_id"] for f in result["findings"]] == ["L1", "L3", "L5"]
    assert result["findings"][0]["status"] == "verletzt"
    assert result["findings"][0]["source"] == {"path": "AGENTS.md", "line": 1}
    assert [f["status"] for f in result["findings"]][1:] == ["unklar", "unklar"]


@pytest.mark.parametrize("mutation", ["extra_path", "extra_rule", "duplicate", "contradiction", "invalid_status", "missing_reason", "extra_key", "wrong_type"])
def test_untrusted_model_matrix_fails_closed(mutation):
    rows = verdicts()
    if mutation == "extra_path":
        rows.append({**rows[0], "path": "foreign.md"})
    elif mutation == "extra_rule":
        rows.append({**rows[0], "rule_id": "L999"})
    elif mutation in {"duplicate", "contradiction"}:
        rows.append({**rows[0], "status": "verletzt" if mutation == "contradiction" else "erfüllt"})
    elif mutation == "invalid_status":
        rows[0]["status"] = "passed"
    elif mutation == "missing_reason":
        del rows[0]["reason"]
    elif mutation == "extra_key":
        rows[0]["content"] = SUBJECTS[0]["content"]
    else:
        rows[0]["rule_id"] = ["L1"]
    result = evaluate_rules(AGENTS, SUBJECTS, "local-model", chat_reply(rows))
    assert result["overall"] == "unklar"
    assert len(result["findings"]) == 3
    assert {f["path"] for f in result["findings"]} == {"01 Inbox/note.md"}


@pytest.mark.parametrize("status,overall", [("verletzt", "verletzt"), ("unklar", "unklar"), ("nicht anwendbar", "erfüllt")])
def test_allowed_verdicts_have_explicit_aggregate_semantics(status, overall):
    result = evaluate_rules(AGENTS, SUBJECTS, "local-model", chat_reply(verdicts(status)))
    assert result["overall"] == overall
    assert {f["status"] for f in result["findings"]} == {status}


def test_every_subject_requires_coverage():
    subjects = SUBJECTS + [{"path": "other.txt", "kind": "text", "content": "Other text."}]
    result = evaluate_rules(AGENTS, subjects, "local-model", chat_reply())
    assert result["overall"] == "unklar"
    assert len(result["findings"]) == 6


@pytest.mark.parametrize("agents", [b"", b" \n", b"\xff", b"# Rules\x00"])
def test_invalid_or_empty_rule_source_never_passes(agents):
    result = evaluate_rules(agents, SUBJECTS, "local-model", chat_reply())
    assert result["overall"] == "unklar"
    assert result["findings"]


@pytest.mark.parametrize("subject", [
    {"path": "image.png", "kind": "binary", "content": b"\x89PNG"},
    {"path": "file.md", "kind": "markdown", "content": b"\xff"},
    {"path": "file.txt", "kind": "text", "content": "text\x00"},
    {"path": "file.txt", "kind": "text", "content": None, "unreadable": True},
    {"path": "file.txt", "kind": "text", "content": "text", "unsupported": True},
    {"path": "file.txt", "kind": "unknown", "content": "text"},
    {"path": "../outside.md", "kind": "markdown", "content": "text"},
    {"path": "/outside.md", "kind": "markdown", "content": "text"},
    {"path": "a/../file.md", "kind": "markdown", "content": "text"},
    {"path": "a\\file.md", "kind": "markdown", "content": "text"},
])
def test_unreadable_unsupported_and_foreign_subjects_fail_without_model(subject):
    def forbidden_chat(**kwargs):
        pytest.fail("Unsupported input must be rejected before model invocation")
    assert evaluate_rules(AGENTS, [subject], "local-model", forbidden_chat)["overall"] == "unklar"


def test_duplicate_subjects_fail_closed():
    assert evaluate_rules(AGENTS, SUBJECTS * 2, "local-model", chat_reply())["overall"] == "unklar"


@pytest.mark.parametrize("failure", ["no_model", "invalid_json", "exception", "overflow", "truncated", "wrong_model", "duplicate_json_key", "extra_envelope", "huge_output"])
def test_model_failures_never_pass(failure):
    model = "" if failure == "no_model" else "local-model"
    def chat(messages, model):
        if failure in {"exception", "overflow"}:
            raise RuntimeError("secret body or context overflow")
        response = chat_reply()(messages, model)
        if failure == "invalid_json":
            response["message"]["content"] = "```json\n{}\n```"
        elif failure == "truncated":
            response["done_reason"] = "length"
        elif failure == "wrong_model":
            response["model"] = "other-model"
        elif failure == "duplicate_json_key":
            response["message"]["content"] = '{"findings": [], "findings": ' + json.dumps(verdicts()) + '}'
        elif failure == "extra_envelope":
            response["message"]["content"] = json.dumps({"findings": verdicts(), "content": "secret"})
        elif failure == "huge_output":
            response["message"]["content"] = " " * 1_000_000
        return response
    result = evaluate_rules(AGENTS, SUBJECTS, model, chat)
    assert result["overall"] == "unklar"
    assert "secret body" not in json.dumps(result)


def test_context_overflow_is_rejected_before_sending_truncated_input():
    def forbidden_chat(**kwargs):
        pytest.fail("Oversized context must not be sent")
    subjects = [{**SUBJECTS[0], "content": "large" * 100_000}]
    assert evaluate_rules(AGENTS, subjects, "local-model", forbidden_chat)["overall"] == "unklar"


def test_output_cannot_repeat_raw_subject_body_or_unbounded_reason():
    for reason in [SUBJECTS[0]["content"], "x" * 401, "raw\nbody"]:
        rows = verdicts()
        rows[0]["reason"] = reason
        result = evaluate_rules(AGENTS, SUBJECTS, "local-model", chat_reply(rows))
        assert result["overall"] == "unklar"
        assert reason not in [f["reason"] for f in result["findings"]]


def test_empty_vault_still_requires_global_rule_evaluation():
    result = evaluate_rules(AGENTS, [], "local-model", chat_reply([]))
    assert result["overall"] == "unklar"
    assert len(result["findings"]) == 3


def test_valid_utf8_bytes_subject_is_fully_evaluated():
    subjects = [{**SUBJECTS[0], "content": "Herkunft: Bücher".encode()}]
    assert evaluate_rules(AGENTS, subjects, "local-model", chat_reply())["overall"] == "erfüllt"


def test_extra_pair_keeps_violations_visible_but_aggregate_is_unclear():
    rows = verdicts("verletzt")
    rows.append({**rows[0], "path": "foreign.md"})
    result = evaluate_rules(AGENTS, SUBJECTS, "local-model", chat_reply(rows))
    assert result["overall"] == "unklar"
    assert {f["status"] for f in result["findings"]} == {"verletzt"}


@pytest.mark.parametrize("subject", [
    {"path": "file.txt", "kind": [], "content": "text"},
    {"path": "\ud800.md", "kind": "markdown", "content": "text"},
    {"path": "file.md", "kind": "markdown", "content": "\ud800"},
    {"path": "file.md", "kind": "markdown", "content": "text", "operation": None},
    {},
    None,
])
def test_malformed_subject_data_returns_unclear(subject):
    assert evaluate_rules(AGENTS, [subject], "local-model", chat_reply())["overall"] == "unklar"


def test_configured_context_limit_prevents_sending_incomplete_context():
    class SmallConnector:
        config = {"context": 64, "num_predict": 32}
        def chat(self, messages, model):
            pytest.fail("Configured context cannot contain the whole input")
    assert evaluate_rules(AGENTS, SUBJECTS, "local-model", SmallConnector().chat)["overall"] == "unklar"


def test_unknown_completion_reason_is_not_a_complete_evaluation():
    assert evaluate_rules(AGENTS, SUBJECTS, "local-model", chat_reply(done_reason="cancelled"))["overall"] == "unklar"


def test_copied_short_secret_line_is_not_written_to_findings():
    subjects = [{**SUBJECTS[0], "content": "Metadata\nTOKEN=abc\nOther text"}]
    rows = verdicts()
    rows[0]["reason"] = "Wert TOKEN=abc passt."
    result = evaluate_rules(AGENTS, subjects, "local-model", chat_reply(rows))
    assert result["overall"] == "unklar"
    assert "TOKEN=abc" not in json.dumps(result)


def test_non_utf8_model_reason_fails_closed():
    rows = verdicts()
    rows[0]["reason"] = "\ud800"
    def chat(messages, model):
        return {"model": model, "message": {"content": json.dumps({"findings": rows}, ensure_ascii=True)}}
    assert evaluate_rules(AGENTS, SUBJECTS, "local-model", chat)["overall"] == "unklar"


def test_invalid_connector_budget_configuration_fails_closed():
    class InvalidConnector:
        config = None
        def chat(self, messages, model):
            pytest.fail("Unknown connector budget must not permit a model request")
    assert evaluate_rules(AGENTS, SUBJECTS, "local-model", InvalidConnector().chat)["overall"] == "unklar"


@pytest.mark.parametrize("underline", ["=====", "-----"])
def test_setext_heading_ends_before_following_paragraph(underline):
    assert parse_rule_units(f"Title\n{underline}\nParagraph rule.\n") == [
        {"id": "L1", "line": 1, "text": f"Title\n{underline}"},
        {"id": "L3", "line": 3, "text": "Paragraph rule."},
    ]


@pytest.mark.parametrize("prefix", ["> ", "> > ", "  > "])
def test_quoted_bullets_each_receive_original_source_position(prefix):
    assert parse_rule_units(f"{prefix}- First rule\n{prefix}- Second rule\n") == [
        {"id": "L1", "line": 1, "text": f"{prefix}- First rule"},
        {"id": "L2", "line": 2, "text": f"{prefix}- Second rule"},
    ]


def test_quoted_fenced_example_keeps_literal_bullets_in_one_unit():
    assert parse_rule_units("> ```md\n> - literal\n> - example\n> ```\n>\n> - Actual rule\n") == [
        {"id": "L1", "line": 1, "text": "> ```md\n> - literal\n> - example\n> ```"},
        {"id": "L6", "line": 6, "text": "> - Actual rule"},
    ]


@pytest.mark.parametrize("separator", ["", "\n"])
def test_unclosed_quoted_fence_ends_with_quote_container(separator):
    markdown = "> ```md\n> - literal example\n" + separator + "- First real rule\n- Second real rule\n"
    first_rule_line = 3 + bool(separator)
    assert parse_rule_units(markdown) == [
        {"id": "L1", "line": 1, "text": "> ```md\n> - literal example"},
        {"id": f"L{first_rule_line}", "line": first_rule_line, "text": "- First real rule"},
        {"id": f"L{first_rule_line + 1}", "line": first_rule_line + 1, "text": "- Second real rule"},
    ]


@pytest.mark.parametrize("prefix", ["", "> "])
def test_extra_quote_inside_fence_is_literal_and_cannot_close_it(prefix):
    markdown = f"{prefix}```md\n{prefix}> ```\n{prefix}- literal rule\n{prefix}```\n- Actual rule\n"
    assert parse_rule_units(markdown) == [
        {"id": "L1", "line": 1, "text": f"{prefix}```md\n{prefix}> ```\n{prefix}- literal rule\n{prefix}```"},
        {"id": "L5", "line": 5, "text": "- Actual rule"},
    ]
