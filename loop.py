"""
An agentic loop over the same retriever, and the baseline it has to beat.

The case for it, measured rather than assumed. A comparison question needs
facts from two filings. One retrieval call blends terms from both subjects
and matches neither well: asked which of Pinterest or Snap had more
employees, the Pinterest fact sits at hybrid rank 83 and the Snap fact beyond
200, and the cross-encoder scored its best candidate at -0.813, which is the
model saying nothing here answers this. Ask about one company instead of two
and the same fact moves from rank 83 to rank 5.

So the loop's job is narrow and testable: SEARCH FOR ONE SUBJECT AT A TIME.
Not "search again", which would change nothing.

THE BAR. Not zero. A one-line change to k already answers some of this:

    k=3    0/5 questions, 1/12 hops in window, generation untested
    k=25   2/5 questions, 5/12 hops in window, 3/5 answered correctly

Three of five is what the loop has to beat. Measuring that before building
was the point of the k-sweep; a loop that scores three proves nothing.

THE METRIC CHANGES SHAPE. With one retrieval, "hops found" means the fact
reached the top 3. There is no single retrieval here, so it means the fact
appeared in the UNION of every passage the model saw across all its searches.
That is the fair comparison against k=25: both ask whether the system put the
fact in front of the model.

Usage:
    python loop.py            run the five multi-hop questions
    python loop.py --verbose  print every search the model issues
"""
import json
import pickle
import sys

import query as Q
from query import first_text
from run_eval import contains_answer
from sentence_transformers import SentenceTransformer

MODEL = "claude-sonnet-5"
MAX_ITERATIONS = 5     # a model that never stops searching runs forever and bills for it
SEARCH_K = 5           # per search. Deliberately small: the point is several
                       # narrow searches, not one wide one. k=25 is the baseline
                       # being beaten, so matching its width would prove nothing.

SEARCH_TOOL = {
    "name": "search",
    "description": (
        "Search a corpus of 16 SEC filings (10-K and 10-Q) for Pinterest, Snap, "
        "Reddit and Meta, covering Q3 2025 through Q2 2026. Returns passages. "
        "Search for ONE company and ONE fact at a time. A query naming two "
        "companies matches neither well."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string",
                      "description": "A single-subject question, e.g. 'Pinterest headcount December 2025'"},
        },
        "required": ["query"],
    },
}

SYSTEM = """You answer questions about SEC filings using only the search tool.

You may search as many times as you need. Search for one company and one fact
at a time: a query naming two companies scores poorly against both.

For a comparison question, search for each subject separately, then compare
the results yourself.

When you have what you need, answer. If the searches do not turn up the facts,
say so plainly rather than guessing."""


def run(question, index, emb, model, client, verbose=False):
    """One question. Returns the answer and everything the model saw."""
    messages = [{"role": "user", "content": question}]
    searches, seen = [], []

    # MAX_ITERATIONS search turns, then one extra answer-only turn. The first
    # fix spent the last search turn on the answer, which cost a search and
    # dropped hops found from 8/12 to 7/12. Forcing an answer and allowing a
    # search are different budgets and should not come out of the same pot.
    for i in range(MAX_ITERATIONS + 1):
        last = i == MAX_ITERATIONS
        if last:
            # Final turn: no tool, so the model must answer with what it has.
            #
            # The first version just stopped at the cap and returned a sentinel.
            # Two of five questions died that way, with the model still issuing
            # increasingly specific searches for a fact that is genuinely hard to
            # retrieve. It had partial evidence and an opinion and was never
            # asked for either. "Ran out of turns" and "could not answer" are
            # different outcomes and the harness was recording the first as the
            # second.
            messages.append({"role": "user", "content":
                             "No more searches. Answer now from what you have "
                             "found, or say plainly which fact you could not find."})
            resp = client.messages.create(
                model=MODEL, max_tokens=2000, system=SYSTEM, messages=messages)
            text = first_text(resp) or ""
            return {"answer": text, "searches": searches, "seen": seen,
                    "iterations": len(searches), "hit_cap": True}

        resp = client.messages.create(
            model=MODEL, max_tokens=2000, system=SYSTEM,
            tools=[SEARCH_TOOL], messages=messages,
        )
        if resp.stop_reason != "tool_use":
            text = first_text(resp) or ""
            return {"answer": text, "searches": searches, "seen": seen,
                    "iterations": len(searches), "hit_cap": False}

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            q = block.input["query"]
            searches.append(q)
            if verbose:
                print(f"      search: {q}")
            cand = Q.retrieve_hybrid(q, index, emb, model, k=Q.RERANK_CANDIDATES)
            hits = Q.rerank(q, cand, k=SEARCH_K)
            # Deduplicated. Two near-identical queries return overlapping
            # chunks, and counting the same passage twice inflates "passages
            # seen" in the output and in the README. It cannot change
            # hops_found, which is an any() over this list, but a number that
            # is only ever (searches x 5) is not measuring anything.
            for c, _ in hits:
                if not any(c["source"] == s["source"] and c["start"] == s["start"]
                           for s in seen):
                    seen.append(c)
            body = "\n\n---\n\n".join(
                f"[{c['source']}]\n{c['text']}" for c, _ in hits)
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": body or "No passages found."})
        messages.append({"role": "user", "content": results})

    # Unreachable: the final iteration always returns. Kept as a guard.
    return {"answer": "[loop exited without answering]",
            "searches": searches, "seen": seen,
            "iterations": len(searches), "hit_cap": True}


def main():
    key = Q.load_api_key()
    if not key:
        sys.exit("No ANTHROPIC_API_KEY. See .env.example.")
    import anthropic
    client = anthropic.Anthropic(api_key=key)

    index = pickle.load(open("index.pkl", "rb"))
    emb = pickle.load(open("embeddings.pkl", "rb"))
    model = SentenceTransformer(emb["model"])
    questions = [q for q in json.load(open("eval_set.json")) if q.get("hops")]

    verbose = "--verbose" in sys.argv
    rows, solved = [], 0
    for item in questions:
        print(f"\n  {item['question'][:66]}")
        r = run(item["question"], index, emb, model, client, verbose)

        # Union metric: did the fact appear in ANYTHING the model saw.
        found = []
        for hop in item["hops"]:
            found.append(any(hop["source_contains"] in c["source"]
                             and contains_answer(hop["fact"], c["text"])
                             for c in r["seen"]))
        all_found = all(found)
        solved += all_found
        print(f"      {len(r['searches'])} searches, {len(r['seen'])} passages seen, "
              f"hops found {sum(found)}/{len(found)}"
              f"{'  [HIT CAP]' if r['hit_cap'] else ''}")
        print(f"      said: {r['answer'].strip()[:150]}")
        rows.append({"question": item["question"], "expected": item["expected_answer"],
                     "searches": r["searches"], "n_passages": len(r["seen"]),
                     "hops_found": sum(found), "n_hops": len(found),
                     "all_hops_found": all_found, "hit_cap": r["hit_cap"],
                     "answer": r["answer"]})

    hops_found = sum(r["hops_found"] for r in rows)
    hops_total = sum(r["n_hops"] for r in rows)
    print(f"\n  {'=' * 60}")
    print(f"  LOOP          all hops in union  {solved}/{len(rows)}   hops {hops_found}/{hops_total}")
    print(f"  k=25 baseline all hops in top 25  2/5   hops 5/12")
    print(f"  {'=' * 60}")
    print("  Answer correctness is graded by judge.py, not by substring match.")

    with open("loop_results.json", "w") as f:
        json.dump({"solved": solved, "n": len(rows),
                   "hops_found": hops_found, "hops_total": hops_total,
                   "rows": rows}, f, indent=2)
        f.write("\n")
    print("\n  Written to loop_results.json")


if __name__ == "__main__":
    main()
