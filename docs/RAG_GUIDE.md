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

## Stage 66: embeddings, meaning search and hybrid search (built ✅; measured on the real model ✅)

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
found **only** by meaning must reach `MIN_COSINE` to count. Otherwise "I couldn't find
that" would become impossible, and the assistant would always hand over its least-bad notes.

### 3b. The real scoreboard (nomic-embed-text, 2026-10-11)

Run on the 15 golden questions over the fixture notes (`python -m app.rag.evaluate`):

| Search | recall@4 | MRR |
|---|---|---|
| BM25 (keywords) | 1.000 | 0.911 |
| BM25 + stemming | 0.833 | 0.694 |
| Meaning only | 0.833 | 0.733 |
| **Hybrid (BM25 + meaning, RRF)** | **1.000** | **0.933** (at `MIN_COSINE = 0.6`) |

- **Meaning alone is worse than keywords here.** It missed "Tell me about my education"
  and "Which skills am I learning right now?" entirely. Our notes are written in the words
  people ask with, which is what BM25 rewards.
- **Hybrid is best.** Each engine fixes the other's misses. For example, "Tell me about
  Python" puts the Python note 3rd with BM25 and 1st with hybrid.
- **Calibrating `MIN_COSINE`:** right notes scored 0.52 to 0.76 (median 0.73). The best
  note for six **off-topic** questions ("What's the weather in Paris?", "Tell me a joke"…)
  scored 0.48 to 0.535.

  | `MIN_COSINE` | Hybrid MRR | Off-topic questions that got notes anyway |
  |---|---|---|
  | 0.50 (the first guess) | 0.900 | **4 of 6** ❌ |
  | 0.55 | 0.900 | 0 of 6 |
  | **0.60 (chosen)** | **0.933** | 0 of 6 |

  The first guess was wrong: it would have answered "weather in Paris?" from your skill
  notes. **This is why you measure instead of guessing.**
- **Caveat:** 15 questions is a small set, written by the same person who wrote the notes.
  It would be worth adding paraphrased questions ("what am I bad at?") over time.

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

Without a model the pieces are the extractive answer split into words. With one (stage
67) they're the model's real tokens, and **the UI barely changed**: it only learned the
`replace` event and the "who wrote it" label. That's why the plumbing was built first.

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

## Stage 67: generation with grounding (built ✅; checked on the real model ✅)

*Turn it on:* `ollama pull llama3.2`, then `OLLAMA_CHAT_MODEL=llama3.2` in `backend/.env`.
Without it, nothing breaks: the answer is the notes themselves, as before.

The **G** in RAG: a language model reads the retrieved notes and writes a short, natural
answer that cites them. Calling a model is the easy part. **Keeping it honest** is the real
work, so the code (`backend/app/rag/generate.py`) has four defences.

### 1. Prompt engineering: the rules come first

Every request starts with a **system prompt**, standing instructions the model reads
before anything else. Ours has five rules:

1. Use **only** the numbered notes. Never invent skills, jobs, dates or proof.
2. Cite every fact like **[1]**.
3. If the notes don't answer, say *"I couldn't find that in your data."* Don't guess.
4. Never call a skill verified unless a note says so.
5. Be brief and practical.

Rule 4 is the project's core rule (**never invent experience**) written for the model.

### 2. The context window: show it only what it needs

A model's **context window** is its working memory: everything it can see at once. Small
local models have small ones, and they get *worse* when stuffed with text. So the model
sees exactly this, and nothing else:

```
system:    the rules
user:      (previous question)           <- the last 2 turns, each cut to 600 characters
assistant: (previous answer)
user:      Notes from my Career AI data:
           [1] (gap) Kubernetes gap: Gap: Kubernetes is missing for the job Backend.
           [2] (skill) Python: Skill: Python. Your status: verified ...
           Question: What am I missing?
```

The notes have a size budget (`MAX_CONTEXT_CHARS = 6000`). They're kept in rank order, so
if anything is cut, it's the weakest note, and the best one is always kept. The model never
sees the database: **PostgreSQL stays the source of truth, and the model only ever sees
a few retrieved notes.**

**Follow-ups:** "How do I learn it?" has nothing to search for. So the *search* text adds
the previous question ("Do I have a Kubernetes gap?"), while the model still sees the real
question. Tested: `test_history_reaches_the_model_and_helps_find_follow_ups`.

### 3. Temperature: boring on purpose

**Temperature** controls randomness when the model picks each next token. High means
creative and varied; low means predictable. We use **0.2**: for answers about *your* data
we want the same faithful answer every time, not creativity.

### 4. Check the answer after it's written

The model's text is checked before it's trusted:

- **Invalid citations are removed.** "[9]" when there were 4 notes points at nothing.
- **An answer that cites nothing is not trusted.** No citation means no evidence that it
  used the notes, so the reply **falls back to the notes themselves**, with a note
  explaining why.
- **If the model fails** (Ollama is off, or the model isn't pulled), the reply also falls
  back to the notes, with the reason.
- **If no note matches the question, the model is never called.** The safest
  hallucination is the one that can't happen.

Because the text streams *while* it's written, a correction arrives as a `replace` event
(the final text), and `done` says who wrote it: `"ai"` or `"notes"`. The chat shows
**"Written by AI from your notes"** or **"From your notes"** under each answer.

**Proof the checks matter (mutation test):** disabling the "cites nothing" check made 2
tests fail. The tests really guard the behaviour.

### What the real model taught us (llama3.2, 2026-10-11)

- **Small models forget rules at the top.** With the rules only in the system prompt,
  just **9 of 18** answers cited a note, so half of them fell back to the plain notes.
  Repeating one line right after the question ("Answer using only these notes, and cite
  the note number for every fact, like [1].") raised that to **18 of 18**. Models pay most
  attention to what they read last. This is called **recency**.
- **The first question is slow.** On first use the model is loaded into memory, which
  took more than 2 minutes on this computer's processor; after that, answers take 3 to 12
  seconds. The timeout is now 5 minutes for reading, but only 5 seconds for connecting,
  so a stopped Ollama still fails fast (measured: 2.8 s).
- **Off-topic questions are never sent to the model.** "What's the weather in Paris?"
  matched no notes, so the model wasn't asked at all.
- **A citation is not proof of a correct answer.** One answer said the skills "with no
  proof yet" were AWS, .NET… and cited the overview note. But that note lists them as
  *missing* skills, not unproven ones. The citation was real; the reading was wrong. A
  follow-up answer also ended with a broken sentence ("To build a project, [1]."). Catching
  this is **faithfulness** checking: stage 68.

### Why a local model?

Ollama runs the model **on this computer**: it's free, and your career data never leaves
the machine. The design doesn't depend on it, though. Anything with a `stream(messages)`
method can be the model (`ChatModel` in `generate.py`), which is how the tests use a
**fake model** that returns fixed words and records what it was sent.

### Interview questions you can now answer

- *How do you reduce hallucination in RAG?* Ground the prompt (only retrieved context,
  explicit rules), use low temperature, require citations and validate them, fall back
  when the answer isn't grounded, and don't call the model when retrieval finds nothing.
- *What is a context window, and how do you manage it?* The model's working memory, in
  tokens. Budget the retrieved context, keep the best-ranked chunks first, and cap the
  chat history.
- *What does temperature do?* It scales the randomness of token sampling. Use low for
  factual and grounded tasks, higher for creative ones.
- *How do you handle follow-up questions in RAG?* Rewrite or expand the retrieval query
  with recent turns (we add the previous question), and pass a short history to the model.
- *How do you test LLM code without calling the model?* Put the model behind an interface
  and use a fake that returns fixed tokens. Test the prompt, the checks and the fallbacks
  deterministically.
- *How do you stream and still validate?* Stream tokens for speed, validate at the end,
  and send a correction (our `replace` event) when the checks change the answer.

## Stage 68: evaluating generation

Stage 66a already measures retrieval. Once a model writes answers, we'll also check
**faithfulness**: does every claim in the answer come from a retrieved note?
