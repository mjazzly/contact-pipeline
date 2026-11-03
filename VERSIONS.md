# Versions

Each version is scored on the same case set and the same two models as the one before, and compared case by case.

## v1.0: the baseline

Prompt v1.0, pipeline 1.0.0. Title read in batches of up to 25 rows; the cache marker on the system prompt.

| Model | Code cases | Titles | Floor flips | Gates | Passed | Cost | Result |
|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | 20 of 20 | 20 of 22 | 2 | 3 of 3 | no | US$0.0007 | [N202611032024](eval/results/N202611032024-haiku-5-5.json), 3 Nov 2026 |
| claude-opus-5-5, high | 20 of 20 | 22 of 22 | 0 | 3 of 3 | yes | US$0.0401 | [N202611032026](eval/results/N202611032026-opus-5-5-high.json), 3 Nov 2026 |

Both baseline rows are scored with checker 2. Every result file names its checker in `checker_version`.

claude-haiku-5-5 missed on two seniorities, both read as unknown and so below the floor: Chief of Staff (T14) and Director-elect (T13). Its reason for Director-elect was that no function is named, so it let a function it could not read decide the seniority as well. Every function was right, and the title count met the bar; the floor flips did not. Against the first run (checker 1), Head of Technology and Head of People came back right and Director-elect went wrong: two runs of the same model on the same round missed on different titles. Chief of Staff missed both times.

claude-opus-5-5 at high effort matched every title and passed. On the titles haiku missed it read Chief of Staff as director ("chief does not set level"), Director-elect as director with function unknown (the seniority and the function judged apart), and Head of Technology and Head of People as vp. It cost about 56 times as much as haiku for the round, most of it output.

**The smallest passing model on v1.0 is claude-opus-5-5 at high effort.**

### Kept as history: scored with checker 1

| Model | Code cases | Titles | Floor flips | Gates | Passed | Cost | Result |
|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | 15 of 20 | 19 of 22 | 3 | 3 of 3 | no | US$0.0006 | [N202611032013](eval/results/N202611032013-haiku-5-5.json), 3 Nov 2026 |

This run read Head of Technology, Head of People and Chief of Staff as unknown, so all three fell below the floor; every function was right. It is not part of the baseline. Its result file carries `"checker_version": "1"` and a note saying so; no score in it was changed.

**Why the checker changed.** Checker 1 scored the code cases on the model's own run. The three rows the model put below the floor never reached Stages 4 and 5, so five code cases (C02, C16, C18, C19, C20) missed with no rule in code failing: one model miss was counted twice, once as titles and again as code. That reads as the code being wrong, against the build's first claim that rules live in code. Checker 2, from 3 Nov 2026, scores the code cases on a second run of the round in which a scripted stand-in reads the titles, so they test code alone, and the model's miss counts once, in the title cases. The model's own run is still reported, with its stop counts beside the score. The bar did not change.

## v1.1: one answer per distinct title

Prompt v1.1, pipeline 1.1.0, checker 2. Built 3 Nov 2026 after the v1.0 baseline.

| Model | Code cases | Titles | Floor flips | Gates | Passed | Cost | Result |
|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | 21 of 21 | 22 of 22 | 0 | 3 of 3 | yes | US$0.0010 | [N202611032037](eval/results/N202611032037-haiku-5-5.json), 3 Nov 2026 |
| claude-haiku-5-5, rerun | 21 of 21 | 22 of 22 | 0 | 3 of 3 | yes | US$0.0010 | [N202611032125](eval/results/N202611032125-haiku-5-5.json), 3 Nov 2026 |
| claude-haiku-5-5, rerun | 21 of 21 | 22 of 22 | 0 | 3 of 3 | yes | US$0.0009 | [N202611032126](eval/results/N202611032126-haiku-5-5.json), 3 Nov 2026 |
| claude-haiku-5-5, rerun | 21 of 21 | 22 of 22 | 0 | 3 of 3 | yes | US$0.0009 | [N202611032128](eval/results/N202611032128-haiku-5-5.json), 3 Nov 2026 |
| claude-opus-5-5, high | 21 of 21 | 22 of 22 | 0 | 3 of 3 | yes | US$0.0358 | [N202611032050](eval/results/N202611032050-opus-5-5-high.json), 3 Nov 2026 |

claude-opus-5-5 at high effort against v1.0: no case changed state, and every one of the 22 titles got the same seniority and function as on v1.0. Without the company it read fewer input tokens (547 against 881) and wrote fewer output tokens (1,486 against 1,630), so the run cost about a tenth less (US$0.0358 against US$0.0401).

**The smallest passing model on v1.1 is claude-haiku-5-5, on four runs of four.** After its first pass it was run three more times on the same code, because its answers had moved between runs on v1.0. All four passed, and all four gave every one of the 22 titles the same seniority and function. claude-opus-5-5 at high effort passed both versions.

claude-haiku-5-5 against v1.0: two cases changed state, both from missed to matched. T13 Director-elect was read as director with function unknown, the two judged apart this time. T14 Chief of Staff was read as director ("not a top officer"). Head of Technology and Head of People came back as vp. C21 matched; it has no v1.0 result. Input tokens fell from 881 to 547 without the company; output rose from 1,045 to 1,648, so the run cost more (US$0.0010 against US$0.0007).

What made the difference is not settled. Every title in the case round is distinct, so deduplication did not touch it; what changed for the model is the request without the company, and the prompt lines that describe it. On v1.0 two haiku runs missed on different titles; on v1.1 four runs answered identically. That points at the request, but v1.0 had only two runs, so it is a pointer and not a proof.

**What changed.** Titles are deduplicated before the model call (P2): each distinct title is asked once, and its answer is given to every row that carries it, so the same title can never get two answers in one run. Stop 3 and the run record still list every row, with the title key and the answer its title received.

Why: on the 120 row demo round (3 Nov 2026, claude-haiku-5-5) the same title came back with different seniorities in different batches. Chief of Staff was read as c_suite, director and staff, so some of its rows passed the floor and some did not. Head of Technology was read as director, vp and unknown.

Decided before the build:

- **The same title** is the redacted title with spaces collapsed, compared without case. Two titles that differ only by a redacted name are the same title. The first row's text is the one sent.
- **The company is no longer sent.** A request entry holds a title key and the title, nothing else.
- **The case round is unchanged**, so v1.1 compares with v1.0 on the same 42 cases. A new code case, C21, runs `data/round_repeats.csv` (eight rows, four distinct titles) with the scripted stand-in and checks each title is asked once and every row carrying it gets that answer. From v1.1 there are 43 cases; C21 has no v1.0 result to compare.

**The prompt.** v1.1 changes four lines of v1.0 and no guidance: the version line, "a row key, the company name and the job title" became "a title key and the job title", and the answer format and its closing rule name title keys instead of row keys. The seniority and function definitions are word for word the same. The v1.0 prompt is kept unchanged in [prompts/v1.0.md](prompts/v1.0.md); the pipeline reads only `prompts/title_read.md`.

What it will not do: make an answer right. It makes every row with that title share one answer, right or wrong. In the case round every title sent is already distinct, so on the 22 title cases v1.1 can only differ from v1.0 through the request no longer carrying the company, and through the model's own variation from run to run.
