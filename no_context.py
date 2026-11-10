"""
Does the model answer from the corpus, or from memory?

Every generation figure in this project assumes the model is reading the
passages it was handed. The corpus is public SEC filings for four well-known
companies, so that assumption is untested and might be false: a model that
already knows Meta's 2025 revenue scores "correct" whether retrieval worked
or not, and the harness cannot tell the difference.

This removes retrieval entirely. Same questions, same prompt, empty context.

    answered correctly with no context at all   -> the number is not retrieval
    refused with no context                     -> the number was retrieval

It is the control condition the eval never had. A control is not a better
measurement, it is the thing that tells you what your measurement means.

Usage:
    python no_context.py
"""
import json
import sys

import anthropic
from query import load_api_key, first_text
from run_eval import contains_answer, refused

MODEL = "claude-sonnet-5"


def ask_blind(question, client):
    """The real prompt from query.answer(), with nothing in the context."""
    prompt = f"""Answer the question using ONLY the context below. If the context doesn't contain the answer, say so explicitly, do not guess.

Context:


Question: {question}

Answer:"""
    resp = client.messages.create(
        model=MODEL, max_tokens=2000,
        messages=[{"role": "user", "content": prompt}])
    return first_text(resp) or ""


def ask_unguarded(question, client):
    """No grounding instruction at all. Does the model simply know this?

    The empty-context test shows the model OBEYS "use only the context". It
    does not show the model is ignorant, and those are different facts with
    different consequences. If the model knows the answer and the prompt is
    what suppresses it, the guardrail is one sentence of English and a prompt
    edit could reintroduce leakage without any other change.
    """
    resp = client.messages.create(
        model=MODEL, max_tokens=2000,
        messages=[{"role": "user", "content": question}])
    return first_text(resp) or ""


def main():
    key = load_api_key()
    if not key:
        sys.exit("No ANTHROPIC_API_KEY.")
    client = anthropic.Anthropic(api_key=key)

    eval_set = [q for q in json.load(open("eval_set.json"))
                if not q.get("hops") and q.get("answerable", True)]

    leaked, refused_n, rows = 0, 0, []
    print(f"  {'expected':<14} {'no-context':<12} says")
    print("  " + "-" * 76)
    for item in eval_set:
        text = ask_blind(item["question"], client)
        ref = refused(text)
        hit = contains_answer(item["expected_answer"], text) and not ref
        leaked += hit
        refused_n += ref
        verdict = "LEAKED" if hit else ("refused" if ref else "wrong")
        rows.append({"question": item["question"],
                     "expected": item["expected_answer"],
                     "verdict": verdict, "answer": text})
        print(f"  {item['expected_answer']:<14} {verdict:<12} {text.strip()[:58]}")

    n = len(eval_set)
    print(f"\n  {'=' * 60}")
    print(f"  answered correctly with NO context   {leaked}/{n}")
    print(f"  refused with no context              {refused_n}/{n}")
    print(f"  {'=' * 60}")
    print(f"\n  reranked answer correctness WITH context is 4/9.")
    if leaked:
        print(f"  {leaked} of those are not evidence that retrieval worked.")
    else:
        print("  No leakage: the generation figures are measuring retrieval.")

    # Second condition: no grounding instruction at all.
    print(f"\n  UNGUARDED: the same questions with no instruction to use context")
    print(f"  {'expected':<14} {'verdict':<12} says")
    print("  " + "-" * 76)
    knows, declines = 0, 0
    for item in eval_set:
        text = ask_unguarded(item["question"], client)
        ref = refused(text)
        hit = contains_answer(item["expected_answer"], text) and not ref
        knows += hit
        declines += ref
        for r in rows:
            if r["question"] == item["question"]:
                r["unguarded_verdict"] = "KNOWS" if hit else ("declined" if ref else "wrong")
                r["unguarded_answer"] = text
        print(f"  {item['expected_answer']:<14} "
              f"{('KNOWS' if hit else 'declined' if ref else 'wrong'):<12} {text.strip()[:58]}")
    print(f"\n  answers correctly with no context and no instruction  {knows}/{n}")
    print(f"  declines                                              {declines}/{n}")

    with open("no_context_results.json", "w") as f:
        json.dump({"n": n, "leaked": leaked, "refused": refused_n,
                   "unguarded_knows": knows, "unguarded_declines": declines,
                   "rows": rows},
                  f, indent=2)
        f.write("\n")
    print("\n  Written to no_context_results.json")


if __name__ == "__main__":
    main()
