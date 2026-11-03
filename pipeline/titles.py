"""Stage 3, the title read: the one step that needs judgement, so the one step that uses the model.

Names and emails stay here. A request carries a title key and the title, with names and emails redacted (P1).
Each distinct title is asked once and its answer given to every row that carries it (P2), so one title can
never get two answers in a run. Code then checks every answer (M1, M2) and applies the seniority floor (F1).
"""
import json
import re
from pathlib import Path

PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "title_read.md"
SENIORITY = ["c_suite", "vp", "director", "manager", "staff", "unknown"]
FUNCTIONS = ["general_management", "operations", "finance", "people", "technology", "sales", "legal",
             "administration", "other", "unknown"]
FLOOR = {"c_suite", "vp", "director"}  # F1: director and above are kept
BATCH = 25
EMAIL_TEXT = re.compile(r"[^@\s()]+@[^@\s()]+")


def prompt():
    """The system prompt and its version line."""
    text = PROMPT.read_text()
    version = re.search(r"^Version: (\S+)", text, re.M).group(1)
    return re.sub(r"^Version: \S+\n+", "", text).strip(), version


class Model:
    """The Messages API. Every request payload is kept, exactly as sent, so a test can read all of them."""

    def __init__(self, model_id, effort=None, client=None):
        self.id, self.effort, self.client = model_id, effort, client
        self.system, self.version = prompt()
        self.payloads, self.answers = [], []
        self.calls = 0
        self.tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

    def ask(self, titles):
        # The cache marker sits on the system prompt, the part every batch shares, so later batches read it.
        req = {"model": self.id, "max_tokens": 16000,
               "system": [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
               "messages": [{"role": "user", "content": json.dumps({"titles": titles})}]}
        if self.effort:
            req["output_config"] = {"effort": self.effort}
        self.payloads.append(json.loads(json.dumps(req)))
        self.calls += 1
        text, usage = self.respond(req)
        for k in self.tokens:
            self.tokens[k] += usage.get(k, 0)
        self.answers.append(text)
        return text

    def respond(self, req):
        res = self.client.messages.create(**req)
        u = res.usage
        usage = {"input": u.input_tokens or 0, "output": u.output_tokens or 0,
                 "cache_read": u.cache_read_input_tokens or 0, "cache_write": u.cache_creation_input_tokens or 0}
        return "".join(b.text for b in res.content if b.type == "text"), usage


def redact(row):
    """P1: the title as sent. Email shaped text and the row's own first and last name are replaced."""
    text = EMAIL_TEXT.sub("[email]", row["job_title"])
    for name in (row["first_name"], row["last_name"]):
        if name:
            text = re.sub(rf"\b{re.escape(name)}\b", "[name]", text, flags=re.I)
    return " ".join(text.split())


def fold(title):
    """P2: titles that differ only in capitals or spacing are the same title."""
    return title.casefold()


def leaks(payload, rows):
    """The guard before each send: any name or email of the rows in this payload."""
    text = json.dumps(payload).lower()
    found = []
    for r in rows:
        for value in (r["first_name"], r["last_name"]):
            if value and re.search(rf"\b{re.escape(value.lower())}\b", text):
                found.append(f"{r['row_key']}: name")
        if r["email"] and r["email"] in text:
            found.append(f"{r['row_key']}: email")
    return found


def check_answer(sent, text):
    """M1 and M2. Returns the good answers by title key, the problems, and whether the whole batch must be asked again."""
    try:
        answer = json.loads(text[text.index("{"): text.rindex("}") + 1])["titles"]
        assert isinstance(answer, list) and all(isinstance(a, dict) for a in answer)
    except (ValueError, KeyError, TypeError, AssertionError):
        return {}, ["answer is not the JSON object asked for"], True
    by_key = {}
    for a in answer:
        by_key.setdefault(str(a.get("title_key")), []).append(a)
    problems = [f"{k}: not a title key that was sent" for k in by_key if k not in sent]
    good = {}
    for k in sent:
        got = by_key.get(k, [])
        if not got:
            problems.append(f"{k}: no answer")
        elif len(got) > 1:
            problems.append(f"{k}: {len(got)} answers")
        elif got[0].get("seniority") not in SENIORITY:
            problems.append(f"{k}: seniority {got[0].get('seniority')!r} is not an allowed value")
        elif got[0].get("function") not in FUNCTIONS:
            problems.append(f"{k}: function {got[0].get('function')!r} is not an allowed value")
        else:
            a = got[0]
            good[k] = {"seniority": a["seniority"], "function": a["function"], "reason": str(a.get("reason", ""))[:200]}
    return good, problems, any("not a title key" in p for p in problems)


def read_titles(rows, model):
    """Every distinct title read once, in batches. A batch with problems is asked once more, for the titles at
    fault (or all of it when the answer cannot be trusted). Problems left after that are returned, and the
    run halts on them. Returns the answers and the title sent, both by row key."""
    keys, groups, text = {}, {}, {}
    for r in rows:
        title = redact(r)
        tk = keys.setdefault(fold(title), f"t{len(keys) + 1:03d}")
        text.setdefault(tk, title)
        groups.setdefault(tk, []).append(r)
    sent = {r["row_key"]: {"title_key": tk, "title": text[tk]} for tk, group in groups.items() for r in group}
    answers, problems = {}, []
    order = list(groups)
    for i in range(0, len(order), BATCH):
        batch = order[i:i + BATCH]
        good, found, whole = {}, None, True
        for attempt in (1, 2):
            ask = batch if whole else [k for k in batch if k not in good]
            payload = [{"title_key": k, "title": text[k]} for k in ask]
            leaked = leaks(payload, [r for k in ask for r in groups[k]])
            if leaked:
                return {}, [f"privacy guard: {x}" for x in leaked], sent
            got, found, whole = check_answer(ask, model.ask(payload))
            good = got if ask == batch else {**good, **got}
            if not found:
                break
        for k, a in good.items():
            for r in groups[k]:
                answers[r["row_key"]] = a
        problems += [named(p, groups) for p in found]
    return answers, problems, sent


def named(problem, groups):
    """A problem about a title, with the rows that carry it, so the halt at Stop 3 names rows."""
    k = problem.split(":")[0]
    if k not in groups:
        return problem
    return f"{k} ({', '.join(r['row_key'] for r in groups[k])}){problem[len(k):]}"


def above_floor(answer):
    return answer["seniority"] in FLOOR
