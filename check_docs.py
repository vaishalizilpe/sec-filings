"""Fail if any number published in a .md file disagrees with results.json.

Six figures went stale across README.md, FINDINGS.md and METRICS.md from a
single change to run_eval.py. Nothing caught it, because nothing was checking.

This verifies the docs agree with results.json. It cannot verify results.json
agrees with reality, so it also fails when results.json is older than any .py
file, which is the only way staleness of the source of truth becomes visible
without rebuilding the index and downloading two models on every pull request.

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


SOURCE_FILES = ("build_index.py", "build_embeddings.py", "query.py", "run_eval.py")


def check_freshness(truth):
    """results.json must have been produced by the code currently on disk.

    Timestamps do not work for this. git does not store mtimes, so a fresh CI
    checkout gives every file the same time and the comparison says nothing.
    A hash of the source files is the same on every machine.
    """
    import hashlib
    h = hashlib.sha256()
    for name in SOURCE_FILES:
        if not os.path.exists(name):
            return [f"{name} is missing; cannot verify results.json is current."]
        with open(name, "rb") as f:
            h.update(f.read())
    now = h.hexdigest()[:16]
    was = truth.get("source_fingerprint")
    if was is None:
        return ["results.json has no source_fingerprint. Re-run run_eval.py."]
    if now != was:
        return [f"results.json was produced by different code "
                f"(fingerprint {was}, current {now}). Re-run run_eval.py."]
    return []


def check_tables(truth):
    """Rows like:  lexical only         4/9      6/9   0.486"""
    fails = []
    pattern = re.compile(
        r"^\s*(lexical only|hybrid \(w=0\.2\)|\+ reranking)\s+"
        r"(\d+)/(\d+)\s+(\d+)/(\d+)\s+([\d.]+)\s*$")
    for path in sorted(glob.glob("*.md")):
        for i, line in enumerate(open(path), 1):
            m = pattern.match(line)
            if not m:
                continue
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
    return fails


# Figures published as current and later proved wrong. They must never reappear
# as a current claim, and are allowed inside the historical sections of
# FINDINGS.md, which carry their own note.
#
# Empty, and it is worth saying why. 0.465 and 0.576 were in here, on the belief
# that the substring matcher had inflated them. It had not. The replacement rule
# was over-strict and under-counted, and this dict was enforcing the wrong
# numbers across every document. A guard is only as good as the value it guards.
RETIRED = {}


def check_retired(truth):
    """Fail if a retired figure is presented as a current result.

    A blanket "every 0.NNN must be in results.json" rule was tried and was
    wrong: FINDINGS.md is a historical log and most of its decimals are records
    of earlier experiments that belong there. Only the figures that were
    actively corrected are policed, and only outside the historical log.
    """
    fails = []
    for path in sorted(glob.glob("*.md")):
        if path == "FINDINGS.md":
            continue          # historical log, annotated rather than rewritten
        for i, line in enumerate(open(path), 1):
            for found in re.findall(r"\b0\.\d{3}\b", line):
                if found in RETIRED:
                    fails.append(
                        f"{path}:{i}  {found} was retired, the measured value "
                        f"is {RETIRED[found]}")
    return fails


def main():
    truth = load_truth()
    fails = check_freshness(truth) + check_tables(truth) + check_retired(truth)
    if fails:
        print(f"\n  {len(fails)} inconsistency(ies) between the docs and results.json:\n")
        for f in fails:
            print(f"    {f}")
        print()
        sys.exit(1)
    print("  docs agree with results.json")


if __name__ == "__main__":
    main()
