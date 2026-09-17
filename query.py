"""
Query the RAG index: retrieve top-k chunks, then ask Claude to answer
using ONLY the retrieved context. This is the "generation" half of RAG.

Requires ANTHROPIC_API_KEY in the environment. Retrieval works without it,
generation does not, that split matters for the eval harness (you can
measure retrieval quality even before you've wired up an API key).

Usage:
    python query.py "How many monthly active users did Pinterest have in 2025?"
"""
import sys
import pickle
from sklearn.metrics.pairwise import cosine_similarity


def retrieve(query, index, k=3):
    vec = index["vectorizer"].transform([query])
    sims = cosine_similarity(vec, index["matrix"])[0]
    top_idx = sims.argsort()[::-1][:k]
    return [(index["chunks"][i], sims[i]) for i in top_idx]


# How much the semantic score counts when the two are combined. 0 is pure
# lexical, 1 is pure semantic.
#
# UNVALIDATED. This was picked by sweeping eight values against nine golden
# pairs and taking a good one, which is tuning a parameter on a test set far too
# small to justify a decimal place. See METRICS.md.
#
# What the sweep DID establish, because it holds across every setting tested: a
# small semantic weight helps and a large one destroys the exact-number
# questions. At w=1.0 Reddit's "$2.2 billion" falls from rank 1 to 33, because a
# specific figure is not a semantic concept. Trust the direction, not the number.
HYBRID_WEIGHT = 0.2


def retrieve_hybrid(query, index, embeddings, model, k=3, w=HYBRID_WEIGHT):
    """Combine word matching and meaning matching.

    Both scores are cosine similarities on L2-normalised vectors, so they are
    roughly on the same scale and can be added. Roughly: their distributions
    differ, which is a known rough edge and probably why the best w is so low.
    """
    lex = cosine_similarity(index["vectorizer"].transform([query]),
                            index["matrix"])[0]
    sem = embeddings["vectors"] @ model.encode([query], normalize_embeddings=True)[0]
    assert len(lex) == len(sem), (
        f"lexical index has {len(lex)} chunks, embeddings have {len(sem)}. "
        f"Rebuild embeddings.pkl after any change to index.pkl."
    )
    combined = (1 - w) * lex + w * sem
    top = combined.argsort()[::-1][:k]
    return [(index["chunks"][i], combined[i]) for i in top]


def answer(query, retrieved_chunks):
    import os
    context = "\n\n---\n\n".join(c["text"] for c, score in retrieved_chunks)
    prompt = f"""Answer the question using ONLY the context below. If the context doesn't contain the answer, say so explicitly, do not guess.

Context:
{context}

Question: {query}

Answer:"""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "[No ANTHROPIC_API_KEY set. Retrieval ran, generation skipped. Set the env var to test end-to-end.]"

    # Generation must never take down the retrieval measurement. The whole point
    # of the eval harness is that retrieval and generation fail independently,
    # so a bad key, a rate limit or an outage degrades to a sentinel string
    # rather than raising and killing the run.
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        return f"[Generation failed: {type(e).__name__}. Retrieval still measured.]"


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "How many monthly active users did Pinterest have in 2025?"

    with open("index.pkl", "rb") as f:
        index = pickle.load(f)

    retrieved = retrieve(query, index, k=3)
    print(f"Query: {query}\n")
    print("Top retrieved chunks:")
    for chunk, score in retrieved:
        print(f"  [{score:.3f}] {chunk['source']} (offset {chunk['start']})")
        print(f"      {chunk['text'][:150].strip()}...")

    print("\nAnswer:")
    print(answer(query, retrieved))
