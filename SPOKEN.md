# Saying this out loud

Short sentences on purpose. Under 12 words each. Losing a word costs you a few words, not a paragraph.

Three lengths. Use the one the question asks for.

---

## 15 seconds, when he asks what the project is

I built a search and answer system over SEC filings.

Then I built the tests that prove whether it works.

The tests are the interesting part. They caught themselves lying twice.

---

## 45 seconds, the full version

I built a search and answer system over SEC filings.

Public company filings, four companies, sixteen documents.

You ask a question. It finds the passage. A model writes the answer.

That part is ordinary. The measurement is where the work went.

My first test said four out of four. It looked like a working system.

It was getting one out of four right.

The test was checking whether search found the right document.

Not whether it found the right passage.

A ten-K is five hundred pages. Every question had the company name in it.

So the right document always came back. The test could barely fail.

I rewrote it to check the passage. The score dropped to one out of four.

That number was the real one. Everything after that was honest.

---

## 90 seconds, if he wants depth

Start with the 45 second version, then add:

I kept going for about two months. Twenty-two findings written up.

Two of them are fixes that made things worse. I left those in.

Two of them are metrics I stopped reporting.

Here is the better one. I had code that decided whether the model refused to answer.

It was a list of phrases. Does the answer contain "no information", that kind of thing.

It failed three times. Each time on wording nobody had written down.

The third time it reported zero refusals. There had been nine.

Every one said "I don't have access to that". My list did not have that phrase.

So I stopped adding phrases. The list was never going to be complete.

The question was about meaning. My test was about characters.

I moved the job to something that reads the answer.

Then I deleted the number the old one had been publishing.

That is the same mistake I had already fixed in the search half.

Searching for characters is not the same as asking the question.

---

## If he asks what you would do differently

I would not have trusted a number before checking cases by hand.

Five times a metric looked reasonable and measured the wrong thing.

Every time, the thing that caught it was reading individual answers.

Not a better metric. Just looking.

---

## Words to avoid saying, and what to say instead

| avoid | say |
|---|---|
| hit at three | accuracy in the top three results |
| cross-encoder | a reranking model |
| agentic loop | an agent that searches in a loop |
| lexical versus semantic | matching words versus matching meaning |
| parametric leakage | answering from memory instead of the documents |
| ten-K | annual report, or spell it out as ten K |

A transcript garbles the left column. The right column survives, and a recruiter follows it.

---

## If a word goes missing

Pause. Two seconds of silence is invisible on a call.

Then say one of these and start a new short sentence:

- Let me say that a different way.
- The short version is this.
- Give me one second.

Do not try to rescue the sentence you lost.

If the word is gone, describe the thing. "The code that checks the answer" works fine.
