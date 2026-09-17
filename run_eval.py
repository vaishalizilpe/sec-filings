"""
The eval harness. This is the part that separates a tutorial RAG project from a
hireable one.

It reports FOUR numbers, because one number has been wrong here three separate
times. See METRICS.md.

  file-level hit@3   did any chunk from the expected FILE reach the top 3?
  fact-level hit@3   does a retrieved passage actually CONTAIN the answer?
  fact-level hit@10  same question, deeper
  MRR                mean reciprocal rank: 1/rank of the first correct result

The gap between the first two is the finding this project is named for. File-level
scoring reported 4/4 on a system that was really at 1/4, because Pinterest's 10-K
is 540 chunks and every query contains the word "Pinterest", so landing SOME chunk
from the right file is close to guaranteed. It is kept in the output on purpose:
seeing both numbers side by side is the point.

Retrieval and generation are also measured separately, because they fail for
different reasons and have different fixes. If fact-level retrieval is low,
rewriting the prompt will not help, the model never saw the fact.

Usage:
    python run_eval.py
    ANTHROPIC_API_KEY is optional. Without it, retrieval is still measured.
"""
import json
import pickle
from query import retrieve, answer

DEPTH = 200   # how far down to look when recording the rank of the right answer


def evaluate(index, eval_set, generate=True):
    results = []
    for item in eval_set:
        q = item["question"]
        expected_answer = item["expected_answer"]
        expected_source = item["expected_source_contains"]

        deep = retrieve(q, index, k=DEPTH)

        # Rank of the first chunk that actually contains the answer. None if it
        # never appears. This is the number that matters.
        rank = next(
            (i + 1 for i, (c, _) in enumerate(deep) if expected_answer in c["text"]),
            None,
        )

        # The old, nearly unfalsifiable metric, kept for contrast.
        top3 = deep[:3]
        file_hit = any(expected_source in c["source"] for c, _ in top3)

        gen_answer = answer(q, top3) if generate else "[generation skipped]"
        correct = expected_answer.lower() in gen_answer.lower()

        results.append({
            "question": q,
            "expected_answer": expected_answer,
            "rank": rank,
            "fact_hit_3": bool(rank and rank <= 3),
            "fact_hit_10": bool(rank and rank <= 10),
            "file_hit_3": file_hit,
            "answer_correct": correct,
            "generated_answer": gen_answer,
            "sources_retrieved": [c["source"] for c, _ in top3],
        })
    return results


def report(results):
    n = len(results)
    file3 = sum(r["file_hit_3"] for r in results)
    fact3 = sum(r["fact_hit_3"] for r in results)
    fact10 = sum(r["fact_hit_10"] for r in results)
    correct = sum(r["answer_correct"] for r in results)
    mrr = sum(1 / r["rank"] for r in results if r["rank"]) / n

    print(f"\n{'=' * 64}")
    print(f"  file-level hit@3   {file3}/{n}   did we reach the right FILE?")
    print(f"  fact-level hit@3   {fact3}/{n}   did a passage CONTAIN the answer?")
    print(f"  fact-level hit@10  {fact10}/{n}")
    print(f"  MRR                {mrr:.3f}   mean of 1/rank")
    print(f"  answer correctness {correct}/{n}")
    print(f"{'=' * 64}\n")

    if file3 > fact3:
        print(f"  NOTE: file-level is {file3}/{n} and fact-level is {fact3}/{n}.")
        print("  The gap is the point. See FINDINGS.md finding 1.\n")

    # Per-question ranks, because no aggregate can show that one question
    # improved thirtyfold while another round-tripped. See METRICS.md lesson 4.
    print(f"  {'rank':>6}  {'answer':<14} question")
    for r in results:
        rank = str(r["rank"]) if r["rank"] else f">{DEPTH}"
        print(f"  {rank:>6}  {r['expected_answer']:<14} {r['question'][:60]}")
    print()


def run_eval():
    with open("index.pkl", "rb") as f:
        index = pickle.load(f)
    with open("eval_set.json", "r") as f:
        eval_set = json.load(f)

    results = evaluate(index, eval_set)
    report(results)

    with open("eval_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Full results written to eval_results.json")
    return results


if __name__ == "__main__":
    run_eval()
