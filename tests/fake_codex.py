"""Stands in for `codex exec` in tests. FAKE_MODE picks how the agent behaves: honestly, or one of the cheats.
FAKE_REVIEW picks what the second AI says about the checks: ok, missing (a part of the request is untested) or garbage."""
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

if "You review acceptance checks" in prompt:
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
    if mode == "regress":  # adds multiply, and breaks add in a way the project's own tests don't notice
        source = calc.read_text(encoding="utf-8").replace("return a + b", "return a + b if a == b else 0")
        calc.write_text(source + "\n\ndef multiply(a, b):\n    return a * b\n", encoding="utf-8")
    reply = "Fixed the bug in calc.py: add now returns a + b."
reply_file.write_text(reply, encoding="utf-8")
