"""
The lexical half of retrieval: chunk every .txt filing, build a TF-IDF index.

TF-IDF scores a chunk by the rare words it shares with the query, where rare
means the word appears in few other chunks. It is the sparse retriever; the
dense one lives in build_embeddings.py and the two are combined in query.py.

An earlier version of this docstring told the reader to ship this and then add
embeddings "as a day 3-4 upgrade", and suggested section-aware chunking as the
fix if facts turned out to be split across boundaries. Both are stale, and in
opposite ways. Embeddings were added, with all-MiniLM-L6-v2 rather than the
Voyage model named here. Section-aware chunking was tried and is impossible on
this corpus: SEC filings carry no heading markup to split on. See FINDINGS.md
finding 9.

Usage:
    python build_index.py corpus
    -> writes index.pkl in the current directory
"""
import sys
import os
import pickle
import glob
from sklearn.feature_extraction.text import TfidfVectorizer


def chunk_filing(text, source, chunk_size=800, overlap=150):
    """Split a filing into overlapping chunks by character count.

    Named chunk_markdown until 2026-09-18, which was wrong in two ways: the
    corpus is .txt, and its docstring pointed at section-aware chunking as the
    upgrade path. That was tested and is impossible here, because SEC filings
    have no heading markup. FINDINGS.md finding 9.

    This cuts words in half. 64% of chunks start mid-word and 824 fragments sit
    in the vocabulary as search terms. Fixing that is finding 18, and it made
    retrieval measurably worse for reasons nobody has named, so it stays as it
    is until there are enough questions to settle it.
    """
    assert chunk_size > overlap, (
        f"chunk_size ({chunk_size}) must exceed overlap ({overlap}), "
        f"or the window never advances and this loops forever."
    )
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]
        chunks.append({"text": chunk_text, "source": source, "start": start})
        start += chunk_size - overlap
    return chunks


# Provenance headers were removed on 2026-09-17 after an ablation. They stamped a
# line naming the company, form and period onto every chunk. See FINDINGS.md
# finding 10: they diluted "pinterest" from 219 chunks (idf 4.76) to 1,817 chunks
# (idf 2.65), and a Pinterest query started returning Snap documents. Testing all
# 16 on/off combinations of the four features put provenance-off ahead of
# provenance-on, MRR 0.486 against 0.438.
#
# Do not re-add without re-running the ablation. Provenance helps only the chunks
# that lack the company name, and taxes every chunk that already has it.


def build_index(root_dir):
    all_chunks = []
    md_files = glob.glob(os.path.join(root_dir, "**", "*.txt"), recursive=True)
    # A missing or empty corpus directory would otherwise build an empty index
    # and report success. Every downstream number would then be computed over
    # nothing, and nothing would say so.
    assert md_files, (
        f"No .txt files found under {root_dir!r}. "
        f"Run fetch_filings.py first, or check the path."
    )
    print(f"Found {len(md_files)} files under {root_dir}")

    for path in md_files:
        try:
            with open(path, "r", errors="ignore") as f:
                text = f.read()
        except Exception as e:
            print(f"  skip {path}: {e}")
            continue
        rel = os.path.relpath(path, root_dir)
        all_chunks.extend(chunk_filing(text, rel))

    assert all_chunks, f"Found {len(md_files)} files but produced 0 chunks."
    print(f"Built {len(all_chunks)} chunks")

    corpus = [c["text"] for c in all_chunks]
    # sublinear_tf: score a term by 1 + log(count) instead of raw count, so a
    # chunk that repeats a word forty times does not beat one that uses it twice
    # in a sentence that answers the question.
    #
    # An earlier comment here said this was "only meaningful AFTER provenance
    # headers exist". Those headers were removed twenty lines above, so by that
    # comment's own logic the setting was pointless. The ablation says otherwise:
    # all 16 on/off combinations of four features were tested and dropping both
    # provenance and sublinear_tf ranks 9th of 16, MRR 0.371 against 0.486 for
    # what shipped. It earns its place on the evidence, not on the reasoning that
    # used to be written here. See FINDINGS.md finding 10.
    #
    # max_features was 20000 and never bound: the vocabulary is 11,423. A cap
    # that never applies is a number a reader has to check before trusting it.
    vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True)
    matrix = vectorizer.fit_transform(corpus)

    with open("index.pkl", "wb") as f:
        pickle.dump({"chunks": all_chunks, "vectorizer": vectorizer, "matrix": matrix}, f)

    print("Saved index.pkl")
    return all_chunks, vectorizer, matrix


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    build_index(root)
