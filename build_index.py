"""
Baseline retriever over a corpus of SEC filings.

Chunks every markdown file under the target folder, builds a TF-IDF index.
TF-IDF is a legitimate production baseline, not a toy. Ship this first,
prove retrieval works, THEN swap in an embedding model (Voyage AI is
Anthropic's recommended embedding provider) as a day 3-4 upgrade once
you've validated the baseline assumption: can retrieval reliably surface
the right chunk for a real question.

Usage:
    python build_index.py corpus
    -> writes index.pkl in the current directory
"""
import sys
import os
import re
import pickle
import glob
import datetime
from sklearn.feature_extraction.text import TfidfVectorizer


def chunk_markdown(text, source, chunk_size=800, overlap=150):
    """Split a markdown file into overlapping chunks by character count.
    Simple on purpose for v1. If eval shows facts getting split across
    chunk boundaries, that's the day 6 fix: switch to section-aware
    chunking (split on markdown headers first, THEN by size).
    """
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]
        chunks.append({"text": chunk_text, "source": source, "start": start})
        start += chunk_size - overlap
    return chunks


TICKERS = {"PINS": "Pinterest", "SNAP": "Snap", "RDDT": "Reddit", "META": "Meta"}


def provenance_header(source):
    """One line naming the company, form and period a chunk came from.

    A chunk is 800 characters of text. The retriever sees only those characters,
    never the filename, so a bullet reading "Headcount was 5,265" has no idea
    which company it describes. It then forfeits the strongest term in the query
    and becomes unreachable at any k. This puts the document's identity inside
    every chunk that came from it.

    Deliberately applied AFTER chunking so chunk boundaries are unchanged and
    provenance is the only variable between index versions.
    """
    m = re.match(r"([A-Z]+)-(10-[KQ])-(\d{4})-(\d{2})-(\d{2})", source)
    if not m:
        return ""
    ticker, form, y, mo, d = m.groups()
    company = TICKERS.get(ticker, ticker)
    date = datetime.date(int(y), int(mo), int(d))
    # Both spellings on purpose: queries say "December 31, 2025", filenames say
    # "2025-12-31", and neither should be the only way in.
    return (f"{company} ({ticker}) {form} for the period ending "
            f"{date.strftime('%B')} {date.day}, {y} ({y}-{mo}-{d}).")


def build_index(root_dir):
    all_chunks = []
    md_files = glob.glob(os.path.join(root_dir, "**", "*.txt"), recursive=True)
    print(f"Found {len(md_files)} markdown files under {root_dir}")

    for path in md_files:
        try:
            with open(path, "r", errors="ignore") as f:
                text = f.read()
        except Exception as e:
            print(f"  skip {path}: {e}")
            continue
        rel = os.path.relpath(path, root_dir)
        file_chunks = chunk_markdown(text, rel)
        header = provenance_header(rel)
        if header:
            for c in file_chunks:
                c["text"] = header + "\n" + c["text"]
        all_chunks.extend(file_chunks)

    print(f"Built {len(all_chunks)} chunks")

    corpus = [c["text"] for c in all_chunks]
    # sublinear_tf: use 1 + log(count) instead of raw count. Only meaningful
    # AFTER provenance headers exist. Before them, the unreachable chunk
    # contained the company name zero times, so there was no repetition to
    # downweight. Once every chunk claims its company once, repetition is the
    # only remaining advantage boilerplate has, and this is what removes it.
    vectorizer = TfidfVectorizer(stop_words="english", max_features=20000,
                                 sublinear_tf=True)
    matrix = vectorizer.fit_transform(corpus)

    with open("index.pkl", "wb") as f:
        pickle.dump({"chunks": all_chunks, "vectorizer": vectorizer, "matrix": matrix}, f)

    print("Saved index.pkl")
    return all_chunks, vectorizer, matrix


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    build_index(root)
