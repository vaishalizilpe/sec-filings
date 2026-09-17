"""
Build a semantic index over the SAME chunks the TF-IDF index already uses.

Why: TF-IDF matches literal words. "How many people does Pinterest employ?"
shares exactly one meaningful word with the chunk that answers it, because the
filing says "headcount" and the question says "employ". No weighting change
connects two words that mean the same thing and share no letters. See FINDINGS.md
finding 8.

Embeddings map text to vectors where similar meaning lands close together, so
"employ" and "headcount" end up near each other despite sharing no characters.

This reads chunks out of index.pkl rather than re-chunking. Both retrievers must
see byte-identical text or the comparison measures two things at once.

Usage:
    python build_embeddings.py
    -> writes embeddings.pkl
"""
import pickle
import sys

MODEL = "all-MiniLM-L6-v2"   # 80MB, 384 dimensions, CPU, no API key, reproducible


def main():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        sys.exit("pip install sentence-transformers")

    with open("index.pkl", "rb") as f:
        index = pickle.load(f)
    chunks = index["chunks"]
    assert chunks, "index.pkl contains no chunks. Run build_index.py first."

    print(f"Encoding {len(chunks)} chunks with {MODEL}")
    print("Same chunks TF-IDF uses, so only the matching method differs.")

    model = SentenceTransformer(MODEL)
    vectors = model.encode(
        [c["text"] for c in chunks],
        batch_size=64,
        show_progress_bar=False,
        normalize_embeddings=True,   # so cosine similarity is a plain dot product
    )
    assert vectors.shape[0] == len(chunks), "vector count does not match chunk count"

    # Chunks are stored alongside the vectors because they are linked only by
    # position: row 47 is chunk 47. If they ever drift apart, retrieval returns
    # confidently wrong passages with no error.
    with open("embeddings.pkl", "wb") as f:
        pickle.dump({"model": MODEL, "vectors": vectors, "chunks": chunks}, f)

    print(f"Saved embeddings.pkl  shape {vectors.shape}")


if __name__ == "__main__":
    main()
