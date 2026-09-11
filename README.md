# sec-filings

A retrieval pipeline over SEC filings, and an evaluation harness that caught its own metric lying.

The corpus is 16 filings (one 10-K and three 10-Qs each) for Pinterest, Snap, Reddit and Meta, covering Q3 2025 through Q2 2026. Multi-company on purpose: "what was revenue last quarter" has sixteen defensible answers, and the only thing separating them is whether retrieval found the right passage.

## The finding

**My first retrieval metric reported 100%. The system was actually at 25%.**

The harness scored retrieval by asking "did any chunk from the expected file appear in the top three results." Pinterest's 10-K is 540 chunks. The query contains the word "Pinterest." Landing *some* chunk from that file is close to guaranteed, so the test was nearly unfalsifiable.

Swapping to a fact-level test, "does a retrieved passage actually contain the answer," changed the picture completely:

| Question | Expected | Right file found | Passage contains the fact |
|---|---|---|---|
| Pinterest headcount, Dec 2025 | 5,265 | yes | **no** |
| Pinterest MAUs, Dec 2025 | 619 million | yes | **no** |
| Pinterest revenue growth, 2025 | 16% | yes | **no** |
| Snap DAUs, Q4 2025 | 474 million | yes | yes |

**File-level: 4/4. Fact-level: 1/4.**

## Why this matters more than a miss

Take the revenue question. Top three results, in rank order:

```
[0.318] SNAP-10-K-2025-12-31.txt   ← wrong company, rank 1
[0.289] PINS-10-K-2025-12-31.txt   ← right company, scored the "hit"
[0.285] META-10-K-2025-12-31.txt   ← wrong company
```

The Pinterest chunk that rescued the score contains this:

> Research and development $1,427,447 $1,240,564 **15%**
> Percentage of revenue 34% 34%

That is the R&D expense line, not revenue growth, and its percentage is one point off the right answer. The Meta chunk contains **22%**, which is Meta's revenue growth.

So the context passed to generation held three plausible percentages from three different companies, and none of them was Pinterest's 16%.

A model given that context does not say "I cannot find this." It answers **15%**: wrong metric, wrong number, right company, sourced from a real Pinterest table, and completely defensible-looking. That is the failure mode that matters if anyone is going to trust the output, and the file-level metric scored it as a perfect hit.

## Why retrieval fails here

Two distinct defects, which need different fixes.

**1. The boilerplate attractor.** Ask for headcount and the top hits are the legal definitions section:

> "the terms 'Pinterest,' 'company,' 'we,' 'us,' and 'our' in this document refer to Pinterest, Inc., a Delaware corporation..."

Zero facts. It wins because TF-IDF rewards term frequency and that section is a pile of the word "Pinterest." This failure is a direct consequence of the multi-company corpus: in a single-company corpus IDF would crush the company name to nothing. Across four companies it stays valuable, and the densest concentration of it sits in a section with no numbers in it.

**2. Boundary luck.** Chunking is fixed 800-character windows with 150 overlap, blind to document structure. From the Pinterest 10-K:

```
• Cash, cash equivalents and marketable securities were $2,467.2 million.
• Headcount was 5,265.
...
Trends in User Metrics
```

"Headcount was 5,265" is 22 characters. The header telling you which section it belongs to can be hundreds of characters away. A window starting after that header keeps the number and loses its label, and lexical retrieval cannot recover the link.

The MAU query technically retrieved the headcount figure once, for a question about MAUs, because the boundary happened to land between them. That is not retrieval working. That is a coin landing face up.

## How it works

```
fetch_filings.py  →  corpus/*.txt      16 filings, 6.1 MB
build_index.py    →  index.pkl         9,811 chunks, 12,110 vocab
query.py          →  answer            top-k retrieval, then generation
run_eval.py       →  eval_results.json two scores
```

Four stages, each persisting to disk, so retrieval can be re-run without re-downloading and re-scored without re-indexing. The real reason they are separate is diagnostic: **each stage fails differently, and fused together you cannot tell which one broke.**

Two design decisions worth calling out:

**The HTML converter preserves block boundaries** before stripping tags. Closing `</p>`, `</tr>` and `</h1>` become newlines; `</td>` becomes a tab. Strip tags first and a financial table collapses into one line with every row boundary gone. You cannot chunk on structure a parser already destroyed.

**Generation failure never takes down the retrieval measurement.** An invalid API key returns a sentinel string rather than raising. The whole premise is that retrieval and generation fail independently, so the harness has to survive one without losing the other. It did not, until a 401 killed a run and exposed it.

## Reproduce it

```bash
pip install -r requirements.txt
export SEC_USER_AGENT="Your Name your@email.com"   # EDGAR returns 403 without this
python3 fetch_filings.py      # rebuilds the corpus from EDGAR
python3 build_index.py corpus
python3 run_eval.py
```

The corpus is gitignored on purpose. Shipping 6 MB of scraped text would make the repo self-contained and unverifiable; shipping the fetcher means anyone who clones it rebuilds the same corpus and gets the same numbers.

## Current state and what is not done

- Fact-level retrieval scoring is the fix in progress. Both metrics should be reported, because the gap between them is itself the interesting number.
- **Header-aware chunking is not implemented.** That is the fix for defect 2 and the before-and-after it produces is the next milestone.
- **Answer correctness has never been measured end to end.** It requires `ANTHROPIC_API_KEY` and currently reads 0/4 because generation is failing, not because generation is wrong. Retrieval is the honest number today.
- The eval set is four golden pairs. Twelve is the target.
- The boilerplate attractor has no fix yet. Sublinear TF weighting is the first thing to try.
