/-!
The rule that decides a job's verdict, in Lean. `lake` isn't needed: `lean Gate.lean` checks the proofs.

This proves things about the rule, not about Python: it says the rule itself has no way around a person's answer.
`python tests/test_bot.py` then compares this rule with `verdict` in proof.py on all 64 cases, when Lean is installed.
-/

/-- What the harness measured about one job. -/
structure Job where
  scanFailed   : Bool  -- the loophole scan found a FAIL, including "does not do what you decided"
  realCheck    : Bool  -- at least one check failed before the work and so tests something
  reviewGap    : Bool  -- part of the request has no check that tests it as meant
  openQuestion : Bool  -- the readers found another meaning and nobody has answered yet
  conflict     : Bool  -- the checks disagree with a person's answer or with every reader
  warning      : Bool  -- something the person should read
deriving Repr

inductive Verdict where
  | doneProven | doneWarnings | notDone | unproven
deriving Repr, DecidableEq

def verdict (j : Job) : Verdict :=
  if j.scanFailed then .notDone
  else if !j.realCheck || j.reviewGap || j.openQuestion || j.conflict then .unproven
  else if j.warning then .doneWarnings
  else .doneProven

def Verdict.isDone : Verdict → Bool
  | .doneProven | .doneWarnings => true
  | _ => false

/-- Lean's `decide` tries all 64 cases, the same idea as a check's DOMAIN. Nothing reaches DONE while a question about
what the person meant is open, or while the checks disagree with what they said. -/
theorem done_needs_your_answer : ∀ a b c d e f : Bool,
    (verdict ⟨a, b, c, d, e, f⟩).isDone = true → d = false ∧ e = false := by decide

/-- Nothing reaches DONE without a check that tests something and a clean scan. -/
theorem done_needs_real_proof : ∀ a b c d e f : Bool,
    (verdict ⟨a, b, c, d, e, f⟩).isDone = true → a = false ∧ b = true ∧ c = false := by decide

/-- A failed scan is NOT DONE, whatever else is true. -/
theorem failure_cannot_be_outvoted : ∀ b c d e f : Bool,
    verdict ⟨true, b, c, d, e, f⟩ = .notDone := by decide

#print axioms done_needs_your_answer

def bit (b : Bool) : String := if b then "1" else "0"

def name : Verdict → String
  | .doneProven => "doneProven" | .doneWarnings => "doneWarnings" | .notDone => "notDone" | .unproven => "unproven"

/-- Prints the whole table, so a test can compare it with proof.py. -/
def main : IO Unit := do
  let both := [false, true]
  for a in both do for b in both do for c in both do for d in both do for e in both do for f in both do
    IO.println s!"{bit a} {bit b} {bit c} {bit d} {bit e} {bit f} {name (verdict ⟨a, b, c, d, e, f⟩)}"
