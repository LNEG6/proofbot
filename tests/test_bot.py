"""End-to-end tests with a fake Codex and a fake WhatsApp server. Run: python tests/test_bot.py"""
import hashlib
import hmac
import json
import os
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
