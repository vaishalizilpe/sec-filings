"""
Day 5: The eval harness. This is the part that separates a tutorial RAG
project from a hireable one.

Measures TWO things separately, because they fail independently:
1. Retrieval hit rate: did the right chunk even get retrieved?
2. Answer correctness: given the retrieved chunk, did generation get it right?

If retrieval hit rate is low, fixing the generation prompt won't help,
the model never saw the fact. Fix chunking or the retriever first.
If retrieval hit rate is high but answer correctness is low, that's a
generation/prompt problem, not a retrieval problem. Different fixes.

Usage:
    python run_eval.py
"""
import json
import pickle
from query import retrieve, answer


def run_eval():
    with open("index.pkl", "rb") as f:
        index = pickle.load(f)
    with open("eval_set.json", "r") as f:
        eval_set = json.load(f)

    retrieval_hits = 0
    answer_correct = 0
    results = []

    for item in eval_set:
        q = item["question"]
        expected_source = item["expected_source_contains"]
        expected_answer = item["expected_answer"]

        retrieved = retrieve(q, index, k=3)
        sources_hit = [c["source"] for c, score in retrieved]
        retrieval_hit = any(expected_source in s for s in sources_hit)
        if retrieval_hit:
            retrieval_hits += 1

        gen_answer = answer(q, retrieved)
        correct = expected_answer.lower() in gen_answer.lower()
        if correct:
            answer_correct += 1

        results.append({
            "question": q,
            "expected_answer": expected_answer,
            "retrieval_hit": retrieval_hit,
            "sources_retrieved": sources_hit,
            "generated_answer": gen_answer,
            "answer_correct": correct,
        })

    n = len(eval_set)
    print(f"\n{'='*60}")
    print(f"Retrieval hit rate:  {retrieval_hits}/{n} ({100*retrieval_hits/n:.0f}%)")
    print(f"Answer correctness:  {answer_correct}/{n} ({100*answer_correct/n:.0f}%)")
    print(f"{'='*60}\n")

    for r in results:
        status = "PASS" if r["answer_correct"] else "FAIL"
        hit = "hit " if r["retrieval_hit"] else "MISS"
        print(f"[{status}] [retrieval {hit}] {r['question']}")
        if not r["answer_correct"]:
            print(f"    expected: {r['expected_answer']}")
            print(f"    got:      {r['generated_answer'][:200]}")

    with open("eval_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nFull results written to eval_results.json")

    return retrieval_hits, answer_correct, n


if __name__ == "__main__":
    run_eval()
