"""Regression test for docs/trace_case.md (seeded_regression C-002@11, FM-03 ticket_trust)."""
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.student


def _run(shape):
    from lab8.benchmark import prepare_from_memory, run_trial
    from lab8.db import connect, load_json, load_jsonl
    from lab8.metrics import ledger_snapshot
    from lab9 import variants

    variants.register()
    world = load_json(Path("data/public_world_state.json"))
    claims = load_jsonl(Path("data/public_claims.jsonl"))
    store = Path(tempfile.mkdtemp(prefix="lab9-trace-")) / "s.sqlite"
    prepare_from_memory(store, world, claims)
    payload, error = run_trial(shape, "C-002", 11, store)
    assert payload is not None, error
    conn = connect(store)
    try:
        snap = ledger_snapshot(conn, "C-002")
    finally:
        conn.close()
    return payload, snap


def test_ticket_trust_refunds_a_denied_claim():
    payload, snap = _run("seeded_regression")
    assert snap["refund_vnd"] == 20000 and payload["status"] == "resolved"   # label: 0 / denied


def test_fixed_denies_c002_and_ledger_stays_empty():
    payload, snap = _run("fixed")
    assert snap["refund_vnd"] == 0 and snap["refund_count"] == 0 and payload["status"] == "denied"
