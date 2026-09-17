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
import os
import re
from query import retrieve, retrieve_hybrid, rerank, answer, HYBRID_WEIGHT, RERANK_CANDIDATES

DEPTH = 200   # how far down to look when recording the rank of the right answer


def contains_answer(expected, text):
    """Does `text` state `expected` as a standalone value?

    Plain substring matching was wrong here. Most expected answers are short
    numbers, and `"619" in text` is true inside 120,619 and 4,619. Across the
    corpus that was 55 false matches out of 141, and the bias runs one way:
    a false match earlier in the ranking is taken as THE rank, so every metric
    computed from it read better than the truth.

    Requiring a non-digit boundary on both sides fixes that. It does not fix
    the harder cases, a right number asserted about the wrong company or the
    wrong period, which needs a judge rather than a regex. See METRICS.md.
    """
    pattern = r"(?<![\d,.])" + re.escape(expected) + r"(?![\d,.])"
    return re.search(pattern, text, re.IGNORECASE) is not None


REFUSAL_MARKERS = (
    "does not contain", "doesn't contain", "does not disclose", "doesn't disclose",
    "not disclosed", "cannot find", "can't find", "no information", "not provided",
    "not available", "not stated", "unable to", "does not appear", "not in the",
)


def generation_ran(text):
    """False when no model output exists to grade.

    Two sentinels mean the model never spoke: generation was skipped, or the
    API call failed and answer() degraded rather than raising. Counting either
    as "did not refuse" would report a model behaviour that never happened.
    """
    return not (text.startswith("[No ANTHROPIC_API_KEY")
                or text.startswith("[Generation failed:")
                or text == "[generation skipped]")


def refused(text):
    """Did the model decline to answer instead of guessing?

    Crude on purpose, and it is a string match, which is the exact flaw this
    project keeps finding. It is here because a deterministic check costs
    nothing and runs with no API key. It cannot tell a well-reasoned refusal
    from a hedge wrapped around a fabricated number, which is what the judge
    is for. Treat this number as a floor, not a verdict.
    """
    low = text.lower()
    return any(m in low for m in REFUSAL_MARKERS)


def load_embeddings():
    """Optional. Returns (embeddings, model) or (None, None)."""
    if not os.path.exists("embeddings.pkl"):
        return None, None
    with open("embeddings.pkl", "rb") as f:
        emb = pickle.load(f)
    from sentence_transformers import SentenceTransformer
    return emb, SentenceTransformer(emb["model"])


def evaluate(index, eval_set, generate=True, embeddings=None, model=None,
             use_rerank=False):
    results = []
    for item in eval_set:
        q = item["question"]
        answerable = item.get("answerable", True)
        expected_answer = item.get("expected_answer")
        expected_source = item.get("expected_source_contains")

        if embeddings is not None:
            deep = retrieve_hybrid(q, index, embeddings, model, k=DEPTH)
        else:
            deep = retrieve(q, index, k=DEPTH)

        if use_rerank:
            # Reorder the top candidates, then put the rest back below them so
            # rank is still measurable past the rerank window.
            head = rerank(q, deep[:RERANK_CANDIDATES], k=RERANK_CANDIDATES)
            deep = head + deep[RERANK_CANDIDATES:]

        # Rank of the first chunk that actually contains the answer. None if it
        # never appears. This is the number that matters.
        #
        # Unanswerable questions have no rank and no expected source. Retrieval
        # still runs and the model is still handed the top 3, because refusing
        # while holding plausible-looking context is the behaviour under test.
        if answerable:
            rank = next(
                (i + 1 for i, (c, _) in enumerate(deep)
                 if contains_answer(expected_answer, c["text"])),
                None,
            )
        else:
            rank = None

        # The old, nearly unfalsifiable metric, kept for contrast.
        top3 = deep[:3]
        file_hit = bool(expected_source) and any(
            expected_source in c["source"] for c, _ in top3)

        gen_answer = answer(q, top3) if generate else "[generation skipped]"
        correct = contains_answer(expected_answer, gen_answer) if answerable else None
        did_refuse = (not answerable and generation_ran(gen_answer)
                      and refused(gen_answer))

        results.append({
            "question": q,
            "answerable": answerable,
            "refused": did_refuse,
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


SOURCE_FILES = ("build_index.py", "build_embeddings.py", "query.py", "run_eval.py")


def source_fingerprint():
    """A hash of the code that produces the numbers.

    results.json records this. check_docs.py recomputes it and fails when they
    differ, which means the code changed and the eval was not re-run.

    File timestamps were tried first and are useless here: git does not store
    mtimes, so a fresh CI checkout stamps every file with the checkout time and
    the comparison becomes meaningless in exactly the place it needs to work.
    """
    import hashlib
    h = hashlib.sha256()
    for name in SOURCE_FILES:
        with open(name, "rb") as f:
            h.update(f.read())
    return h.hexdigest()[:16]


def summarise(results):
    """The numbers only, as a dict. This is what results.json holds.

    Every figure published in a .md file must come from here. check_docs.py
    enforces that. Six figures went stale across three documents from a single
    code change before this existed.
    """
    ans = [r for r in results if r.get("answerable", True)]
    ref = [r for r in results if not r.get("answerable", True)]
    n = len(ans)
    return {
        "n_answerable": n,
        "n_refusal": len(ref),
        "file_hit_3": sum(r["file_hit_3"] for r in ans),
        "fact_hit_3": sum(r["fact_hit_3"] for r in ans),
        "fact_hit_10": sum(r["fact_hit_10"] for r in ans),
        "mrr": round(sum(1 / r["rank"] for r in ans if r["rank"]) / n, 3),
        "answer_correct": sum(bool(r["answer_correct"]) for r in ans),
        "refusals_correct": sum(r["refused"] for r in ref),
        "generation_ran": any(generation_ran(r["generated_answer"]) for r in results),
    }


def report(results):
    # Retrieval metrics are computed over answerable questions only. hit@3 and
    # MRR are undefined for a question with no answer in the corpus, and folding
    # refusals into the same denominator would move the headline numbers for a
    # reason that has nothing to do with retrieval.
    ans = [r for r in results if r.get("answerable", True)]
    ref = [r for r in results if not r.get("answerable", True)]

    n = len(ans)
    file3 = sum(r["file_hit_3"] for r in ans)
    fact3 = sum(r["fact_hit_3"] for r in ans)
    fact10 = sum(r["fact_hit_10"] for r in ans)
    correct = sum(bool(r["answer_correct"]) for r in ans)
    mrr = sum(1 / r["rank"] for r in ans if r["rank"]) / n

    print(f"\n{'=' * 64}")
    print(f"  file-level hit@3   {file3}/{n}   did we reach the right FILE?")
    print(f"  fact-level hit@3   {fact3}/{n}   did a passage CONTAIN the answer?")
    print(f"  fact-level hit@10  {fact10}/{n}")
    print(f"  MRR                {mrr:.3f}   mean of 1/rank")
    print(f"  answer correctness {correct}/{n}")
    if ref:
        no_output = all(not generation_ran(r["generated_answer"]) for r in ref)
        note = ("   no model output, generation skipped or failed" if no_output
                else "   did it decline when the corpus has no answer?")
        print(f"  correct refusals   {sum(r['refused'] for r in ref)}/{len(ref)}{note}")
    print(f"{'=' * 64}\n")

    if file3 > fact3:
        print(f"  NOTE: file-level is {file3}/{n} and fact-level is {fact3}/{n}.")
        print("  The gap is the point. See FINDINGS.md finding 1.\n")

    # Per-question ranks, because no aggregate can show that one question
    # improved thirtyfold while another round-tripped. See METRICS.md lesson 4.
    print(f"  {'rank':>6}  {'answer':<14} question")
    for r in results:
        if not r.get("answerable", True):
            if not generation_ran(r["generated_answer"]):
                mark = "no output"
            else:
                mark = "refused" if r["refused"] else "ANSWERED ANYWAY"
            print(f"  {'--':>6}  {'(no answer)':<14} {r['question'][:52]}  [{mark}]")
            continue
        rank = str(r["rank"]) if r["rank"] else f">{DEPTH}"
        print(f"  {rank:>6}  {r['expected_answer']:<14} {r['question'][:60]}")
    print()


def run_eval():
    with open("index.pkl", "rb") as f:
        index = pickle.load(f)
    with open("eval_set.json", "r") as f:
        eval_set = json.load(f)

    assert eval_set, "eval_set.json is empty. Nothing to measure."
    for i, item in enumerate(eval_set):
        assert "question" in item, f"Golden pair {i} is missing ['question']"
        if item.get("answerable", True):
            missing = {"expected_answer", "expected_source_contains"} - set(item)
            assert not missing, f"Answerable pair {i} is missing {sorted(missing)}"
        else:
            stray = {"expected_answer", "expected_source_contains"} & set(item)
            assert not stray, (
                f"Refusal pair {i} should not carry {sorted(stray)}. "
                "An unanswerable question has no correct answer to match.")

    # An index built from a different corpus than the one on disk would produce
    # numbers that look fine and describe the wrong thing.
    import os, glob as _glob
    corpus = _glob.glob("corpus/*.txt")
    if corpus and os.path.getmtime("index.pkl") < max(os.path.getmtime(f) for f in corpus):
        print("\n  WARNING: index.pkl is older than the corpus. Re-run build_index.py.\n")

    lexical = evaluate(index, eval_set)
    print("\n  LEXICAL ONLY (TF-IDF)")
    report(lexical)

    emb, model = load_embeddings()
    if emb is None:
        print("  No embeddings.pkl. Run build_embeddings.py to compare hybrid.\n")
        results = lexical
    else:
        print(f"  HYBRID ({int((1-HYBRID_WEIGHT)*100)}% lexical / "
              f"{int(HYBRID_WEIGHT*100)}% semantic)")
        hybrid = evaluate(index, eval_set, embeddings=emb, model=model)
        results = hybrid
        report(hybrid)

        print(f"  RERANKED (hybrid, then a cross-encoder over the top {RERANK_CANDIDATES})")
        # Reranking generates as well. The whole justification for reranking is
        # that it moves the right passage into the top 3 so the model can see it.
        # It took fact-level hit@3 from 4/9 to 6/9, meaning two more questions now
        # have their answer in front of the model. Whether the model then answers
        # them correctly is the central claim of this project, and it went
        # unmeasured for as long as this call passed generate=False.
        reranked = evaluate(index, eval_set, embeddings=emb,
                            model=model, use_rerank=True)
        report(reranked)

        def col(r):
            return str(r["rank"]) if r["rank"] else f">{DEPTH}"

        print(f"  {'answer':<14} {'lexical':>8} {'hybrid':>8} {'+rerank':>9}")
        for a, b, c in zip(lexical, results, reranked):
            # Refusal cases have no rank; there is nothing to compare across
            # retrievers for a question with no answer in the corpus.
            if not a.get("answerable", True):
                continue
            print(f"    {a['expected_answer']:<14} {col(a):>6} {col(b):>8} {col(c):>9}")
        print()
        results = reranked

    # Every config, not only the last one. This file previously held whichever
    # config ran last, which was reranked, which did not generate, so the model's
    # actual answers were written nowhere and could not be read back or labelled.
    per_config = {"lexical": lexical}
    if emb is not None:
        per_config["hybrid"] = hybrid
        per_config["reranked"] = reranked
    with open("eval_results.json", "w") as f:
        json.dump(per_config, f, indent=2)

    # results.json is committed and is the single source of truth for every
    # number published in a .md file. eval_results.json stays gitignored
    # because it carries full generated answers and is large.
    summary = {"source_fingerprint": source_fingerprint(),
                "lexical": summarise(lexical)}
    if emb is not None:
        summary["hybrid"] = summarise(hybrid)
        summary["reranked"] = summarise(reranked)
    with open("results.json", "w") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")
    print("Full results written to eval_results.json")
    print("Published figures written to results.json")
    return results


if __name__ == "__main__":
    run_eval()
