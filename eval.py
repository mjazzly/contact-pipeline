#!/usr/bin/env python3
"""The eval harness. One command runs the case set on a model and records the result.

    python eval.py --model claude-haiku-5-5
    python eval.py --model claude-opus-5-5 --effort high
    python eval.py --mock          (scripted stand-in, no API call; never counted)

What a run does:
  1. Runs data/round_cases.csv through the pipeline on the chosen model, confirming each stop the way
     eval/answers.txt says. Every model request payload is kept.
  2. Runs the same round again with a scripted stand-in reading the titles; the code cases are scored on
     this run, so they test code alone. Then data/round_repeats.csv with the same stand-in, for C21: each
     distinct title asked once. Then the case round three times to test the stops (G2): no confirmations,
     Stops 1 and 2 only, and a Stop 1 count that does not match. And once with a stand-in that answers
     badly (G3). These six use scripted stand-ins, so they cost nothing.
  3. Scores all of it with eval/check.py against eval/expected/ and writes result.json and
     transcript.json to eval/runs/<label>/, and a copy of the result to eval/results/.
"""
import argparse
import json
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "eval"))

from check import BAR, CHECKER_VERSION, score  # noqa: E402
from mock import BadModel, ScriptedModel  # noqa: E402
from pipeline import VERSION  # noqa: E402
from pipeline.rules import intake  # noqa: E402
from pipeline.stub import ValidationStub  # noqa: E402
from pipeline.titles import Model  # noqa: E402
from run import api_key, parse_confirm, run_round  # noqa: E402

ROUND = ROOT / "data" / "round_cases.csv"
REPEATS = ROOT / "data" / "round_repeats.csv"
FIXTURES = ROOT / "data" / "stub_fixtures.json"


def answers():
    """The confirmation the harness gives, read from eval/answers.txt like a person typing it."""
    line = next(l.strip() for l in (ROOT / "eval" / "answers.txt").read_text().splitlines()
                if l.strip() and not l.startswith("#"))
    if line == "--confirm-all":
        return parse_confirm("", True)
    return parse_confirm(line.removeprefix("--confirm").strip())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-haiku-5-5")
    p.add_argument("--effort", default=None)
    p.add_argument("--label", default=None)
    p.add_argument("--mock", action="store_true")
    a = p.parse_args()

    started = datetime.now()
    run_id = "N" + started.strftime("%Y%m%d%H%M")
    tag = "mock" if a.mock else a.model.removeprefix("claude-") + (f"-{a.effort}" if a.effort else "")
    label = a.label or f"{run_id}-{tag}"
    run_dir = ROOT / "eval" / ("runs-mock" if a.mock else "runs") / label
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    print(f"run {label}: pipeline {VERSION}, model {'mock (scripted, no model)' if a.mock else a.model}"
          + (f", effort {a.effort}" if a.effort else ""))

    if a.mock:
        model = ScriptedModel()
    else:
        import anthropic
        model = Model(a.model, a.effort, anthropic.Anthropic(api_key=api_key()))

    result = {"label": label, "run_id": run_id, "date": started.date().isoformat(),
              "started_at": started.isoformat(timespec="seconds"), "mode": "mock" if a.mock else "harness",
              "blind": True, "counted": False, "skill_version": model.version, "server_version": VERSION,
              "checker_version": CHECKER_VERSION, "model": None if a.mock else a.model, "effort": a.effort,
              "completed": False, "error": None}
    payloads, stub_calls = {}, []
    try:
        stub = ValidationStub(FIXTURES)
        print("\n== main run ==")
        main_run = (run_round(ROUND, answers(), model, stub, run_dir / "main"), run_dir / "main")
        payloads["main"] = model.payloads

        print("\n== code run: scripted stand-in reads the titles ==")
        stand_in, code_stub = ScriptedModel(), ValidationStub(FIXTURES)
        code_run = (run_round(ROUND, parse_confirm("", True), stand_in, code_stub, run_dir / "code"), run_dir / "code")
        payloads["code run"], stub_calls = stand_in.payloads, code_stub.calls

        print("\n== repeats run: one answer per distinct title ==")
        stand_in = ScriptedModel()
        repeats = (run_round(REPEATS, parse_confirm("", True), stand_in, ValidationStub(FIXTURES), run_dir / "repeats"),
                   run_dir / "repeats")
        payloads["repeats run"] = stand_in.payloads

        halts = []
        for name, confirm, stop_at, reason in (("no confirmations", "", 1, "waiting for confirmation"),
                                               ("stops 1 and 2 only", "1=29,2=22", 3, "waiting for confirmation"),
                                               ("wrong count at stop 1", "1=28", 1, "confirmed 28")):
            print(f"\n== stop test: {name} ==")
            stand_in, folder = ScriptedModel(), run_dir / "stops" / name.replace(" ", "_")
            rec = run_round(ROUND, parse_confirm(confirm), stand_in, ValidationStub(FIXTURES), folder)
            payloads[f"stop test: {name}"] = stand_in.payloads
            halts.append((name, (rec, folder), stop_at, reason))

        print("\n== answer check test ==")
        bad_model, folder = BadModel(), run_dir / "answer_check"
        bad = (run_round(ROUND, parse_confirm("", True), bad_model, ValidationStub(FIXTURES), folder), folder)
        payloads["answer check test"] = bad_model.payloads

        cases, gates, verdict = score(main_run, code_run, repeats, halts, bad, payloads, intake(ROUND)["rows"],
                                      intake(REPEATS)["rows"], stub_calls)
        result.update(completed=True, verdict=verdict, cases=cases, gates=gates,
                      main_status=main_run[0]["status"], main_record=str(main_run[0]["record_file"]),
                      main_counts=main_run[0]["counts"])
    except Exception as e:  # a harness that did not finish is recorded, never counted
        result["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    t = model.tokens
    result.update(model_calls=model.calls, tokens=t,
                  total_input=t["input"] + t["cache_read"] + t["cache_write"], cost_usd=cost(model, a.mock),
                  cache=True, bar=f"every code case, {BAR['titles']} of 22 titles, no floor flips, all three gates")
    result["counted"] = not a.mock and result["completed"] and model.calls > 0
    result["verdict"] = result.get("verdict") or {"passed": False, "gates_held": 0}
    (run_dir / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    (run_dir / "transcript.json").write_text(json.dumps(
        {"payloads": payloads, "answers": model.answers}, indent=1) + "\n")
    if not a.mock:
        (ROOT / "eval" / "results").mkdir(exist_ok=True)
        shutil.copyfile(run_dir / "result.json", ROOT / "eval" / "results" / f"{label}.json")

    v = result["verdict"]
    print(f"\n{label}: {'PASSED' if v['passed'] else 'NOT PASSED'}")
    if result["completed"]:
        print(f"  code cases {v['code_matched']} of {v['code_of']}, titles {v['titles_matched']} of {v['titles_of']}, "
              f"floor flips {v['floor_flips']}, gates held {v['gates_held']} of 3")
        c = result["main_counts"]
        print(f"  model run: {c.get('at_or_above_floor', 'n/a')} at or above the floor (17 expected), "
              f"{c.get('import_rows', 'no')} rows in the import file (14 expected)")
        for cid, c in {**result["cases"], **result["gates"]}.items():
            ok = c.get("match", c.get("held"))
            if not ok:
                print(f"  MISS {c['name']}: {'; '.join(c['fails'])}")
    print(f"  model calls {model.calls}, cost {'n/a' if result['cost_usd'] is None else f'US${result['cost_usd']:.4f}'}")
    print(f"  {run_dir / 'result.json'}")
    sys.exit(0 if result["completed"] else 1)


def cost(model, mock):
    from run import cost as priced
    return None if mock else priced(model)


if __name__ == "__main__":
    main()
