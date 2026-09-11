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
        all_chunks.extend(file_chunks)

    print(f"Built {len(all_chunks)} chunks")

    corpus = [c["text"] for c in all_chunks]
    vectorizer = TfidfVectorizer(stop_words="english", max_features=20000)
    matrix = vectorizer.fit_transform(corpus)

    with open("index.pkl", "wb") as f:
        pickle.dump({"chunks": all_chunks, "vectorizer": vectorizer, "matrix": matrix}, f)

    print("Saved index.pkl")
    return all_chunks, vectorizer, matrix


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    build_index(root)
