#!/usr/bin/env python3
"""One round of the contact pipeline: a contact vendor export in, a CRM import file and a run record out.

    python run.py --round data/round_cases.csv --confirm-all
    python run.py --round data/round_cases.csv --confirm 1=29,2=22
    python run.py --round data/round_cases.csv --model claude-opus-5-5 --effort high

Six stages and four stops. At each stop the run prints the count and halts unless that stop is confirmed:
by --confirm-all, or by --confirm with the count you saw (a count that differs halts the run). The import
file is written only once every stop has passed. A halted run still writes its run record.
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from pipeline import VERSION
from pipeline.rules import IMPORT_COLUMNS, intake, reason_group, scope, to_import
from pipeline.stub import KEEP, ValidationStub
from pipeline.titles import Model, above_floor, read_titles

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = "claude-haiku-5-5"


class Halt(Exception):
    def __init__(self, stop, reason, problems=None):
        super().__init__(reason)
        self.stop, self.reason, self.problems = stop, reason, problems or []


def parse_confirm(text, confirm_all=False):
    counts = {}
    for part in filter(None, (text or "").split(",")):
        n, _, count = part.partition("=")
        counts[int(n)] = int(count)
    return {"all": confirm_all, "counts": counts}


def stop(record, n, name, count, detail, confirm):
    """K1: the run goes past a stop only when the stop is confirmed, and only for the count shown."""
    entry = {"stop": n, "name": name, "count": count, "detail": detail, "confirmed": False, "how": None,
             "at": datetime.now().isoformat(timespec="seconds")}
    record["stops"].append(entry)
    print(f"Stop {n}, {name}: {count}")
    for k, v in detail.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            print(f"    {k}:")
            for item in v:
                print("      " + "  ".join(f'"{x}"' if field == "title" else str(x) for field, x in item.items()))
        else:
            print(f"    {k}: {json.dumps(v)}")
    if confirm["all"]:
        entry.update(confirmed=True, how="--confirm-all")
    elif n in confirm["counts"]:
        if confirm["counts"][n] != count:
            raise Halt(n, f"confirmed {confirm['counts'][n]} but the count is {count}")
        entry.update(confirmed=True, how=f"--confirm {n}={count}")
    else:
        raise Halt(n, f"waiting for confirmation of {count}")


def cost(model):
    prices = json.loads((ROOT / "prices.json").read_text()).get(model.id)
    if not prices or model.calls == 0:
        return None
    t = model.tokens
    return (t["input"] * prices["input"] + t["cache_write"] * prices["cache_write_5m"]
            + t["cache_read"] * prices["cache_read"] + t["output"] * prices["output"]) / 1e6


def run_round(round_path, confirm, model, stub, out_dir):
    round_path, out_dir = Path(round_path), Path(out_dir)
    name = round_path.stem
    started = datetime.now()
    import_path = out_dir / "output" / f"{name}_import.csv"
    record = {"round": round_path.name, "pipeline_version": VERSION, "prompt_version": model.version,
              "started_at": started.isoformat(timespec="seconds"), "status": None, "halt": None,
              "counts": {}, "stops": [], "exclusions": [], "titles": [], "import_file": None}
    exclude = lambda key, stage, reason: record["exclusions"].append({"row_key": key, "stage": stage, "reason": reason})
    try:
        # Stage 1: intake
        got = intake(round_path)
        rows = got["rows"]
        record["counts"]["intake"] = len(rows)
        if got["missing"]:
            raise Halt(1, "missing headers: " + ", ".join(got["missing"]))
        stop(record, 1, "rows read", len(rows),
             {"blank_lines_skipped": got["blank_lines"], "columns": got["columns"]}, confirm)

        # Stage 2: scope, email checks, duplicates
        rows, excluded = scope(rows)
        for key, reason in excluded:
            exclude(key, 2, reason)
        record["counts"]["after_scope"] = len(rows)
        stop(record, 2, "rows in scope", len(rows),
             {"excluded": dict(Counter(reason_group(r) for _, r in excluded)), "columns_dropped": got["unused"]},
             confirm)

        # Stage 3: title read
        answers, problems, sent = read_titles(rows, model)
        if problems:
            guard = any(p.startswith("privacy guard") for p in problems)
            raise Halt(3, "privacy guard" if guard else "answer check failed", problems)
        below = []
        for r in rows:
            a = answers[r["row_key"]]
            record["titles"].append({"row_key": r["row_key"], **sent[r["row_key"]], **a,
                                     "floor": "in" if above_floor(a) else "out"})
            if not above_floor(a):
                exclude(r["row_key"], 3, f"below seniority floor ({a['seniority']})")
                below.append({"row_key": r["row_key"], "title": sent[r["row_key"]]["title"],
                              "seniority": a["seniority"], "reason": a["reason"]})
        rows = [r for r in rows if above_floor(answers[r["row_key"]])]
        record["counts"]["at_or_above_floor"] = len(rows)
        record["counts"]["below_floor"] = len(below)
        record["counts"]["distinct_titles"] = len({s["title_key"] for s in sent.values()})
        stop(record, 3, "rows at or above the seniority floor", len(rows),
             {"distinct_titles_asked": record["counts"]["distinct_titles"], "below_floor": len(below),
              "below_floor_rows": below}, confirm)

        # Stage 4: validation
        verdicts = {r["row_key"]: stub.check(r["email"]) for r in rows}
        for r in rows:
            if verdicts[r["row_key"]] not in KEEP:
                exclude(r["row_key"], 4, f"validation: {verdicts[r['row_key']]}")
        rows = [r for r in rows if verdicts[r["row_key"]] in KEEP]
        tally = Counter(verdicts.values())
        record["counts"]["after_validation"] = len(rows)
        stop(record, 4, "rows with a valid or suspect email", len(rows),
             {"valid": tally["valid"], "suspect": tally["suspect"],
              "excluded": {v: tally[v] for v in ("invalid", "honeypot", "no_result") if tally[v]}}, confirm)

        # Stage 5: format. K2: written beside the target, then moved into place.
        import_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = import_path.with_suffix(".tmp")
        with open(tmp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=IMPORT_COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow(to_import(r, answers[r["row_key"]], verdicts[r["row_key"]], name))
        os.replace(tmp, import_path)
        record["counts"]["import_rows"] = len(rows)
        record["import_file"] = str(import_path.relative_to(out_dir))
        record["status"] = "complete"
    except Halt as h:
        record["status"] = f"halted_at_stop_{h.stop}"
        record["halt"] = {"stop": h.stop, "reason": h.reason, "problems": h.problems}
        print(f"Halted at Stop {h.stop}: {h.reason}")
        for p in h.problems:
            print(f"    {p}")

    # Stage 6: the run record, every time (K3)
    record["model"] = {"id": model.id, "effort": model.effort, "calls": model.calls, "tokens": model.tokens,
                       "cost_usd": cost(model)}
    record["validation_calls"] = len(stub.calls)
    record["finished_at"] = datetime.now().isoformat(timespec="seconds")
    results = out_dir / "results"
    results.mkdir(parents=True, exist_ok=True)
    record_path = results / f"{name}-{started.strftime('%Y%m%d%H%M%S')}.json"
    record_path.write_text(json.dumps(record, indent=2) + "\n")
    record["record_file"] = str(record_path.relative_to(out_dir))
    if record["import_file"]:
        print(f"Import file: {out_dir / record['import_file']} ({record['counts']['import_rows']} rows)")
    m = record["model"]
    price = "not priced" if m["cost_usd"] is None else f"US${m['cost_usd']:.4f}"
    print(f"Model: {m['id']}{', effort ' + m['effort'] if m['effort'] else ''}, {m['calls']} calls, cost {price}")
    print(f"Run record: {record_path}")
    return record


def api_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "ANTHROPIC_API_KEY" and v.strip():
                return v.strip().strip('"')
    sys.exit("No API key. Put ANTHROPIC_API_KEY=... in .env in this folder (see .env.example).")


def main():
    p = argparse.ArgumentParser(description="Run one round of the contact pipeline.")
    p.add_argument("--round", required=True, help="the contact vendor export, .csv or .xlsx")
    p.add_argument("--confirm-all", action="store_true", help="confirm every stop")
    p.add_argument("--confirm", default="", help="stops confirmed with the count seen, for example 1=29,2=22")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--effort", default=None)
    a = p.parse_args()
    confirm = parse_confirm(a.confirm, a.confirm_all)
    # A run with no confirmations halts at Stop 1 before any model call, so it needs no key.
    client = None
    if confirm["all"] or confirm["counts"]:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key())
    model = Model(a.model, a.effort, client)
    stub = ValidationStub(ROOT / "data" / "stub_fixtures.json")
    out = Path(os.environ.get("PIPELINE_DATA") or ROOT)
    record = run_round(a.round, confirm, model, stub, out)
    sys.exit(0 if record["status"] == "complete" else 3)


if __name__ == "__main__":
    main()
