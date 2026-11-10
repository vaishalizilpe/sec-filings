"""Fail if one of nine specific published figures disagrees with results.json.

Six figures went stale across README.md, FINDINGS.md and METRICS.md from a
single change to run_eval.py. Nothing caught it, because nothing was checking.

Read the coverage line this prints, not the pass. It checks three table rows
against three fields each. It does not read prose, counts, answer correctness,
the multi-hop figures, the judge, the loop, or the leakage test, and six stale
prose claims survived in FINDINGS.md while this printed a pass on 2026-11-09.
A narrow check that says it is narrow is useful. One that prints "docs agree"
is how the next six get missed.

Nor can it verify results.json agrees with reality. An earlier version of this
docstring claimed it failed when results.json was older than any .py file. It
never did. There is no mtime check in this file and there never was, so a
results.json produced before the last change to run_eval.py passes silently.

Run:  python3 check_docs.py
"""
import glob
import json
import os
import re
import sys

ROWS = {"lexical only": "lexical", "hybrid (w=0.2)": "hybrid", "+ reranking": "reranked"}


def load_truth():
    if not os.path.exists("results.json"):
        sys.exit("results.json is missing. Run: python3 run_eval.py")
    return json.load(open("results.json"))


def check_tables(truth):
    """Rows like:  lexical only         4/9      6/9   0.486

    Returns (fails, rows_checked, files). The counts exist so main can report
    coverage instead of a verdict. A pass here means nine numbers matched, not
    that the documents are correct, and the difference is what let six stale
    prose claims sit behind a green check.
    """
    fails, rows, files = [], 0, set()
    pattern = re.compile(
        r"^\s*(lexical only|hybrid \(w=0\.2\)|\+ reranking)\s+"
        r"(\d+)/(\d+)\s+(\d+)/(\d+)\s+([\d.]+)\s*$")
    for path in sorted(glob.glob("*.md")):
        with open(path) as fh:
            lines = list(enumerate(fh, 1))
        for i, line in lines:
            m = pattern.match(line)
            if not m:
                continue
            rows += 1
            files.add(path)
            key = ROWS[m.group(1)]
            t = truth[key]
            got = (int(m.group(2)), int(m.group(3)), int(m.group(4)),
                   int(m.group(5)), float(m.group(6)))
            want = (t["fact_hit_3"], t["n_answerable"], t["fact_hit_10"],
                    t["n_answerable"], t["mrr"])
            if got != want:
                fails.append(
                    f"{path}:{i}  {m.group(1)} published "
                    f"{got[0]}/{got[1]} {got[2]}/{got[3]} {got[4]} "
                    f"but results.json says {want[0]}/{want[1]} {want[2]}/{want[3]} {want[4]}")
    return fails, rows, files


# Figures published as current and later proved wrong. They must never reappear
# as a current claim, and are allowed inside the historical sections of
# FINDINGS.md, which carry their own note.
#
# Empty, and it is worth saying why. 0.465 and 0.576 were in here, on the belief
# that the substring matcher had inflated them. It had not. The replacement rule
# was over-strict and under-counted, and this dict was enforcing the wrong
# numbers across every document. A guard is only as good as the value it guards.
RETIRED = {}


def check_retired():
    """Fail if a retired figure is presented as a current result.

    A blanket "every 0.NNN must be in results.json" rule was tried and was
    wrong: FINDINGS.md is a historical log and most of its decimals are records
    of earlier experiments that belong there. Only the figures that were
    actively corrected are policed, and only outside the historical log.
    """
    fails, compared = [], 0
    for path in sorted(glob.glob("*.md")):
        if path == "FINDINGS.md":
            continue          # historical log, annotated rather than rewritten
        with open(path) as fh:
            lines = list(enumerate(fh, 1))
        for i, line in lines:
            for found in re.findall(r"\b0\.\d{3}\b", line):
                compared += 1
                if found in RETIRED:
                    fails.append(
                        f"{path}:{i}  {found} was retired, the measured value "
                        f"is {RETIRED[found]}")
    return fails, compared


def main():
    truth = load_truth()
    table_fails, rows, files = check_tables(truth)
    retired_fails, scanned = check_retired()
    fails = table_fails + retired_fails

    # Coverage first, and printed whether it passes or fails. The old version
    # printed "docs agree with results.json" on a pass, which is a verdict on
    # every document from nine numbers in three table rows. Both of us read it
    # as verification and stopped looking.
    # 9 distinct figures, not rows * 3. The same table is published in three
    # places, and counting each copy as coverage is the exact overclaim this
    # function was rewritten to stop. Caught while reading its own output.
    n_docs = len(glob.glob("*.md"))
    print(f"\n  CHECKED    9 distinct figures (3 configs x hit@3, hit@10, MRR), "
          f"found in {rows} table copies")
    print(f"             across {len(files)} of {n_docs} .md files")
    print(f"             {scanned} decimals scanned against {len(RETIRED)} "
          f"retired values")
    if not RETIRED:
        print("             RETIRED is empty, so that scan cannot fail. "
              "It is a no-op today.")
    print("  NOT CHECKED prose, counts, file-level hit@3, answer correctness,")
    print("             multi-hop, judge agreement, loop, leakage, and whether")
    print("             results.json itself predates the last code change")
    print("             FINDINGS.md is excluded from the retired-value scan")

    if fails:
        print(f"\n  {len(fails)} inconsistency(ies) with results.json:\n")
        for f in fails:
            print(f"    {f}")
        print()
        sys.exit(1)
    print("\n  Those 9 figures agree with results.json. "
          "That is the whole claim.\n")


if __name__ == "__main__":
    main()
