"""What did the person actually mean?

AI agents take words too literally, and two AIs asked the same thing tend to make the same silent guess, so a
second opinion stays quiet exactly when it matters. So the readers here are spread apart on purpose:

- literal reads the exact words and adds nothing.
- intent reads for the outcome the person wants.
- rival must find a different reasonable meaning from the one the agent chose, or say there is none.

Each reading is turned into code, then the harness (no AI) runs every reading on every input and groups the ones
that behave the same. Each group is one meaning. If there is one meaning, nobody is bothered. If there are more, the
harness picks the fewest inputs that tell them apart and the last AI words them as questions for the person.
It may say a difference isn't worth asking about, but that is written down in the report. It never picks the answer.

When inputs can't be listed (free text, how a page looks), readers answer in words instead and the last AI compares
them. That comparison is a judgement, not a measurement, and the report says so.
"""
import ast
import itertools
import json
import random
import re
from concurrent.futures import ThreadPoolExecutor

MARK = "PROOFBOT-PROBE "
INPUT_LIMIT = 5000      # past this, inputs are sampled at random with a fixed seed, and the report says so
COLUMN_LIMIT = 400      # most values kept from one input's range
QUESTION_LIMIT = 3      # for a whole job, however many rounds it takes; the rest go in the report

LENSES = {
    "literal": "Read it like a strict lawyer or a computer. Take every word exactly as written and add nothing that "
               "was not said. Where the words leave something open, do the least the words require. Treat examples "
               "as the only cases mentioned.",
    "intent": "Read it like a sensible colleague who knows why the person is asking. Work out the outcome they "
              "actually want. Include what they would obviously expect even though they didn't say it, and treat "
              "their examples as examples of a general rule, not as the whole rule.",
    "rival": "Below is how the agent read the request. Find the most plausible DIFFERENT meaning a reasonable person "
             "could really have had. It must behave differently on at least one realistic input. Do not invent "
             "requirements the words can't support, and do not write something silly. If you honestly believe there "
             "is only one reasonable reading, write NO OTHER READING instead.",
}

SHARED = """You are one of several readers of a request a person sent to a coding agent. People rarely say everything
they mean, and AI agents often take words too literally. Each reader comes at the request from a different side, so
that a harness can compare the readings and find where they really differ. You do not do the task, you run nothing,
and you can't see the other readers.

The request, word for word:
<<<
{request}
>>>
{settled}
How to read it: {lens}
"""

CODE = """
Turn your reading into code. For each function below, write expected(...) with exactly that signature. It returns
the right output for those inputs under your reading, or raises ValueError if your reading says the input should be
refused. Standard library only. Do not import the project: it is not available to you.

Also define EXTRA, a dict of input name -> list of more values worth trying, if the inputs listed miss something that
matters under your reading: a boundary, an empty value, a negative number, another option. Plain numbers, strings,
booleans or None only. Use EXTRA = {{}} if nothing is missing.

{shapes}

Reply in exactly this format, one block per check, and nothing else:

### check_name.py
ASSUMES: one plain sentence saying how you read the request
```python
EXTRA = {{}}
def expected(...):
    ...
```
"""

WORDS = """
This task can't be listed as inputs and outputs, so give your reading in words.{claim}
Reply in exactly this format and nothing else:

ASSUMES: one plain sentence saying how you read the request
DELIVERS: one plain sentence saying what the person would have at the end
LEAVES ALONE: one plain sentence saying what you would not touch
"""

LAST_CHECK = """You are the last check before an AI agent starts work on a person's request. Several readers read the
request from different sides.{how}

The request, word for word:
<<<
{request}
>>>
{settled}
What the readers assumed:
{assumed}

{task}

Never choose the answer yourself: only the person can say what they meant. Keep questions short and in everyday words
someone non-technical could answer. Reply with JSON only, no other text:
{shape}"""

ROW_TASK = """The harness found these differences. For each one, decide whether two or more options are things a
reasonable person could really mean, and whether the answer changes what gets built. If so, keep the question, even if
another option is silly: leave a silly option out of "options" and rewrite the rest in plain words, keeping their letters.
Set worth_asking to false, and say why, only when just one option is reasonable.

{questions}"""

ROW_SHAPE = """{{"questions": [{{"id": "q1", "worth_asking": true, "ask": "...", "options": {{"A": "...", "B": "..."}}, "why": ""}}]}}"""

WORD_TASK = """Decide whether these readings would lead to work the person would see as different. If they would, write
one question per real difference, with one option per reading. If they all amount to the same work, reply with an empty
list. Ignore differences in wording. Ask only about what the request itself leaves open, not about other places, later
work or edge cases it doesn't touch. Most requests need no question, and none need more than two."""

WORD_SHAPE = """{{"questions": [{{"ask": "...", "options": {{"A": "...", "B": "..."}}}}]}}"""

# Runs in its own process: it loads a check's definitions but none of its top-level assertions, so a request's example
# can't stop a reading being compared before the work is done, then calls one function on a list of inputs.
PROBE = r'''
import ast, json, sys
path = sys.argv[1]
sys.argv = [path]
job = json.load(sys.stdin.buffer)
space = {"__name__": "proofbot_probe", "__file__": path, "__builtins__": __builtins__}
keep = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.ClassDef)
for node in ast.parse(job["source"]).body:
    if isinstance(node, keep):
        try:
            exec(compile(ast.Module([node], []), path, "exec"), space)
        except Exception:
            pass

def plain(value):
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 9)
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    return repr(value)

def column(values):
    values = list(values)
    if len(values) > LIMIT:
        step = len(values) / LIMIT
        values = [values[int(index * step)] for index in range(LIMIT)] + [values[-1]]
    return [value for value in values if value is None or isinstance(value, (bool, int, float, str))]

function = space.get(job.get("function") or "expected")
out = {"function": callable(function)}
for key in ("DOMAIN", "EXTRA"):
    given = space.get(key)
    if isinstance(given, dict):
        out[key.lower()] = {str(name): column(values) for name, values in given.items()}
outputs = []
for inputs in job.get("inputs") or []:
    try:
        outputs.append(plain(function(**inputs)))
    except Exception:
        outputs.append({"raises": True})
out["outputs"] = outputs
print("MARK" + json.dumps(out), flush=True)
'''.replace("MARK", MARK).replace("LIMIT", str(COLUMN_LIMIT))


def short(value, size=220):
    return " ".join(str(value or "").split())[:size]


def key(value):
    return json.dumps(value, sort_keys=True)


def says(value):
    """An output, the way a person would read it."""
    return "refuse with an error" if value == {"raises": True} else repr(value)


def shape(text):
    """The parts of a check a reader may see: what gets called and how, not how the agent read the request."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    named = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    if "expected" not in named:
        return None
    run = ast.get_source_segment(text, named["run"]) if "run" in named else ""
    return {"signature": f"def expected({ast.unparse(named['expected'].args)}):", "run": run,
            "expected": ast.get_source_segment(text, named["expected"])}


def describe_shapes(statements, show_reading):
    parts = []
    for item in statements:
        domain = ", ".join(f"{name}: {values[:12]!r}{' and more' if len(values) > 12 else ''}"
                           for name, values in item["domain"].items())
        parts.append(f"=== {item['check']} ===\nHow the code gets called:\n{item['form']['run'] or '(not shown)'}\n"
                     f"Inputs listed: {domain}\n"
                     + (f"How the agent read it:\n{item['form']['expected']}" if show_reading
                        else f"Write:\n{item['form']['signature']}"))
    return "\n\n".join(parts)


def reader_prompt(lens, request, settled, statements, claim):
    head = SHARED.format(request=request, settled=settled_block(settled), lens=LENSES[lens])
    if statements:
        return head + CODE.format(shapes=describe_shapes(statements, lens == "rival"))
    told = f"\nHow the agent read it: {claim}" if lens == "rival" and claim else ""
    return head + WORDS.format(claim=told)


def settled_block(settled):
    if not settled:
        return ""
    return "\nAlready settled by the person, so treat these as facts:\n" + "\n".join(f"- {line}" for line in settled) + "\n"


def parse_code(reply, names):
    found = {}
    pieces = re.split(r"^#{2,4}\s*`?([\w.-]+\.py)`?\s*$", reply, flags=re.M)
    for name, body in zip(pieces[1::2], pieces[2::2]):
        if name not in names:
            continue
        code = re.search(r"```(?:python|py)?[ \t]*\n(.*?)```", body, re.S)
        if code is None:
            if "NO OTHER READING" in body.upper():
                found[name] = {"same": True}
            continue
        assumes = re.search(r"^ASSUMES:\s*(.+)$", body, re.M)
        found[name] = {"source": code.group(1), "assumes": short(assumes.group(1) if assumes else "")}
    return found


def parse_words(reply):
    if "NO OTHER READING" in reply.upper():
        return {"same": True}
    found = {}
    for label, field in (("ASSUMES", "assumes"), ("DELIVERS", "delivers"), ("LEAVES ALONE", "leaves")):
        match = re.search(rf"^{label}:\s*(.+)$", reply, re.M)
        if match:
            found[field] = short(match.group(1))
    return found if "assumes" in found else None


def same_kind(value, column):
    """Extra inputs must be the same kind as the listed ones. Text given to a number input, or half a day given to a
    whole number of days, finds a difference nobody asked about, and every false alarm costs a person's attention."""
    kinds = {type(item) for item in column}
    if type(value) in kinds:
        return True
    return isinstance(value, int) and not isinstance(value, bool) and float in kinds


def make_rows(columns, seed):
    """Every combination, or a fixed random sample when there are too many. Returns rows and the true total."""
    names = list(columns)
    total = 1
    for values in columns.values():
        total *= max(len(values), 1)
    if not names or total == 0:
        return [], 0
    if total <= INPUT_LIMIT:
        return [dict(zip(names, combo)) for combo in itertools.product(*columns.values())], total
    rng = random.Random(seed)
    seen, rows = set(), []
    for _ in range(INPUT_LIMIT * 4):
        row = {name: rng.choice(columns[name]) for name in names}
        mark = key(row)
        if mark not in seen:
            seen.add(mark)
            rows.append(row)
        if len(rows) >= INPUT_LIMIT:
            break
    return rows, total


def group_readers(vectors):
    """Readers that give the same output on every input are one meaning."""
    groups = {}
    for reader, outputs in vectors.items():
        groups.setdefault(key(outputs), []).append(reader)
    return list(groups.values())


def differing(rows, vectors):
    return [index for index in range(len(rows)) if len({key(outputs[index]) for outputs in vectors.values()}) > 1]


def pick_rows(vectors, groups, rows_differ, limit=QUESTION_LIMIT):
    """The fewest inputs that tell the meanings apart, picked greedily: each pick separates the most remaining pairs."""
    leads = [group[0] for group in groups]
    pairs = set(itertools.combinations(range(len(leads)), 2))
    chosen = []
    while pairs and len(chosen) < limit:
        best, split = None, set()
        for index in rows_differ:
            here = {pair for pair in pairs
                    if key(vectors[leads[pair[0]]][index]) != key(vectors[leads[pair[1]]][index])}
            if len(here) > len(split):
                best, split = index, here
        if best is None:
            break
        chosen.append(best)
        pairs -= split
    return chosen


def make_question(number, check, inputs, index, vectors, groups, assumed):
    choices = {}
    for group in groups:
        value = vectors[group[0]][index]
        choices.setdefault(key(value), {"output": value, "readers": []})["readers"] += group
    options = []
    for letter, choice in zip("ABCDEFGH", choices.values()):
        reader = next((name for name in choice["readers"] if assumed.get(name)), None)
        options.append({"label": letter, "output": choice["output"], "says": says(choice["output"]),
                        "readers": choice["readers"], "assumes": assumed.get(reader, "")})
    shown = ", ".join(f"{name}={value!r}" for name, value in inputs.items())
    return {"id": f"q{number}", "check": check, "inputs": inputs, "ask": f"What should happen for {shown}?",
            "options": options, "worth": True}


def keep_to_budget(found, answered, limit=QUESTION_LIMIT):
    """Past the budget for a job, differences go in the report instead of another round of questions."""
    if not found or not found.get("ok"):
        return found
    room = max(limit - answered, 0)
    asked, over = found["questions"][:room], found["questions"][room:]
    for item in over:
        item.update(worth=False, why="you have already answered enough questions on this job")
    found["questions"], found["dropped"] = asked, found["dropped"] + over
    return found


def question_text(question):
    lines = [f"{question['id']}: {question['ask']}"]
    for option in question["options"]:
        lines.append(f"  {option['label']}: {option['says']}")
    return "\n".join(lines)


def parse_json(reply):
    try:
        return json.loads(reply[reply.find("{"):reply.rfind("}") + 1])
    except ValueError:
        return None


def last_check_rows(think, request, settled, assumed, questions):
    """The last AI words the questions and may set one aside. It can't change what the harness measured."""
    listing = "\n\n".join(f"{item['id']}: {item['ask']}\n" + "\n".join(
        f"  {option['label']}: {option['says']} (read this way by {', '.join(option['readers'])})"
        for option in item["options"]) for item in questions)
    prompt = LAST_CHECK.format(how=" A harness ran every reading on every input, so these differences are measured, not "
                                   "guessed.", request=request, settled=settled_block(settled), assumed=assumed,
                               task=ROW_TASK.format(questions=listing), shape=ROW_SHAPE.format())
    data = parse_json(think("last", prompt))
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        return "the last check's answer could not be read, so every difference is shown as measured"
    for item in data["questions"]:
        question = next((entry for entry in questions if isinstance(item, dict) and entry["id"] == item.get("id")), None)
        if question is None:
            continue
        if item.get("worth_asking") is False:
            question.update(worth=False, why=short(item.get("why")))
        if item.get("ask"):
            question["ask"] = short(item["ask"], 240)
        labels = item.get("options") if isinstance(item.get("options"), dict) else {}
        for option in question["options"]:
            if labels.get(option["label"]):
                option["says"] = short(labels[option["label"]], 160)
        kept = [option for option in question["options"] if labels.get(option["label"])]
        if len(kept) >= 2:  # a person only sees what a reasonable person could mean
            question["options"] = [{**option, "label": letter} for letter, option in zip("ABCDEFGH", kept)]
    return None


def last_check_words(think, request, settled, assumed):
    prompt = LAST_CHECK.format(how="", request=request, settled=settled_block(settled), assumed=assumed, task=WORD_TASK,
                               shape=WORD_SHAPE.format())
    data = parse_json(think("last", prompt))
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        return None
    questions = []
    for number, item in enumerate(data["questions"][:QUESTION_LIMIT], 1):
        if isinstance(item, dict) and isinstance(item.get("options"), dict) and len(item["options"]) > 1:
            options = [{"label": str(label), "says": short(text, 160), "readers": [], "assumes": ""}
                       for label, text in item["options"].items()]
            questions.append({"id": f"q{number}", "check": None, "inputs": None, "ask": short(item.get("ask"), 240),
                              "options": options, "worth": True})
    return questions


def compare(item, parsed, probe, probe_reader, pins, failed):
    """Run every reading of one check on every input, with no AI involved, and group what comes back."""
    check, text = item["check"], item["text"]
    columns = {name: list(values) for name, values in item["domain"].items()}
    sources, assumed, agreed = {}, {}, []
    for lens, readings in parsed.items():
        entry = readings.get(check)
        if entry is None:
            failed.append(f"{lens} on {check}: no usable reading came back")
        elif entry.get("same"):
            agreed.append(lens)
        else:
            info = probe_reader(check, entry["source"], None)
            if not info or not info["function"]:
                failed.append(f"{lens} on {check}: its reading would not run")
                continue
            sources[lens], assumed[lens] = entry["source"], entry["assumes"]
            for name, values in (info.get("extra") or {}).items():
                if name in columns:
                    have = {key(value) for value in columns[name]}
                    columns[name] += [value for value in values if key(value) not in have and same_kind(value, columns[name])]
    rows, total = make_rows(columns, key(sorted(columns)) + check)
    mine = [pin for pin in pins if pin.get("check") == check and "output" in pin]
    for pin in mine:
        if pin["inputs"] not in rows:
            rows.append(pin["inputs"])
    agent = probe(check, text, rows, "expected")
    conflicts = []
    if not agent or len(agent["outputs"]) != len(rows):
        return {"check": check, "rows": 0, "total": total, "error": "the agent's reading would not run"}, [], [], None
    vectors = {"agent": agent["outputs"]}
    if rows and all(output == {"raises": True} for output in agent["outputs"]):
        conflicts.append(f"{check}: expected() fails on every input, so it may lean on the code it is meant to test")
    ruled_out = []
    for lens, source in sources.items():
        info = probe_reader(check, source, rows)
        if not info or len(info["outputs"]) != len(rows):
            failed.append(f"{lens} on {check}: its reading would not run")
            continue
        vectors[lens] = info["outputs"]
    for pin in mine:
        index = rows.index(pin["inputs"])
        for reader in list(vectors):
            if key(vectors[reader][index]) != key(pin["output"]):
                if reader == "agent":
                    conflicts.append(f"{check} still disagrees with your answer for "
                                     f"{', '.join(f'{k}={v!r}' for k, v in pin['inputs'].items())}")
                else:
                    ruled_out.append(reader)
                    del vectors[reader]
    groups = group_readers(vectors)
    listed = {name: {key(value) for value in values} for name, values in item["domain"].items()}
    rows_differ = differing(rows, vectors)
    # Ask about inputs the agent listed before ones a reader added, so a person hears about a $100 order, not a -$1 one.
    picks = pick_rows(vectors, groups, sorted(rows_differ, key=lambda index: sum(
        key(value) not in listed[name] for name, value in rows[index].items())))
    return ({"check": check, "rows": len(rows), "total": total, "sampled": len(rows) < total, "meanings": len(groups),
             "differ": len(rows_differ), "groups": groups, "assumed": assumed, "agreed": agreed,
             "ruled_out": sorted(set(ruled_out))},
            conflicts, [(check, rows[index], index, vectors, groups, assumed) for index in picks], None)


def read_request(request, settled, checks, think, probe, probe_reader, pins=(), claim=""):
    """Spread the readers, compare what they mean, and return what the person needs to be asked."""
    statements = []
    for name, source in checks:
        text = source.decode("utf-8", "replace").lstrip("﻿")
        form = shape(text)
        info = probe(name, text, None, "expected") if form else None
        if form and info and info.get("domain"):
            statements.append({"check": name, "text": text, "form": form, "domain": info["domain"]})

    def one(lens):
        try:
            return lens, think(lens, reader_prompt(lens, request, settled, statements, claim))
        except Exception as error:
            return lens, error

    with ThreadPoolExecutor(len(LENSES)) as pool:
        replies = dict(pool.map(one, LENSES))
    failed = [f"{lens}: {type(reply).__name__}" for lens, reply in replies.items() if isinstance(reply, Exception)]
    usable = {lens: reply for lens, reply in replies.items() if not isinstance(reply, Exception)}

    if not statements:
        readers = {lens: parse_words(reply) for lens, reply in usable.items()}
        failed += [f"{lens}: its answer could not be read" for lens, found in readers.items() if found is None]
        readers = {lens: found for lens, found in readers.items() if found}
        distinct = {lens: found for lens, found in readers.items() if not found.get("same")}
        questions = []
        if not usable:
            return {"ok": False, "error": "no reader could run: " + "; ".join(failed)}
        if len(distinct) > 1 or (claim and distinct):
            lines = [f"- {lens}: {found['assumes']} It would deliver: {found.get('delivers', '?')} "
                     f"It would leave alone: {found.get('leaves', '?')}" for lens, found in distinct.items()]
            if claim:
                lines.insert(0, f"- the agent's own checks: {claim}")
            worded = last_check_words(think, request, settled, "\n".join(lines))
            if worded is None:
                failed.append("the last check's answer could not be read")
            questions = worded or []
        return {"ok": True, "mode": "words", "readers": distinct, "questions": questions, "failed": failed,
                "statements": [], "conflicts": [], "dropped": []}

    parsed = {lens: parse_code(reply, [item["check"] for item in statements]) for lens, reply in usable.items()}
    results, conflicts, picks = [], [], []
    for item in statements:
        result, found, chosen, _ = compare(item, parsed, probe, probe_reader, pins, failed)
        results.append(result)
        conflicts += found
        picks += chosen
    questions = [make_question(number, check, inputs, index, vectors, groups, assumed)
                 for number, (check, inputs, index, vectors, groups, assumed) in enumerate(picks[:QUESTION_LIMIT], 1)]
    if questions:
        assumed = "\n".join(f"- {lens}: {text}" for result in results for lens, text in result.get("assumed", {}).items())
        try:
            note = last_check_rows(think, request, settled, assumed or "(none given)", questions)
        except Exception as error:
            note = f"the last check could not run ({type(error).__name__}), so every difference is shown as measured"
        if note:
            failed.append(note)
    # Setting a question aside is fine when the odd reading is a reader's. When the agent stands alone against every
    # reader and nobody will be asked, nothing else would catch it, so its check has to be fixed.
    for item in questions:
        if not item["worth"] and any(option["readers"] == ["agent"] for option in item["options"]):
            conflicts.append(f"{item['check']}: every reader disagrees with the agent's check. {item['ask']} "
                             f"{item.get('why') or ''}".strip())
    return {"ok": True, "mode": "compared", "statements": results, "conflicts": conflicts, "failed": failed,
            "questions": [item for item in questions if item["worth"]],
            "dropped": [item for item in questions if not item["worth"]]}
