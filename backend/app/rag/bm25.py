"""BM25: the classic keyword-ranking algorithm, written from scratch to learn how it works.

RAG step 2 is RETRIEVE: given a question, find the few chunks most likely to answer it.
BM25 ("Best Matching 25", Robertson et al., 1990s) is how search engines ranked text for
decades, and it is still the keyword half of most "hybrid" RAG systems today.

The idea, in three ingredients. A chunk scores high for a question when:

1. It contains the question's words (term frequency, TF)...
   ...but with diminishing returns: mentioning "python" 10 times shouldn't count 10x
   more than once. Controlled by k1.

2. Those words are RARE across all chunks (inverse document frequency, IDF).
   "kubernetes" in 1 chunk out of 50 is a strong signal; "skill" in 45 of 50 is noise.

3. The chunk isn't just long. A long chunk contains more words by chance, so its TF is
   scaled down relative to the average chunk length. Controlled by b.

For one query word q and one chunk D:

    idf(q)      = ln( (N - n(q) + 0.5) / (n(q) + 0.5) + 1 )
    tf_part     = f(q, D) * (k1 + 1) / ( f(q, D) + k1 * (1 - b + b * |D| / avgdl) )
    score(q, D) = idf(q) * tf_part

    N      = number of chunks          n(q)  = how many chunks contain q
    f(q,D) = times q appears in D      |D|   = words in D,  avgdl = average |D|

and a chunk's score for the whole question is the SUM over the question's words.
k1 = 1.5 and b = 0.75 are the textbook defaults.

What BM25 can't do: it only matches exact words. "container orchestration" won't find a
chunk that says "Kubernetes". That's what embeddings fix in stage 66 ("meaning search").
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

K1 = 1.5
B = 0.75

# Very common words carry no meaning for ranking ("what", "the", "my"...). Removing them
# is called stop-word filtering. Kept short and explicit so it's easy to read.
STOP_WORDS = frozenset(
    """a an and are as at be by can do does for from has have how i in is it its me my of on
    or so that the their there these this to was what when where which who why will with
    you your yours""".split()
)

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.]*")


def tokenize(text: str) -> list[str]:
    """Lowercase words, keeping "c++", "c#", "node.js"; drop stop words and a trailing dot.

    "What skills am I MISSING for Node.js?" -> ["skills", "am", "missing", "node.js"]
    """
    tokens = []
    for raw in _TOKEN.findall(text.lower()):
        token = raw.rstrip(".")
        if token and token not in STOP_WORDS:
            tokens.append(token)
    return tokens


@dataclass(frozen=True)
class Hit:
    index: int  # position of the chunk in the list given to BM25Index
    score: float


class BM25Index:
    """Build once over a list of texts, then ask it for the best matches to a question."""

    def __init__(self, texts: list[str], k1: float = K1, b: float = B) -> None:
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(t)) for t in texts]  # word -> count, per chunk
        self.lengths = [sum(d.values()) for d in self.docs]
        self.n_docs = len(self.docs)
        self.avgdl = (sum(self.lengths) / self.n_docs) if self.n_docs else 0.0
        # Document frequency: in how many chunks each word appears.
        self.df: Counter[str] = Counter()
        for doc in self.docs:
            self.df.update(doc.keys())

    def idf(self, word: str) -> float:
        n = self.df.get(word, 0)
        return math.log((self.n_docs - n + 0.5) / (n + 0.5) + 1)

    def score(self, query: str, index: int) -> float:
        doc, length = self.docs[index], self.lengths[index]
        total = 0.0
        for word in set(tokenize(query)):  # a word repeated in the question counts once
            f = doc.get(word, 0)
            if f == 0:
                continue
            norm = 1 - self.b + self.b * (length / self.avgdl if self.avgdl else 0)
            total += self.idf(word) * f * (self.k1 + 1) / (f + self.k1 * norm)
        return total

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        """The best `top_k` chunks with a score above zero, best first."""
        hits = [Hit(i, self.score(query, i)) for i in range(self.n_docs)]
        hits = [h for h in hits if h.score > 0]
        hits.sort(key=lambda h: (-h.score, h.index))
        return hits[:top_k]
