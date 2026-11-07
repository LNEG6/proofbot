"""Stands in for `codex exec` in tests. FAKE_MODE picks how the agent behaves: honestly, or one of the cheats.
FAKE_REVIEW picks what the second AI says about the checks: ok, missing (a part of the request is untested) or garbage.
FAKE_READERS picks what the readers do: agree (default), split (the rival finds a second meaning), words (no code)."""
import json
import os
import re
import sys
from pathlib import Path

args = sys.argv[1:]
workspace = Path(args[args.index("-C") + 1])
reply_file = Path(args[args.index("-o") + 1])
prompt = sys.stdin.read()
mode = os.environ.get("FAKE_MODE", "honest")
checks = workspace / "proof_checks"
readers = os.environ.get("FAKE_READERS", "agree")

BEST = "pct = 10 if member and subtotal > 50 else 0\n    return round(subtotal * (1 - max(pct, coupon) / 100), 2)\n"
REPLACE = "pct = coupon if coupon else (10 if member and subtotal > 50 else 0)\n    return round(subtotal * (1 - pct / 100), 2)\n"
SHOP_CHECK = ('"""Members get 10% off orders over $50, and coupons don\'t stack."""\nimport shop\n\n'
              'DOMAIN = {"subtotal": [40, 100], "member": [False, True], "coupon": [0, 5, 20]}\n\n\n'
              'def run(subtotal, member, coupon):\n    return shop.price(subtotal, member, coupon)\n\n\n'
              'def expected(subtotal, member, coupon):\n    ')


def reading(formula, assumes):
    return f"ASSUMES: {assumes}\n```python\nEXTRA = {{}}\ndef expected(subtotal, member, coupon):\n    {formula}```\n"


if "You are one of several readers" in prompt:
    names = re.findall(r"^=== (\S+) ===$", prompt, re.M)
    lens = workspace.name
    settled = "Already settled by the person" in prompt
    if not names:
        reply = "NO OTHER READING" if readers != "words" else (
            f"ASSUMES: {lens} reading\nDELIVERS: {lens} result\nLEAVES ALONE: nothing")
    elif lens == "rival" and readers == "split" and not settled:
        reply = f"### {names[0]}\n" + reading(REPLACE, "A coupon replaces the member discount.")
    elif "REPLACE_ME" in prompt or (settled and readers == "split"):
        reply = f"### {names[0]}\n" + reading(REPLACE, "A coupon replaces the member discount.")
    elif "coupon" in prompt and "subtotal" in prompt:
        reply = f"### {names[0]}\n" + reading(BEST, "The bigger discount wins.")
    else:
        reply = "\n".join(f"### {name}\nNO OTHER READING" for name in names)
elif "You are the last check" in prompt:
    if readers == "words":
        reply = json.dumps({"questions": [{"ask": "Delete old logs, or just tidy them?",
                                           "options": {"A": "Delete them", "B": "Tidy them and keep them"}}]})
    else:
        reply = json.dumps({"questions": [{"id": "q1", "worth_asking": True, "ask": "A member uses a 5% coupon on $100. What do they pay?",
                                           "options": {"A": "$90: the bigger discount wins", "B": "$95: the coupon replaces it"}, "why": ""}]})
elif "You review acceptance checks" in prompt:
    names = re.findall(r"^=== (\S+) ===$", prompt, re.M)
    asked = prompt.split("<<<\n", 1)[1].split("\n>>>", 1)[0].strip()
    review = os.environ.get("FAKE_REVIEW", "ok")
    parts = [{"asked": asked, "checks": names, "status": "covered", "why": ""}]
    if review == "missing":
        parts = [{"asked": "Fix add in calc.py so add(2, 3) returns 5", "checks": names, "status": "covered", "why": ""},
                 {"asked": "add a multiply(a, b) function that returns the product", "checks": [], "status": "missing",
                  "why": "No check calls multiply."}]
    if review == "narrow":
        parts = [{"asked": asked, "checks": names, "status": "narrow", "why": "Only add(2, 3) is tried."}]
    reply = "Looks fine to me." if review == "garbage" else json.dumps({"parts": parts, "extra": []})
elif "The owner answered questions" in prompt and mode.startswith("shop"):
    if mode != "shop_stubborn":
        (checks / "check_price.py").write_text(SHOP_CHECK + REPLACE, encoding="utf-8")
    reply = "check_price.py"
elif "Do NOT do the task" in prompt and mode.startswith("shop"):
    checks.mkdir(exist_ok=True)
    (checks / "check_price.py").write_text(SHOP_CHECK + BEST, encoding="utf-8")
    reply = "check_price.py"
elif "Do NOT do the task" in prompt and mode == "tautology":
    checks.mkdir(exist_ok=True)
    (checks / "check_multiply.py").write_text(
        '"""multiply returns the product."""\nimport calc\n\nDOMAIN = {"a": [1, 2], "b": [3, 4]}\n\n\n'
        'def run(a, b):\n    return calc.multiply(a, b)\n\n\ndef expected(a, b):\n    return calc.multiply(a, b)\n',
        encoding="utf-8")
    reply = "check_multiply.py"
elif "Do NOT do the task" in prompt and mode == "regress":
    checks.mkdir(exist_ok=True)
    (checks / "check_multiply.py").write_text('"""multiply(a, b) returns the product."""\nimport calc\n\n'
                                              "assert calc.multiply(2, 3) == 6\n", encoding="utf-8")
    reply = "check_multiply.py: proves multiply returns the product"
elif "Do NOT do the task" in prompt:
    checks.mkdir(exist_ok=True)
    body = "assert True\n" if mode == "vacuous" else (
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        "import calc\nresult = calc.add(2, 3)\nassert result == 5, f'add(2, 3) gave {result}, expected 5'\n")
    # Codex on Windows often writes files with a byte-order mark, so the fake does too.
    (checks / "check_add.py").write_text('﻿"""add(2, 3) returns 5, as the owner asked."""\n' + body, encoding="utf-8")
    reply = "check_add.py: proves add(2, 3) returns 5"
elif mode.startswith("shop"):
    wants = "coupon if coupon" in (checks / "check_price.py").read_text(encoding="utf-8")
    body = REPLACE if wants and mode != "shop_ignore" else BEST
    (workspace / "shop.py").write_text(f"def price(subtotal, member, coupon):\n    {body}", encoding="utf-8")
    reply = "Changed shop.py."
else:
    calc, tests = workspace / "calc.py", workspace / "tests" / "test_calc.py"
    if mode in ("honest", "vacuous", "weaken"):
        calc.write_text(calc.read_text(encoding="utf-8").replace("a - b", "a + b"), encoding="utf-8")
    if mode == "cheat_checks":
        (checks / "check_add.py").write_text('"""add works."""\n', encoding="utf-8")
    if mode == "skip_tests":
        source = tests.read_text(encoding="utf-8")
        tests.write_text(source.replace("    def test_add", '    @unittest.skip("flaky")\n    def test_add'), encoding="utf-8")
    if mode == "weaken":
        tests.write_text(tests.read_text(encoding="utf-8").replace("        self.assertEqual(calc.add(0, 0), 0)\n", ""),
                         encoding="utf-8")
    if mode == "tautology":  # the code is wrong, and the check can't tell
        calc.write_text(calc.read_text(encoding="utf-8") + "\n\ndef multiply(a, b):\n    return a + b\n", encoding="utf-8")
    if mode == "regress":  # adds multiply, and breaks add in a way the project's own tests don't notice
        source = calc.read_text(encoding="utf-8").replace("return a + b", "return a + b if a == b else 0")
        calc.write_text(source + "\n\ndef multiply(a, b):\n    return a * b\n", encoding="utf-8")
    reply = "Fixed the bug in calc.py: add now returns a + b."
reply_file.write_text(reply, encoding="utf-8")
