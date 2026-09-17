# What I did, in plain language

Every step of this project in one sentence each, in the order it happened.
`FINDINGS.md` has the evidence and the numbers. This file is the story.

---

## Building it

- Downloaded 16 SEC filings from EDGAR for Pinterest, Snap, Reddit and Meta, which are the annual and quarterly reports public companies must file.
- Stripped out a block of machine-tagging at the top of each filing, because it was code, not prose, and it would have polluted the search.
- Cut each filing into small overlapping pieces called chunks, so a search could return one paragraph instead of a 500KB document, which produced 9,465 chunks in total.
- Built a TF-IDF index, which scores a chunk by how many *rare* words it shares with the question, rare meaning the word appears in few other chunks.
- Wrote nine golden pairs, each one a question plus the exact answer string, so the system could be scored automatically instead of judged by eye.

## Finding out the score was lying

- The first metric asked "did any chunk from the correct filing land in the top 3", and it said 4 out of 4.
- That number was meaningless, because Pinterest's annual report is 540 chunks, so any Pinterest question lands *something* from the right file almost by accident.
- Replaced it with a metric that asks "does a returned passage actually contain the answer", and the real score was 1 out of 4.
- That gap between 4 out of 4 and 1 out of 4 is the finding the whole project is named after.
- Added MRR, which is the average of 1 divided by the position of the first correct result, because a pass/fail at position 3 treats rank 4 and rank 9,465 as equally bad.
- Checked whether the model was the problem and it was not, because whenever the right passage was found the model answered correctly, which meant fixing the prompt would have been wasted work.

## Fixing retrieval, including the fixes that failed

- Found that a chunk buried in the middle of a filing contained no mention of the company, so a question naming Pinterest had no way to prefer Pinterest's own text.
- Tried adding a provenance header, a line at the top of every chunk naming its company and filing.
- Tried sublinear TF, which stops a chunk from winning just because it repeated one word forty times.
- Discovered the provenance fix had quietly broken other questions, and that the reason written in the notes at the time was wrong.
- Found that 5% of the corpus was being discarded because it was tables rather than sentences, which is exactly where the numeric answers live, and fixed the chunker to keep them.
- Ran an ablation, meaning every one of the 16 on/off combinations of four features, and it proved the provenance headers were making things worse, so they were deleted.

## Adding a second way to search

- Added embeddings, which convert a piece of text into 384 numbers that represent its meaning, so "how many people work there" can match "headcount" despite sharing no words.
- Tested embeddings on their own and they were *worse* than TF-IDF, because exact figures like 212,537 are precisely what meaning-based search is bad at.
- Combined the two into hybrid retrieval, 80% keyword and 20% meaning, because the two methods fail on different questions.
- Hybrid improved five of the nine questions and yet MRR went down, which was the metric misleading me for a third time, since one question slipping from 1st to 2nd costs more than another jumping from 27th to 7th gains.
- Wrote in the repo that the 80/20 split is unvalidated because it was tuned on nine questions, which is a guess with a decimal point on it.

## Reranking

- Added a second pass called reranking, which takes the candidates the first search returned and sorts them again more carefully.
- Used a cross-encoder to do it, which is a model that reads the question and one passage side by side rather than comparing two sets of numbers made separately.
- Ran it over only the top 50, because a cross-encoder must read each passage individually and doing that for all 9,465 would be unusably slow.
- Reranking moved the real score from 4 of 9 to 6 of 9, the first time that number had moved in the entire project.
- At the same time the old file-level score got *worse*, 8 of 9 down to 7 of 9, so the two metrics moved in opposite directions and proved the original finding all over again.

**The sentence that carries the whole design: retrieve wide and cheap, rerank narrow and expensive.**

## Fixing the grader

- Found the scorer used plain substring matching, so "619" counted as a hit inside "120,619" and "4,619", which was 55 false matches out of 141 across the corpus.
- The bias only ran one way, because a false match higher up the list is taken as *the* rank, so every number computed from it read better than the truth.
- Replaced it with a match requiring a non-digit boundary, and got that wrong too, because a number at the end of a sentence is followed by a period, so `"headcount was 5,265."` scored as a miss.
- Fixed it properly by treating a comma or period as part of a number only when a digit follows it, which rejects 120,619 and 619.4 while accepting 5,265 at the end of a sentence.
- Found on re-running that the original numbers had been right all along, because although the corpus held 55 false matches, none of them ever outranked a true one on these nine questions.
- Noticed the eval set had no unanswerable questions, so a model that always guesses could never be caught.
- Added three questions whose answers are genuinely absent, each one sitting next to something real: Snap's monthly users when Snap only reports daily, Pinterest revenue per user in Japan when Japan never appears, and a CEO's pay which lives in a different filing.
- Reported refusals as their own score rather than mixing them into hit@3, because a question with no answer has no rank and folding it in would move the headline numbers for the wrong reason.

## Keeping the documents honest

- Noticed that one change to the code left six published figures wrong across three different documents at the same time, and nothing caught it.
- Made `results.json` the single place a published number is allowed to be authored, written by the eval itself.
- Wrote `check_docs.py`, which reads every `.md` file and fails if any published figure disagrees with `results.json`.
- Put it in GitHub Actions so it runs on every push and every pull request, using only the standard library, because a check that needs an install is a check that breaks for unrelated reasons.
- Chose not to run the full eval in CI, because that would mean fetching 16 filings from SEC, rebuilding the index and downloading two models on every pull request, which is slow enough that it would eventually be switched off.
- That leaves a gap, since the check proves the documents match `results.json` but not that `results.json` matches reality, so the eval now records a hash of the code that produced it and the check fails when the code has changed without a re-run.
- Tried file timestamps for that first and they were useless, because git does not store them and a fresh checkout stamps every file with the same time, so the check would have silently passed forever in the one place it mattered.

## Measuring generation for the first time

- Discovered that only the hybrid configuration ever called the model, because the other two passed a flag that skipped generation, so their reported answer score of 0 out of 9 was a setting rather than a result.
- Discovered the results file kept only whichever configuration ran last, which was the one that did not generate, so the model's actual answers were saved nowhere and could not be read back or graded by hand.
- Fixed both, so all three configurations generate and every configuration's answers are kept.
- Found that reranking moved retrieval from 4 of 9 to 6 of 9 while the answer score barely moved, because two questions got better and two got worse.
- One of those regressions had its rank improve to the best possible position and still got the answer wrong, which cannot be a retrieval problem.
- The likely reason is that the model is handed the top 3 passages, not the top 1, so promoting the right passage reorders what sits beside it and can push out context the model was using.
- Could not claim any of that, because four runs of identical code gave refusal scores of 1 of 3, 2 of 3, 2 of 3 and 3 of 3, and a difference of two questions sits inside that spread.
- Traced the instability to the model being free to pick among several plausible next words rather than always taking the most likely one, which is what the temperature setting controls.
- Tried to set temperature to 0 and the API rejected it, because temperature, top_p and top_k are all deprecated on this model, so there is no way to make generation repeatable.
- Decided therefore to keep generation figures out of the results table entirely, leaving it retrieval-only, because retrieval is deterministic and every figure in it can be reproduced.

## Making the key work the same way every time

- Hit a confusing failure where the eval reported that generation was skipped even though the key was set, because it had been exported in one terminal window and the eval was running in another.
- Made the code read the environment first and fall back to a local `.env` file, so the key is a property of the project rather than of whichever shell happens to be open.
- Wrote the four-line parser by hand rather than adding a dependency to a repository that has three.
- Kept `.env` out of git, committed a `.env.example` holding only the variable name, and checked that no key had ever reached any commit in this repository or the one the key was copied from.

## Still open

- No human labels exist for the generated answers yet, and every comparison between graders depends on having them. This is now possible, because the answers are finally being saved.
- The boundary fix cannot catch a correct number stated about the wrong company or the wrong period, which needs a judge rather than a rule.
- Whether the reranking regression is real cannot be settled on this model, because there is no way to remove the run-to-run randomness, so it needs more questions rather than more runs.
- Nine questions is a small sample, and repeated runs do nothing about that.
