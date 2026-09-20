import json
from pathlib import Path

import pytest

from indexcards import app
from indexcards.app import _validate_paths
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.persistence.file_io import save_document
from indexcards.persistence.format_guide import FORMAT_GUIDE
from indexcards.persistence.schema_file import schema_text


def _clean_fixture(tmp_path):
    document = Document(name="Clean")
    document.add_card(Card(id="c_1", text="Hello"))
    path = tmp_path / "clean.idxcards"
    save_document(document, path)
    return path


def test_validate_returns_zero_for_a_clean_file(tmp_path, capsys):
    path = _clean_fixture(tmp_path)

    exit_code = _validate_paths([path])

    assert exit_code == 0
    assert f"OK: {path}" in capsys.readouterr().out


def test_validate_returns_one_for_a_file_needing_repair(tmp_path, capsys):
    path = tmp_path / "needs_repair.idxcards"
    document = Document(name="Needs Repair")
    document.add_card(Card(id="c_1"))
    save_document(document, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["links"] = [{"id": "l_1", "source": "c_1", "target": "c_missing"}]
    path.write_text(json.dumps(data), encoding="utf-8")

    exit_code = _validate_paths([path])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert f"FAIL: {path}" in out
    assert "l_1" in out


def test_validate_returns_one_for_a_hard_load_failure(tmp_path, capsys):
    path = tmp_path / "broken.idxcards"
    path.write_text("{not valid json", encoding="utf-8")

    exit_code = _validate_paths([path])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert f"FAIL: {path}" in out


def test_validate_checks_every_path_and_fails_if_any_do(tmp_path, capsys):
    clean_path = _clean_fixture(tmp_path)
    broken_path = tmp_path / "broken.idxcards"
    broken_path.write_text("{not valid json", encoding="utf-8")

    exit_code = _validate_paths([clean_path, broken_path])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert f"OK: {clean_path}" in out
    assert f"FAIL: {broken_path}" in out


def _run_main_expecting_exit(monkeypatch, flag):
    def no_qapplication(*args, **kwargs):
        raise AssertionError("text-only commands must not create a QApplication")

    monkeypatch.setattr(app, "QApplication", no_qapplication)
    monkeypatch.setattr("sys.argv", ["indexcards", flag])
    with pytest.raises(SystemExit) as exit_info:
        app.main()
    return exit_info.value.code


def test_format_guide_flag_prints_the_guide_without_starting_qt(monkeypatch, capsys):
    code = _run_main_expecting_exit(monkeypatch, "--format-guide")

    assert code == 0
    assert capsys.readouterr().out == FORMAT_GUIDE


def test_schema_flag_prints_the_schema_without_starting_qt(monkeypatch, capsys):
    code = _run_main_expecting_exit(monkeypatch, "--schema")

    assert code == 0
    printed = capsys.readouterr().out
    assert printed == schema_text()
    assert json.loads(printed)["title"].startswith("IndexCards document")


SKILL_PATH = Path(__file__).parent.parent / "skills" / "indexcards" / "SKILL.md"


def test_bundled_skill_has_frontmatter_and_names_every_agent_command():
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert text.startswith("---\n")
    header = text.split("---\n")[1]
    assert "name: indexcards" in header
    assert "description:" in header
    for flag in ("--format-guide", "--schema", "--validate"):
        assert flag in text
