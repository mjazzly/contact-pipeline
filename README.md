# Contact Pipeline, v1.1

Every week a contact vendor export of business contacts arrives and has to become a CRM import file: rows outside the region removed, duplicates and broken emails taken out, each job title read for seniority and function, emails checked with an email validation service, and the rest mapped onto a fixed import schema. A person confirms the count at each step before the next one runs. This build is a synthetic twin of that weekly round. Every round runs the same stages, the same checks and the same stops, and leaves a run record behind.

It proves three points a reader can open and check:

1. **Rules live in code, judgement lives with the model.** Geography, duplicates, the validation verdict and the output format are code in `pipeline/rules.py` and `pipeline/stub.py`. The model does one step, the one that needs judgement: reading a job title for seniority and function.
2. **The model never sees a person's name or email.** `pipeline/titles.py` sends a title key and the title, nothing else, with any name or email inside the title replaced. Each distinct title is asked once and its answer joined back to every row that carries it. The harness reads every model request payload and fails the run if a name or email appears in any of them.
3. **The stops are real.** The run halts at each stop with the count and goes on only when that stop is confirmed. The import file is written once every stop has passed, and never before.

All data is synthetic. The names are neutral, the companies are generic, the locations are in the US and Canada (plus the out of scope rows that test the filter), and the email validation service is a seeded stub, so a round is repeatable and costs nothing beyond the title read.

## The stages

| Stage | Who does it | Stop |
|---|---|---|
| 1. Intake: read the export, check the headers, count the rows | Code | Stop 1: confirm the count |
| 2. Scope: keep US and Canada, drop unused columns, take out blank, malformed and duplicate emails | Code | Stop 2: confirm the count kept, with each exclusion reason counted |
| 3. Title read: names and emails removed; each distinct title sent once; seniority and function back per title with a short reason and given to every row with that title; rows below the floor excluded | Model, checked by code | Stop 3: confirm the floor split, with the model's reason for each row excluded |
| 4. Validation: every email to the stub; invalid, honeypot and no result excluded; suspect kept and marked | Code | Stop 4: confirm the valid and excluded counts |
| 5. Format: names and emails joined back by row key, mapped onto the import schema, employee counts banded | Code | none |
| 6. Record: counts at every stage, every exclusion with its reason, the model, the cost, the stop confirmations | Code | none |

## The rules

**Scope (Stage 2), in this order.** A row that is excluded carries the reason of the first rule it fails, and only that one.

- **S1** Country is read from a fixed list of spellings (US, USA, U.S., United States; Canada, CAN). Any other country that is filled in is out of scope.
- **S2** A row with a blank country is kept only when the person's city or state is filled. The company's location does not count.
- **S3** A blank country is filled from a known US state or Canadian province code; otherwise it stays blank.
- **E1** A blank email is excluded, and so is a malformed one (not exactly one @, no local part, no dot in the domain, or a space).
- **D1** Duplicates are matched on the trimmed, lower case email. The first row in file order is kept. Scope runs first, so an out of scope copy never pushes out the copy that is in scope.

**Title read (Stage 3).**

- **P1** The request carries a title key and the title, and no other field. Email shaped text and the row's own first and last name are replaced before the call. A guard checks each payload before it is sent.
- **P2** Each distinct title is asked once. Titles that differ only in capitals or spacing are the same title, and so are two titles that differ only by a redacted name. Its answer goes to every row that carries it, so one title never gets two answers in a run.
- **M1** Seniority is one of `c_suite, vp, director, manager, staff, unknown`. Function is one of `general_management, operations, finance, people, technology, sales, legal, administration, other, unknown`.
- **M2** Code checks every answer: exactly one answer for each title key sent, no other keys, allowed values only. A batch with a problem is asked once more. A problem that is still there halts the run at Stop 3, naming each title and the rows that carry it; no row is ever dropped quietly.
- **F1** The floor is director: c_suite, vp and director are kept.
- Titles go to the model in batches of up to 25.

**Validation (Stage 4).**

- **V1** The stub returns valid, invalid, honeypot, suspect or no result. The case round's addresses have fixed verdicts in `data/stub_fixtures.json`; any other address gets one from a hash of the seed and the address.
- **V2** Valid and suspect are kept; suspect shows in the Email Status column.

**Format (Stage 5).**

- **B1** Employee bands: 1 to 10, 11 to 50, 51 to 200, 201 to 500, 501 to 1,000, 1,001 to 5,000, 5,001 to 10,000, 10,001+. A count with commas is read as a number; a blank or unreadable count is Unknown.

**Stops.**

- **K1** A stop passes with `--confirm-all`, or with `--confirm` and the count the person saw. A count that differs halts the run.
- **K2** The import file is written beside its target and moved into place only after every stop has passed.
- **K3** A halted run still writes its run record.

## The case set

`data/round_cases.csv` holds 29 rows, written by hand, each one a planted case. The expected outcome of every row, every title and every stop count was written in `eval/expected/` before any code. The model never sees that folder.

- **Code cases, C01 to C21.** Scored on a second run of the round in which a scripted stand-in reads the titles, so they test code alone and a model's miss is counted once, in the title cases. Duplicate email in different casing; scope before duplicates; a Canada row kept and a Mexico row excluded; a USA spelling; blank country with a city (kept), with a province code (kept as Canada), with no person location (excluded), and with only the company's location (excluded); malformed and blank emails excluded and never sent for validation; honeypot, no result and invalid excluded; suspect kept and marked; employee bands at the edges; a name inside a title redacted for the model and restored in the import file; the count at every stop (29, 22, 17, 14); one fate for every row; the import file on every column code writes. C21 runs `data/round_repeats.csv`, eight rows with four distinct titles (in different capitals and spacing, and with two different names redacted), and checks each title is asked once, with no company in the request, and that every row carrying it gets the same answer.
- **Title cases, T01 to T22.** Every title in the round, each with its accepted seniority and function. The traps: "Head of People", "VP Operations", "Assistant to the Director", "Director-elect", "Chief of Staff", "Senior Manager, Benefits", a title in capitals, an empty title, a title that tries to give the model an instruction, and a title with the person's own first name in it.
- **Gates.** G1 privacy: no name, email or email local part in any model request. G2 stops: a run with no confirmations halts at Stop 1 with no model or validation call and no import file; a run with Stops 1 and 2 confirmed halts at Stop 3; a Stop 1 count that does not match halts. G3 answer check: a stand-in that answers with a value not allowed, a missing row, a row answered twice and a key never sent is asked once more, then halts at Stop 3 with each problem named.

**The bar:** every code case matched, at least 20 of the 22 titles matched, no title answer that moves a row across the floor, and all three gates held. The case list with each expected answer is in [eval/CASES.md](eval/CASES.md).

## Files

| Path | What it is |
|---|---|
| `run.py` | One round: the six stages, the four stops, the run record. |
| `pipeline/rules.py` | Intake, scope, email checks, duplicates, bands and the import schema. |
| `pipeline/titles.py` | The title read: redaction, the model call, the answer check, the floor. |
| `pipeline/stub.py` | The email validation service, as a seeded stub. |
| `prompts/title_read.md` | The model's only instructions, with its version line. |
| `data/round_cases.csv` | The case round. |
| `data/round_repeats.csv` | The round for C21: repeated titles. |
| `data/stub_fixtures.json` | The stub's fixed verdicts for the case round. |
| `data/demo_round.xlsx` | A 120 row demo round from `scripts/generate.py`, seed 6. Not scored. |
| `eval.py` | The harness: the case round on a model, the same round with a stand-in for the code cases, the stop tests and the answer check test, then the score. |
| `eval/check.py` | The checker, against `eval/expected/`. |
| `eval/mock.py` | The scripted stand-ins: one that answers well, one that answers badly. |
| `eval/run_eval.js` | The scorecard starts harnesses with Node; this hands the call to `eval.py`. |
| `package.json` | Only so Node reads `eval/run_eval.js` the same way wherever the scorecard copies the build. |
| `requirements.txt` | The two Python packages, pinned. |
| `run`, `evals` | Short forms of `run.py` and `eval.py` through uv. |
| `VERSIONS.md` | Each version's results against the one before, and what the next version changes. |
| `harness.json` | The adapter the scorecard reads. |
| `prices.json` | Prices per million tokens, with the date they were read. |
| `results/` | One run record per round. |
| `output/` | The import files. |

## Run it

Needs [uv](https://docs.astral.sh/uv/). Two short commands wrap the uv call; any further flags go straight through to `run.py` or `eval.py`.

```
./run demo                            # the 120 row demo round; halts at Stop 1 with the count
./run demo --confirm-all              # every stop confirmed
./run cases --confirm 1=29,2=22       # the case round, through Stop 2
./run path/to/export.csv --confirm-all
./evals mock                          # the harness on the scripted stand-in: no key, seconds, never counted
./evals haiku                         # the harness on claude-haiku-5-5
./evals opus                          # the harness on claude-opus-5-5 at high effort
```

The long form, which is what both run, needs Python 3.12 with the two packages in `requirements.txt`; uv builds and caches that environment outside this folder:

```
uv run --no-project --python 3.12 --with-requirements requirements.txt python run.py --round data/round_cases.csv
```

In any Python 3.12 environment with the requirements installed, `python run.py ...` does the same. The model calls need an Anthropic API key in a file called `.env` in this folder (see `.env.example`); a run with no confirmations halts at Stop 1 and needs no key.

```
python run.py --round data/round_cases.csv                       # halts at Stop 1 with the count
python run.py --round data/round_cases.csv --confirm 1=29        # goes on to Stop 2 and halts
python run.py --round data/round_cases.csv --confirm 1=29,2=22,3=17,4=14
python run.py --round data/round_cases.csv --confirm-all --model claude-opus-5-5 --effort high
python scripts/generate.py --seed 6 --rows 120 --out data/demo_round.xlsx
```

Each run reads the round from the start, so stepping through the stops one at a time asks the model again at each step past Stop 2. The run record goes to `results/` and the import file to `output/`; set `PIPELINE_DATA` to write both somewhere else.

### Rerun every case with one command (the harness)

```
python eval.py --mock                                   # scripted stand-in, no key, seconds; never counted
python eval.py --model claude-haiku-5-5
python eval.py --model claude-opus-5-5 --effort high
```

A run writes `result.json` and `transcript.json` (every payload sent and every answer) to `eval/runs/<label>/`, with the pipeline's own record and import file beside them, and a copy of the result to `eval/results/`. The scorecard picks the build up from `harness.json` and runs the same harness through `node eval/run_eval.js`, which needs uv on the path.

## Choices

- **Batches of 25 titles per call**, not one call per title: the answer check gives the reliability, and the case round is one call.
- **The company is not sent.** The model judges the title alone, which lets one question stand for every row with that title.
- **Stop 3 shows the model's reason for each row it excludes**, since those are the rows a person needs to see to confirm the split.
- **No one page summary** from the run record; the record and the site entry cover it.
- The function list has no entry for promotional roles; such a title reads as other.

## Limits

- One case round. The model is scored on 22 titles, so a single miss is a large share of the score.
- The validation service is a stub. A real service returns more verdicts and fails in ways this one does not.
- Stepping through the stops one command at a time repeats the model call; the case round costs little, a large round would not.
