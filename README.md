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

And the problem that is left was caused by one of the fixes. The header puts a date on every chunk, and search only finds things using rare words. Put a date everywhere and dates stop being useful:

| Word | Before headers | After |
|---|---|---|
| december | 1,118 chunks, helps | 3,549 chunks, barely helps |
| 2025 | 2,549 chunks, helps | 6,270 chunks, barely helps |

The header paid for the company name by giving up the date. The MAU question needs the date. That is finding 7, and it is where simple word matching runs out.

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
- **Fact-level scoring, MRR and per-question ranks are not yet in `run_eval.py`.** They were computed separately to produce the numbers above.
- **MAU is the problem that is left, and no setting will fix it.** The three words that say which quarter ("december", "31", "2025") are the weakest words in the question, and the headers I added made them weaker. You cannot make a common word rare by changing how you count it. Fixing it means reading the date out of the question and filtering on it, which is a different kind of system.
- Four golden pairs. Twelve is the target.
- TF-IDF rather than embeddings, deliberately. A dense retriever would have partially papered over the provenance problem and it would never have been found.
