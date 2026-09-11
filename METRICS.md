# Metric lessons

Six lessons, each one paid for by a number that turned out to be lying. Written in the order they were learned.

---

## 1. A metric that cannot fail is not a metric

Retrieval was scored as "did any chunk from the expected **file** reach the top 3."

Pinterest's 10-K is 540 chunks. Every question contains the word "Pinterest." Landing some chunk from that file is close to guaranteed.

```
file-level   4/4   (100%)
fact-level   1/4   ( 25%)   does a retrieved passage contain the answer?
```

**Before shipping a metric, ask what input would make it fail.** If you cannot construct one easily, it is not measuring anything.

---

## 2. Measure the halves separately or you cannot assign blame

Retrieval and generation fail for different reasons and have different fixes.

```
fact-level retrieval   1/4
answer correctness     1/4     same questions, same pattern
```

Because they matched question by question, generation was provably blameless. It refused honestly on all three misses rather than guessing. **Rewriting the prompt would have changed nothing.** One combined number would have sent a week in the wrong direction.

---

## 3. A binary threshold hides real progress

Hit-at-3 scores rank 4 and rank 9,811 identically.

```
headcount rank   >200  ->  33  ->  7
hit@3             1/4      1/4     1/4
```

The hardest case improved roughly thirtyfold across two changes and the headline never twitched. **If your metric is a cliff, work that does not clear the cliff looks like no work at all.**

---

## 4. A continuous metric sees what a threshold cannot, and brings its own blind spot

```
              hit@3   hit@10    MRR
naive          1/4      2/4    0.301
+provenance    1/4      2/4    0.330
+sublinear TF  1/4      3/4    0.343
```

MRR moves monotonically. It is also dominated by whatever is already at rank 1:

```
MRR 0.343 = (1.000 + 0.167 + 0.063 + 0.143) / 4
             ^^^^^ one question is 73% of the score
```

**Report per-question ranks next to any aggregate.** The aggregate cannot show that one case improved thirtyfold, one moderately, one round-tripped, and one never changed.

---

## 5. A score that rises while the system degrades is the same bug in a new costume

```
k=3    1/4
k=50   3/4
```

Raising k to 50 "improves" retrieval by 200%. It also buys fifty passages of context, mostly noise, and gives generation fifty chances to grab a wrong number. Lesson 1 was a metric that could not fail; this is a metric you can pass by making things worse.

**The tell is the same in both: the number moved and no mechanism explains why it should have.**

---

## 6. Fixes are not general improvements. Know which cases they tax

`sublinear_tf=True` replaces raw term counts with `1 + log(count)`.

```
headcount chunk   says "pinterest" 1x   ->  helped   (33 -> 7)
boilerplate       says "pinterest" 4x   ->  advantage cut 4.00x to 2.39x
revenue chunk     repeats "revenue" 5x  ->  HURT     (4 -> 6)
```

It helps chunks that state a fact once and taxes chunks that legitimately repeat. Net positive across four questions, and a tradeoff rather than a free win.

**"I enabled a flag and the number improved" is not a finding. Knowing which inputs the flag costs you is.**

---

## 7. A fix can break something else while you are not looking

Adding a header to every chunk gave each one its company name. That solved the worst problem and quietly created a new one.

```
word        before headers              after headers
december    1,118 chunks, helps (3.17)  3,549 chunks, barely helps (2.02)
2025        2,549 chunks, helps (2.35)  6,270 chunks, barely helps (1.45)
```

Search finds things using rare words. Put a date on all 9,811 chunks and dates stop being rare, so they stop helping.

The MAU question needs the date to find the right quarter. It moved from rank 27 to 25, which looked like a small improvement. It was **a big improvement and a new problem, cancelling out.**

I missed it because the MAU number was already wrong before and still wrong after. **A wrong number stays wrong, so nothing looked different.**

**When a fix helps less than you expected, check whether it also broke something.** "Small win" and "big win minus a new problem" look identical in the final number, and only one of them means what you think it means.
