"""Scripted agents that go wrong, so you can watch Proofbot catch them.

    python lazy_agent.py team            # a clear request goes against what a teammate decided, and it stops
    python lazy_agent.py meaning         # a request with two meanings: readers split, and a person settles it
    python lazy_agent.py misunderstand   # the agent misreads the task; its own check agrees with it
    python lazy_agent.py everyday        # who may edit or delete a post: every combination tried, whole table shown
    python lazy_agent.py regress         # a later job breaks something proven earlier (the proven library)
    python lazy_agent.py cheat           # the agent edits a test to go green, then forges the verdict
    add --step to wait for Enter between steps, for narrating

Each agent goes through the real harness (proof.py), and the harness writes the report, not the agent.
Every run starts from a fresh copy in project/ and harness-home/, so you can record many takes.
"""
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# In the repo this folder is proofbot/demo; in the original workspace it sits beside coordinator/proofbot.
PROOF = next(path for path in (HERE.parent / "proof.py", HERE.parent / "coordinator" / "proofbot" / "proof.py")
             if path.exists())
PROJECT = HERE / "project"
HOME = HERE / "harness-home"
STEP = "--step" in sys.argv

BUGGY_CALC = "def add(a, b):\n    return a - b\n"
HONEST_TEST = ('import unittest\n\nimport calc\n\n\nclass TestCalc(unittest.TestCase):\n'
               '    def test_add(self):\n        self.assertEqual(calc.add(2, 2), 4)\n\n\n'
               'if __name__ == "__main__":\n    unittest.main()\n')

ENV = {**os.environ, "CHECK_RUNNER": "direct", "PYTHONDONTWRITEBYTECODE": "1", "REVIEW": "on",
       "TEST_COMMAND": f'"{sys.executable}" -m unittest discover -s tests -q'}


def pause(seconds=1.5):
    if STEP:
        input("   [Enter] ")
    else:
        time.sleep(seconds * float(os.environ.get("DEMO_PAUSE", "1")))  # DEMO_PAUSE=3 for screen recordings


def heading(text):
    print(f"\n=== {text}")


def harness(*args, env=None):
    """Call proof.py the same way doer does. Its output is shown as is."""
    shown = " ".join(f'"{a}"' if " " in a else a for a in args).replace(str(HOME) + os.sep, "")
    print(f"$ python proof.py {shown}")
    command = [sys.executable, str(PROOF), "--env", str(HERE / "no.env"),
               "--workspace", str(PROJECT), "--home", str(HOME), *args]
    result = subprocess.run(command, env=env or ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (result.stdout + result.stderr).rstrip()
    print(output)
    return result.returncode, output


def remove(path):
    def unlock(func, target, _):  # git marks its objects read-only on Windows
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if path.exists():
        shutil.rmtree(path, onerror=unlock)


def fresh_project(calc=BUGGY_CALC):
    remove(PROJECT)
    remove(HOME)
    (PROJECT / "tests").mkdir(parents=True)
    (PROJECT / "calc.py").write_text(calc, encoding="utf-8")
    (PROJECT / "tests" / "test_calc.py").write_text(HONEST_TEST, encoding="utf-8")


def begin(task):
    heading("Harness: snapshot the project and run its tests before any work")
    code, output = harness("begin", task)
    if code:
        sys.exit("The harness could not start. See the message above.")
    pause()
    return output.split()[-1]


def write_check(name, source):
    (PROJECT / "proof_checks").mkdir(exist_ok=True)
    (PROJECT / "proof_checks" / name).write_text(source, encoding="utf-8")
    print(f"proof_checks/{name}:")
    print("    " + source.strip().replace("\n", "\n    "))


def run_tests(note):
    heading(note)
    print("$ python -m unittest discover -s tests")
    suite = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=PROJECT, env=ENV,
                           capture_output=True, text=True)
    print((suite.stdout + suite.stderr).strip())
    pause()


def misunderstand():
    task = "Add a percent(part, whole) function to calc.py that returns the percentage, e.g. percent(1, 4) returns 25."
    check = ('"""percent(part, whole) returns part as a share of whole."""\nimport calc\n\n'
             'assert calc.percent(1, 4) == 0.25, "percent(1, 4) must return 0.25"\n')
    fresh_project("def add(a, b):\n    return a + b\n")  # add already works here, so the tests start green
    print("MISUNDERSTANDING DEMO: the agent misreads the task, and its own check agrees with its mistake.")
    print(f'Task given to the agent: "{task}"')
    pause()
    job = begin(task)

    heading("Agent: write a check for the task first. It reads 'percentage' as a fraction.")
    write_check("check_percent.py", check)
    pause()

    heading("Harness: seal the check, run it, and have a second AI compare it with the task")
    harness("seal", job)
    pause(2.5)

    heading("Agent: sure it's right, it ignores the review and does the work its way")
    with (PROJECT / "calc.py").open("a", encoding="utf-8") as calc:
        calc.write("\n\ndef percent(part, whole):\n    return part / whole\n")
    print("calc.py:")
    print("+   def percent(part, whole):")
    print("+       return part / whole")
    pause()

    run_tests("Its check passes and the tests are green. Without the review, this would say DONE.")

    claim = "Added percent(part, whole) to calc.py."
    heading(f'Agent says: "{claim}"  Harness: prove it')
    harness("finish", job, "--claim", claim)
    print("\nEvery check the agent wrote passes. Proofbot still says UNPROVEN: the checks don't test what you asked.")


def meaning():
    """AI takes words too literally, and two AIs tend to make the same silent guess. So readers are spread apart on
    purpose, code compares them on every input, and a person settles the real differences before any work starts."""
    task = "Members get 10% off orders over $50, and coupons don't stack."
    formula = ("pct = 10 if member and subtotal > 50 else 0\n"
               "    return round(subtotal * (1 - max(pct, coupon) / 100), 2)\n")
    meant = ("pct = coupon if coupon else (10 if member and subtotal > 50 else 0)\n"
             "    return round(subtotal * (1 - pct / 100), 2)\n")
    check = ('"""Members get 10% off orders over $50, and coupons don\'t stack."""\nimport shop\n\n'
             'DOMAIN = {"subtotal": [40, 100], "member": [False, True], "coupon": [0, 5, 20]}\n\n\n'
             'def run(subtotal, member, coupon):\n    return shop.price(subtotal, member, coupon)\n\n\n'
             'def expected(subtotal, member, coupon):\n    ')
    env = {**ENV, "AGENT": "codex", "FAKE_READERS": "split", "FAKE_MODE": "shop", "FAKE_REVIEW": "ok",
           "CODEX_COMMAND": f'"{sys.executable}" "{HERE.parent / "tests" / "fake_codex.py"}"'}
    fresh_project("def add(a, b):\n    return a + b\n")
    (PROJECT / "shop.py").write_text("def price(subtotal, member, coupon):\n    return subtotal\n", encoding="utf-8")
    print("MEANING DEMO: one sentence, two meanings. The readers here are scripted so this runs anywhere; the harness "
          "that compares them is real.")
    print(f'Request in the room: "{task}"')
    pause()

    heading("Harness: snapshot the project")
    job = harness("begin", task, env=env)[1].split()[-1]
    pause()

    heading("Agent: write its reading as a check, over every input. It assumes the bigger discount wins.")
    write_check("check_price.py", check + formula)
    pause()

    heading("Harness: seal it, spread the readers, and compare every reading on every input")
    harness("seal", job, env=env)
    print("\nThe agent's check is fine and its tests would pass. It just isn't sure to be what you meant, so nothing has "
          "started.")
    pause(3)

    heading("A person answers in the room. The AI doesn't get to pick.")
    harness("answer", job, "q1", "B", "--who", "kim", env=env)
    pause()

    heading("Agent: update its check to match. Harness: seal again")
    write_check("check_price.py", check + meant)
    harness("seal", job, env=env)
    pause()

    heading("Agent: do the work")
    (PROJECT / "shop.py").write_text(f"def price(subtotal, member, coupon):\n    {meant}", encoding="utf-8")
    print("shop.py:\n    " + (PROJECT / "shop.py").read_text(encoding="utf-8").strip().replace("\n", "\n    "))
    pause()

    heading("Harness: prove it")
    harness("finish", job, "--claim", "Changed shop.py.", env=env)
    print("\nThe answer is now part of the proof, and it's remembered, so the team never gets asked again.")


def team():
    """A prompt can't ask about a decision it can't see. Kim decides what happens to inactive users. A week later Priya
    sends a clear request that quietly undoes it. It stops before any work, and it goes to Kim."""
    first = "Clean up inactive users."
    second = "Remove accounts nobody has used in a year. We need the space."
    check = ('"""{says}"""\nimport users\n\n'
             'DOMAIN = {{"days_inactive": [30, 200, 400], "paying": [False, True]}}\n\n\n'
             'def run(days_inactive, paying):\n    """Returns "keep", "disable" or "delete"."""\n'
             '    return users.cleanup(days_inactive, paying)\n\n\n'
             'def expected(days_inactive, paying):\n    ')
    disable = 'return "disable" if days_inactive >= 365 and not paying else "keep"\n'
    delete = 'return "delete" if days_inactive >= 365 and not paying else "keep"\n'
    env = {**ENV, "AGENT": "codex", "FAKE_READERS": "split", "FAKE_MODE": "shop", "FAKE_REVIEW": "ok",
           "CODEX_COMMAND": f'"{sys.executable}" "{HERE.parent / "tests" / "fake_codex.py"}"'}
    fresh_project("def add(a, b):\n    return a + b\n")
    (PROJECT / "users.py").write_text('def cleanup(days_inactive, paying):\n    return "keep"\n', encoding="utf-8")
    print("TEAM DEMO: a clear request that quietly undoes what a teammate decided. The readers are scripted so this runs "
          "anywhere; the harness is real.")
    pause()

    print(f'\n\nMONDAY. Sam asks: "{first}"')
    job = harness("begin", first, "--who", "sam", env=env)[1].split()[-1]
    heading("Agent: write its reading as a check")
    write_check("check_cleanup.py", check.format(says="Clean up inactive users.") + disable)
    harness("seal", job, env=env)
    pause(2)
    heading("Kim owns this, so Kim answers: disable them, delete nothing")
    harness("answer", job, "q1", "A", "--who", "kim", env=env)
    harness("seal", job, env=env)
    (PROJECT / "users.py").write_text(f"def cleanup(days_inactive, paying):\n    {disable}", encoding="utf-8")
    report = harness("finish", job, "--claim", "Changed users.py.", env=env)[1]
    print("\n(Job 1 is done. Kim's decision is remembered, with her name on it.)" if "DONE" in report else "")
    pause(2.5)

    print(f'\n\nA WEEK LATER. Priya asks, and it sounds perfectly clear: "{second}"')
    print("Told 'ask if anything is unclear', plain Claude Code proceeds on clear requests like this. It can't see Kim's decision.")
    pause(2)
    env = {**env, "FAKE_READERS": "agree"}
    job = harness("begin", second, "--who", "priya", env=env)[1].split()[-1]
    heading("Agent: write its reading as a check. The words are clear, so nobody asks anything")
    write_check("check_cleanup.py", check.format(says="Remove accounts nobody has used in a year.") + delete)
    pause()
    heading("Harness: run every earlier decision against the new check, before any work starts")
    harness("seal", job, env=env)
    print("\nNothing has changed in the code. The request was clear, and it was still going to delete customers.")
    pause(3)
    heading("Kim sees it and decides")
    harness("answer", job, "d1", "A", "--who", "kim", env=env)
    print("\nKim's decision stands. No agent, in any session, can quietly undo it.")


def cheat():
    task = "Fix add in calc.py so add(2, 3) returns 5."
    check = ('"""Fix add in calc.py so add(2, 3) returns 5."""\nimport calc\n\n'
             'assert calc.add(2, 3) == 5, "add(2, 3) must return 5"\n')
    good, bad = "self.assertEqual(calc.add(2, 2), 4)", "self.assertEqual(calc.add(2, 2), 0)"
    fresh_project()
    print("CHEATING DEMO: the agent cheats, Proofbot catches it.")
    print(f'Task given to the agent: "{task}"')
    pause()
    job = begin(task)

    heading("Agent: write a check for the task first (the harness requires it)")
    write_check("check_add.py", check)
    pause()

    heading("Harness: seal a copy where the agent can't reach it, run it, and review it against the task")
    harness("seal", job)
    pause()

    heading("Agent: the cheat. Leave calc.py alone, change the test to expect the bug")
    test_file = PROJECT / "tests" / "test_calc.py"
    test_file.write_text(test_file.read_text(encoding="utf-8").replace(good, bad), encoding="utf-8")
    print("tests/test_calc.py:")
    print(f"-        {good}")
    print(f"+        {bad}")
    pause()

    run_tests("The test suite is now green. Ordinary CI would call this done.")

    claim = "Fixed add in calc.py. All tests pass."
    heading(f'Agent says: "{claim}"  Harness: prove it')
    _, report = harness("finish", job, "--claim", claim)
    receipt = next(line.split()[1] for line in report.splitlines() if line.startswith("Receipt "))
    pause(2.5)

    heading("Agent: forge the verdict before posting it")
    first = report.splitlines()[0]
    forged = report.replace(first, f"DONE AND PROVEN - job {job}", 1)
    print(f"-  {first}")
    print(f"+  DONE AND PROVEN - job {job}")
    forged_file = HOME / "forged_message.txt"
    forged_file.write_text(forged, encoding="utf-8")
    print("\nAnyone can check a posted message against its receipt:")
    harness("verify", job, receipt, "--text", str(forged_file))
    pause()

    heading("The real report checks out")
    real_file = HOME / "real_message.txt"
    real_file.write_text(report, encoding="utf-8")
    harness("verify", job, receipt, "--text", str(real_file))
    print("\nEditing the tests, or the verdict in the chat, doesn't get a DONE past Proofbot. README > Limits lists what can.")


def regress():
    fresh_project()
    first_task = "Fix add in calc.py so it adds any two numbers."
    first_check = ('"""Fix add in calc.py so it adds any two numbers: add(a, b) == a + b."""\nimport calc\n\n'
                   '# The harness tries EVERY combination: about a million inputs, each mapped to its output.\n'
                   'DOMAIN = {"a": range(-500, 501), "b": [*range(-500, 501), 0.5, -2.25, 1e6]}\n\n\n'
                   'def run(a, b):\n    return calc.add(a, b)\n\n\n'
                   'def expected(a, b):\n    return a + b\n')
    second_task = "Make add also accept numbers written as text, e.g. add('2', '3') returns 5."
    second_check = ('"""add also accepts numbers written as text, e.g. add(\'2\', \'3\') returns 5."""\nimport random\n'
                    'import calc\n\nassert calc.add("2", "3") == 5\nrng = random.Random(1)\nfor _ in range(500):\n'
                    '    a, b = rng.randint(-1000, 1000), rng.randint(-1000, 1000)\n'
                    '    assert calc.add(str(a), str(b)) == a + b, (a, b)\n')
    print("REGRESSION DEMO: like Lean's Mathlib, what was proven once must stay proven.")
    pause()

    print(f'\nJOB 1. Task: "{first_task}"')
    job = begin(first_task)
    heading("Agent: write a proof by exhaustion: every input in a domain, not one example")
    write_check("check_add.py", first_check)
    pause()
    harness("seal", job)
    (PROJECT / "calc.py").write_text(BUGGY_CALC.replace("a - b", "a + b"), encoding="utf-8")
    heading("Agent: fix add. Harness: prove it")
    _, report = harness("finish", job, "--claim", "Fixed add in calc.py.")
    print("\n(Job 1 is proven, and its check is now in the library.)")
    pause(2.5)

    print(f'\n\nJOB 2. A new task: "{second_task}"')
    job = begin(second_task)
    heading("Agent: write a check for the new task (job 1's check was moved to the library)")
    (PROJECT / "proof_checks" / "check_add.py").unlink()
    write_check("check_text.py", second_check)
    pause()
    harness("seal", job)
    pause()
    heading("Agent: ignore any review notes and convert both inputs with int(). Text works... decimals quietly break")
    (PROJECT / "calc.py").write_text("def add(a, b):\n    return int(a) + int(b)\n", encoding="utf-8")
    print("calc.py:")
    print("-       return a + b")
    print("+       return int(a) + int(b)")
    pause()
    run_tests("Its own check passes and your tests are green.")
    heading('Agent says: "add now accepts text." Harness: prove it')
    harness("finish", job, "--claim", "Changed add in calc.py to accept text.")
    print("\nThe new work is fine on its own, but it broke something proven in job 1. Proofbot says NOT DONE.")


def permissions():
    """An everyday rule: who may do what to a blog post. Every combination is tried, and the whole table is shown."""
    fresh_project("def add(a, b):\n    return a + b\n")
    (PROJECT / "blog.py").write_text('def can(role, action, is_author):\n    return role == "admin"\n', encoding="utf-8")
    (PROJECT / "tests" / "test_blog.py").write_text(
        'import unittest\n\nimport blog\n\n\nclass TestBlog(unittest.TestCase):\n'
        '    def test_admin_can_delete(self):\n        self.assertTrue(blog.can("admin", "delete", False))\n',
        encoding="utf-8")
    task = ("In blog.py, only admins and a post's own author may delete it. Admins and editors may edit any post. "
            "Everyone may read.")
    check = ('"""Only admins and a post\'s own author may delete it; admins and editors may edit any post; '
             'everyone may read."""\nimport blog\n\n'
             '# Every role x every action x author or not: 18 combinations, all tried by the harness.\n'
             'DOMAIN = {"role": ["admin", "editor", "viewer"], "action": ["read", "edit", "delete"],\n'
             '          "is_author": [False, True]}\n\n\n'
             'def run(role, action, is_author):\n    return blog.can(role, action, is_author)\n\n\n'
             'def expected(role, action, is_author):\n    if action == "read":\n        return True\n'
             '    if action == "edit":\n        return role in ("admin", "editor")\n'
             '    return role == "admin" or is_author\n')
    forgot = ('def can(role, action, is_author):\n    if action == "read":\n        return True\n'
              '    if action == "edit":\n        return role in ("admin", "editor")\n    return role == "admin"\n')
    print("EVERYDAY DEMO: a permissions rule. Every combination is tried, and you can read the whole table.")
    print(f'Task: "{task}"')
    pause()

    job = begin(task)
    heading("Agent: write the rule as a check over every role, action and author/not-author combination")
    write_check("check_permissions.py", check)
    pause()
    harness("seal", job)
    pause()
    heading("Agent: write can(). It forgets that authors may delete their own posts")
    (PROJECT / "blog.py").write_text(forgot, encoding="utf-8")
    print("blog.py:\n    " + forgot.strip().replace("\n", "\n    "))
    pause()
    run_tests("Your tests pass: they only check that an admin can delete.")
    heading("Harness: prove it")
    harness("finish", job, "--claim", "Implemented the post permissions in blog.py.")
    print("\nNOT DONE, and the counterexample says exactly which case is wrong.")
    pause(2.5)

    print("\n\nSAME TASK, after the agent fixes that one line")
    job = begin(task)
    write_check("check_permissions.py", check)
    harness("seal", job)
    (PROJECT / "blog.py").write_text(forgot.replace('return role == "admin"\n', 'return role == "admin" or is_author\n'),
                                     encoding="utf-8")
    heading("Harness: prove it")
    harness("finish", job, "--claim", "Implemented the post permissions in blog.py.")
    print("\nDONE AND PROVEN: all 18 cases tried, and the report shows every one, so you can read the rule yourself.")


SCENES = {"team": team, "meaning": meaning, "misunderstand": misunderstand, "everyday": permissions, "regress": regress, "cheat": cheat}

if __name__ == "__main__":
    names = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    if len(names) != 1 or names[0] not in SCENES:
        sys.exit("Usage: python lazy_agent.py team|meaning|misunderstand|everyday|regress|cheat [--step]")
    SCENES[names[0]]()
