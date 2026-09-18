"""
Query the RAG index: retrieve top-k chunks, then ask Claude to answer
using ONLY the retrieved context. This is the "generation" half of RAG.

Requires ANTHROPIC_API_KEY in the environment. Retrieval works without it,
generation does not, that split matters for the eval harness (you can
measure retrieval quality even before you've wired up an API key).

Usage:
    python query.py "How many monthly active users did Pinterest have in 2025?"
"""
import os
import sys
import pickle
from sklearn.metrics.pairwise import cosine_similarity


def load_api_key():
    """ANTHROPIC_API_KEY from the environment, falling back to a local .env.

    The environment wins, so `export ANTHROPIC_API_KEY=...` still overrides.
    .env is gitignored and is never read for anything except this one name.

    Written by hand rather than with python-dotenv: this repo has three
    dependencies and a .env parser is four lines. A key that lives in a shell
    you opened an hour ago is a key that silently is not there when something
    else runs, which cost two rounds of debugging a `generation skipped` that
    had nothing to do with the code.
    """
    # A value has to be long enough to be a real key. A shell profile holding a
    # six-character placeholder is truthy, wins over .env, and then every call
    # fails with AuthenticationError while the harness reports "generation
    # skipped". Checking that a value is present is not the same as checking it
    # could be real, which is the mistake this whole repo is about.
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key and len(key.strip()) >= 40:
        return key.strip()
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        lines = fh.readlines()
    for line in lines:
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            val = line.split("=", 1)[1].strip().strip("\"'")
            if len(val) >= 40:
                return val
    return None


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


# How many candidates the reranker re-scores. Not swept, chosen by reasoning:
# it has to exceed the worst rank we currently see (16), with headroom for
# questions not yet written. 50 is also a common production default, which is
# weak evidence it is sane rather than invented.
#
# Reranking reorders, it does not rescue. If an answer sits at rank 300 in the
# cheap search, a window of 50 never sees it.
RERANK_CANDIDATES = 50

_cross_encoder = None


def _load_cross_encoder():
    """Lazy, because it downloads 80MB and most runs do not need it."""
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _cross_encoder


def rerank(query, candidates, k=3):
    """Re-score candidates with a cross-encoder, return the best k.

    The retrievers above encode question and chunk SEPARATELY, so a chunk is
    encoded before the question exists and cannot know what was asked. That is
    what makes them fast enough to run over 9,465 chunks.

    A cross-encoder reads the question and the chunk TOGETHER and scores the
    pair, so it can notice that "employ" in a question lines up with "headcount"
    in a passage. Far more accurate, and far too slow to run over the whole
    corpus, which is why it only sees the top RERANK_CANDIDATES.
    """
    if not candidates:
        return []
    model = _load_cross_encoder()
    pairs = [(query, c["text"]) for c, _ in candidates]
    scores = model.predict(pairs, show_progress_bar=False)
    assert len(scores) == len(candidates), "reranker returned the wrong number of scores"
    order = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
    return [(candidates[i][0], float(scores[i])) for i in order[:k]]


def answer(query, retrieved_chunks):
    context = "\n\n---\n\n".join(c["text"] for c, score in retrieved_chunks)
    prompt = f"""Answer the question using ONLY the context below. If the context doesn't contain the answer, say so explicitly, do not guess.

Context:
{context}

Question: {query}

Answer:"""

    api_key = load_api_key()
    if not api_key:
        return ("[No ANTHROPIC_API_KEY. Retrieval ran, generation skipped. "
                "Put it in .env, see .env.example, or export it.]")

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
