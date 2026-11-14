"""Production-policy regressions for the unchanged seeded threat catalog."""

import pytest

from tests.supplychain.evaluate import CASES, evaluate


@pytest.fixture(scope="module")
def results(ssh_keygen):
    return {row["id"]: row for row in evaluate()["results"]}


@pytest.mark.parametrize("case", [pytest.param(case, id=case["id"]) for case in CASES])
def test_supplychain_policy(case, results):
    row = results[case["id"]]
    if case["expected_rung"]:
        assert row["first_catch"] is not None, row
        assert row["first_catch"] == case["expected_rung"], row
    else:
        assert row["outcome"] == "accepted_control", row


def test_case_catalog_and_no_claimed_emulator_execution(results):
    assert len(results) == len(CASES) == 22
    assert sum(case["expected_rung"] is not None for case in CASES) == 20
    assert all(row["rungs"]["ci_replay"] == "not_run" for row in results.values())
    assert results["duplicate-run"]["signals"]["independent_runs"] == 1
    assert results["benign"]["signals"]["independent_runs"] == 1
