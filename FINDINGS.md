# Findings, in the order they happened

A working log. Each step came from not believing the previous number.

Setup: 16 SEC filings, four companies (PINS, SNAP, RDDT, META), Q3 2025 through Q2 2026. 9,811 chunks at 800 characters with 150 overlap. TF-IDF. Four golden pairs.

Multi-company on purpose: "what was revenue last quarter" has sixteen defensible answers, so retrieval has to disambiguate company and period rather than just match a topic.

---

## 1. The metric reported 4/4 and the system did not work

Retrieval was scored as "did any chunk from the expected **file** reach the top three." Pinterest's 10-K is 540 chunks and every query says "Pinterest," so the test was close to unfalsifiable.

Scoring on whether a retrieved passage actually **contains** the answer:

| Question | Expected | Right file | Passage has the fact |
|---|---|---|---|
| Pinterest headcount, Dec 2025 | 5,265 | yes | no |
| Pinterest MAUs, Dec 2025 | 619 million | yes | no |
| Pinterest revenue growth, 2025 | 16% | yes | no |
| Snap DAUs, Q4 2025 | 474 million | yes | yes |

**File-level 4/4. Fact-level 1/4.**

The revenue query, top three in rank order:

```
[0.318] SNAP-10-K-2025-12-31.txt   wrong company, rank 1
[0.289] PINS-10-K-2025-12-31.txt   right company, scored the "hit"
[0.285] META-10-K-2025-12-31.txt   wrong company
```

The Pinterest chunk that rescued the score reads `Research and development $1,427,447 $1,240,564 15%`. R&D expense, not revenue growth, one point off the right answer. The Meta chunk carries 22%, which is Meta's revenue growth. Three plausible percentages from three companies, none of them correct.

---

## 2. Generation was never the problem

With a working API key, answer correctness came back **1/4**, matching fact-level retrieval exactly, question by question.

Generation succeeded on the one question where retrieval surfaced the fact and refused on the three where it did not:

> "It only mentions MAU data as of September 30, 2025 and September 30, 2024, but does not provide a figure for December 31, 2025."

**Zero invented answers.** So the prompt was fine and retrieval was the whole problem. That refusal also named the real failure: right company, wrong quarter.

**Correction:** an earlier version of this log predicted the model would confidently answer 15% from that R&D table. It did not. The instruction "if the context doesn't contain the answer, say so explicitly, do not guess" held. The wrong answer was sitting in the context and only that line prevented it.

---

## 3. Four questions, three different diseases

Sweeping k and recording the rank at which the correct fact first appears:

| Answer | Rank | Diagnosis |
|---|---|---|
| Snap DAU 474 | 1 | works |
| Pinterest revenue 16% | 6 | ranking, just outside k=3 |
| Pinterest MAU 619 | 27 | ranking, badly |
| Pinterest headcount 5,265 | not in top 200 | unreachable |

```
   k   fact-level hits
   1   1/4
   3   1/4
  10   2/4
  50   3/4
```

Two are ranking problems where the passage exists and is outranked. One is not reachable at any k. **Raising k to 50 scores 3/4 and is a fake fix**: fifty passages of context, mostly noise, and fifty chances for generation to pick a wrong number.

---

## 4. The unreachable chunk did not know what document it was in

It holds four of the five query terms, including the rarest one:

| Query term | In N of 9,811 chunks | IDF | Present |
|---|---|---|---|
| pinterest | 218 | **4.80** | **no** |
| headcount | 104 | 5.54 | yes |
| december | 1,118 | 3.17 | yes |
| 31 | 1,763 | 2.72 | yes |
| 2025 | 2,549 | 2.35 | yes |

It has "headcount" and still cannot place in the top 200, because it never says "Pinterest," the strongest discriminator available. The chunk sits physically inside Pinterest's 10-K. The retriever sees 800 characters, not the filename.

**This killed the fix that looked obvious.** Sublinear TF downweights over-repetition and cannot reach a chunk that never says the term at all. That only surfaced because the term counts were pulled to *explain* the change before making it.

> A change you can implement without looking is a change you can get wrong without noticing.

---

## 5. Fix one: provenance headers

Every chunk gets a line naming its company, form and period:

```
Pinterest (PINS) 10-K for the period ending December 31, 2025 (2025-12-31).
• Headcount was 5,265.
```

Applied **after** chunking so boundaries stay byte-identical and provenance is the only variable.

| Answer | Before | After |
|---|---|---|
| Snap DAU 474 | 1 | 1 |
| Pinterest revenue 16% | 6 | **4** |
| Pinterest MAU 619 | 27 | 25 |
| Pinterest headcount 5,265 | **>200** | **33** |

**hit@3: 1/4, unchanged.** The prediction was 3/4 or 4/4. Wrong.

Headcount went from unreachable to rank 33, the single failure this targeted. The metric did not move because k=3 is a cliff.

Side effect, intended: "pinterest" went from 218 chunks (IDF 4.80) to 1,887 (IDF 2.65). It stopped separating boilerplate from facts and started separating Pinterest from Snap, which is the job it should have had.

---

## 6. Fix two: sublinear TF, which was premature rather than wrong

After provenance, both the boilerplate and the fact chunk claim the company. The only remaining difference is repetition, which is exactly what sublinear TF attacks.

| Chunk | says "pinterest" | linear | sublinear |
|---|---|---|---|
| Boilerplate | 4 | 4.00 | 2.39 |
| Fact chunk | 1 | 1.00 | 1.00 |

| Answer | naive | +prov | +subTF | Why |
|---|---|---|---|---|
| Snap DAU 474 | 1 | 1 | 1 | never broken |
| Pinterest headcount 5,265 | >200 | 33 | **7** | was starved of the key term; provenance fed it, sublinear TF cut boilerplate's 4x repetition advantage |
| Pinterest MAU 619 | 27 | 25 | **16** | **a period problem, not a company problem.** Top 16 results are 11 Pinterest 10-Q chunks and 5 Pinterest 10-K chunks. All Pinterest, so provenance discriminated nothing |
| Pinterest revenue 16% | 6 | 4 | **6** | **regressed.** The correct chunk repeats "revenue" 5x, "increased" 5x, "2024" 4x. It was partly winning through repetition, and sublinear TF taxed it too |

```
              hit@3   hit@10    MRR
naive          1/4      2/4    0.301
+provenance    1/4      2/4    0.330
+sublinear TF  1/4      3/4    0.343
```

**Sublinear TF is a tradeoff, not a free win.** It helps chunks that state a fact once and taxes chunks that legitimately repeat.

---

## Where it stands

Two changes. The hardest case went from unreachable in 9,811 chunks to rank 7. **hit@3 has read 1/4 through all three measurements**, which is the clearest argument in this repo for not trusting a single number.

**Next:** MAU is the interesting one left. The provenance header already carries "December 31, 2025" and it still loses to September quarters, because the 10-Qs mention December comparatives too. Period disambiguation needs more than a date in a header.

See [METRICS.md](METRICS.md) for the six metric lessons on their own.
