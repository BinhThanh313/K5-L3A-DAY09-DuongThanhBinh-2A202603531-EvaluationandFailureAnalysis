"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    import math

    problems: list[str] = []
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"metric {k} is {v}")
    man = pr["manifest"]
    want = int(man["items"]) * len(man["seeds"])
    if len(pr["rows"]) != want:
        problems.append(f"{len(pr['rows'])} rows, expected {want} (items x seeds): dropped or duplicated rows")
    keys_pr = [(r["item_id"], r["seed"]) for r in pr["rows"]]
    if len(set(keys_pr)) != len(keys_pr):
        problems.append("duplicate (item_id, seed) rows")
    if set(keys_pr) != {(r["item_id"], r["seed"]) for r in base["rows"]}:
        problems.append("(item_id, seed) set differs from the baseline's (cherry-picked items or seeds)")
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s): {pr['evaluator_failures'][0]}")
    graded = [m["id"] for m in spec["metrics"] if m["id"] in GRADERS]
    for mid in graded:
        n_none = sum(1 for r in pr["rows"] if r.get(mid) is None)
        if n_none:
            problems.append(f"{n_none} row(s) with no value for graded metric {mid} (crashed grader)")
    slices_pr = {r["item_id"]: sorted(r.get("slices") or []) for r in pr["rows"]}
    slices_base = {r["item_id"]: sorted(r.get("slices") or []) for r in base["rows"]}
    for item, tags in slices_pr.items():
        if item in slices_base and slices_base[item] != tags:
            problems.append(f"item {item} slice tags {tags} differ from baseline {slices_base[item]}")
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(spec.get("metrics", []), base_spec.get("metrics", []), "id", "metric")
        problems += _ratchet(spec.get("slices", []), base_spec.get("slices", []), "name", "slice")
    return problems


def _ratchet(new: list[dict], old: list[dict], key: str, what: str) -> list[str]:
    """Thresholds may only get stricter: max may not rise, min may not fall, blocking may not turn off,
    no_significant_drop may not be dropped, and an entry may not disappear."""
    out: list[str] = []
    cur = {e[key]: e for e in new}
    for e in old:
        name = e[key]
        n = cur.get(name)
        if n is None:
            out.append(f"{what} {name} removed from the spec")
            continue
        if e.get("blocking") and not n.get("blocking", what == "slice"):
            out.append(f"{what} {name} is no longer blocking")
        o_th, n_th = (e.get("threshold") or e), (n.get("threshold") or n)
        for bound, worse in (("max", lambda a, b: b > a), ("max_increase", lambda a, b: b > a),
                             ("min", lambda a, b: b < a)):
            if bound in o_th and (bound not in n_th or worse(o_th[bound], n_th[bound])):
                out.append(f"{what} {name}: {bound} loosened {o_th[bound]} -> {n_th.get(bound)}")
        if o_th.get("no_significant_drop") and not n_th.get("no_significant_drop"):
            out.append(f"{what} {name}: no_significant_drop dropped")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        tag = f"slice:{name}/{metric}"
        if not a:
            verdict, note, val = "MISSING", "no rows in this slice", None
        else:
            val = sum(a.values()) / len(a)
            verdict, note = "ok", ""
            if "min" in s and val < s["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if s.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"\u0394 {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        bad = verdict != "ok"
        if bad and s.get("blocking", True):
            blocked.append(tag)
        shown = "n/a" if val is None else f"{val:.4f}"
        lines.append(f"  {tag:<34} {shown:<8} min={s.get('min')} {note:<28} "
                     f"{'BLOCK' if bad and s.get('blocking', True) else ('warn' if bad else 'ok')}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
