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

## Stage 66: embeddings + vector search (next)

*Needs Ollama (free) with `nomic-embed-text`.* We'll turn each note and question into a
list of numbers (an **embedding**) that captures meaning, find the notes **closest in
meaning** (cosine similarity), and combine that with BM25 (**hybrid search**). Then we'll
score it with the same golden set as 66a, so we'll *know* whether meaning search helps.

## Stage 67: generation with grounding

*Needs Ollama with `llama3.2`.* The model writes a natural answer **using only the
retrieved notes**, cites them as [1] [2], and says when the notes don't cover the question.

## Stage 68: evaluating generation

Stage 66a already measures retrieval. Once a model writes answers, we'll also check
**faithfulness**: does every claim in the answer come from a retrieved note?
