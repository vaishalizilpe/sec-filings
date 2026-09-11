# sec-filings

A retrieval pipeline over SEC filings, and an evaluation harness that caught its own metrics lying three separate times.

The corpus is 16 filings (one 10-K and three 10-Qs each) for Pinterest, Snap, Reddit and Meta, covering Q3 2025 through Q2 2026. Multi-company on purpose: "what was revenue last quarter" has sixteen defensible answers, and the only thing separating them is whether retrieval found the right passage.

**The retriever is ordinary. The harness is the point.**

## Headline

The first retrieval metric reported **4/4**. The system was actually at **1/4**.

It scored a hit whenever any chunk from the expected *file* reached the top three. Pinterest's 10-K is 540 chunks and every query says "Pinterest," so the test was close to unfalsifiable. Scoring on whether a retrieved passage actually **contains** the answer gave 1/4.

Two fixes later, the hardest question moved from unreachable in 9,811 chunks to rank 7, and **hit@3 still reads 1/4**:

```
              hit@3   hit@10    MRR
naive          1/4      2/4    0.301
+provenance    1/4      2/4    0.330
+sublinear TF  1/4      3/4    0.343
```

| Question | naive | +prov | +subTF |
|---|---|---|---|
| Snap DAU 474 | 1 | 1 | 1 |
| Pinterest revenue 16% | 6 | 4 | 6 |
| Pinterest MAU 619 | 27 | 25 | 16 |
| Pinterest headcount 5,265 | >200 | 33 | 7 |

Three metrics, three different stories about the same two changes.

And the failure that is left was caused by one of the fixes. The provenance header stamps a date onto every chunk, which collapsed the IDF (inverse document frequency, a measure of how rare a word is across the corpus) of every date word:

| Word | Before headers | After headers |
|---|---|---|
| december | 1,118 chunks, IDF 3.17 | 3,549 chunks, IDF 2.02 |
| 2025 | 2,549 chunks, IDF 2.35 | 6,270 chunks, IDF 1.45 |

The header bought company disambiguation by spending period disambiguation. The MAU question needs the period. That is finding 7, and it is where pure lexical retrieval runs out.

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
fetch_filings.py  ->  corpus/*.txt      16 filings, 6.1 MB
build_index.py    ->  index.pkl         9,811 chunks, provenance headers, TF-IDF
query.py          ->  answer            top-k retrieval, then generation
run_eval.py       ->  eval_results.json two scores
```

Four stages, each persisting to disk, so retrieval can be re-run without re-downloading and re-scored without re-indexing. The real reason they are separate is diagnostic: **each stage fails differently, and fused together you cannot tell which one broke.**

Three design decisions worth calling out:

**The HTML converter preserves block boundaries** before stripping tags. Closing `</p>`, `</tr>` and `</h1>` become newlines, `</td>` becomes a tab. Strip tags first and a financial table collapses into one line with every row boundary gone. You cannot chunk on structure a parser already destroyed.

**Provenance headers are prepended after chunking, not before,** so chunk boundaries stay byte-identical across index versions and provenance is the only variable.

**Generation failure never takes down the retrieval measurement.** An invalid key returns a sentinel string rather than raising. The premise is that retrieval and generation fail independently, so the harness has to survive one without losing the other. It did not, until a 401 killed a run and exposed it.

## Reproduce it

```bash
pip install -r requirements.txt
export SEC_USER_AGENT="Your Name your@email.com"   # EDGAR returns 403 without this
export ANTHROPIC_API_KEY="..."                     # retrieval works without it, generation does not
python3 fetch_filings.py
python3 build_index.py corpus
python3 run_eval.py
```

The corpus is gitignored on purpose. Shipping 6 MB of scraped text would make the repo self-contained and unverifiable; shipping the fetcher means anyone who clones it rebuilds the same corpus and gets the same numbers.

## Current state

- **The pipeline answers 1 of 4 questions.** The diagnosis is the work here, not the performance.
- **Eight golden pairs now, four of them corner cases.** Fact-level scoring, MRR and per-question ranks are still computed outside `run_eval.py`. They were computed separately to produce the numbers above.
- **MAU is the failure that is left, and no parameter will fix it.** The three period terms ("december", "31", "2025") have the lowest IDF in the query, and the provenance headers lowered them further. IDF is a property of the corpus, not a setting, so you cannot raise it by changing how you count. Fixing it needs query parsing plus metadata filtering, or hybrid search. Either way it stops being pure lexical retrieval.
- Four golden pairs. Twelve is the target.
- TF-IDF rather than embeddings, deliberately. A dense retriever would have partially papered over the provenance problem and it would never have been found.
