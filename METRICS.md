# Metric lessons

Seven lessons, each one paid for by a number that turned out to be lying. In the order they were learned.

Terms are defined in [FINDINGS.md](FINDINGS.md#terms-used-here).

---

## 1. A metric that cannot fail is not a metric

Retrieval was scored as "did any chunk from the expected **file** reach the top 3."

Pinterest's 10-K is 540 chunks. Every question contains the word "Pinterest." Landing some chunk from that file is close to guaranteed, so the test was **unfalsifiable**: almost no input could make it fail.

```
file-level   4/4   (100%)
fact-level   1/4   ( 25%)   does a retrieved passage contain the answer?
```

**Before shipping a metric, ask what input would make it fail.** If you cannot construct one easily, it is not measuring anything.

---

## 2. Measure the halves separately or you cannot assign blame

Retrieval (finding the right passages) and generation (writing an answer from them) fail for different reasons and need different fixes.

```
fact-level retrieval   1/4
answer correctness     1/4     same questions, same pattern
```

Because they matched question by question, generation was provably blameless: zero **hallucinations**, three honest refusals. **Rewriting the prompt would have changed nothing.** One combined number would have sent a week in the wrong direction.

---

## 3. A binary threshold hides real progress

**hit@k** asks "did a correct result land in the top k?" It is pass or fail, so rank 4 and rank 9,811 score identically.

```
headcount rank   >200  ->  33  ->  7
hit@3             1/4      1/4     1/4
```

The hardest case improved roughly thirtyfold across two changes and the headline never twitched. **If your metric is a cliff, work that does not clear the cliff looks like no work at all.**

---

## 4. A continuous metric sees what a threshold cannot, and brings its own blind spot

**MRR**, mean reciprocal rank: for each question take 1 divided by the rank of the first correct result, then average. Continuous, so it registers a move from rank 200 to rank 7.

```
              hit@3   hit@10    MRR
naive          1/4      2/4    0.301
+provenance    1/4      2/4    0.330
+sublinear TF  1/4      3/4    0.343
```

MRR rises every time. It is also dominated by whatever already sits at rank 1:

```
MRR 0.343 = (1.000 + 0.167 + 0.063 + 0.143) / 4
             ^^^^^ one question is 73% of the score
```

**Report per-question ranks next to any aggregate.** No single number can show that one case improved thirtyfold, one moderately, one round-tripped, and one never changed.

---

## 5. A score that rises while the system degrades is the same bug in new clothes

```
k=3    1/4
k=50   3/4
```

Raising k (how many chunks retrieval returns) to 50 "improves" the score by 200%. It also buys fifty passages of context, mostly noise, and gives generation fifty chances to grab a wrong number.

Lesson 1 was a metric that could not fail. This is a metric you can pass by making things worse. **The tell is identical: the number moved and no mechanism explains why it should have.**

---

## 6. A fix is not a general improvement. Know which cases it taxes

**Sublinear TF** replaces a raw word count with `1 + log(count)`, so repetition has diminishing returns.

```
headcount chunk   says "pinterest" 1x   ->  helped   (33 -> 7)
boilerplate       says "pinterest" 4x   ->  advantage cut 4.00x to 2.39x
revenue chunk     repeats "revenue" 5x  ->  TAXED    (4 -> 6)
```

It helps chunks that state a fact once and taxes chunks that legitimately repeat. Net positive across four questions, and a tradeoff rather than a free win.

**"I enabled a flag and the number improved" is not a finding. Knowing which inputs the flag costs you is.**

---

## 7. A fix can break something else while you are not looking

Provenance headers (a line on each chunk saying which company and period it came from) gave every chunk its company name. That solved the worst failure and quietly created a new one.

IDF, inverse document frequency, measures how rare a word is across the corpus. Stamping a date onto all 9,811 chunks collapsed the IDF of date words:

```
word        before headers            after headers
december    1,118 chunks, IDF 3.17    3,549 chunks, IDF 2.02
2025        2,549 chunks, IDF 2.35    6,270 chunks, IDF 1.45
```

**But a falling IDF is not the lesson, and that is the trap.** The same change dropped "pinterest" from 4.80 to 2.65 and that was fine. The difference is whether the term still lines up with the thing it names:

```
"pinterest"  1,870 of 1,887 chunks are in the four Pinterest files   still works
"december"   spread evenly across all four annual reports            broken
```

All four companies have a December 31 fiscal year end. After the header, "december" stopped meaning "Pinterest's December filing" and started meaning **"this is an annual report."**

The MAU question moved from rank 27 to 25, which looked like a small improvement. It was **a large improvement and a new regression, cancelling out.**

I missed it because the MAU result was already failing before and after. **A wrong number stays wrong, so nothing looked different.**

**Two lessons here, and the second one is the sharper one.**

**When a fix helps less than you predicted, check whether it also cost something.** "Small win" and "large win minus a new regression" are identical in the final number, and only one of them means what you think.

**And do not read a metric's movement as the explanation.** "IDF dropped" was true of both terms and only explains one of them. The real question is whether a term still identifies what it claims to. That only surfaced when the file-by-file distribution was pulled, which happened because someone asked whether low IDF was the good one.

---

## 8. Ground truth must come from somewhere you trust more than the system

Every golden pair here was found with `grep` over the raw filings, never with the pipeline.

```bash
grep -o "Revenue was \$[0-9.]* billion" corpus/RDDT-10-K-2025-12-31.txt
```

**You cannot test a system using the system itself.** If the answer key comes from the thing being measured, the score only tells you the system agrees with itself, which it always will.

There is a second, more uncomfortable version of the same point. At 16 documents, `grep` answers these questions faster and more reliably than the pipeline does. That does not make the pipeline pointless, it makes the honest claim narrower: retrieval is for questions with no exact keyword to match, and for corpora too large to read the matches. Neither is true at this size.

**Know what would beat your system, and say so before someone asks.**
