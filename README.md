# sec-filings

A retrieval pipeline over SEC filings, and an evaluation harness that caught its own metric lying.

The corpus is 16 filings (one 10-K and three 10-Qs each) for Pinterest, Snap, Reddit and Meta, covering Q3 2025 through Q2 2026. Multi-company on purpose: "what was revenue last quarter" has sixteen defensible answers, and the only thing separating them is whether retrieval found the right passage.

## What this found, in the order it happened

Four findings. Each one came from not believing the previous number.

### 1. A metric that could not fail

The harness scored retrieval by asking "did any chunk from the expected file reach the top three." Pinterest's 10-K is 540 chunks and every question contains the word "Pinterest," so landing *some* chunk from that file is close to guaranteed. The test was nearly unfalsifiable.

It reported **4/4**.

Scoring instead on whether a retrieved passage actually contains the answer:

| Question | Expected | Right file | Passage has the fact |
|---|---|---|---|
| Pinterest headcount, Dec 2025 | 5,265 | yes | **no** |
| Pinterest MAUs, Dec 2025 | 619 million | yes | **no** |
| Pinterest revenue growth, 2025 | 16% | yes | **no** |
| Snap DAUs, Q4 2025 | 474 million | yes | yes |

**File-level 4/4. Fact-level 1/4.**

The revenue query is the clearest case. Top three, in rank order:

```
[0.318] SNAP-10-K-2025-12-31.txt   <- wrong company, rank 1
[0.289] PINS-10-K-2025-12-31.txt   <- right company, scored the "hit"
[0.285] META-10-K-2025-12-31.txt   <- wrong company
```

The Pinterest chunk that rescued the score reads:

> Research and development $1,427,447 $1,240,564 **15%**

R&D expense, not revenue growth, one point off the right answer. The Meta chunk carries **22%**, which is Meta's revenue growth. Three plausible percentages from three companies, and not one of them was Pinterest's 16%.

### 2. Generation is blameless

With a working API key, answer correctness is **1/4**, matching fact-level retrieval exactly.

That is not a coincidence. Generation succeeded on the one question where retrieval surfaced the fact, and refused on the three where it did not:

> "The context does not contain this information. It only mentions MAU data as of September 30, 2025 and September 30, 2024, but does not provide a figure for December 31, 2025."

**Generation added zero errors.** It never guessed and never dressed a near-miss as an answer. So rewriting the prompt would change nothing. Retrieval is the entire problem, and measuring the two separately is what proved it.

An earlier version of this README predicted the model would confidently answer 15% from that R&D table. It did not. The instruction "if the context doesn't contain the answer, say so explicitly, do not guess" held. The wrong answer was sitting in the context and only that line prevented it, which is worth knowing before anyone removes it.

### 3. Four questions, three different diseases

Sweeping k, the number of chunks retrieved, and recording the rank at which the correct fact first appears:

| Answer | Rank | Diagnosis |
|---|---|---|
| Snap DAU 474 | **1** | works |
| Pinterest revenue 16% | **6** | ranking, just outside k=3 |
| Pinterest MAU 619 | **27** | ranking, badly |
| Pinterest headcount 5,265 | **not in top 200** | unreachable |

```
   k   fact-level hits
   1   1/4
   3   1/4
   5   1/4
  10   2/4
  25   2/4
  50   3/4
 100   3/4
```

Two of these are ranking problems: the passage exists and is reachable, it is just outranked by boilerplate. One is not a ranking problem at all.

Raising k to 50 scores 3/4 and is a fake fix. It buys fifty passages of context, mostly noise, and hands generation fifty chances to pick a wrong number. Same mistake as the file-level metric: a number rising while nothing improves.

### 4. The chunk does not know which document it is in

Headcount is unreachable at any k. The chunk containing it holds four of the five query terms:

| Query term | In N of 9,811 chunks | IDF | In the fact chunk |
|---|---|---|---|
| pinterest | 218 | **4.80** | **no** |
| headcount | 104 | 5.54 | yes |
| december | 1,118 | 3.17 | yes |
| 31 | 1,763 | 2.72 | yes |
| 2025 | 2,549 | 2.35 | yes |

It has "headcount," the rarest term in the query. It still cannot place in the top 200, because it never says "Pinterest," and that term appears in only 218 of 9,811 chunks, making it the strongest discriminator available. The chunk forfeits it and drowns.

The chunk sits inside Pinterest's 10-K. It simply does not know that. TF-IDF sees 800 characters of text, not the filename they came from.

```
• Cash, cash equivalents and marketable securities were $2,467.2 million.
• Headcount was 5,265.
...
Trends in User Metrics
```

"Headcount was 5,265" is 22 characters. The nearest header is hundreds of characters away, and it does not name the company either.

**This also kills the fix that looked obvious.** Sublinear TF downweights chunks that over-repeat a term. This chunk never says the term. The planned fix was irrelevant to the worst case, and that only surfaced because the numbers got pulled before the code got changed.

## Why retrieval fails here, summarised

**The boilerplate attractor.** Ask for headcount and the top hits are the legal definitions section, which contains no facts and wins by repeating the company name. This is a direct consequence of the multi-company corpus: in a single-company corpus IDF would crush the company name to nothing, but across four companies it stays valuable, and the densest pile of it sits where there are no numbers.

**Chunks without provenance.** Fixed 800-character windows with 150 overlap, blind to structure, producing passages that carry a figure and no indication of which company or period it belongs to.

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

- **Fact-level scoring is not yet in `run_eval.py`.** It was computed separately to produce the numbers above. Both metrics should be reported, because the gap between them is itself the finding.
- **Chunk provenance is the next change.** Prepend company, form and period to every chunk so a passage carries its own identity. This attacks the failure that was actually measured rather than the one that was predicted.
- **Answer correctness is 1/4**, measured end to end. It matches fact-level retrieval exactly, which is how we know generation is not the problem.
- The eval set is four golden pairs. Twelve is the target.
- Sublinear TF is **not** the fix for the headcount case and was dropped after the term counts were checked. It may still help the two ranking failures.
