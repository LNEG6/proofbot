# Proofbot

**A teammate in your group chat that asks the right person, and never forgets the answer.**

Agents act on their guess of what you meant, and you only find out it was wrong after the work is done. A wrong guess feels the same to the agent as a right one, so it goes ahead confidently. On a team it's worse: the agent asks whoever typed, not whoever decided, and by next week it has forgotten the answer.

Proofbot fixes that in a [Switch](https://github.com/sandbox-quantum/switch) room. Two agents read your request from opposite ends. If they disagree, the room gets one plain question before any work starts. The answer is saved with the name of the person who gave it, it becomes a check the code has to pass, and no later job can quietly undo it.

![Paths fan out from one sentence between a cautious agent and a bold agent. When a person answers, the wrong outcomes are struck out and one line is left](docs/what-it-fixes.png)

*An illustration. Each line is one thing the sentence could mean. The real question comes before any work starts.*

```text
sam      @proof-doer Clean up inactive users.
referee  q1: Someone who doesn't pay hasn't used the product for exactly one year.
             What should happen to their account?
           A: Turn the account off, but keep it so it can be turned back on later
           B: Leave it alone for now, because only accounts inactive for more than a year count
           C: Delete the account for good
kim      A

         ...a week later...

priya    @proof-doer Remove accounts nobody has used in a year. We need the space.
referee  d1 (for kim): This goes against what kim decided in job 1. Keep that, or change it?
           A: Keep what kim decided
           B: Change it. The new request wins
```

The questions above came from a real run through the harness with Claude Code in the terminal. The second is shortened, and no work started until each one was answered.

## How it works

![The steps: you ask, a cautious and a bold agent read it, code compares them, a person answers if they disagree, the doer works, and the harness decides](docs/how-it-works.png)

The hackathon calls this a workflow, which only means who does what, in what order:

| Step | Who | What happens |
| --- | --- | --- |
| 1 | A person | Asks for something in the team chat |
| 2 | `doer` | Writes its reading of the request as checks, before touching any code |
| 3 | Two agents | One reads the request as cautiously as it can, the other as boldly as it can |
| 4 | The harness (no AI) | Runs both readings on every input, and runs every earlier decision against the new checks |
| 5 | `referee` | If everything agrees, work starts and nobody is bothered. If not, it asks the person who decided before, or whoever asked |
| 6 | A person | Answers with a letter or in their own words. The answer binds the checks and the code |
| 7 | `doer` | Does the work |
| 8 | The harness | Reruns everything from its own sealed copy and scans for cheating |
| 9 | `referee` | Posts the verdict. `doer` never gets to say it's done |

## Why it needs Switch

Switch isn't an agent. It's what lets coding agents sit in a team chat as members, next to people. A terminal has one person in it, and decisions belong to a team, so Proofbot is built on what a room gives you:

| Switch feature | What Proofbot uses it for |
| --- | --- |
| **Room documents** | The team's decisions live in the room. Every agent that joins reads them, so a brand-new agent already knows what Kim decided. An agent can only edit a document it created, so `doer` can't change the record |
| **Targeted messages** | A question goes to the person who decided, not to whoever happened to type |
| **Sender identity** | [switchlink.py](switchlink.py) reads the room's history itself. An answer only counts if Switch shows a person said it, and the name on the decision is the one Switch reports |
| **Direct posting** | The harness posts its own verdict to the room, using the session Switch gives the agent, so no AI can retype or soften it |
| **Separate room members** | `doer` and `referee` have their own folders, so the agent doing the work isn't the one announcing the result |
| **Any agent in one room** | Claude Code does the work and Codex referees by default, so they don't share blind spots. Without Switch you'd have to wire that up yourself |
| **People and agents in one chat** | Two people can disagree and it notices. Priya can't quietly undo what Kim decided, because the room sees the conflict before any work starts |
- **One import sets it all up.** [proofbot.template.yaml](proofbot.template.yaml) creates both agents and the room, and each agent runs on whichever coding agent you pick: Claude Code, Codex or OpenCode.

Switch Trust checks what agents *say*. Proofbot checks what they *did*, and whether it's what your team decided.

## Run it in Switch

You need Python 3.10 or newer, git, [Switch Console](https://github.com/sandbox-quantum/switch/releases/latest), and Claude Code or Codex signed in. Proofbot itself uses only the Python standard library. A local Switch server doesn't need Docker.

1. Install Switch Console and choose **Run a server on this computer**.
2. Connect a chat app under **Home > Messaging apps**. Discord gives each agent its own name and avatar. Telegram is quicker to set up, but one bot posts for everyone.
3. Clone this repo somewhere outside the project you want to work on:

```powershell
git clone https://github.com/qunatumstuff/proofbot
```

4. In Switch Console, go to **Templates > Import template** and import `proofbot.template.yaml`. Pick your project folder, the proofbot folder and your chat app.
5. Let both agents run `python`. Switch's default auto mode may stop and ask a person before each command, which stalls the room. For a demo, allow it under each agent's settings, or set `auto_approve: true` on both agents in the template if you're happy for them to run without checks.
6. In the room, ask for something: `@proof-doer Members get 10% off orders over $50, and coupons don't stack.`

`seal` and `finish` can each take a few minutes. A whole job took about 13 minutes in testing.

## Try it without Switch

These need no setup, and each builds its own scratch project:

```powershell
python demo/lazy_agent.py team            # a clear request goes against what a teammate decided, and it stops
python demo/lazy_agent.py meaning         # one sentence, two meanings: the readers split and a person settles it
python demo/lazy_agent.py everyday        # a permissions rule, every combination tried
python demo/lazy_agent.py regress         # a later job breaks something proven earlier
python demo/lazy_agent.py cheat           # the agent edits a test, then forges the verdict
python tests/test_bot.py                  # fake agents try every cheat. No network needed
```

The readers in `team` and `meaning` are scripted so they run anywhere. To use real ones on your own project, copy `.env.example` to `.env`, set `WORKSPACE` and `TEST_COMMAND`, then run:

```powershell
python proof.py run "Capitalize the customer's name on the invoice."
```

## Catching misunderstandings

A request is one sentence, but the person's meaning could be anywhere on a spectrum. So [readings.py](readings.py) sends one reader to each end:

| Reader | How it reads |
| --- | --- |
| `cautious` | The least the words could mean, and nothing that can't be undone |
| `bold` | The most the words could reasonably mean, finished the way you'd want it |

If both ends agree, everything between them agrees too, so nobody gets asked. Each reading becomes a real `expected()` function, and the harness runs both on every input. Two readings are the same meaning if they give the same output every time, so this is a measurement, not an AI's opinion. Past 5,000 inputs it takes a fixed random sample.

A last AI turns any difference into a plain question. It can set a silly one aside, and the report lists that under NOT ASKED, but it can never pick the answer. If it sets one aside and both readers disagree with the agent, the agent has to fix its checks. A job asks three questions at most, however many rounds it takes, and anything past that goes in the report.

When inputs can't be listed, like "clean up the logs", readers answer in words and an AI compares them. The report says so, because that's a judgement, not a measurement.

### What your team decided stays decided

This is the part a prompt can't do.

Each answer is saved the moment it's given, with who gave it. Before any new work starts, the harness runs every earlier decision and every proven check against the new checks, so it catches a rule whether it was settled by a letter, in someone's own words, or never asked about at all. A request that goes against one stops, and the person who decided gets asked. They can keep their decision, or change it, which retires the old proof. Later questions on the same inputs go to the same person.

Decisions and proven checks bind every later job, in any session, with any agent. A correction works the same way: `begin --correction` starts a job whose check must fail on the old behaviour, so it can't end in an apology.

### What real models did

These are real runs with Claude Code. The check in the first four rows was written by hand to be careless on purpose, and the last three were correct.

| Request | Result |
| --- | --- |
| "Capitalize the customer's name on the invoice." | Asked what to do with a name typed in capitals |
| "Members get 10% off orders over $50, and coupons don't stack." | Found 3 meanings and asked whether a coupon is a percent or dollars |
| "Clean up the logs." | Asked whether to touch the logging in the code too |
| "Fix add in calc.py, add(2, 3) should return 5." (the check returned 5 for everything) | Both readers disagreed, so the agent had to fix its check |
| "Fix add in calc.py so it adds two numbers." | One meaning, nobody asked |
| "Only admins and the post's author can delete a post. Banned users can't do anything." | One meaning, nobody asked |
| "Flag an invoice as overdue once it's more than 30 days old, unless it's been paid." | Asked about future dates, which it shouldn't have. Readers are now told to stick to inputs that can happen |

One whole job, with the agent also doing the work, asked two questions, built the right thing, and ended DONE, READ THE WARNINGS because the test project had no test suite. It took about 13 minutes. That's a handful of requests, not a benchmark, and the AI steps don't give the same answer every time.

### Why not just tell the agent to ask?

You should. Told only "if anything is unclear, ask", Claude Code asked good questions on the three ambiguous requests above and said PROCEED on the other four, in seconds. Left alone, it picked a meaning silently on all three. So spotting ambiguity is the cheap part, and our readers are much slower than that one line.

What a prompt can't do:

- **Ask the right person.** On "Remove accounts nobody has used in a year", it asked the person who typed in 5 of 5 tries. It had no way to know a teammate had already decided.
- **See a decision the code doesn't show.** On a clear request that undid an earlier decision about discounts, it said PROCEED in 2 of 3 tries.
- **Make the answer stick.** It can still get it wrong in code, say "done", and forget by the next session. Here, each option comes with an exact input and output, so the answer becomes a check the code has to pass, in a process it can't tamper with, in this job and every later one.

### Three mistakes that shaped this

An AI assistant made all three of these while we were building Proofbot.

| What happened | What Proofbot does about it |
| --- | --- |
| Asked for a Monte Carlo chart, "more spread out", it drew a different kind of map. The extra words replaced the main request. | The review treats the main thing you asked for as its own part, so checks that keep the description but lose the thing fail. |
| Corrected about an example, it explained itself, then used the same example again. | A correction is a new job. It needs a check that fails on the old behaviour, and that check binds every later job. |
| Asked how to stop this happening, it patched the one example. | A correction has to cover the whole kind of mistake, and the bold reader treats your examples as examples of a rule. |

A wrong guess and a right one feel the same to an agent, so being told off doesn't change anything by itself. A check that has to keep passing does.

## Lean for agents

People let AI write proofs in Lean because they never have to trust the AI: a small kernel checks every step. But Lean can't tell you whether the theorem says what you meant. A person has to read the statement. Formal verification has the same gap for software, and [Anthropic's work on verified software](https://www.anthropic.com/research/formal-verification) lists the theorem statements among the things you still have to trust.

Proofbot applies that idea to an agent's work, and puts most of its effort into that gap.

| In Lean | In Proofbot |
| --- | --- |
| The theorem statement, written before the proof | The checks, sealed before the work starts |
| A person reads the statement | Readers find where it could mean something else, and people settle it in the room |
| A theorem holds *for all* inputs | Checks test the rule over many inputs; a one-example check is flagged NARROW |
| `decide`: proof by checking every case of a finite type | Proof by exhaustion: the harness tries every combination in a check's DOMAIN and names the first counterexample |
| The proof: written by anyone, trusted by no one | The agent's code changes |
| The kernel | `proof.py`: reruns the sealed checks, your tests and the loophole scan |
| `sorry` | Skipped, deleted or weakened tests and edited checks, all flagged |
| `#print axioms` | THIS PROOF RELIES ON, at the end of every report |
| Mathlib: proven once, stays proven | The proven library: a later job that breaks an earlier proof is NOT DONE |

This is an analogy: checks are Python running on chosen inputs, not proofs about all programs. A proof by exhaustion covers its domain and nothing beyond it, and the report says so. There is one real Lean file, [lean/Gate.lean](lean/Gate.lean), which proves the verdict rule can't reach DONE with a question open. It proves things about the rule, not about Python, and `tests/test_bot.py` checks that `proof.py` follows the same rule in all 64 cases when Lean is installed.

Other projects bring Lean to agents too. [Lean4Agent](https://arxiv.org/abs/2606.06523) checks agent workflows, and the [Lean-Agent Protocol](https://arxiv.org/abs/2604.01483) gates each action against rules formalized in Lean. Those check an agent against rules someone already wrote down. Proofbot works one step earlier, on whether what got written down is what the person meant.

## How the proof works

1. **Before:** the harness snapshots the workspace and runs your tests and every check in the proven library.
2. **Checks first:** the agent writes acceptance checks in `proof_checks/`, without doing the task.
3. **Seal:** the harness copies those checks outside the agent's folder and runs them. They must fail now, because a check that already passes proves nothing.
4. **Readers and review:** readers look for other meanings, earlier decisions run against the new checks, and a second AI says which check tests each part of your request.
5. **Questions:** people settle anything left open, the agent updates its checks, and step 3 runs again.
6. **Work:** the agent does the task.
7. **Proof:** the harness reruns its sealed copy of the checks, your tests and the library, compares the code with what you decided, diffs the workspace, and scans for cheating. Then it writes the report and a receipt ID.
8. **Library:** when a job is DONE, its checks join the proven library, and every later job must keep them passing.

A report opens with one of **DONE AND PROVEN**, **DONE, READ THE WARNINGS**, **NOT DONE** or **UNPROVEN** (nothing could prove it either way).

| How an agent goes wrong | What catches it |
| --- | --- |
| Reads you too literally, or picks one meaning silently | The two readers split, and it stops for a question |
| Quietly undoes what a teammate decided | Earlier decisions run against the new checks, and it stops before any work |
| Keeps the description but loses the main thing you asked for | The review marks that part wrong |
| Gets corrected, then repeats the mistake | The correction's check is in the proven library: NOT DONE |
| Keeps its own reading after you answered | The harness compares its checks with your answer |
| Builds the old thing anyway | The code is called on the exact inputs you decided |
| Drops part of the task | The second AI's review |
| Checks one example, then special-cases it | The review flags it NARROW, and readers add inputs |
| Writes a check that compares the code with itself | `expected()` runs without the project, so it fails |
| Exits early, forges output, or returns an object equal to anything | The code and `expected()` run in separate processes and the harness compares plain outputs |
| Breaks something an earlier job proved | The proven library: NOT DONE |
| Says "done" without changing anything | "no project files changed" |
| Edits the checks so they pass | The harness runs its sealed copy |
| Writes checks that pass no matter what | They pass before the work, so the job is UNPROVEN |
| Skips, deletes or weakens your tests | Each is flagged, and NOT DONE |
| Edits the report it sends you | `verify` catches a changed copy |

`python tests/test_bot.py` acts out each of these with a fake agent.

## Limits

- **Readers agreeing doesn't prove the meaning.** It makes a misunderstanding less likely, and the report says so. A reader can miss an input, and models share blind spots.
- **A correction is only as strong as its check.** If the check misses the mistake, the mistake can come back. What you decided is also given to the agent as a rule, but only the checks enforce it.
- **Only listable inputs are measured.** Free text and how a page looks fall back to an AI comparing readings in words.
- **The room document is a copy.** Agents read it, but only the harness enforces it, and that needs the `referee` to keep it up to date.
- **The AI steps can be wrong.** The review and the last check are judgements. With `--room`, the harness checks answers against Switch itself. Without a Switch session it can't, and the report says nothing confirmed who answered.
- **On one computer, the folders aren't a wall.** An agent that can write to the proofbot folder could forge job files that `verify` accepts, because receipts aren't signed. Proofbot blocks this when run directly: with Claude Code the agent gets file tools limited to the workspace, and Codex has its sandbox. Inside a Switch room, check how your agent is confined.
- **Code can still tell it's being tested.** Code that detects the harness and behaves differently would pass. THIS PROOF RELIES ON says so. Checks without a DOMAIN run in one process with the code, and the report names them.
- **With Claude Code, checks run as you.** The sandbox comes from Codex, so AI-written checks run with your full access unless you use `AGENT=codex`.
- A clash is only found before the work when the new check takes the same inputs as the earlier one. Otherwise the proven library catches it at the end, as NOT DONE.
- To change a requirement that came from a decision, answer B to the contradiction. For any other proven check, delete its file in `home/library/` and its line in `library.json`.
- The harness snapshots the workspace with git and runs `git init` if the folder has none. It never commits or changes your branch.
- Jobs run one at a time. A task that is a question, not a change, comes back UNPROVEN, because there's nothing to check.
- `python proof.py run` with nobody at the keyboard can't ask you anything. The agent then works on its best reading, and the job ends UNPROVEN.

## Commands

```powershell
python proof.py doctor                     # can the checks run here?
python proof.py run "your task"            # one whole job from the terminal
python proof.py begin "your task"          # step 1, for an agent that runs the steps itself
python proof.py begin "what went wrong" --correction   # a correction: it becomes a check that binds later jobs
python proof.py seal 3                     # seal the checks, spread the readers, print any questions
python proof.py questions 3                # what still needs answering
python proof.py decisions                  # what this team has decided, for the room document
python proof.py answer 3 q1 B --who kim    # record a person's answer: a letter, or their own words
python proof.py begin "your task" --who sam   # say who asked
python proof.py finish 3 --claim "..."     # prove it and print the report
python proof.py show 3                     # a job's report
python proof.py verify 3 P3-... --recheck  # is the receipt genuine, and do the checks still pass?
```

`.env.example` lists the settings. `AGENT=claude` or `AGENT=codex` picks the AI, and Claude Code is the default when it's installed. Working alone from your phone? There's also a [WhatsApp front end](docs/whatsapp.md).
