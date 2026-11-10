"""
An LLM judge for answers no string match can grade, and a measurement of the
judge itself.

Why this exists. contains_answer is a substring test built for "5,265". Every
multi-hop answer in this project is categorical: Pinterest, Meta, Reddit, Yes.
In a comparison question BOTH candidates appear in any reasoned answer,
whichever the model picks, so the test cannot tell "Meta won" from "Pinterest
won". It scored a refusal as correct, and it scored "Pinterest grew revenue
faster" as correct on a question whose answer is Meta. Two string heuristics
have failed. This is the third approach and it is a model, so the first thing
it has to do is prove it is better than the thing it replaces.

Three design decisions, each the opposite of the obvious one.

1. The judge grades BLIND. It is never told the expected answer. It is asked
   only what the response concluded, and the comparison happens in Python. A
   judge handed the answer in advance is biased toward confirming it, and you
   would never see that bias, because it would agree with you.

2. The judge is the measured object, not the tool. The headline number is not
   "the judge says N answers are correct". It is how often the judge agrees
   with the human labels in labels.json. A judge nobody has scored is a string
   match with extra steps and a larger bill.

3. Negative controls. Deliberately corrupted answers are mixed in. A judge
   that never returns "wrong" cannot be used, and the only way to find that
   out is to try to make it fail.

Usage:
    python judge.py            measure the judge against labels.json
    python judge.py --controls include the negative controls
"""
import json
import sys

from query import load_api_key, first_text

MODEL = "claude-sonnet-5"

EXTRACT_PROMPT = """You are reading one answer produced by a question-answering system.

Report what the answer ASSERTS, nothing else. Do not judge whether it is right. Do not use outside knowledge.

Reply with exactly one line, in one of these two forms:

ASSERTED: <the bare value only>
REFUSED: <short reason it declined>

The value after ASSERTED must be the answer alone and nothing else. No
explanation, no comparison, no other candidate, no units of reasoning. If the
answer is a company, write only that company's name. If it is a number, write
only that number.

  answer: "Pinterest grew faster, with 69% against Meta's 22%"
  correct output -> ASSERTED: Pinterest
  wrong output   -> ASSERTED: Pinterest grew faster (69% vs Meta's 22%)

The second form is wrong because it names both candidates, and whatever reads
this line cannot then tell which one was chosen.

An answer can state facts and still decline the question it was asked. If it
says it cannot determine, cannot confirm, or could not find what it needed,
that is REFUSED, even when it reports other figures along the way. Report what
it concluded about THE QUESTION ASKED, not the strongest fact it happened to
find.

  question: "Which had more employees, Pinterest or Snap?"
  answer:   "Pinterest reported 5,265. I could not find Snap's figure, so I
             cannot say which had more."
  correct output -> REFUSED: could not find Snap's headcount
  wrong output   -> ASSERTED: Pinterest had 5,265 employees

Question that was asked:
{question}

The answer to read:
{answer}
"""


def extract(question, answer_text, client):
    """Ask the judge what an answer concluded. It never sees the expected value."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content":
                   EXTRACT_PROMPT.format(question=question, answer=answer_text)}],
    )
    text = first_text(resp) or ""
    line = text.strip().splitlines()[0] if text.strip() else ""
    if line.upper().startswith("REFUSED"):
        return "refused", line.split(":", 1)[-1].strip()
    if line.upper().startswith("ASSERTED"):
        return "asserted", line.split(":", 1)[-1].strip()
    return "unparsed", line


def verdict(kind, asserted, expected, answerable, rank=None):
    """Turn a blind extraction into the same three labels a human used.

    Two jobs, split deliberately. The model classifies the text, because that
    needs reading. The code applies the project's rules, because those are
    deterministic and the model has no way to know them.

    The refusal rule is the clearest case. labels.json counts a refusal as
    correct behaviour only when retrieval never put the answer in the top 3;
    refusing while holding the answer in context is wrong. The judge cannot
    see rank, so it labelled two such cases "refused" where the human said
    "wrong". That was not a judge error, it was a rule the judge was never
    given. rank is passed in and applied here.

    The comparison is a substring test and that is a known weak point, which
    is why the prompt now forces a bare value. An earlier version let the
    judge return "Pinterest grew faster in 2025 (69% vs Meta's 22%)" and the
    test found "meta" inside it and scored a wrong answer correct. The
    substring problem did not go away by grading blind, it moved from the
    answer into the extraction.
    """
    if kind == "unparsed":
        return "unparsed"
    if kind == "refused":
        # Refusing while the answer was in front of it is not a refusal worth
        # crediting. Same rule the human labels use.
        if answerable and rank is not None and rank <= 3:
            return "wrong"
        return "refused"
    if not answerable:
        return "wrong"          # answered a question with no answer in the corpus
    a = asserted.strip().lower()
    e = str(expected).strip().lower()
    return "correct" if e in a else "wrong"


CONTROLS = [
    # (question, answer text, what a working judge must say)
    ("What was Pinterest's headcount as of December 31, 2025?",
     "Pinterest's headcount was 9,999.", "wrong"),
    ("Which grew revenue faster in 2025, Pinterest or Meta?",
     "Pinterest grew revenue faster in 2025, with a 69% increase compared to "
     "Meta's 22% increase.", "wrong"),
    ("Which company had more employees at the end of 2025, Pinterest or Snap?",
     "The context does not contain employee counts for either Pinterest or Snap.",
     "refused"),
    ("What was Pinterest's headcount as of December 31, 2025?",
     "Pinterest's headcount was 5,265.", "correct"),
]
CONTROL_EXPECTED = ["5,265", "Meta", "Pinterest", "5,265"]


def grade_loop(client):
    """Grade loop_results.json with the same blind extraction.

    Separate entry point on purpose. The agreement run above is what
    establishes whether this judge can be trusted; this is what it is then
    used for. Running the second without the first is how you end up with a
    confident number from an unmeasured grader.
    """
    data = json.load(open("loop_results.json"))
    ok = 0
    print(f"  {'expected':<12} {'extracted':<28} verdict")
    print("  " + "-" * 62)
    for r in data["rows"]:
        kind, asserted = extract(r["question"], r["answer"], client)
        v = verdict(kind, asserted, r["expected"], True)
        ok += v == "correct"
        print(f"  {r['expected']:<12} {asserted[:28]:<28} {v}")
    print(f"\n  LOOP ANSWERS CORRECT: {ok}/{len(data['rows'])}")
    print(f"  k=25 baseline:        3/5")
    return ok


def main():
    if "--loop" in sys.argv:
        key = load_api_key()
        if not key:
            sys.exit("No ANTHROPIC_API_KEY.")
        import anthropic
        grade_loop(anthropic.Anthropic(api_key=key))
        return
    key = load_api_key()
    if not key:
        sys.exit("No ANTHROPIC_API_KEY. See .env.example.")
    import anthropic
    client = anthropic.Anthropic(api_key=key)

    labels = json.load(open("labels.json"))["labels"]
    rows, agree = [], 0
    print(f"  {'human':<9} {'judge':<9} {'ok':<3} question")
    print("  " + "-" * 74)
    for L in labels:
        kind, asserted = extract(L["question"], L["model_answer"], client)
        v = verdict(kind, asserted, L.get("expected_answer"),
                    L.get("answerable", True), L.get("rank_of_answer"))
        ok = v == L["label"]
        agree += ok
        rows.append({"question": L["question"], "human": L["label"], "judge": v,
                     "agreed": ok, "extracted": asserted})
        print(f"  {L['label']:<9} {v:<9} {'yes' if ok else 'NO ':<3} {L['question'][:48]}")

    n = len(labels)
    print(f"\n  AGREEMENT WITH HUMAN LABELS: {agree}/{n}")
    out = {"n_labels": n, "agreed": agree, "rows": rows}

    if "--controls" in sys.argv:
        print(f"\n  NEGATIVE CONTROLS   a judge that never says 'wrong' is unusable")
        passed = 0
        ctl = []
        for (q, a, must), exp in zip(CONTROLS, CONTROL_EXPECTED, strict=True):
            kind, asserted = extract(q, a, client)
            v = verdict(kind, asserted, exp, True)
            ok = v == must
            passed += ok
            ctl.append({"question": q, "answer": a, "must_say": must,
                        "judge": v, "passed": ok, "extracted": asserted})
            print(f"  {must:<9} {v:<9} {'yes' if ok else 'NO ':<3} {a[:52]}")
        print(f"\n  CONTROLS PASSED: {passed}/{len(CONTROLS)}")
        out["controls"] = {"passed": passed, "n": len(CONTROLS), "rows": ctl}

    with open("judge_results.json", "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print("\n  Written to judge_results.json")


if __name__ == "__main__":
    main()
