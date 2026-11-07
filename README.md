# Proofbot

Text an AI coding agent a task on WhatsApp. It does the work in one folder on your PC without asking you anything. When it's finished, you get one message: what changed, then proof that the work is really done, written by a harness the agent can't touch.

## Quick start

You need Python 3.10 or newer, git, and the [Codex CLI](https://github.com/openai/codex) signed in (`codex login`). Proofbot uses only the Python standard library, so there is nothing to `pip install`.

```powershell
git clone https://github.com/qunatumstuff/proofbot
cd proofbot

# 1. Watch it catch agents going wrong. No setup: each scene builds its own scratch project.
python demo/lazy_agent.py misunderstand   # the agent misreads the task; its own check agrees with it
python demo/lazy_agent.py everyday        # a permissions rule, every combination tried
python demo/lazy_agent.py regress         # a later job breaks something proven earlier
python demo/lazy_agent.py cheat           # the agent edits a test, then forges the verdict

# 2. Run the test suite: a fake agent tries every cheat, plus a fake WhatsApp server. No network needed.
python tests/test_bot.py

# 3. Use it on your own project.
copy .env.example .env                    # then set WORKSPACE and TEST_COMMAND in .env
python proof.py doctor                    # can the checks run here?
python proof.py run "Fix the date parsing in utils.py"
```

The demo scenes use Codex only for the second-AI review; without Codex they still run and the report warns that nothing checked the checks. To text tasks from your phone, set up [Telegram through Switch](#telegram-or-any-app-switch-connects) or [WhatsApp](#set-up-whatsapp) below.

## Lean for agent work

People let AI write proofs in Lean because they never have to trust the AI: a small kernel checks every step, and a person only reads the theorem statement to make sure it says what they meant. Proofbot does the same for an agent's work on your code.

| In Lean | In Proofbot |
| --- | --- |
| The theorem statement, written before the proof | The checks, sealed before the work starts |
| A misformalized statement (it says something you didn't mean) | A second AI compares the checks with your request: MISSING, WRONG or NARROW |
| A theorem holds *for all* inputs | Checks test the rule over many inputs; a one-example check is flagged NARROW |
| `decide`: proof by checking every case of a finite type | Proof by exhaustion: the harness tries every input combination in a check's DOMAIN, maps each input to its output, and names the first counterexample |
| The proof: written by anyone, trusted by no one | The agent's code changes |
| The kernel | `proof.py`: reruns the sealed checks, your tests and the loophole scan |
| `sorry` | Skipped, deleted or weakened tests and edited checks, all flagged |
| `#print axioms` | THIS PROOF RELIES ON, at the end of every report |
| Mathlib: proven once, stays proven | The proven library: a later job that breaks an earlier proof is NOT DONE |
| Anyone can re-check a proof file | The receipt and `verify` |

You read one thing, PROOF 1: what the checks say, against what you asked. The harness checks the rest.

### Proof by exhaustion

A check can list its inputs instead of picking a few. The harness, not the agent, then tries every combination (up to 10 million), maps every input to its output, and compares each output with the expected one:

```python
"""Fix add in calc.py so it adds any two numbers."""
import calc

DOMAIN = {"a": range(-500, 501), "b": [*range(-500, 501), 0.5, -2.25, 1e6]}

def run(a, b):          # what the code does
    return calc.add(a, b)

def expected(a, b):     # what it should do
    return a + b
```

### Everyday tasks

Most everyday bugs live in combinations: a rule that works for admins but not for authors, a discount that breaks for one customer type, a status change nobody tested. Those inputs are lists of options, so every combination can be tried:

| Everyday task you'd text the bot | What DOMAIN lists |
| --- | --- |
| "Only admins and the post's author may delete it" | every role × action × author or not |
| "Members get 10% off orders over $50, coupons don't stack" | every customer type × coupon × order-size band |
| "An order can't be refunded once it has shipped" | every order status × event → next status |
| "Show 'email required' before 'email invalid'" | every empty / valid / invalid state of each field |
| "Dark mode and compact view must work together" | every combination of the feature flags |

When the table has 24 rows or fewer, the report prints all of it, so you read the rule you're trusting, not a count. `python demo/lazy_agent.py everyday` shows the permissions example: the first try is NOT DONE with `role='editor', action='delete', is_author=True: got False, expected True`, and the fix is DONE AND PROVEN with all 18 rows shown.

Some things can't be listed: free text, how a page looks, speed, other companies' services. Checks for those try chosen inputs instead, and the report says so under THIS PROOF RELIES ON.

### How big a domain can be

The add example above is 1,005,004 inputs in under two seconds. The report says `all 1,005,004 inputs tried: a -500..500, b 1004 values, every output as expected (map 247a28bb9563)`, or names the first input that breaks, such as `a=-500, b=0.5: got -500, expected -499.5`. The map fingerprint goes into the receipt, so `verify --recheck` can later show that every input still gives the same output. A proof by exhaustion covers its domain and nothing beyond it, and the report says so under THIS PROOF RELIES ON.

## What you get back

This is from a real run, where Codex was asked to *"Fix add in calc.py so it adds, and add a multiply(a, b) function that returns the product."*

```text
DONE AND PROVEN - job 1
Receipt P1-dcaf5a393635
You asked: "Fix add in calc.py so it adds, and add a multiply(a, b) function that returns the product."
Agent's own summary (a claim, not proof): "Changed calc.py: fixed add(a, b) to return the sum and added multiply(a, b) ..."

WHAT CHANGED (measured by the harness)
- calc.py: +5 -1

PROOF 1: CHECKS WRITTEN AND SEALED BEFORE THE WORK
PASS check_add.py: ... (failed before, passes now)
PASS check_multiply.py: ... (failed before, passes now)

PROOF 2: YOUR TEST SUITE, RUN BY THE HARNESS
before: FAIL (exit 1), after: pass (exit 0)

PROOF 3: LOOPHOLE SCAN
ok sealed checks untouched; the harness ran its own copy
ok all 2 check(s) failed before the work, so they test something new
ok 1 project file(s) changed
ok no test files deleted
ok no tests skipped, marked xfail or narrowed with only
ok no assertions removed from tests
ok no existing tests edited
ok no test or build settings changed
ok test suite passes (before: fail, after: pass)
ok while writing checks the agent touched only the check folder
ok every file the agent names was really changed
```

The first line is always one of: **DONE AND PROVEN**, **DONE, READ THE WARNINGS**, **NOT DONE**, or **UNPROVEN** (nothing could prove it either way).

Reports now open with one more section, which catches an agent that misunderstood you. Here the task was *"Add a percent(part, whole) function to calc.py that returns the percentage, e.g. percent(1, 4) returns 25."* The agent read "percentage" as a fraction and wrote a check that agreed with it, so its check passed and the tests stayed green:

```text
UNPROVEN - job 1
...
PROOF 1: DO THE CHECKS MATCH WHAT YOU ASKED?
(judged by a second AI that saw only your request and the checks)
ok "Add a percent(part, whole) function to calc.py": check_percent.py
WRONG "returns the percentage, e.g. percent(1, 4) returns 25": check_percent.py tests something else. The check expects 0.25 instead of the requested 25.

PROOF 2: CHECKS WRITTEN AND SEALED BEFORE THE WORK
PASS check_percent.py: percent(part, whole) returns part as a share of whole. (failed before, passes now)
...
```

That run used a scripted agent; the review and the report are the real harness. Try it: `python demo/lazy_agent.py misunderstand`.

## How the proof works

1. **Before:** the harness snapshots the workspace and runs your tests and every check in the proven library.
2. **Checks first:** the agent writes acceptance checks for your task in `proof_checks/`, without doing the task.
3. **Seal:** the harness copies those checks into its own folder, outside the agent's reach, and runs them. They must fail now. A check that already passes proves nothing and is flagged.
4. **Review:** a second AI, shown only your request and the sealed checks (not the agent's reasoning), splits your request into its parts and says which check tests each one. A part with no check, or a check that expects something you didn't mean, goes back to the agent to fix before any work starts. If it stays unfixed, the job can only end UNPROVEN. A check that tries so few inputs that special-casing them would pass is flagged NARROW.
5. **Work:** the agent does the task.
6. **Proof:** the harness runs its sealed copy of the checks, your tests and the proven library again, diffs the workspace, and scans for cheating. Then it writes the report, gives it a receipt ID, and sends it to you itself. The agent never sees the report before you do.
7. **Library:** when a job is DONE, each of its checks that failed before and passes now joins the proven library for that workspace. Every later job must keep them all passing.

| How an agent fakes it | What catches it |
| --- | --- |
| Misunderstands you, or drops part of the task, and writes checks that agree with its mistake | The second AI's review: a missing or misread part makes the job UNPROVEN |
| Checks one example, then special-cases it | The review flags the check NARROW |
| Breaks something an earlier job proved, in a way your tests miss | The proven library: the job is NOT DONE |
| Says "done" without changing anything | "no project files changed", and its named files show as unchanged |
| Edits the checks so they pass | The harness runs its sealed copy; the edit is flagged |
| Writes checks that pass no matter what | They pass before the work, so they're marked empty and the job is UNPROVEN |
| Skips, deletes or weakens your tests | Skip/xfail/only markers, deleted test files and removed assertions are each flagged |
| Changes test or build settings | Flagged as a warning to read |
| Breaks your tests while fixing something | Your test suite passed before and fails now |
| Edits the report it sends you | It can't: the bot sends the report. `verify` also catches a changed copy |
| Edits the evidence afterwards | Evidence lives outside the workspace; the receipt hash and ledger chain break |

`python tests/test_bot.py` acts out each of these with a fake agent and checks they're caught.

## Set up WhatsApp

You need about 15 minutes, a Meta developer account, and ngrok (already installed on this PC).

1. Go to [developers.facebook.com](https://developers.facebook.com), create an app, and add the **WhatsApp** product.
2. In **WhatsApp > API Setup**, note the test number's **Phone number ID** and copy the **temporary access token**. Under **To**, add your own WhatsApp number and confirm the code Meta sends you.
3. In **App settings > Basic**, copy the **App secret**.
4. Copy `.env.example` to `.env` and fill it in: your workspace folder, test command, the token, phone number ID, app secret, a verify phrase you make up, and your own number.
5. Start the bot, and the tunnel in a second terminal:

```powershell
python whatsapp_bot.py
```

```powershell
ngrok http 8787
```

6. In **WhatsApp > Configuration**, set the callback URL to the ngrok `https://...` address plus `/webhook`, enter your verify phrase, and save. Under **Webhook fields**, subscribe to **messages**.
7. From your phone, text the test number: `Fix the typo in README.md`. You'll get "On it.", two short progress messages, then the proof.

Other messages it understands: `status`, `show 3` (resend job 3's report) and `verify 3 P3-...` (re-check a receipt and re-run its sealed checks).

The temporary token lasts 24 hours. For longer, create a system-user token with the `whatsapp_business_messaging` permission in Meta Business settings. Only your number can give orders, and only requests signed with your app secret are accepted.

## Let the sandbox run Python

Codex works inside its Windows sandbox, which can only change the workspace. That was tested on this PC: writes to Documents and to Temp were blocked. The sandbox runs as separate Windows accounts (`CodexSandboxOffline`, `CodexSandboxOnline`), and those can't read a Python installed just for you. Until that's fixed:

- Codex can't run Python while it works. It can still edit files, and the harness still checks everything.
- `python proof.py doctor` reports a problem, and the bot won't start with sandboxed checks.

Pick one:

- **Let the sandbox accounts run Python.** This is a permissions change on your PC, so it's your call; I haven't made it or tested it. Afterwards, `doctor` should say OK.

```powershell
icacls "$env:LOCALAPPDATA\Programs\Python\Python311" /grant "CodexSandboxOffline:(OI)(CI)RX" /grant "CodexSandboxOnline:(OI)(CI)RX" /T
```

- **Or set `CHECK_RUNNER=direct` in `.env`.** Checks and tests then run as you, unsandboxed. Codex itself stays sandboxed, but the checks it writes run with your full access.

## Telegram, or any app Switch connects

Switch connects Telegram, Slack, Teams, Discord and Mattermost. Connect Telegram in Switch Console under **Messaging apps** (you'll need a bot token from @BotFather). Then import [proofbot.template.yaml](proofbot.template.yaml), choose the workspace and this folder, and pick Telegram. You get one agent that only you can address, plus a room with you in it.

Here the agent runs the steps itself (`begin`, `seal`, `finish`) and posts the report, so the guarantee is weaker than on WhatsApp, where the bot does steps 1, 3 and 5 and sends the message. To check a posted report, copy it and run:

```powershell
Get-Clipboard | python proof.py verify 3 P3-... --text -
```

## Commands

```powershell
python proof.py doctor                     # can the sandbox run the checks?
python proof.py run "your task"            # one whole job from the terminal
python proof.py show 3                     # a job's report
python proof.py verify 3 P3-... --recheck  # is the receipt genuine, and do the checks still pass?
python tests/test_bot.py                   # fake agent + fake WhatsApp, every cheat
```

## Limits

- The same agent writes the checks and does the work. A second AI checks them against your request, but that review is a judgement, not proof: it can miss a subtle misreading, and the report says who judged it. It runs `codex exec` read-only and adds about 10 seconds. `REVIEW=off` turns it off; reports then warn that nothing checked the checks.
- The proven library lives in the harness home (`home/library/`), one per workspace. If you change a requirement on purpose, delete its file there (and its line in `library.json`), or every later job will be NOT DONE.
- The WhatsApp side was tested against a fake WhatsApp server that follows Meta's documented webhook and message formats, not against your real Meta app.
- The harness snapshots the workspace with git and runs `git init` if the folder has none. It never commits or changes your branch.
- Jobs run one at a time. A task that is a question, not a change, comes back UNPROVEN, because there's nothing to check.
