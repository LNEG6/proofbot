"""End-to-end tests with a fake Codex and a fake WhatsApp server. Run: python tests/test_bot.py"""
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import proof  # noqa: E402
import readings  # noqa: E402
import switchlink  # noqa: E402
import whatsapp_bot  # noqa: E402

CALC = "def add(a, b):\n    return a - b\n"
TESTS = """import unittest
import calc


class TestCalc(unittest.TestCase):
    def test_add(self):
        self.assertEqual(calc.add(2, 2), 4)
        self.assertEqual(calc.add(0, 0), 0)
"""


def workspace(root, name):
    folder = root / name
    (folder / "tests").mkdir(parents=True)
    (folder / "calc.py").write_text(CALC, encoding="utf-8")
    (folder / "tests" / "test_calc.py").write_text(TESTS, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(folder)], check=True)
    return folder


def settings(root, folder):
    return proof.Settings(folder, root / "home", codex=f'"{sys.executable}" "{HERE / "fake_codex.py"}"', runner="direct",
                          test_command=f'"{sys.executable}" -m unittest discover -s tests -q')


def job(root, mode, request="Fix add in calc.py so add(2, 3) returns 5.", name=None):
    os.environ["FAKE_MODE"] = mode
    state, report = proof.run_job(settings(root, workspace(root, name or mode)), request)
    return state, report


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)

    # 1. An honest agent: checks fail first, pass after, nothing suspicious.
    state, report = job(root, "honest")
    assert state["verdict"] == "DONE AND PROVEN", report
    assert report.startswith("DONE AND PROVEN - job 1\nReceipt P1-"), report
    for line in ("- calc.py: +1 -1", "PROOF 1: DO THE CHECKS MATCH WHAT YOU ASKED?",
                 'ok "Fix add in calc.py so add(2, 3) returns 5.": check_add.py',
                 "PROOF 2: CHECKS WRITTEN AND SEALED BEFORE THE WORK",
                 "PASS check_add.py: add(2, 3) returns 5, as the owner asked. (failed before, passes now)",
                 "before: FAIL (exit 1), after: pass (exit 0)", "ok sealed checks untouched; the harness ran its own copy",
                 "ok every file the agent names was really changed", "PROOF 3: YOUR TEST SUITE, RUN BY THE HARNESS",
                 "PROOF 4: REQUIREMENTS PROVEN IN EARLIER JOBS\n- none yet\n"
                 "Added to the library, so every later job must keep them passing: check_add.py",
                 "PROOF 5: LOOPHOLE SCAN", "THIS PROOF RELIES ON\n"
                 "- a second AI, not you, judged that the checks match your request\n"
                 "- check_add.py tried chosen inputs, not every input in a domain\n"
                 "- the checks and tests ran without a sandbox, with your full access"):
        assert line in report, (line, report)
    honest = state
    print("PASS: honest work is DONE AND PROVEN, with every check shown.")

    # 2. Each way of faking it.
    expectations = {
        "lazy": ("NOT DONE", ["FAIL no project files changed", "WARN the agent says it changed calc.py, but they are unchanged",
                              "FAIL check_add.py still fails"]),
        "cheat_checks": ("NOT DONE", ["FAIL sealed checks edited or deleted by the agent: check_add.py",
                                      "FAIL check_add.py still fails"]),
        "skip_tests": ("NOT DONE", ['FAIL skip or only markers added: tests/test_calc.py: @unittest.skip("flaky")',
                                    "WARN existing tests edited, read them: tests/test_calc.py"]),
        "weaken": ("NOT DONE", ["FAIL assertions removed from tests: tests/test_calc.py (-1)"]),
        "vacuous": ("UNPROVEN", ["WARN already passed before any work, so they prove nothing: check_add.py"]),
    }
    for mode, (want, lines) in expectations.items():
        state, report = job(root, mode)
        lazy_like = mode == "lazy" and "Fixed" in state["claim"]
        assert state["verdict"] == want, (mode, report)
        for line in lines:
            assert line in report, (mode, line, report)
    print("PASS: lazy claim, edited sealed check, skipped test, weakened test and an empty check are all caught.")

    # 2b. Misunderstandings: a second AI compares the sealed checks with the request before the work starts.
    os.environ["FAKE_REVIEW"] = "missing"
    state, report = job(root, "honest", name="missing_part", request="Fix add in calc.py so add(2, 3) returns 5, "
                        "and add a multiply(a, b) function that returns the product.")
    assert state["verdict"] == "UNPROVEN", report
    assert 'MISSING "add a multiply(a, b) function that returns the product": no check tests this.' in report, report
    assert (root / "home" / "jobs" / str(state["job"]) / "checks-fix-reply.txt").exists(), "no chance to fix the checks"
    os.environ["FAKE_REVIEW"] = "garbage"
    state, report = job(root, "honest", name="unreadable_review")
    assert state["verdict"] == "DONE, READ THE WARNINGS", report
    assert "WARN nothing checked the checks against your request: the reviewer's answer could not be read" in report
    os.environ["FAKE_REVIEW"] = "narrow"
    state, report = job(root, "honest", name="narrow_check")
    assert state["verdict"] == "DONE, READ THE WARNINGS", report
    assert 'NARROW "Fix add in calc.py so add(2, 3) returns 5.": check_add.py tries too few inputs' in report, report
    assert "- some parts are proven only for a few example inputs" in report, report
    os.environ["FAKE_REVIEW"] = "ok"
    print("PASS: a part of the request with no check is UNPROVEN, an example-only check is flagged, "
          "and an unreadable review is never a pass.")

    # 2c. The proven library: a later job that breaks an earlier proven requirement is NOT DONE,
    # even when the project's own tests still pass.
    folder = workspace(root, "library")
    os.environ["FAKE_MODE"] = "honest"
    first, _ = proof.run_job(settings(root, folder), "Fix add in calc.py so add(2, 3) returns 5.")
    assert first["verdict"] == "DONE AND PROVEN" and first["library_added"] == ["check_add.py"], first
    os.environ["FAKE_MODE"] = "regress"
    state, report = proof.run_job(settings(root, folder), "Add a multiply(a, b) function to calc.py.")
    assert state["verdict"] == "NOT DONE", report
    assert state["suite_after"]["ok"], "the regression must slip past the project's own tests"
    assert f"FAIL check_add.py from job {first['job']}: add(2, 3) returns 5, as the owner asked. (broken by this job)" \
        in report, report
    assert f"FAIL broke requirements proven in earlier jobs: check_add.py from job {first['job']}" in report, report
    print("PASS: breaking a requirement proven in an earlier job is NOT DONE, even when your tests still pass.")

    # 2d. Proof by exhaustion: the harness tries every input combination and maps each one to its output.
    folder = workspace(root, "exhaustive")
    exhaustive = settings(root, folder)
    source = (b'"""add(a, b) == a + b for every a, b in -10..10."""\nimport calc\n'
              b'DOMAIN = {"a": range(-10, 11), "b": range(-10, 11)}\n'
              b'def run(a, b):\n    return calc.add(a, b)\n'
              b'def expected(a, b):\n    return a + b\n')
    result = proof.run_check(exhaustive, source, "check_add.py")
    assert not result["ok"] and result["exhaustive"]["counterexample"] == "a=-10, b=-10: got 0, expected -20", result
    (folder / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    result = proof.run_check(exhaustive, source, "check_add.py")
    assert result["ok"] and result["exhaustive"]["total"] == 441, result
    assert result["exhaustive"]["domain"] == "a -10..10, b -10..10", result
    assert "all 441 inputs tried: a -10..10, b -10..10, every output as expected (map " in proof.exhaustive_note(result)
    print("PASS: proof by exhaustion tries every input, maps every output and names the first counterexample.")

    # 2e. What did you mean? Readers are spread apart on purpose, code compares them, and a person settles the rest.
    REQUEST = "Members get 10% off orders over $50, and coupons don't stack."

    def shop(name, mode, ask=None, readers="split"):
        os.environ["FAKE_MODE"], os.environ["FAKE_READERS"] = mode, readers
        folder = workspace(root, name)
        (folder / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")  # the suite starts green
        (folder / "shop.py").write_text("def price(subtotal, member, coupon):\n    return subtotal\n", encoding="utf-8")
        return proof.run_job(settings(root, folder), REQUEST, ask=ask)

    state, report = shop("shop_open", "shop")  # nobody to ask
    assert state["verdict"] == "UNPROVEN", report
    assert "check_price.py: 2 meaning(s) across all 12 inputs" in report and "(compared by the harness, not by an AI)" in report, report
    assert "OPEN q1: A member uses a 5% coupon on $100. What do they pay?" in report, report
    assert "$95: the coupon replaces it" in report, report

    asked = []

    def pick_b(text):
        asked.append(text)
        return "B"

    state, report = shop("shop_answered", "shop", pick_b)
    assert len(asked) == 1 and state["verdict"] == "DONE AND PROVEN", report
    assert "YOU DECIDED (owner): A member uses a 5% coupon on $100. What do they pay? $95: the coupon replaces it" in report, report
    assert "ok does what you decided:" in report, report
    assert "readers agreeing on one meaning makes a misunderstanding less likely, not impossible" in report, report
    decisions = proof.load_decisions(settings(root, Path(state["workspace"])))
    assert decisions and "$95" in decisions[0]["said"], decisions
    verdict_text = proof.verify(settings(root, Path(state["workspace"])), state["job"], state["receipt"], report)
    assert verdict_text[0], verdict_text[1]

    state, report = shop("shop_stubborn", "shop_stubborn", lambda text: "B")  # keeps its own reading after the answer
    assert state["verdict"] in ("NOT DONE", "UNPROVEN"), report
    assert "still disagrees with your answer" in report, report

    state, report = shop("shop_ignore", "shop_ignore", lambda text: "B")  # updates the check, then builds the old thing
    assert state["verdict"] == "NOT DONE", report
    assert "FAIL does not do what you decided" in report, report
    assert proof.load_decisions(settings(root, Path(state["workspace"]))), "an answer stands even when the job fails"

    state, report = shop("shop_clear", "shop", lambda text: 1 / 0, readers="agree")  # one meaning: nobody is bothered
    assert state["verdict"] == "DONE AND PROVEN" and "check_price.py: 1 meaning(s)" in report, report

    os.environ["FAKE_READERS"] = "agree"
    state, report = job(root, "tautology", request="Add a multiply(a, b) function to calc.py.")  # compares the code with itself
    assert state["verdict"] == "NOT DONE", report
    assert "expected() fails on every input" in report and "in separate processes" in report, report

    os.environ["FAKE_READERS"] = "words"
    state, report = job(root, "honest", request="Clean up the logs.", name="words")
    assert state["verdict"] == "UNPROVEN" and "OPEN q1: Delete old logs, or just tidy them?" in report, report
    assert "an AI compared the readings in words" in report, report
    os.environ["FAKE_READERS"] = "agree"

    silly = {"check": "check_x.py", "ask": "add(2, 0)?", "worth": False, "why": "5 is not a sum.", "options": [
        {"label": "A", "readers": ["agent"]}, {"label": "B", "readers": ["literal", "intent"]}]}
    item = {"check": "check_x.py", "text": "def expected(a):\n    return 5\n", "form": {}, "domain": {"a": [1]}}
    original = readings.last_check_rows
    readings.last_check_rows = lambda think, request, settled, assumed, questions: questions[0].update(
        worth=False, why="5 is not a sum.")
    found = readings.read_request(
        "Fix add.", [], [("check_x.py", b'"""x"""\nDOMAIN = {"a": [1]}\ndef run(a):\n    return a\ndef expected(a):\n    return 5\n')],
        think=lambda lens, prompt: f"### check_x.py\nASSUMES: {lens}\n```python\nEXTRA = {{}}\ndef expected(a):\n    return a\n```",
        probe=lambda name, text, inputs, function: {"function": True, "domain": {"a": [1]}, "outputs": [5] * len(inputs or [])},
        probe_reader=lambda name, text, inputs: {"function": True, "outputs": [1] * len(inputs or [])})
    readings.last_check_rows = original
    assert found["conflicts"] and "every reader disagrees with the agent's check" in found["conflicts"][0], found
    assert not found["questions"] and found["dropped"], found

    # A clear request can undo what a teammate decided. No agent can ask about a decision it can't see.
    BEST_CHECK = ('"""Always give the biggest discount."""\nimport shop\n\n'
                  'DOMAIN = {"subtotal": [40, 100], "member": [False, True], "coupon": [0, 5, 20]}\n\n\n'
                  'def run(subtotal, member, coupon):\n    return shop.price(subtotal, member, coupon)\n\n\n'
                  'def expected(subtotal, member, coupon):\n    pct = 10 if member and subtotal > 50 else 0\n'
                  '    return round(subtotal * (1 - max(pct, coupon) / 100), 2)\n')

    def team(name, answer):
        os.environ["FAKE_MODE"], os.environ["FAKE_READERS"] = "shop", "split"
        folder = workspace(root, name)
        (folder / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (folder / "shop.py").write_text("def price(subtotal, member, coupon):\n    return subtotal\n", encoding="utf-8")
        shared = settings(root, folder)
        first, _ = proof.run_job(shared, REQUEST, ask=lambda text: "B")
        assert first["verdict"] == "DONE AND PROVEN", first["verdict"]
        os.environ["FAKE_READERS"] = "agree"
        number = proof.begin(shared, "Make sure customers always get the biggest discount.", who="sam")
        (folder / "proof_checks" / "check_price.py").write_text(BEST_CHECK, encoding="utf-8")
        proof.seal(shared, number)
        state = proof.load_state(proof.job_dir(shared, number))
        questions = proof.open_questions(state)
        assert questions and questions[0]["id"] == "d1", questions
        assert "goes against what owner decided" in questions[0]["ask"] and questions[0]["owner"] == "owner", questions
        assert "(for owner)" in readings.question_text(questions[0]), questions
        proof.answer_question(shared, number, "d1", answer, "owner")
        return shared, folder, number

    shared, folder, number = team("team_change", "B")  # the person who decided agrees to change it
    assert [entry["job"] for entry in proof.load_decisions(shared)] == [int(number)], "the old decision must be gone"
    assert not proof.load_library(shared), "its old proof must stop binding the workspace"
    proof.seal(shared, number)
    (folder / "shop.py").write_text("def price(subtotal, member, coupon):\n    pct = 10 if member and subtotal > 50 else 0\n"
                                    "    return round(subtotal * (1 - max(pct, coupon) / 100), 2)\n", encoding="utf-8")
    state, report = proof.finish(shared, number, "Changed shop.py.")
    assert state["verdict"].startswith("DONE"), report
    assert "Changed what owner decided in job" in report, report

    shared, folder, number = team("team_keep", "A")  # the decision stands, so the new check has to change
    assert "owner decided, in job" in proof.decisions_text(shared), proof.decisions_text(shared)
    proof.seal(shared, number)
    state = proof.load_state(proof.job_dir(shared, number))
    assert "still disagrees with your answer" in " ".join(state["readings"]["conflicts"]), state["readings"]
    assert proof.verdict({**state, "scan": []}) == "UNPROVEN", state["readings"]
    assert proof.load_decisions(shared), "a kept decision stays"
    print("PASS: a clear request that goes against a teammate's decision stops before any work, goes to that "
          "teammate, and can be kept or changed.")

    # A correction is a job, so it can't end in an explanation, and it binds what comes after it.
    os.environ["FAKE_MODE"], os.environ["FAKE_READERS"] = "honest", "agree"
    corrected = settings(root, workspace(root, "correction"))
    state, report = proof.run_job(corrected, "Fix add in calc.py so add(2, 3) returns 5.", correction=True)
    assert state["verdict"] == "DONE AND PROVEN", report
    assert state["library_added"] == ["check_add.py"], "the correction must join the library"
    said = [entry["said"] for entry in proof.load_decisions(corrected)]
    assert said == ["Correction: Fix add in calc.py so add(2, 3) returns 5."], said
    later = proof.checks_prompt("Add subtract to calc.py.", said)
    assert "These bind you" in later and "Correction: Fix add" in later, later
    assert "These bind you" in proof.work_prompt("Add subtract.", ["check_x.py"], said)
    assert "Fix the whole kind of" in proof.checks_prompt("Stop doing that.", correction=True)
    assert "These bind you" not in proof.checks_prompt("Add subtract to calc.py.")
    assert 'keep the description but lose the thing are "wrong"' in proof.review_prompt("A chart, spread out.", [])

    full = {"ok": True, "questions": [], "conflicts": ["x"], "dropped": [
        {"id": "q1", "worth": False, "why": "you have already answered enough questions on this job"}, {"id": "q2", "worth": False, "why": "silly"}]}
    readings.promote(full, 3)
    assert not full["questions"], "the limit is three for the whole job"
    full = {"ok": True, "questions": [], "conflicts": ["x"], "dropped": [{"id": "q2", "worth": False, "why": "silly"}]}
    assert [item["id"] for item in readings.promote(full, 1)["questions"]] == ["q2"]

    many = {"ok": True, "questions": [{"id": f"q{n}", "worth": True} for n in range(4)], "dropped": []}
    kept = readings.keep_to_budget(many, 2)
    assert [item["id"] for item in kept["questions"]] == ["q0"] and len(kept["dropped"]) == 3, kept
    assert "answered enough questions" in kept["dropped"][0]["why"], kept

    rows = [{"x": 1}, {"x": 2}, {"x": 3}]
    vectors = {"a": [1, 2, 3], "b": [1, 2, 9], "c": [0, 2, 9]}
    groups = readings.group_readers(vectors)
    assert len(groups) == 3 and readings.differing(rows, vectors) == [0, 2]
    assert sorted(readings.pick_rows(vectors, groups, [0, 2])) == [0, 2], "two inputs tell three meanings apart"
    assert len(readings.group_readers({"a": [1.0], "b": [1.0]})) == 1
    print("PASS: a request with two meanings stops for a question, your answer binds the checks and the code, "
          "a clear request asks nothing, and a check that leans on the code is caught.")

    # 2f. Cheating from inside the code under test: each stays wrong, and each used to get a DONE AND PROVEN.
    os.environ["FAKE_READERS"] = "agree"
    CHECK = ('"""add(a, b) == a + b."""\nimport calc\nDOMAIN = {"a": range(-5, 6), "b": range(-5, 6)}\n'
             'def run(a, b):\n    return calc.add(a, b)\ndef expected(a, b):\n    return a + b\n')
    WRONG = "def add(a, b):\n    return a + b if (a, b) in ((2, 2), (0, 0)) else a - b\n"
    CHEATS = {
        "exit early": ("import os, sys\nif 'proof_checks' in sys.argv[0]:\n"
                       "    print('PROOFBOT-EXHAUSTIVE {\"total\": 121, \"domain\": \"all\", \"map\": \"beef\"}', flush=True)\n"
                       "    os._exit(0)\n" + WRONG),
        "equals anything": ("class R(int):\n    def __eq__(self, other):\n        return True\n    __hash__ = int.__hash__\n"
                            "def add(a, b):\n    return R(a + b if (a, b) in ((2, 2), (0, 0)) else a - b)\n"),
        "patched loop": "import itertools\nitertools.product = lambda *a: iter(())\n" + WRONG,
    }
    for cheat, code in CHEATS.items():
        folder = workspace(root, "cheat_" + cheat.replace(" ", "_"))
        cheated = settings(root, folder)
        number = proof.begin(cheated, "Fix add in calc.py so it adds any two numbers.")
        (folder / "proof_checks").mkdir()
        (folder / "proof_checks" / "check_add.py").write_text(CHECK, encoding="utf-8")
        proof.seal(cheated, number)
        (folder / "calc.py").write_text(code, encoding="utf-8")
        state, report = proof.finish(cheated, number, "Fixed calc.py.")
        assert state["verdict"] == "NOT DONE", (cheat, report)
        assert "in separate processes" in report, (cheat, report)
    print("PASS: exiting early, forging a line of output, an object that equals anything and a patched loop are all caught.")

    # 2g. Inside a Switch session the harness talks to the room itself, against a fake Switch server here.
    posted, timeline = [], []

    class FakeSwitch(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            allowed = self.headers.get("Authorization") == "Bearer swlr_test"
            if self.path == "/agents/a1/message":
                posted.append(body)
                result = {"ok": True}
            elif self.path == "/agents/a1/ops/list_rooms":
                result = {"result": [{"room_id": "r1", "name": "proof-room"}, {"room_id": "r2", "name": "other"}]}
            elif self.path == "/agents/a1/ops/get_room_detail":
                result = {"result": {"agent_names": ["proof-doer", "proof-referee"], "connected_user_names": ["kim", "sam"]}}
            elif self.path == "/agents/a1/ops/read_context":
                result = {"result": {"threads": [{"root": entry, "replies": []} for entry in timeline]}}
            else:
                allowed = False
            self.send_response(200 if allowed else 403)
            self.end_headers()
            self.wfile.write(json.dumps(result if allowed else {}).encode())

        def log_message(self, *args):
            pass

    fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeSwitch)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    link = {"SWITCH_API_ENDPOINT": f"http://127.0.0.1:{fake.server_address[1]}", "SWITCH_API_TOKEN": "swlr_test", "SWITCH_AGENT_ID": "a1"}

    try:
        switchlink.Room("proof-room", env={})
        raise AssertionError("no session, so no room")
    except switchlink.SwitchError as error:
        assert "isn't running inside a Switch session" in str(error)
    room = switchlink.Room("proof-room", env=link)
    assert room.id == "r1"
    for body, reply, want in (("A", "A", True), ("a.", "A", True), ("@proof-referee A", "A", True), ("A lot of it", "A", False),
                              ("B", "A", False), ("option b", "B", True), ("keep them all please", "keep them", True)):
        assert switchlink.says(body, reply) is want, (body, reply)
    timeline[:] = [{"id": "m1", "kind": "message", "sender_name": "proof-doer", "body": "A", "timestamp": 5000},
                   {"id": "m2", "kind": "message", "sender_name": "kim", "body": "A", "timestamp": 1000},
                   {"id": "m3", "kind": "room_join", "sender_name": "sam", "body": "A", "timestamp": 6000}]
    assert room.confirm("A", 2000) is None, "an agent's word, an old message or a join can't count as an answer"
    timeline.append({"id": "m4", "kind": "message", "sender_name": "kim", "body": "a", "timestamp": 7000})
    assert room.confirm("A", 2000)["id"] == "m4"

    os.environ["FAKE_MODE"], os.environ["FAKE_READERS"] = "shop", "split"
    folder = workspace(root, "direct")
    (folder / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (folder / "shop.py").write_text("def price(subtotal, member, coupon):\n    return subtotal\n", encoding="utf-8")
    (folder / "proof_checks").mkdir()
    (folder / "proof_checks" / "check_price.py").write_text(BEST_CHECK, encoding="utf-8")

    def cli(*args, session=link):
        environment = {**os.environ, **session, "AGENT": "codex", "CHECK_RUNNER": "direct", "REVIEW": "off",
                       "CODEX_COMMAND": f'"{sys.executable}" "{HERE / "fake_codex.py"}"'}
        return subprocess.run([sys.executable, str(HERE.parent / "proof.py"), "--env", str(HERE / "no.env"), "--workspace", str(folder),
                               "--home", str(root / "home_direct"), "--room", "proof-room", *args], capture_output=True, text=True, env=environment)

    number = cli("begin", "Members get 10% off orders over $50, and coupons don't stack.").stdout.split()[-1]
    posted.clear()
    timeline.clear()
    sealed = cli("seal", number)
    assert "Posted to the room by the harness." in sealed.stdout, sealed.stdout + sealed.stderr
    assert posted and posted[0]["room_id"] == "r1" and "WHAT DID YOU MEAN?" in posted[0]["content"], posted
    refused = cli("answer", number, "q1", "B", "--who", "someone an AI made up")
    assert refused.returncode == 1 and "Only a person's answer counts" in refused.stderr, refused
    timeline.append({"id": "m9", "kind": "message", "sender_name": "kim", "body": "B", "timestamp": int(time.time() * 1000) + 1000})
    answered = cli("answer", number, "q1", "B", "--who", "someone an AI made up")
    assert "Recorded from kim:" in answered.stdout, answered.stdout + answered.stderr
    state = proof.load_state(root / "home_direct" / "jobs" / number)
    assert state["answers"][0]["who"] == "kim" and state["answers"][0]["confirmed"] == "m9", state["answers"]
    assert "YOU DECIDED (kim, confirmed by Switch):" in "\n".join(proof.meaning_lines(state)), state["answers"]
    alone = cli("seal", number, session={"SWITCH_API_ENDPOINT": "", "SWITCH_API_TOKEN": "", "SWITCH_AGENT_ID": ""})
    assert alone.returncode == 0 and "WARN not connected to the Switch room" in alone.stdout, alone.stdout + alone.stderr
    down = cli("seal", number, session={**link, "SWITCH_API_ENDPOINT": "http://127.0.0.1:9"})
    assert down.returncode == 0 and "WARN not connected to the Switch room" in down.stdout, down.stdout + down.stderr
    fake.shutdown()
    print("PASS: inside Switch the harness posts its own verdict, only a person's answer counts, the name comes from "
          "Switch, and a room it can't reach never stops a job.")

    # 3. Receipts: genuine, edited message, edited evidence.
    home_settings = settings(root, Path(honest["workspace"]))
    good_report = (root / "home" / "jobs" / "1" / "report.txt").read_text(encoding="utf-8")
    trusted, text = proof.verify(home_settings, 1, honest["receipt"], "Forwarded\n" + good_report, recheck=True)
    assert trusted and "letter for letter" in text and "same result now" in text, text
    trusted, text = proof.verify(home_settings, 1, honest["receipt"], good_report.replace("+1 -1", "+40 -2"))
    assert not trusted and "+40" in text, text
    trusted, text = proof.verify(home_settings, 1, "P1-000000000000")
    assert not trusted and "does not match the evidence" in text, text
    evidence_file = root / "home" / "jobs" / "1" / "evidence.json"
    original = evidence_file.read_text(encoding="utf-8")
    evidence_file.write_text(original.replace('"verdict":"DONE AND PROVEN"', '"verdict":"DONE AND PROVEN!"'), encoding="utf-8")
    trusted, text = proof.verify(home_settings, 1, honest["receipt"])
    assert not trusted, text
    evidence_file.write_text(original, encoding="utf-8")
    print("PASS: receipts verify, and an edited message, made-up receipt or edited evidence is rejected.")

    # 4. The WhatsApp side, against a fake Graph API.
    sent = []

    class FakeGraph(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            sent.append({"path": self.path, "auth": self.headers["Authorization"], **body})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"messages":[{"id":"wamid.x"}]}')

        def log_message(self, *args):
            pass

    graph = ThreadingHTTPServer(("127.0.0.1", 0), FakeGraph)
    threading.Thread(target=graph.serve_forever, daemon=True).start()
    os.environ["FAKE_MODE"] = "honest"
    env = {"WORKSPACE": str(workspace(root, "whatsapp")), "PROOF_HOME": str(root / "home"),
           "CODEX_COMMAND": f'"{sys.executable}" "{HERE / "fake_codex.py"}"', "CHECK_RUNNER": "direct",
           "TEST_COMMAND": f'"{sys.executable}" -m unittest discover -s tests -q', "WHATSAPP_TOKEN": "test-token",
           "PHONE_NUMBER_ID": "1234", "APP_SECRET": "test-secret", "VERIFY_TOKEN": "hello",
           "OWNER_NUMBER": "+65 9123 4567", "GRAPH_BASE": f"http://127.0.0.1:{graph.server_address[1]}"}
    bot, server = whatsapp_bot.serve(env, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def status(url, data=None, headers=None):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers or {}), timeout=10) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()

    assert status(f"{base}/webhook?hub.mode=subscribe&hub.verify_token=hello&hub.challenge=42") == (200, "42")
    assert status(f"{base}/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=42")[0] == 403

    def webhook(sender, text, message_id, secret=b"test-secret"):
        body = json.dumps({"entry": [{"changes": [{"value": {"messages": [
            {"from": sender, "id": message_id, "type": "text", "text": {"body": text}}]}}]}]}).encode()
        signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
        return status(f"{base}/webhook", body, {"X-Hub-Signature-256": signature, "Content-Type": "application/json"})

    assert webhook("6591234567", "Fix add in calc.py", "m0", secret=b"forged")[0] == 403
    assert webhook("6500000000", "delete everything", "m1") == (200, "ok")
    assert webhook("6591234567", "Fix add in calc.py so add(2, 3) returns 5.", "m2") == (200, "ok")
    assert webhook("6591234567", "Fix add in calc.py so add(2, 3) returns 5.", "m2") == (200, "ok")  # Meta retry
    deadline = time.time() + 60
    while time.time() < deadline and not any("Receipt P" in m["text"]["body"] for m in sent):
        time.sleep(0.2)
    bodies = [m["text"]["body"] for m in sent]
    assert all(m["to"] == "6591234567" and m["auth"] == "Bearer test-token" and m["path"] == "/1234/messages" for m in sent)
    assert bodies[0].startswith("On it."), bodies
    final = bodies[-1]
    assert final.startswith("DONE AND PROVEN - job") and len(final) <= 4096, final
    assert sum("Receipt P" in body for body in bodies) == 1, "the retried webhook must not start a second job"
    assert not any("delete everything" in body for body in bodies), "a stranger's message must be ignored"
    number, receipt = final.split(" - job ")[1].split("\n")[0], final.split("Receipt ")[1].split("\n")[0]
    assert webhook("6591234567", f"verify {number} {receipt}", "m3") == (200, "ok")
    deadline = time.time() + 30
    while time.time() < deadline and not sent[-1]["text"]["body"].startswith("VERIFIED"):
        time.sleep(0.2)
    assert sent[-1]["text"]["body"].startswith("VERIFIED"), sent[-1]
    server.shutdown()
    graph.shutdown()
    print("PASS: WhatsApp webhook checks Meta's signature and your number, ignores retries and strangers, "
          "and texts back the proof.")

# 5. The verdict rule in lean/Gate.lean is the one proof.py runs: compare them on every case. Needs Lean, so it's optional.
lean = shutil.which("lean")
if lean:
    table = subprocess.run([lean, "--run", str(HERE.parent / "lean" / "Gate.lean")], capture_output=True, text=True, timeout=300).stdout
    rows = [line.split() for line in table.splitlines() if line[:1] in "01" and len(line.split()) == 7]
    names = {"doneProven": "DONE AND PROVEN", "doneWarnings": "DONE, READ THE WARNINGS", "notDone": "NOT DONE", "unproven": "UNPROVEN"}
    for *flags, lean_says in rows:
        failed, real, gap, question, conflict, warned = [flag == "1" for flag in flags]
        fake = {"scan": [{"level": "FAIL", "text": "x"}] * failed + [{"level": "WARN", "text": "y"}] * warned,
                "checks": [{"before": {"ok": not real}}], "review": {"ok": True, "parts": [{"status": "missing" if gap else "covered"}]},
                "readings": {"questions": [{}] * question, "conflicts": ["z"] * conflict}}
        assert proof.verdict(fake) == names[lean_says], (flags, lean_says, proof.verdict(fake))
    assert len(rows) == 64, table
    print("PASS: the verdict rule proved in lean/Gate.lean matches proof.py on all 64 cases.")
else:
    print("SKIP: Lean isn't installed, so lean/Gate.lean wasn't compared with proof.py.")
