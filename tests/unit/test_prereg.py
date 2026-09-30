import pytest

from backtest_core import prereg


def test_register_writes_a_sha256sum_line_and_is_idempotent(tmp_path):
    spec = tmp_path / "prereg_x.md"
    spec.write_text("rules", encoding="utf-8")
    h = prereg.register(spec)
    assert prereg.register(spec) == h
    lines = (tmp_path / "spec.sha256").read_text(encoding="utf-8").splitlines()
    assert lines == [f"{h} *prereg_x.md"]


def test_a_changed_spec_cannot_be_registered_again_or_verified(tmp_path):
    spec = tmp_path / "prereg_x.md"
    spec.write_text("rules", encoding="utf-8")
    prereg.register(spec)
    spec.write_text("rules, edited after the result", encoding="utf-8")
    with pytest.raises(prereg.HashMismatchError):
        prereg.register(spec)
    with pytest.raises(prereg.HashMismatchError):
        prereg.verify(spec)


def test_ledger_written_by_sha256sum_with_a_path_is_understood(tmp_path):
    spec = tmp_path / "prereg_y.md"
    spec.write_text("abc", encoding="utf-8")
    (tmp_path / "spec.sha256").write_text(f"{prereg.sha256(spec)} */c/some/where/prereg_y.md\n", encoding="utf-8")
    assert prereg.verify(spec) == prereg.sha256(spec)


def test_a_holdout_can_be_spent_once(tmp_path):
    prereg.spend_holdout(tmp_path, "2024-26")
    with pytest.raises(prereg.HoldoutSpentError):
        prereg.spend_holdout(tmp_path, "2024-26")


def test_a_holdout_refuses_to_run_under_edited_rules(tmp_path):
    spec = tmp_path / "prereg_z.md"
    spec.write_text("rules", encoding="utf-8")
    prereg.register(spec)
    spec.write_text("new rules", encoding="utf-8")
    with pytest.raises(prereg.HashMismatchError):
        prereg.spend_holdout(tmp_path, "oos", spec=spec)
    assert not (tmp_path / "holdout_oos.spent").exists()
