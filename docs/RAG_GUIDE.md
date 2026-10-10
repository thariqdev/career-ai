# Learning RAG by building it into Career AI

A step-by-step guide that grows with each stage. Each stage says **what** we built,
**why**, **where the code is**, and **what an interviewer may ask**.

---

## The one-paragraph version

A large language model (LLM) only knows what it saw in training. It doesn't know *your*
skills or *your* job postings, so if you ask it, it may confidently make things up
(that's called **hallucinating**). **RAG (Retrieval-Augmented Generation)** fixes this:
before the model answers, we **retrieve** the few pieces of *your* data most relevant to
the question and hand only those to the model, with the instruction "answer only from
these, and cite them". The model becomes a writer working from the right pages, not a
guesser.

```
 your data (PostgreSQL)                                   your question
          │                                                     │
          ▼                                                     ▼
   1. CHUNK  ── small self-contained notes ──►  2. RETRIEVE  (find the best notes)
                                                                │
                                                                ▼
                                   3. GENERATE  (write the answer from those notes,
                                                 citing [1] [2], or say "not found")
```

In Career AI, **PostgreSQL stays the source of truth**. RAG only *reads* it and explains it.

---

## Stage 65: chunking + BM25 keyword search (no AI yet) ✅

**What you can do:** open **Assistant** in the top menu and ask "What am I missing for my
jobs?", "Which skills have no proof yet?" or "Tell me about Python". The reply shows
the best notes from your data, numbered as sources, each linking to its page.

### Step 1: Chunking (`backend/app/rag/chunker.py`)

A retriever can only return what you gave it, so **how you cut the data decides what can
be answered**. We make one note per:

| Note | Example text |
|---|---|
| overview | "Overview summary of your career data: 24 skills saved, 3 verified … Most needed missing skills to learn first: AWS, …" |
| skill | "Skill: Python (Languages). Your status: verified, proven by evidence: FundsApp repo. On your CV: yes. Jobs that need it: …" |
| job | "Job description: Backend at Acme. Match: 50% … Missing skills (gaps to learn): Kubernetes, AWS." |
| gap | "Gap: Kubernetes is missing for the job Backend at Acme (required). To close this gap: learn …" |
| evidence, project, work, education | one note each |

Rules we followed (standard RAG advice):

- **One fact-cluster per note**: small enough to be precise, complete enough to make
  sense alone.
- **Use the words people ask with** ("missing", "proof", "learn"), because keyword
  search only matches words that are literally in the note.
- **Every note carries its source** (a link), so answers can cite.
- **Rebuilt on every question** from PostgreSQL, so it's never out of date. (Big systems
  index ahead of time and re-index when data changes; we're small enough not to need that.)

### Step 2: Retrieval with BM25 (`backend/app/rag/bm25.py`)

BM25 is the classic search-engine ranking formula, and it's still the "keyword half" of
most modern RAG systems. We wrote it from scratch (about 60 lines). A note scores high
when:

1. **It contains the question's words**, with diminishing returns (10 mentions ≠ 10×
   better). That's the `k1` knob.
2. **Those words are rare** across all notes (IDF, inverse document frequency):
   "Kubernetes" in 1 of 35 notes is a strong signal; "skill" in 30 of 35 is noise.
3. **It isn't just long.** Long notes contain more words by chance, so they're scaled
   down. That's the `b` knob.

```
idf(q)   = ln( (N − n(q) + 0.5) / (n(q) + 0.5) + 1 )
score    = Σ over question words q of  idf(q) · f·(k1+1) / ( f + k1·(1 − b + b·|D|/avgdl) )
k1 = 1.5,  b = 0.75
```

There's a worked example by hand in `tests/test_rag_assistant.py`
(`test_bm25_matches_a_hand_worked_example`, score 1.10516). Recompute it on paper once;
it's the best way to really get it.

### Step 3: "Generation" (`backend/app/rag/assistant.py`)

For now the answer **is** the retrieved notes, numbered as sources ("extractive"). So it
can never say something your data doesn't. If nothing matches, it says *"I couldn't find
anything about that…"* instead of guessing. **Knowing when to say "I don't know" is part
of RAG.**

### What we saw on real data (and why stage 66 exists)

- "What am I missing for my **jobs**?" doesn't match the word **"job"**, because BM25
  needs the exact word (there's no stemming).
- Asking about "container orchestration" won't find a note about "Kubernetes": same
  meaning, different words.
- Several gap notes tie on the same score, because their wording is almost identical.

Keyword search finds **words**, not **meaning**. Stage 66 adds meaning.

### Interview questions you can now answer

- *What is RAG and why use it instead of fine-tuning?* RAG gives the model fresh, private
  data at question time, needs no retraining, can cite sources, and updates the moment
  the data changes. Fine-tuning changes the model's weights: it's slow, costly, and can't
  cite where an answer came from.
- *What is chunking and how do you choose chunk size?* Small enough to be precise, large
  enough to stand alone. Make one chunk per natural unit (here: a skill, a job, a gap).
- *Explain BM25.* TF with saturation (k1), IDF for rarity, and length normalisation (b).
- *What does BM25 miss?* Synonyms and paraphrases, so pair it with embeddings ("hybrid
  search").
- *How do you stop hallucinations?* Retrieve first, answer only from what was retrieved,
  cite sources, and say "not found" when retrieval finds nothing.

---

## Stage 66a: measure first (evaluation), and an "improvement" that wasn't ✅

**Run it yourself** (from `backend/`):

```powershell
.venv/Scripts/python -m app.rag.evaluate
```

### Why measure before improving?

Without a score, "it seems better" is a feeling, not evidence. Real RAG teams keep a small
**golden set**: questions, each with the notes that *should* be retrieved. They re-score
every change against it. Ours is 15 questions over a **fixed, made-up career** built in a
throwaway database (`app/rag/evaluate.py`), so the score changes only when the code or
the note wording changes, never because your real data changed.

### The two numbers

- **Recall@k:** of the notes that should be found, the fraction in the top *k* (k = 4,
  because the assistant reads 4 notes). This asks: *did the right facts reach the model?*
  Example: expected {A, B}, top 4 = [A, X, Y, Z] gives recall@4 = **0.5**.
- **MRR (mean reciprocal rank):** 1 ÷ the position of the **first** right note,
  averaged over all questions. 1st place = 1.0, 2nd = 0.5, 3rd = 0.33, not in the top k = 0.
  This asks: *how high up is the first good answer?*

### The experiment: stemming

We'd seen "jobs" fail to match "job", so we tried **stemming**: cutting words to a common
root (jobs → job, learning → learn) on both the notes and the question
(`stem()` in `app/rag/bm25.py`). The textbook says this helps. The numbers:

| | recall@4 | MRR |
|---|---|---|
| BM25 (no stemming) | **1.000** | **0.889** |
| BM25 + stemming | 0.833 | 0.672 |

**It made retrieval worse.** Why: our notes repeat label words, since every skill note
starts with "Skill:" and says "Jobs that need it". With stemming, the question words
"skills" and "jobs" match *nearly every note*, BM25 sees them as common (low IDF), and
the right note (often the long overview) gets drowned out. "Which skills have no proof
yet?" went from found (1st place) to not found at all.

**Decision, backed by numbers:** stemming stays in the code (so the experiment can be
re-run) but is **off** (`USE_STEMMING = False` in `app/rag/assistant.py`). A test,
`test_retrieval_quality_does_not_regress`, locks the score in. Flipping stemming on
makes it fail, which was checked.

### Two honest caveats

1. **The golden set is biased.** I wrote both the notes *and* the questions, so they share
   wording, which is partly why the baseline scores a perfect recall. Real evaluation uses
   questions from real users, ideally collected before you see the notes.
2. **16 notes is tiny.** Scores on small sets swing a lot from one question. Treat them as
   a smoke alarm, not a leaderboard.

### Interview questions you can now answer

- *How do you evaluate a RAG system?* Separate **retrieval** (recall@k, MRR, precision)
  from **generation** (faithfulness to the sources, answer relevance). Use a golden set,
  and re-run it on every change.
- *What's the difference between recall@k and MRR?* Recall: did the right documents
  arrive at all? MRR: how high was the first right one?
- *Does stemming always help keyword search?* No. It depends on your text. Measure it.
  (Here it hurt, because of repeated label words.)
- *What's wrong with a golden set the developer wrote?* Shared wording inflates scores.
  Use real user questions.

## Stage 66: embeddings, meaning search and hybrid search (built ✅; real-model scores pending Ollama)

**Turn it on** (once Ollama is installed and `ollama pull nomic-embed-text` is done): add
this line to `backend/.env`, then restart the backend:

```
OLLAMA_EMBED_MODEL=nomic-embed-text
```

Without it, or if Ollama isn't running, the Assistant uses keyword search and says so.
**Score it:** `.venv/Scripts/python -m app.rag.evaluate` adds "meaning" and "hybrid" rows
automatically when Ollama answers.

### 1. Embeddings: meaning as numbers (`backend/app/rag/embeddings.py`)

An **embedding model** turns text into a list of numbers, a **vector**. `nomic-embed-text`
gives 768 of them. It was trained so that texts with **similar meaning point in similar
directions**, even with no words in common:

```
"Kubernetes"                 → [0.12, -0.40, 0.88, …]  ┐  point the same way
"container orchestration"    → [0.10, -0.37, 0.91, …]  ┘
"garden planner"             → [-0.70, 0.22, 0.05, …]     points elsewhere
```

nomic-embed-text wants a **task prefix**: `search_document: ` for notes and
`search_query: ` for the question, so both sides are embedded "for retrieval".

### 2. Cosine similarity: how close two meanings are

```
cos(a, b) = (a · b) / (|a| · |b|)          a · b = a₁b₁ + a₂b₂ + …
```

It's the cosine of the angle between the two arrows: **1** means the same direction, **0**
means unrelated, and **−1** means opposite. It ignores length, so a long note and a short
question can still match. Worked by hand in `test_cosine_by_hand`: (1,1) vs (1,0) gives
1/√2 ≈ 0.707, a 45° angle.

**Meaning search** = embed every note, embed the question, and return the highest cosines.
A "vector database" like **pgvector** does exactly this at scale. With our few dozen notes,
a Python loop is instant.

### 3. A trap: meaning search always finds *something*

Every note has *some* cosine with any question, even "astronaut spaceship". So a note
found **only** by meaning must reach `MIN_COSINE` (0.5, a first guess that the scoreboard
will calibrate) to count. Otherwise "I couldn't find that" would become impossible, and
the assistant would always hand over its least-bad notes.

### 4. Hybrid search with Reciprocal Rank Fusion (RRF)

Keyword search is great at **exact names** ("FastAPI", "K8s"). Meaning search is great at
**paraphrases**. Use both and merge the two rankings:

```
RRF score of a note = Σ over each ranking  1 / (60 + its rank)
```

Why ranks, not scores? BM25 scores (0 to about 20) and cosines (−1 to 1) are on different
scales, but "1st place" means the same in both. Worked by hand in `test_rrf_by_hand`: a
note that's 2nd in one list and 1st in the other (1/62 + 1/61 = 0.0325) beats a note
that's 1st in only one list (1/61 = 0.0164). **Agreement wins.**

### 5. Engineering details that matter in real systems

- **Caching:** embedding is the slow part, so each note's vector is cached by
  (model, text) and only re-computed when the text changes (`CachedEmbedder`, which keeps
  the most recently used 5,000).
- **Graceful fallback:** if Ollama is down or the model isn't pulled, the assistant uses
  keyword search and puts a `note` in the reply instead of failing.
- **Testing without the model:** the tests use a tiny **fake embedder** that maps synonyms
  to the same direction. That tests our plumbing and maths, not the real model's quality.
  The real model is measured by the scoreboard.

### Interview questions you can now answer

- *What is an embedding?* A vector representing meaning, where similar texts have nearby
  vectors.
- *Why cosine similarity rather than distance?* It compares direction (meaning), not
  length.
- *What is hybrid search and why use it?* BM25 + vector search, fused with RRF. It catches
  exact terms *and* paraphrases.
- *Why RRF instead of adding scores?* The scores aren't on the same scale; ranks are.
- *What's a similarity threshold for?* Vector search always returns neighbours; a
  threshold lets the system say "not found".
- *What is a vector database?* Storage plus fast nearest-neighbour search over vectors
  (pgvector, FAISS, Pinecone). Unnecessary at tiny scale, essential at millions of chunks.

## Stage 67a: the chatbot UI (streaming, citations, one shared conversation) ✅

**Use it:** click the **💬** button at the bottom-right of any page, or open **Assistant** in
the menu (the same conversation, more room).

### Streaming: why answers appear word by word

A language model writes one small piece (a **token**) at a time. Waiting for the whole
answer feels slow, so chat apps **stream**: the server sends each piece as soon as it
exists, and the page shows it immediately. We use **NDJSON** (newline-delimited JSON: one
JSON object per line) over a normal HTTP response:

```
{"type": "meta", "sources": [...], "retrieval": "bm25", "searched": 35}
{"type": "delta", "text": "Here's "}
{"type": "delta", "text": "what "}
…
{"type": "done"}
```

- **meta comes first:** the sources are known *before* any text, because retrieval
  happens before generation. That's the R before the G in RAG.
- **deltas, joined, are the answer.** A test checks this:
  `test_the_stream_sends_meta_then_deltas_then_done`.
- **All database work happens before streaming starts**, so a half-sent answer never holds
  a database connection, and a bad question still gets a normal 422 error.
- **Network chunks don't line up with lines.** A chunk can end in the middle of a JSON
  line, so the reader keeps the unfinished part and adds it to the next chunk
  (`parseNdjson`, tested).
- **Stop** cancels the request with an `AbortController`.

Today the pieces are the extractive answer split into words. In stage 67 they'll be the
model's real tokens, and **the UI won't need to change**. That's why the plumbing was
built first.

### Citations you can click

Answers refer to sources as **[1] [2]**. The chat turns each into a button; clicking it
highlights that source chip under the answer, and the chip links to the skill or job page.
Numbers with no matching source (like "[2024]") stay plain text (`splitCitations`, tested).
**Showing sources is how a RAG system earns trust.**

### One conversation, everywhere

The floating widget and the full page read the **same chat store** (`lib/chatStore.ts`,
using React's `useSyncExternalStore`). The newest 50 messages are kept in **your browser
only** (localStorage), so the chat survives page changes. "Clear chat" removes them. On a
job's or skill's page, the suggestions are about *that* job or skill.

### Interview questions you can now answer

- *How do you stream LLM output to a web page?* Server-sent chunks: NDJSON or SSE over
  HTTP. The client reads the stream incrementally and appends deltas; cancelling uses an
  AbortController.
- *Why send the sources before the text?* Retrieval finishes before generation starts,
  and the UI can show "what I'm reading" while the answer is written.
- *How do you show a RAG answer is grounded?* Inline citations linked to the source
  documents.

## Stage 67: generation with grounding

*Needs Ollama with `llama3.2`.* The model writes a natural answer **using only the
retrieved notes**, cites them as [1] [2], and says when the notes don't cover the question.

## Stage 68: evaluating generation

Stage 66a already measures retrieval. Once a model writes answers, we'll also check
**faithfulness**: does every claim in the answer come from a retrieved note?
