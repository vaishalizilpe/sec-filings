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
