# sec-filings

A retrieval pipeline over SEC filings, and an evaluation harness that caught its own metrics lying five separate times.

The corpus is 16 filings (one 10-K and three 10-Qs each) for Pinterest, Snap, Reddit and Meta, covering Q3 2025 through Q2 2026. Multi-company on purpose: "what was revenue last quarter" has sixteen defensible answers, and the only thing separating them is whether retrieval found the right passage.

**The retriever is ordinary. The harness is the point.**

**[FINDINGS.md](FINDINGS.md)** is the full log, twelve findings in the order they happened, including six predictions recorded as wrong.
**[METRICS.md](METRICS.md)** is the fourteen metric lessons on their own, each with the numbers that paid for it.

## Headline

**The first retrieval metric reported 4/4 on a system that was actually at 1/4.**

It scored a hit whenever any chunk from the expected *file* reached the top three. Pinterest's 10-K is 540 chunks and every query contains the word "Pinterest", so grabbing *some* chunk from the right file was close to guaranteed. The test could barely fail.

Scoring instead on whether a retrieved passage actually **contains** the answer gave 1/4.

That was the original eval set of four questions, in September 2026. It is a claim about a broken metric, not about performance, which is why it stays the headline even though the current numbers are different.

## Current results

Nine golden pairs now, five of them written to break things on purpose. Same nine questions across all three rows, so only the retriever changes:

```
                   hit@3   hit@10    MRR
lexical only         4/9      6/9   0.486
hybrid (w=0.2)       4/9      7/9   0.462
+ reranking          6/9      8/9   0.571
```

**The system answers six of nine questions in its top three results.** The diagnosis is the work here, not the performance.

**These are not comparable to the 1/4 above.** That was four questions, these are nine, and five of the nine were written specifically to be hard. A score only means something against a fixed test set, which is [metric lesson 9](METRICS.md).

## What the harness caught

Five times a number disagreed with reality. The full log is in [FINDINGS.md](FINDINGS.md); the short version:

**A metric that could not fail.** File-level 4/4, fact-level 1/4.

**A metric that could not see success.** Two fixes took the hardest question from unreachable in 9,811 chunks to rank 7, and `hit@3` read 1/4 through all three measurements. It is a threshold, so rank 33 and rank 9,811 score identically.

**A fix that was hurting.** An ablation across all 16 feature combinations found provenance headers diluted "pinterest" from 219 chunks to 1,817, and a Pinterest question started returning **Snap documents**. Removed.

**A metric that went down on a change that helped.** Hybrid improved five of nine questions and MRR **fell**, because one question slipping rank 1 to 2 costs more than another jumping 27 to 7 gains.

**Two metrics moving in opposite directions.** Reranking made file-level worse (8/9 to 7/9) and fact-level better (4/9 to 6/9). It reaches the right *file* less often and finds the actual *answer* more often. Measuring file-level only, you would have discarded the largest single improvement in the project.

## When not to use this

**For 16 documents, `grep` beats this pipeline.** It is exact, instant, free, and it never gets it wrong:

```bash
grep -o "Revenue was \$[0-9.]* billion" corpus/RDDT-10-K-2025-12-31.txt
```

That returns the right answer in under a second. The pipeline currently returns the right passage for 1 question out of 4. If the job is "find a known figure in a known filing," building retrieval is worse than `grep` in every way that can be measured.

Retrieval earns its place when one of these is true:

- **You do not know the exact words.** Ask "how is the ad business doing" and `grep` has nothing to match on. Retrieval ranks by overall similarity, so it can return something useful for a question with no keyword in it.
- **The corpus is too big to read the matches.** 16 files is fine. 16,000 files and `grep` hands you 400 hits in no particular order.
- **You want an answer, not a list of line numbers.** The generation step turns passages into a sentence, and the prompt makes it refuse when the passages do not contain the answer.

At this corpus size, only the third is really true here, and that is worth being honest about.

### The answer key was built with grep on purpose

Every golden pair in `eval_set.json` was found with `grep` over the raw filings, not with this pipeline.

That is deliberate. **You cannot test a system using the system itself.** Ground truth has to come from a method you trust more than the thing being measured, or you are just checking that the system agrees with itself.

So: `grep` for truth, retrieval for the thing on trial.

## How it works

```
fetch_filings.py    ->  corpus/*.txt       16 filings, 6.2 MB
build_index.py      ->  index.pkl          9,465 chunks, TF-IDF with sublinear term frequency
build_embeddings.py ->  embeddings.pkl     the same chunks as 384-dim vectors
query.py            ->  answer             lexical, hybrid or reranked retrieval, then generation
run_eval.py         ->  eval_results.json  both retrievers side by side, per-question ranks
```

Four stages, each persisting to disk, so retrieval can be re-run without re-downloading and re-scored without re-indexing. The real reason they are separate is diagnostic: **each stage fails differently, and fused together you cannot tell which one broke.**

Four design decisions worth calling out:

**The HTML converter preserves block boundaries** before stripping tags. Closing `</p>`, `</tr>` and `</h1>` become newlines, `</td>` becomes a tab. Strip tags first and a financial table collapses into one line with every row boundary gone. You cannot chunk on structure a parser already destroyed.

**Every change is measured against byte-identical chunks.** When provenance headers existed they were prepended after chunking, never before, so chunk boundaries stayed the same across index versions and the change under test was the only variable. Same rule applies to anything added next.

**Generation failure never takes down the retrieval measurement.** An invalid key returns a sentinel string rather than raising. The premise is that retrieval and generation fail independently, so the harness has to survive one without losing the other. It did not, until a 401 killed a run and exposed it.

**Anything that can fail silently is asserted.** `glob`, `replace` and `re.sub` all do nothing quietly when they match nothing, which is how you get a run that reports success having computed over an empty corpus. The XBRL strip uses `re.subn` and asserts the match count is exactly 1, because `re.sub` cannot tell you it matched nothing. Read the assertion messages if one fires; each names the failure it is catching.

## Reproduce it

```bash
pip install -r requirements.txt
export SEC_USER_AGENT="Your Name your@email.com"   # EDGAR returns 403 without this
export ANTHROPIC_API_KEY="..."                     # retrieval works without it, generation does not
python3 fetch_filings.py
python3 build_index.py corpus
python3 build_embeddings.py     # optional. without it, run_eval reports lexical only
python3 run_eval.py
```

The corpus is gitignored on purpose. Shipping 6 MB of scraped text would make the repo self-contained and unverifiable; shipping the fetcher means anyone who clones it rebuilds the same corpus and gets the same numbers.

## Current state

```
                 hit@3   hit@10    MRR
lexical only       4/9      6/9   0.486
hybrid (w=0.2)     4/9      7/9   0.462
+ reranking        6/9      8/9   0.571
```

**The pipeline answers six of nine questions in its top three results.** The diagnosis is the work here, not the performance.

Reranking produced the clearest demonstration of the finding this repo is named for. The two retrieval metrics moved in **opposite directions**:

```
file-level hit@3    8/9  ->  7/9   worse
fact-level hit@3    4/9  ->  6/9   better
```

It reaches the right *file* less often and finds the actual *answer* more often, because the right file was never what mattered. Measuring file-level only, you would have concluded reranking hurt and discarded the largest single improvement in the project.

**Nine golden pairs**, five written to break things on purpose: company disambiguation, a comparative period, a relative date, vocabulary mismatch, and a fact that only exists in a table. Every figure in this README comes out of `run_eval.py`.

**Read hit@10, not MRR, for this system.** The top k chunks are passed to a model that reads all of them, so whether the fact is 3rd or 9th does not matter, only whether it is in there. MRR weights position 1 heavily, which is right for a search engine a person reads and wrong here. The two metrics disagree about hybrid and the per-question table settles it.

**`HYBRID_WEIGHT = 0.2` is not validated.** Eight values swept against nine golden pairs is tuning on a test set too small to justify a decimal place. The direction holds across every setting (a little semantic helps, a lot destroys the exact-number questions); the specific value does not.

**Pure embeddings are worse than pure TF-IDF here**, MRR 0.205 against 0.486. An exact figure like "$2.2 billion" is not a semantic concept, so it falls from rank 1 to 33. Hybrid exists because the two retrievers fail differently, not because embeddings are better.

**TF-IDF first was deliberate, and it paid.** Every finding in this repo came from a lexical failure being inspectable: you can point at a term count and say why a chunk lost. A dense retriever would have papered over the provenance bug and the unfalsifiable metric, and neither would have been found.

### Open problems

**Period disambiguation.** "MAUs as of December 31, 2025" still returns Pinterest chunks from September quarters. All four companies have a December fiscal year end, so "december" means "this is an annual report" rather than naming one document. Fixing it needs the date parsed out of the question and used as a filter, which is a different kind of retrieval.

**Nine golden pairs is thin.** Enough to find a bug, not enough to justify a tuned parameter. Twenty would be better.

**Answer correctness has never been measured end to end.** It needs a working `ANTHROPIC_API_KEY` and currently reports 0/9 because generation fails, not because generation is wrong.
