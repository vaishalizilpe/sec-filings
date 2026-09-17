# Findings, in the order they happened

A working log. Each step came from not believing the previous number.

**Setup:** a **corpus** (the full set of documents being searched) of 16 SEC filings, four companies (PINS, SNAP, RDDT, META), Q3 2025 through Q2 2026. Split into 9,811 **chunks** (small passages, here 800 characters with 150 overlap) and indexed with TF-IDF.

Multi-company on purpose: "what was revenue last quarter" has sixteen defensible answers, so **retrieval** (finding the right passages for a question) has to **disambiguate** both company and period, not just match a topic.

> **A note on every number below.** Until finding 13, the harness decided whether a
> passage contained the answer with a plain substring test. `"619" in text` is true
> inside `120,619` and `4,619`, and across the corpus that was 55 false matches out
> of 141. A false match sitting higher in the ranking is taken as *the* rank, so the
> bias runs one way and every figure measured before that fix read better than the
> truth. The comparisons still hold, because both sides of each one carried the same
> bias, but the individual decimals in findings 1 to 12 are not reliable and cannot
> be re-derived, since the code has moved on. They are kept rather than deleted, for
> the same reason the rest of this file keeps its mistakes.

## Terms used here

| Term | What it means |
|---|---|
| **corpus** | the full set of documents being searched |
| **chunk** | one small passage a document is split into |
| **retrieval** | finding the passages most likely to answer a question |
| **lexical** retrieval | matching literal words. The opposite is **semantic**, matching meaning, which is what embeddings do |
| **TF-IDF** | the scoring method here. Term Frequency times Inverse Document Frequency |
| **TF** | term frequency: how often a word appears in this chunk |
| **IDF** | inverse document frequency: how rare a word is across the whole corpus. Rare words narrow things down, common words do not |
| **sublinear TF** | count a repeated word as `1 + log(count)` instead of the raw count, so the tenth mention adds much less than the second |
| **golden pairs** | the answer key. A question plus the answer you already know is correct, plus where it should come from. Also called **ground truth** |
| **eval harness** | the scaffolding that runs the system against the answer key and reports a score |
| **hit@k** | did a correct result land in the top k? Binary, pass or fail |
| **MRR** | mean reciprocal rank. For each question take 1 divided by the rank of the first correct result, then average. Continuous, so it can see a move from rank 200 to rank 7 |
| **provenance** | where a chunk came from: which company, which filing, which period |
| **hallucination** | a model inventing an answer instead of admitting it does not know |

---

## 1. The metric reported 4/4 and the system did not work

Retrieval was scored as "did any chunk from the expected **file** reach the top three." Pinterest's 10-K is 540 chunks and every query contains the word "Pinterest," so landing some chunk from that file is close to guaranteed. The test was **unfalsifiable**: there was almost no input that could make it fail.

Scoring instead on whether a retrieved passage actually **contains** the answer:

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

The Pinterest chunk that rescued the score reads `Research and development $1,427,447 $1,240,564 15%`. That is R&D expense, not revenue growth, and its percentage is one point off the right answer. The Meta chunk carries 22%, which is Meta's revenue growth. Three plausible percentages from three companies in the retrieved context, none of them correct.

---

## 2. Generation was never the problem

An **eval harness** should measure retrieval and generation separately, because they fail for different reasons and need different fixes.

With a working API key, **answer correctness** came back **1/4**, matching fact-level retrieval exactly, question by question.

Generation succeeded on the one question where retrieval surfaced the fact and refused on the three where it did not:

> "It only mentions MAU data as of September 30, 2025 and September 30, 2024, but does not provide a figure for December 31, 2025."

**Zero hallucinations.** It never invented a number. So the prompt was fine and retrieval was the entire problem. Rewriting the prompt would have changed nothing.

That refusal also named the real failure in plain terms: right company, wrong quarter. That turns out to be finding 7.

**Correction:** an earlier version of this log predicted the model would confidently answer 15% from that R&D table. It did not. The prompt instruction "if the context doesn't contain the answer, say so explicitly, do not guess" held. The wrong answer was sitting in the retrieved context and only that one line prevented it, which is worth knowing before anyone deletes it.

---

## 3. Four questions, three different failure modes

A **k-sweep**: vary k (how many chunks retrieval returns) and record the rank at which the correct fact first appears.

The point is diagnostic. If raising k finds the fact, it is a **ranking** problem, meaning the right passage exists and is scored too low. If it never appears, the passage is unreachable and no amount of tuning helps.

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

Two ranking problems, one unreachable, one working. **Raising k to 50 scores 3/4 and is a fake fix**: fifty passages of context, mostly noise, and fifty chances for generation to grab a wrong number. The score rises while the system gets worse.

---

## 4. The unreachable chunk did not know which document it was in

It holds four of the five query terms, including the rarest one:

| Query term | In N of 9,811 chunks | IDF | Present in the chunk |
|---|---|---|---|
| pinterest | 218 | **4.80** | **no** |
| headcount | 104 | 5.54 | yes |
| december | 1,118 | 3.17 | yes |
| 31 | 1,763 | 2.72 | yes |
| 2025 | 2,549 | 2.35 | yes |

It has "headcount" and still cannot place in the top 200, because it never says "Pinterest." That term appears in only 218 of 9,811 chunks, giving it a high IDF, which makes it the strongest thing in the query for narrowing down candidates. The chunk forfeits it and drowns.

The chunk sits physically inside Pinterest's 10-K. **Lexical retrieval sees 800 characters of text, not the filename they came from.**

**This killed the fix that looked obvious.** Sublinear TF reduces the advantage a chunk gets from repeating a word, and cannot help a chunk that never says the word at all. That only surfaced because the term counts were pulled to *explain* the change before making it.

> A change you can implement without looking is a change you can get wrong without noticing.

---

## 5. Fix one: provenance headers

> **Superseded by finding 10. The headers were removed on 2026-09-17.**
>
> Nothing measured below is wrong. Provenance headers really did take the
> headcount question from unreachable to rank 33, and that number was correct at
> the time. What did not survive was the conclusion, once two more features and
> five more golden pairs existed.
>
> **A before-and-after in time is not an ablation.** This section measured one
> change at one moment. Finding 10 measured the current system with and without
> each feature, and reached the opposite verdict. Both were honest. Only one is
> still true.


Give every chunk its **provenance**, a line naming the company, filing type and period it came from:

```
Pinterest (PINS) 10-K for the period ending December 31, 2025 (2025-12-31).
• Headcount was 5,265.
```

Prepended **after** chunking, not before, so chunk boundaries stay byte-identical to the previous index and provenance is the only variable that changed.

| Answer | Before | After |
|---|---|---|
| Snap DAU 474 | 1 | 1 |
| Pinterest revenue 16% | 6 | **4** |
| Pinterest MAU 619 | 27 | 25 |
| Pinterest headcount 5,265 | **>200** | **33** |

**hit@3: 1/4, unchanged.** The prediction was 3/4 or 4/4. Wrong.

Headcount went from unreachable to rank 33, which is the single failure this targeted. The metric did not move because hit@3 is a threshold, and rank 33 scores the same as rank 9,811.

**Intended side effect:** "pinterest" went from 218 chunks (IDF 4.80) to 1,887 (IDF 2.65). Its IDF dropped because every Pinterest chunk now claims the company.

**A dropping IDF is not automatically bad.** What matters is whether the term still lines up with the thing it names. Here it does:

```
"pinterest"  1,887 chunks over 12 files
             PINS-10-K:540  PINS-10-Q:467  PINS-10-Q:450  PINS-10-Q:413  SNAP:5
             1,870 of 1,887 are the four Pinterest files
```

Eight other files contribute 17 chunks between them, which is noise. So the term stopped separating boilerplate from facts and started separating Pinterest from Snap, which is the job it should have had. Lower IDF, same meaning.

The same trade goes badly for dates, for a reason that is not obvious. See finding 7.

---

## 6. Fix two: sublinear TF, which was premature rather than wrong

**Sublinear TF** replaces a raw word count with `1 + log(count)`. Saying a word twice is real evidence; saying it twenty times is barely more informative than saying it five times, and a raw count rewards it as though it were four times better.

It was dropped in finding 4, correctly at the time: the unreachable chunk contained the company name zero times, and you cannot reduce the advantage of repeating a word that is never said.

Provenance changed the premise. Now both chunks claim the company, so **repetition is the only thing separating them on that term**, which is exactly what sublinear TF targets.

| Chunk | says "pinterest" | raw TF | sublinear TF |
|---|---|---|---|
| Boilerplate | 4 | 4.00 | 2.39 |
| Fact chunk | 1 | 1.00 | 1.00 |

| Answer | naive | +prov | +subTF | Why |
|---|---|---|---|---|
| Snap DAU 474 | 1 | 1 | 1 | never broken |
| Pinterest headcount 5,265 | >200 | 33 | **7** | was missing the highest-IDF term. Provenance supplied it, then sublinear TF cut boilerplate's 4x repetition advantage to 2.39x |
| Pinterest MAU 619 | 27 | 25 | **16** | **a period problem, not a company problem.** The top 16 results are 11 Pinterest 10-Q chunks and 5 Pinterest 10-K chunks. All Pinterest, so provenance disambiguated nothing. See finding 7 |
| Pinterest revenue 16% | 6 | 4 | **6** | **regressed.** The correct chunk repeats "revenue" 5 times, "increased" 5 times, "2024" 4 times. It was partly winning *through* repetition, and sublinear TF taxed it too |

```
              hit@3   hit@10    MRR
naive          1/4      2/4    0.301
+provenance    1/4      2/4    0.330
+sublinear TF  1/4      3/4    0.343
```

**Sublinear TF is a tradeoff, not an improvement.** It helps chunks that state a fact once and taxes chunks that legitimately repeat. Net positive across these four questions, and it costs you the revenue case.

---

## 7. Fix one broke something else, and I did not notice

MAU only moved from rank 27 to 25 when I added the provenance headers (provenance means "where it came from", so these headers say which company and period a chunk belongs to). That looked like a small win. It was two things cancelling each other out.

### The problem

The question is "how many MAUs did Pinterest have as of December 31, 2025?"

Retrieval here is **lexical** (matching literal words) rather than **semantic** (matching meaning). It ranks chunks using **TF-IDF**, which multiplies two things:

- **TF, term frequency:** how often a word appears in this chunk
- **IDF, inverse document frequency:** how rare the word is across all chunks

IDF is the part that matters here. A word in 44 chunks has high IDF and narrows things down a lot. A word in 6,270 chunks has low IDF and tells you almost nothing, because most chunks have it.

Every word in that question, sorted by IDF:

| Word | Appears in | IDF | What it tells you |
|---|---|---|---|
| maus | 44 chunks | **6.38** | the topic |
| monthly | 79 chunks | 5.81 | the topic |
| active | 269 chunks | 4.59 | the topic |
| users | 1,820 chunks | 2.68 | the topic |
| pinterest | 1,887 chunks | 2.65 | the company |
| december | 3,549 chunks | **2.02** | **the period** |
| 31 | 5,799 chunks | **1.53** | **the period** |
| 2025 | 6,270 chunks | **1.45** | **the period** |

The three words carrying the **period** (which quarter) have the lowest IDF in the question.

So retrieval does exactly what the numbers tell it to. It finds chunks about MAUs and mostly ignores which quarter they came from. Top five results:

```
1. PINS-10-Q-2025-09-30   MAU methodology, wrong quarter
2. PINS-10-Q-2026-03-31   MAU definition, wrong quarter
3. PINS-10-K-2025-12-31   right file, but no 619 in it
4. PINS-10-Q-2026-06-30   MAU section, wrong quarter
5. PINS-10-K-2025-12-31   right file, but no 619 in it
```

All Pinterest. None with the answer. Company disambiguation (telling the four companies apart) works. **Period disambiguation** does not.

### I caused half of this, and the reason is not the one I first wrote down

The provenance header stamps a date onto every chunk. All 9,811 of them. The IDF of date words collapsed:

| Word | Before headers | After headers |
|---|---|---|
| december | 1,118 chunks, IDF 3.17 | **3,549 chunks, IDF 2.02** |
| 2025 | 2,549 chunks, IDF 2.35 | **6,270 chunks, IDF 1.45** |

My first explanation was "IDF dropped, so the term stopped helping." That is the symptom, not the cause. Finding 5 has an IDF drop just as large and it was fine.

**The actual cause: all four companies have a December 31 fiscal year end.**

```
"december"   3,549 chunks over 16 of 16 files
             SNAP-10-K:1031  META-10-K:837  RDDT-10-K:689  PINS-10-K:540
             every company's annual report
```

Compare that to "pinterest" in finding 5, where 1,870 of 1,887 chunks sit in the four Pinterest files. **That term still lines up with what it names. This one does not.**

After the header, "december" no longer means "Pinterest's December filing." It means **"this is an annual report."** One date, four companies.

**So the date and the company live in separate terms, and neither alone identifies a document.** You would need both to fire together, and TF-IDF scores every term independently. Meanwhile "maus" at IDF 6.38 outweighs both of them combined.

**The lesson is not "do not lower IDF."** It is: check whether a term still corresponds to the thing it is supposed to identify. Finding 5 lowered an IDF and kept the correspondence. Finding 7 lowered one and destroyed it.

I missed this at the time because the MAU result was already failing. **A wrong number stays wrong, so nothing looked different.**

### Why this one is harder

The first two failures were **weighting** problems: the right chunk existed and was scored too low. Changing how terms are scored fixed them.

This is not a weighting problem. The period is in the question and in the header, and lexical matching still cannot use it, because **you cannot raise a word's IDF by changing how you count it.** IDF is a property of the whole corpus (the full set of documents being searched), not a setting.

Three real options, none of them small:

1. **Query parsing plus metadata filtering.** Read the date out of the question, then only search documents matching that period. Accurate, and it means the system has to understand the query rather than match against it.
2. **A token unique to one document**, such as `pins_20251231`. It has to combine company *and* period. A period-only token like `period_20251231` fails for exactly the reason above: all four annual reports would carry it. A combined token appears in 540 chunks and nowhere else, so it is rare, high IDF, and unambiguous. Only works if you also rewrite the query to contain the same token, which means parsing both the company and the date out of the question.
3. **Hybrid search.** Lexical scoring for the topic, a hard metadata filter for the period.

All three mean giving up on pure lexical retrieval.

**That is the honest ending: this is the edge of what TF-IDF can do, and I found it by measuring rather than by reading that it has limits.**

---

## 8. The corner I mislabelled, and the one thing TF-IDF cannot do

I wrote four extra golden pairs to break things on purpose: company disambiguation, a comparative period, a relative date, and a question with no date in it. Baseline on all eight:

| Question | Tests | Rank |
|---|---|---|
| Reddit revenue $2.2bn | company disambiguation | **1** |
| Pinterest MAU growth 12% | comparative period | **3** |
| Reddit growth 69%, "last year" | relative date | **4** |
| Pinterest headcount, no date | no date at all | **84** |

Three of the four corners already work, and two of those contradict what I predicted.

**Company disambiguation works.** Rank 1. Four companies is easy even with the company name at IDF 2.65.

**The comparative-period question works, at rank 3, precisely because there is no filter.** The question asks about 2024 and lexical retrieval returns the 2025 filing, which is the right source. I had argued this corner was the reason to prefer a soft boost over a hard filter. It is stronger than that: **a hard filter would break a question that currently passes.**

### The remaining failure is not what I called it

I labelled the last one "no date." That was wrong, and the term counts say so:

```
question:  "How many people does Pinterest employ?"

  employ      in     7 chunks   idf 8.11   NOT in the target chunk
  people      in   210 chunks   idf 4.84   NOT in the target chunk
  does        in   251 chunks   idf 4.66   NOT in the target chunk
  pinterest   in 1,887 chunks   idf 2.65   in the target chunk

the document says:
  headcount   in   104 chunks   idf 5.54   in the target, NOT in the question
```

**The only word shared between question and answer is "pinterest," the weakest of the four.** And "employ", the highest-IDF term in the whole question at 8.11, sits in seven chunks and none of them is the right one. The strongest signal in the query is steering retrieval away from the answer.

Adding a date would not help. "employ" still would not match "headcount." This is **vocabulary mismatch**: two words with the same meaning and no letters in common.

**No amount of filtering, boosting or reweighting fixes this.** Lexical retrieval matches literal words. There is no literal word to match.

### Where TF-IDF stops

This is what **embeddings** (dense vectors that place text with similar meaning close together) are for. "employ" and "headcount" appear in similar contexts across a training corpus, so a semantic retriever puts them near each other even though they share nothing lexically.

TF-IDF earned its place first. The provenance bug, the IDF collapse, the metric that could not fail, all of those were findable because lexical failures are explainable: you can point at a term count and say why. A dense retriever would have partially papered over the provenance problem and it would never have been found.

**Now it has hit the failure it structurally cannot solve.** That is the difference between using embeddings because everyone does, and using them because you found the specific case that requires them.

---

## 9. Five percent of the corpus was never text

Checking what the 800-character cuts were landing in the middle of turned up chunks like this:

```
snap-20260331 0001564408 12-31 2026 Q1 false P3Y P1Y 1 1 392 424
xbrli:shares iso4217:USD snap:class snap:plan xbrli:pure snap:segment
0001564408 2026-01-01 2026-03-31 0001564408 snap:CommonClassANonVotingMember
```

That is **inline XBRL**, the machine-readable financial tagging the SEC requires. It lives in the same HTML file as the prose, hidden from a browser, and the scraper pulled the tag contents out as text. `0001564408` is Snap's SEC company number. `us-gaap:CommonClassBMember` is an accounting taxonomy code.

**456 of 9,811 chunks, 5%, contained no readable content at all.** And they were full of exactly the terms the period questions depend on:

```
'2025'      in 429 of the 456   94%
'2024'      in 239              52%
'december'  in 127              28%
```

All of it sat in a single `<ix:header>` block per filing, so removing it is one line at fetch time. The `ix:nonFraction` tags that wrap real displayed numbers are left alone.

### A bug the README was bragging about not having

The same check found this, two lines apart in `fetch_filings.py`:

```python
raw  = re.sub(r"(?i)</t[dh]>", "\t", raw)   # turn table cells into tabs
text = re.sub(r"[ \t]+", " ", text)          # ...then delete every tab
```

Tabs added, then collapsed away. Meanwhile the README claimed:

> "Closing `</p>`, `</tr>` and `</h1>` become newlines, `</td>` becomes a tab... You cannot chunk on structure a parser already destroyed."

Row boundaries survived, because newlines were not in that character class. **Cell boundaries did not.** The public repo documented a design decision the code undid. After the fix, 1,537 chunks carry table structure that was previously flattened.

### Results, and they are mixed

```
      answer  before   after
       5,265       7       7
         619      16      27      worse
         16%       6       3      better
         474       1       1
 2.2 billion       1       1
         12%       3       1      better
       5,116      84      73      slightly better, still broken
         69%       4       6      worse

hit@3   3/8 -> 4/8
hit@10  6/8 -> 6/8
MRR   0.371 -> 0.462
```

Two better, two worse, MRR up 25%. Removing 346 chunks changes the IDF of everything slightly, so rankings shift in both directions.

**It did not fix the period problem, as predicted.** "december" went from IDF 2.02 to 2.00. The XBRL was only about 4% of the chunks carrying date terms; the provenance headers did the real damage and still do.

### Why header-aware chunking is off the list

The same investigation checked whether the original Week 1 plan's fix was viable:

```
source HTML:  <h1>: 0   <h2>: 0   <h3>: 0   <h4>: 0
              <b>:  0   font-weight:bold: 0
```

**SEC filings carry no heading markup at all.** They are styled with inline CSS on plain spans and divs, so a heading is indistinguishable from body text once tags are stripped:

```
'...positive environment. \n Our Users and Our Platform \n 619 million monthly active users...'
```

Header-aware chunking was inherited from the original plan, which was written for a corpus of **markdown files**, where `#` headings genuinely exist. It was carried forward for eleven days without anyone checking whether it applied here. It does not.

---

## 10. An ablation says two of the four features were not earning their place

Four changes had accumulated: XBRL stripping, the tab fix, provenance headers, sublinear TF. Each was measured when it was added, none since.

An **ablation** removes one piece at a time and measures what it was contributing. All 16 on/off combinations, the same nine golden pairs:

```
 xbrl  tab  prov  subTF   hit@3  hit@10    MRR
 True True FALSE   True    4/9     6/9    0.486   <- best
 True True  True   True    4/9     7/9    0.438   <- what was shipped
 True True  True  FALSE    4/9     6/9    0.438
FalseFalse  True  FALSE    4/9     5/9    0.432
 ...
 True True FALSE  FALSE    4/9     6/9    0.371   <- 9th of 16
FalseFalse FALSE  FALSE    4/9     5/9    0.402
```

### Provenance headers were hurting

Per question, with and without:

```
question            with  without
headcount 5,265        7        9   worse
MAU 619               27       22   better
revenue 16%            3        7   worse
Snap DAU 474           1        1
Reddit 2.2bn           1        1
MAU growth 12%         1        1
employ 5,116          73       27   better
Reddit 69%             6       28   worse
SBC 212,537            4        1   better
```

**Three better, three worse.** MRR rises from 0.438 to 0.486 mostly because SBC goes 4 to 1 and employ goes 73 to 27, and movements near the top of the ranking dominate MRR. hit@10 actually drops, 7/9 to 6/9.

So this is a genuine tradeoff, not a clean win, and the aggregate flatters it.

**The reason to remove it anyway is not the score.** The headers diluted "pinterest" from 219 chunks (IDF 4.76) to 1,817 (IDF 2.65), and with the company name that weak, a Pinterest question started returning **Snap documents at the top of the results**. Wrong-company answers are the worst failure class for this use case, worse than a miss, because they look right.

### Sublinear TF was masked, not useless

Tested alone, sublinear TF changed nothing: MRR 0.438 either way. The obvious reading is that it does nothing and should also go.

That reading is wrong, and the full sweep shows why:

```
 True True FALSE   True   0.486   drop provenance, keep sublinear TF
 True True FALSE  FALSE   0.371   drop both
```

**Dropping both is the 9th best of 16 configurations, and worse than shipping everything unchanged.** Sublinear TF was doing real work the whole time. It looked useless only because provenance was hurting enough to hide it.

**Features interact. You cannot test removals one at a time and add up the conclusions.** That is the same shape as finding 7, where two effects cancelled and looked like a small change.

### What is left

XBRL stripping, the tab fix, sublinear TF, fixed 800-character chunking. Provenance headers deleted, and `build_index.py` is 86 lines down from 110.

---

## 11. Hybrid retrieval, and why pure embeddings lose

Finding 8 established that "how many people does Pinterest employ" cannot be reached by word matching. The filing says "headcount", the question says "employ", and the only shared word is "pinterest", the weakest term in the query.

Three chunking strategies and two weighting changes had all failed on it:

| Attempt | Result |
|---|---|
| Header-aware chunking | **Impossible.** SEC filings have zero `<h1>` to `<h4>` and zero `<b>` tags. A heading is indistinguishable from body text once markup is stripped |
| Table-aware chunking | Fixed 546 orphaned chunks, **moved zero questions.** Eight of nine answers live in prose, not tables |
| Line-aware chunking | **Worse at every size.** A 36-character fragment, "in part by an increase in headcount.", scored 0.63 and beat the real answer at 0.37 |
| Larger fixed chunks | Swept 1600 to 4800. Nothing clearly better than 800, and `employ` got worse at every size |
| Provenance headers | Helped this question and caused Pinterest queries to return Snap documents. Removed |

Best result across all of it: rank 27.

### Pure embeddings are worse, not better

Same chunks, same questions, `all-MiniLM-L6-v2`, only the matching method changed:

```
question           tf-idf   embed
headcount 5,265         9      45   worse
MAU 619                22       9   better
revenue 16%             7       2   better
SNAP DAU 474            1       4   worse
RDDT 2.2bn              1      33   worse
MAU growth 12%          1       8   worse
employ 5,116           27      17   better
RDDT 69%               28       4   better
SBC 212,537             1       2   worse

tf-idf       hit@3 4/9   hit@10 6/9   MRR 0.486
embeddings   hit@3 2/9   hit@10 6/9   MRR 0.205
```

**MRR less than half.** Every question TF-IDF had at rank 1 got worse. Reddit's "$2.2 billion" fell from 1 to 33, because **a specific figure is not a semantic concept**: embeddings match meaning, and an exact number carries almost none.

And `employ`, the one question this was chosen to fix, went 27 to 17. Better, nowhere near solved.

### The two retrievers fail differently, so combine them

```python
combined = (1 - w) * lexical + w * semantic
```

Sweeping `w`:

```
    w                   mix  hit@3  hit@10    MRR
  0.0           pure tf-idf    4/9     6/9  0.486
  0.1     90% lex / 10% sem    4/9     7/9  0.507
  0.2     80% lex / 20% sem    4/9     8/9  0.465
  0.3     70% lex / 30% sem    3/9     8/9  0.426
  0.5     50% lex / 50% sem    3/9     5/9  0.283
  1.0       pure embeddings    2/9     6/9  0.205
```

**Shipped at w=0.2**, per question:

```
  5,265         9 ->  5   better
  619          22 -> 16   better
  16%           7 ->  6   better
  474           1 ->  1
  2.2 billion   1 ->  1
  12%           1 ->  2   worse
  5,116        27 ->  7   better
  69%          28 ->  9   better
  212,537       1 ->  1
```

**Five better, one worse, three unchanged.** The three unchanged are the exact-number questions, which is the regression that did not happen. `employ` finally moved, 27 to 7. hit@10 goes 6/9 to 8/9.

### MRR goes down, and that is the metric being wrong again

MRR falls from 0.486 to 0.465 because `MAU growth` slipped from rank 1 to rank 2. **One question moving one place costs more MRR than another moving twenty places gains it**, since MRR weights the top of the ranking heavily.

Five questions improved and the summary statistic went down. That is metric lesson 4 happening live: no aggregate can represent nine questions moving in different directions, and the per-question table is the evidence.

### The weight is not validated, and the repo says so

`HYBRID_WEIGHT = 0.2` was chosen by sweeping eight values against nine golden pairs and picking a good one. **That is tuning a parameter on a test set far too small to justify a decimal place**, and it is the same trap as raising k to 50.

What the sweep does establish, because it holds across every setting: **a small semantic weight helps and a large one destroys the exact-number questions.** Trust the direction, not the number. The constant carries this warning in a comment in `query.py`.

---

## 12. Reranking, and the two metrics moving in opposite directions

After hybrid, nothing was badly broken. Five questions sat between rank 5 and 16: the right passage was being found, just not first. That is a **ranking** problem, and it has a standard answer.

### Why a second model

The retrievers so far encode the question and the chunk **separately**, then compare the results. A chunk is encoded before the question exists, so it cannot know what was asked. That is what makes them fast enough to run over 9,465 chunks.

A **cross-encoder** reads the question and the chunk **together** and scores the pair, so it can notice that "employ" in a question lines up with "headcount" in a passage. Far more accurate, and far too slow for a whole corpus.

So: cheap search narrows 9,465 to 50, then the expensive model orders those 50.

`RERANK_CANDIDATES = 50` was chosen by reasoning, not swept. It has to exceed the worst rank currently seen (16) with headroom, and 50 is a common production default. **Reranking reorders, it does not rescue:** an answer at rank 300 in the cheap search is never seen.

### Results

```
answer          lexical   hybrid   +rerank
  5,265               9        5         1
  619                22       16        18   worse
  16%                 7        6         1
  474                 1        1         2   worse
  2.2 billion         1        1         3   worse
  12%                 1        2         1
  5,116              27        7         8   worse
  69%                28        9         6
  212,537             1        1         1

                 lexical   hybrid   +rerank
fact-level hit@3     4/9      4/9       6/9
fact-level hit@10    6/9      8/9       8/9
MRR                0.486    0.465     0.576
```

**hit@3 moves for the first time in the project, 4/9 to 6/9.** MRR 0.576 is the highest recorded. Two questions go from rank 5 and 6 to rank 1.

The prediction written before running was: mid-ranked questions improve, at least one rank-1 question gets worse, aggregate improves modestly. **That one was right.** Three rank-1 questions slipped (474 to 2, 2.2bn to 3) and `employ` went 7 to 8.

### The clearest demonstration of finding 1 in the whole project

The two retrieval metrics moved in **opposite directions**:

```
file-level hit@3    8/9  ->  7/9   worse
fact-level hit@3    4/9  ->  6/9   better
```

The reranker reaches the "right file" **less** often and finds the actual answer **more** often, because the right file was never what mattered. Pinterest's 10-K is 540 chunks, so hitting that file is close to free; hitting the passage containing 5,265 is the hard part.

**Anyone measuring file-level only would have concluded reranking made things worse and discarded the best result in the project.**

### What it did not fix

`619`, the MAU question, went 16 to 18. Reranking cannot solve period disambiguation, because the passages it is ordering are all Pinterest MAU passages from different quarters and the cross-encoder has no more idea which quarter is wanted than TF-IDF did. That failure is still open and still needs the date parsed out of the question.

---

## Where it stands

```
                   hit@3   hit@10    MRR
lexical only         4/9      6/9   0.486
hybrid (w=0.2)       4/9      7/9   0.462
+ reranking          6/9      8/9   0.571
```

Six changes shipped, two of them reverted after measurement. Nine golden pairs, five written to break things on purpose.

**What is shipped:** XBRL stripping, the tab fix, sublinear TF, hybrid retrieval at 20% semantic weight, cross-encoder reranking over the top 50.

**What was built and removed:** provenance headers (caused Pinterest queries to return Snap documents, finding 10), table-aware chunking (fixed 546 orphaned chunks, moved zero questions, finding 9).

**What was tested and rejected:** header-aware chunking (impossible, SEC filings have no heading markup), line-aware chunking (worse at every size from 150 to 800), larger fixed chunks (nothing beats 800), pure embeddings (MRR 0.205 against 0.486).

### The open problems

**Period disambiguation.** `619`, the MAU question, is at rank 18 and has now defeated three retrievers. All four companies have a December fiscal year end, so "december" means "this is an annual report" rather than naming one document. Lexical, semantic and cross-encoder retrieval all fail the same way, because they are all ordering Pinterest MAU passages from different quarters and none of them knows which quarter was asked for. Fixing it means parsing the date out of the question and filtering, which is a different kind of retrieval.

**Generation only sees the top 3.** `run_eval.py` passes `deep[:3]` to the model, so a fact at rank 5 is found by retrieval and never reaches generation. hit@10 of 8/9 describes something the user never experiences. Testing k=5 and k=10 is cheap and now worth it, since reranking made the top of the list trustworthy.

**Answer correctness has never been measured on nine questions.** It reports 0/9 because the API key is invalid, not because generation is wrong. It was measured once at four questions (finding 2) and matched fact-level retrieval exactly.

**Nine golden pairs is thin.** Enough to find a bug, not enough to justify a tuned parameter. `HYBRID_WEIGHT = 0.2` and `RERANK_CANDIDATES = 50` are both unvalidated and both say so in the code.

See [METRICS.md](METRICS.md) for the fourteen metric lessons on their own.
