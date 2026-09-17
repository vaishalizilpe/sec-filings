# Metric lessons

Fourteen lessons, each one paid for by a number that turned out to be lying. In the order they were learned.

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

---

## 9. A score is only comparable against the same test set

Adding the four corner questions moved the numbers:

```
              hit@3   hit@10    MRR
4 questions    1/4      3/4    0.343
8 questions    3/8      6/8    0.371
```

**Nothing about the pipeline changed.** Two of the four questions I added happen to be easy for it, so the aggregate rose.

Comparing scores across different test sets tells you about the test set, not the system. **Say when the set changed, and never put two numbers from different sets in the same table without a note.**

## 10. Name the failure precisely or you fix the wrong thing

The last corner question failed at rank 84. I called it "the no-date corner" and proposed date parsing, filtering and boosting, all of which need a parsed date.

The question was "how many people does Pinterest employ?" The document says "headcount." **The only shared word was "pinterest."** Adding a date would not have helped, because "employ" still does not match "headcount."

Three proposed fixes, all aimed at a problem that was not the problem, because I named the failure by the most visible thing about the question rather than by checking which terms actually matched.

---

## 11. Look at what your preprocessing actually produced

Nobody checked what the chunks contained until question 8 failed at rank 84. The check took five minutes and found that **456 of 9,811 chunks, 5% of the corpus, were machine-readable XBRL tagging with no readable content**, and that a tab-preservation step was being undone by a whitespace collapse two lines later.

Both had been there since the first commit. Both were invisible in every metric, because a score tells you how well the system did on what it was given and never what it was given.

**Print twenty random chunks before you trust any number computed over them.**

---

## 12. A before-and-after in time is not an ablation

Every feature here was measured when it was added: build it, measure, keep it if the number moved. That is a **before-and-after in time**, and it is confounded, because the system keeps changing underneath.

Provenance headers took the hardest question from unreachable to rank 33 when they were added. True at the time. Two features and five golden pairs later, an **ablation** (remove one piece from the current system and measure) said they were net negative and causing wrong-company results.

Both measurements were honest. The first one aged out.

**And one-at-a-time removals do not add up.** Removing sublinear TF alone changed nothing, so it looked useless. Removing both it and provenance scored 0.371, worse than changing nothing at all, while removing provenance and keeping sublinear TF scored 0.486. It was doing real work, hidden behind a bigger problem.

**Ablate the current system, test combinations rather than single removals, and re-run it whenever the system or the test set changes.**

---

## 13. The right change can make your summary statistic worse

Hybrid retrieval improved five of nine questions, left three unchanged, and made one worse by a single rank. MRR went **down**, 0.486 to 0.462.

```
  5,116        27 ->  7   better
  69%          28 ->  9   better
  5,265         9 ->  5   better
  12%           1 ->  2   worse    <- this one costs more MRR than the rest gain
```

MRR is the mean of 1/rank, so it weights the top of the ranking heavily. Rank 1 to 2 costs 0.5. Rank 27 to 7 gains 0.11. One small slip at the top outweighs a twentyfold improvement further down.

hit@10 told the opposite story, 6/9 to 8/9, from the same nine ranks.

**Neither metric is wrong. Both are summaries, and a summary of nine numbers moving in different directions is not decidable.** Read the per-question table, decide, and then say which metric you are choosing and why.

---

## 14. Keep the broken metric, because one day it will disagree

File-level scoring was discredited in lesson 1. It reported 4/4 on a system running at 1/4, because Pinterest's 10-K is 540 chunks and every query names Pinterest, so hitting the right file is close to free.

It was kept in the harness output anyway. Reranking is why that paid:

```
file-level hit@3    8/9  ->  7/9   worse
fact-level hit@3    4/9  ->  6/9   better
```

**The same change made one metric worse and the other better.** The reranker reaches the right file less often and finds the actual answer more often.

Anyone measuring file-level only would have concluded reranking hurt and thrown away the largest single improvement in the project.

**A metric you have proven wrong is still worth printing, next to the one you trust.** The moment they disagree is the moment you learn something, and a discredited metric is only dangerous when it is the only one in the room.


## 15. Check what randomness you left switched on before you average anything

Four runs of identical code gave four different scores. The instinct was to run it five times and report the mean. The cause turned out to be a parameter nobody had set, so the average would have been a precise measurement of a default.

**An average over a knob you forgot to exists is not a measurement of your system.** Before treating variance as something to smooth out, find out where it comes from. Sometimes it is a property of the problem. Here it was `temperature`, sitting at the API default of 1.0, on a task with exactly one correct answer and nothing to be creative about.

The second half matters more, and it survives even when the knob is unreachable.

**Repeated runs fix run-to-run variance. They do nothing about sample variance.** Those are two different problems that look identical in a spreadsheet:

```
run-to-run     the same question answered differently      more runs fixes this
sample         only nine questions exist                   only more questions fix this
```

Run the eval a thousand times and you get a very tight estimate of how this system behaves on these nine questions. That says almost nothing about the tenth. Averaging harder produces confidence, not validity, and confidence in a number that does not generalise is worse than the noisy version, because the noisy version at least looked uncertain.

[Finding 17](FINDINGS.md) is where this came from: the sampling controls turned out to be deprecated on the model, so the run-to-run half cannot be fixed at all, and the honest response was to keep generation figures out of the headline table rather than average them into looking solid.
