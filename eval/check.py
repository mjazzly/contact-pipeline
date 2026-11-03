"""The checker. Scores a harness run against eval/expected, which the model never sees.

Code cases (C) are decided by code and must all match. They are scored on a run where a scripted stand-in
reads the titles, so a model's miss is never counted again as a code miss. Title cases (T) score the model
on its own run. Gates (G) are the three points the build proves: the model never sees a name or email, the
stops halt, bad answers halt.
"""
import csv
import json
import re
from pathlib import Path

# Checker 1 scored the code cases on the model's own run; checker 2 scores them on the stand-in's run.
CHECKER_VERSION = "2"
EXPECTED = Path(__file__).resolve().parent / "expected"
FLOOR = {"c_suite", "vp", "director"}
MODEL_COLUMNS = ["Seniority", "Function"]
BAR = {"titles": 20, "gates": 3}


def load(name):
    return json.loads((EXPECTED / name).read_text())


def read_csv(path):
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def fates(record, import_rows):
    out = {}
    for e in record["exclusions"]:
        out.setdefault(e["row_key"], []).append(("excluded", e["stage"], e["reason"]))
    for row in import_rows:
        out.setdefault(row["Row Key"], []).append(("kept", None, None))
    return out


def row_fails(key, got, want):
    have = got.get(key, [])
    if len(have) != 1:
        return [f"{key}: {len(have)} fates on record"]
    fate, stage, reason = have[0]
    if fate != want["fate"]:
        return [f"{key}: {fate}, expected {want['fate']}"]
    if fate == "excluded":
        ok = reason == want["reason"] if "reason" in want else reason.startswith(want["reason_starts"])
        if stage != want["stage"] or not ok:
            return [f"{key}: excluded at stage {stage} ({reason}), expected stage {want['stage']} ({want.get('reason') or want['reason_starts'] + '...'})"]
    return []


def privacy_hits(payloads, intake_rows):
    """G1: every payload, read as text, against every name, email and email local part in the export."""
    hits = []
    for i, p in enumerate(payloads):
        text = json.dumps(p).lower()
        for r in intake_rows:
            email = r["email"].strip().lower()
            for kind, value in (("first name", r["first_name"]), ("last name", r["last_name"])):
                v = value.strip().lower()
                if v and re.search(rf"\b{re.escape(v)}\b", text):
                    hits.append(f"payload {i + 1}: {kind} of {r['row_key']}")
            for kind, value in (("email", email), ("email local part", email.split("@")[0])):
                if len(value) > 2 and value in text:
                    hits.append(f"payload {i + 1}: {kind} of {r['row_key']}")
    return hits


def asked(payloads):
    """Every title entry in a list of request payloads, in the order sent."""
    return [t for p in payloads for t in json.loads(p["messages"][0]["content"])["titles"]]


def score(main, code_run, repeats, halts, bad, payloads, intake_rows, repeats_rows, stub_calls):
    """main (the model's run), code_run and repeats (the stand-in's runs of the case round and the repeats
    round), halts and bad are (record, run folder) pairs from eval.py. stub_calls are the code run's
    validation calls."""
    record, folder = code_run
    rows_want, titles_want, counts = load("rows.json"), load("titles.json"), load("counts.json")
    want_cols, want_import = read_csv(EXPECTED / "import.csv")
    import_path = folder / record["import_file"] if record.get("import_file") else None
    cols, got_import = read_csv(import_path) if import_path and import_path.exists() else (None, [])
    by_key = {r["Row Key"]: r for r in got_import}
    want_by_key = {r["Row Key"]: r for r in want_import}
    got = fates(record, got_import)
    sent = {t["row_key"]: t["title"] for t in record["titles"]}
    titles_asked = {t["title"] for t in asked(payloads["code run"])}

    def rows(*keys):
        return [f for k in keys for f in row_fails(k, got, rows_want[k])]

    def field(key, column, value):
        have = by_key.get(key, {}).get(column)
        return [] if have == value else [f"{key}: {column} is {have!r}, expected {value!r}"]

    def stops():
        s = {x["stop"]: x for x in record["stops"]}
        fails = []
        for n in (1, 2, 3, 4):
            if n not in s:
                fails.append(f"stop {n} never reached")
            elif s[n]["count"] != counts[f"stop_{n}"]["count"]:
                fails.append(f"stop {n}: {s[n]['count']}, expected {counts[f'stop_{n}']['count']}")
        if 2 in s and s[2]["detail"]["excluded"] != counts["stop_2"]["excluded"]:
            fails.append(f"stop 2 reasons: {s[2]['detail']['excluded']}")
        if 3 in s and s[3]["detail"]["below_floor"] != counts["stop_3"]["below_floor"]:
            fails.append(f"stop 3 below floor: {s[3]['detail']['below_floor']}")
        if 4 in s:
            d, w = s[4]["detail"], counts["stop_4"]
            if (d["valid"], d["suspect"], d["excluded"]) != (w["valid"], w["suspect"], w["excluded"]):
                fails.append(f"stop 4 detail: {d}")
        if len(got_import) != counts["import_rows"]:
            fails.append(f"import rows: {len(got_import)}, expected {counts['import_rows']}")
        return fails

    def accounted():
        keys = [r["row_key"] for r in intake_rows]
        fails = [f"{k}: {len(got.get(k, []))} fates" for k in keys if len(got.get(k, [])) != 1]
        if len(record["exclusions"]) != counts["exclusions"]:
            fails.append(f"{len(record['exclusions'])} exclusions, expected {counts['exclusions']}")
        return fails

    def import_file():
        schema = want_cols[:4] + MODEL_COLUMNS + want_cols[4:]
        if cols != schema:
            return [f"columns {cols}, expected {schema}"]
        if [r["Row Key"] for r in got_import] != list(want_by_key):
            return ["rows differ from the expected rows or their order"]
        return [f"{k}: {c} is {by_key[k][c]!r}, expected {v!r}"
                for k, w in want_by_key.items() for c, v in w.items() if by_key[k][c] != v]

    def repeated():
        want, (rec, _) = load("repeats.json"), repeats
        sent_titles = asked(payloads["repeats run"])
        fails = []
        if [t["title"] for t in sent_titles] != want["titles_sent"]:
            fails.append(f"titles asked: {[t['title'] for t in sent_titles]}")
        extra = sorted({f for t in sent_titles for f in t} - set(want["request_fields"]))
        if extra:
            fails.append(f"a request carries {extra}")
        by = {t["row_key"]: t for t in rec["titles"]}
        if len(by) != want["rows"]:
            fails.append(f"{len(by)} rows answered, expected {want['rows']}")
        keys = set()
        for group in want["groups"]:
            got = {(by[k]["title_key"], by[k]["seniority"], by[k]["function"]) for k in group if k in by}
            if len(got) != 1 or any(k not in by for k in group):
                fails.append(f"{', '.join(group)} answered {sorted(got)}")
            keys |= {g[0] for g in got}
        if len(keys) != want["distinct_titles"]:
            fails.append(f"{len(keys)} title keys, expected {want['distinct_titles']}")
        s3 = next((x for x in rec["stops"] if x["stop"] == 3), None)
        if not s3:
            fails.append("stop 3 never reached")
        else:
            if s3["count"] != want["stop_3"]["count"]:
                fails.append(f"stop 3: {s3['count']}, expected {want['stop_3']['count']}")
            listed = [x["row_key"] for x in s3["detail"]["below_floor_rows"]]
            if listed != want["stop_3"]["below_floor_rows"]:
                fails.append(f"stop 3 lists {listed}")
            if s3["detail"].get("distinct_titles_asked") != want["distinct_titles"]:
                fails.append(f"stop 3 says {s3['detail'].get('distinct_titles_asked')} titles asked")
        return fails

    p = counts["privacy_payload_title"]
    code = {
        "C01": ("Duplicate email with different casing", lambda: rows("r0010", "r0011")),
        "C02": ("Scope runs before duplicates", lambda: rows("r0012", "r0013")),
        "C03": ("Canada row kept", lambda: rows("r0001") + field("r0001", "Country", "Canada")),
        "C04": ("Mexico row excluded", lambda: rows("r0002")),
        "C05": ("USA spelling read as United States", lambda: rows("r0006") + field("r0006", "Country", "United States")),
        "C06": ("Blank country, city filled: kept", lambda: rows("r0003") + field("r0003", "Country", "")),
        "C07": ("Blank country, province code: kept as Canada", lambda: rows("r0005") + field("r0005", "Country", "Canada")),
        "C08": ("Blank country, every person location empty: excluded", lambda: rows("r0004")),
        "C09": ("Company location does not count as person location", lambda: rows("r0007")),
        "C10": ("Malformed email excluded and never sent for validation",
                lambda: rows("r0008") + [f"sent for validation: {c}" for c in stub_calls if "dana.reyes" in c]),
        "C11": ("Blank email excluded and never sent for validation",
                lambda: rows("r0009") + (["a blank address was sent for validation"] if "" in stub_calls else [])),
        "C12": ("Honeypot excluded", lambda: rows("r0014")),
        "C13": ("Suspect kept and marked", lambda: rows("r0015") + field("r0015", "Email Status", "suspect")),
        "C14": ("No result excluded", lambda: rows("r0016")),
        "C15": ("Invalid excluded", lambda: rows("r0017")),
        "C16": ("Employee bands at the edges",
                lambda: [f for k in ("r0018", "r0020", "r0021", "r0023", "r0027")
                         for f in field(k, "Employee Band", want_by_key[k]["Employee Band"])]),
        "C17": ("Name in a title redacted for the model, restored in the import file",
                lambda: ([] if sent.get(p["row_key"]) == p["title"] and p["title"] in titles_asked
                         else [f"sent {sent.get(p['row_key'])!r}"])
                + field("r0026", "Job Title", want_by_key["r0026"]["Job Title"])),
        "C18": ("Counts at every stop", stops),
        "C19": ("Every row has exactly one fate; every exclusion one reason", accounted),
        "C20": ("Import file matches on every column code writes", import_file),
        "C21": ("Each distinct title asked once; every row carrying it gets that answer", repeated),
    }
    cases = {}
    for cid, (name, run) in code.items():
        fails = run()
        cases[cid] = {"name": f"{cid}. {name}", "match": not fails, "fails": fails}

    answers = {t["row_key"]: t for t in main[0]["titles"]}
    flips = 0
    for tid, w in ((k, v) for k, v in titles_want.items() if k.startswith("T")):
        a = answers.get(w["row_key"])
        fails = []
        if not a:
            fails = ["no answer on record"]
        else:
            if a["seniority"] not in w["seniority"]:
                fails.append(f"seniority {a['seniority']}, accepted {w['seniority']}")
            if a["function"] not in w["function"]:
                fails.append(f"function {a['function']}, accepted {w['function']}")
            if (a["seniority"] in FLOOR) != (w["floor"] == "in"):
                flips += 1
                fails.append(f"floor flipped: {a['seniority']} puts it {'in' if a['seniority'] in FLOOR else 'out'}")
        cases[tid] = {"name": f"{tid}. {w['title'] or '(empty title)'}", "match": not fails, "fails": fails}

    hits = privacy_hits([x for v in payloads.values() for x in v], intake_rows + repeats_rows)
    g2 = []
    for label, (rec, f), stop_at, reason in halts:
        if rec["status"] != f"halted_at_stop_{stop_at}":
            g2.append(f"{label}: status {rec['status']}")
        if rec.get("import_file") or (f / "output").exists():
            g2.append(f"{label}: an import file was written")
        if reason and reason not in (rec["halt"] or {}).get("reason", ""):
            g2.append(f"{label}: halt reason {rec['halt']}")
        if stop_at == 1 and (rec["model"]["calls"] or rec["validation_calls"]):
            g2.append(f"{label}: {rec['model']['calls']} model calls, {rec['validation_calls']} validation calls")
    brec, bfolder = bad
    probs = " | ".join((brec["halt"] or {}).get("problems", []))
    g3 = [f"no problem named for: {kind}" for kind in ("not an allowed value", "no answer", "2 answers", "not a title key")
          if kind not in probs]
    if brec["status"] != "halted_at_stop_3":
        g3.append(f"status {brec['status']}")
    if brec.get("import_file") or (bfolder / "output").exists():
        g3.append("an import file was written")
    if brec["model"]["calls"] != 2:
        g3.append(f"{brec['model']['calls']} calls, expected the first ask and one retry")
    gates = {
        "G1": {"name": "Privacy: no name or email in any model request", "held": bool(payloads["main"]) and not hits,
               "fails": hits or ([] if payloads["main"] else ["no model request was made"]), "payloads": sum(map(len, payloads.values()))},
        "G2": {"name": "Stops: an unconfirmed or misconfirmed stop halts and writes no import file", "held": not g2, "fails": g2},
        "G3": {"name": "Answer check: a bad answer halts at Stop 3 after one retry", "held": not g3, "fails": g3},
    }
    code_matched = sum(cases[c]["match"] for c in code)
    titles_matched = sum(c["match"] for k, c in cases.items() if k.startswith("T"))
    gates_held = sum(g["held"] for g in gates.values())
    verdict = {"code_matched": code_matched, "code_of": len(code), "titles_matched": titles_matched,
               "titles_of": len(cases) - len(code), "floor_flips": flips, "gates_held": gates_held,
               "passed": code_matched == len(code) and titles_matched >= BAR["titles"] and flips == 0
               and gates_held == BAR["gates"]}
    return cases, gates, verdict
