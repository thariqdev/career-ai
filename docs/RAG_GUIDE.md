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

## The whole system on one page (stages 65–75)

```
question ─► (follow-up?) rewrite into a standalone question ─────────── stage 73
         ─► route: an exact-list question? ── yes ─► read-only TOOL ─── stages 69–70
         │                                            (SQL, exact)
         ─► search the notes: BM25 + meaning, fused (RRF) ───────────── stages 65–66
         ─► write: list? code writes it, the model adds one sentence ── stage 74
         │         otherwise the model writes from the notes only ───── stage 67
         ─► check: citations valid, rules on skills/"verified" ──────── stages 67–68
         │         fail → show the notes themselves, with the reason
         ─► stream to the chat (sources first), models kept warm ────── stages 67a, 72
```

| Decision | Chosen because (measured) |
|---|---|
| BM25 without stemming | stemming lowered MRR from 0.889 to 0.672 |
| Hybrid search, `MIN_COSINE` 0.6 | MRR 0.933 vs 0.911 for BM25; at 0.5, 4 of 6 off-topic questions got notes |
| Repeat the citation rule after the question | cited answers rose from 9/18 to 18/18 |
| Rule checks live, AI judge only for measuring | rules: 3/8 caught with 0 false alarms; the best judge rejected 1 right answer in 8 |
| Keyword routing behind guards (not the model) | 0 wrong tools on every set; the model picked 7 wrong tools |
| Code writes exact lists | the model alone listed 4, 25 and 24 of 28 gaps; code lists all 28 every time |
| Keep-alive and warm-up | first word in about 2 s instead of about 19 s |
| Follow-up rewrite | won in stage 73, but **didn't reproduce** in stage 75 (see there) |

**Check everything still works:** `.venv/Scripts/python -m app.rag.scorecard` (add `--full`
for the real-model measures). Its quick part also runs with the test suite.

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

## Stage 68: faithfulness, checking the answer against its notes ✅

**Run it:** `.venv/Scripts/python -m app.rag.faithfulness_eval` (from `backend/`).

A citation shows *where* the model looked, not that it read the note correctly. In stage
67 a real answer said the skills "with no proof yet" were AWS and .NET, and cited the
overview note, which lists them as *missing*. **Faithfulness** asks: does every statement
in the answer come from its notes?

### Who checks the checker? A hand-labelled set

You can't measure a checker without knowing the right answers. So `faithfulness_eval.py`
holds **16 answers written and labelled by hand** over the fixed made-up career:

- **8 faithful answers**, including tricky ones: "Docker **isn't** verified yet" must
  not be flagged just because it contains the word "verified".
- **8 unfaithful answers** of the kinds small models really produce: an extra skill
  (Terraform), a false "verified", missing skills called "on your CV", the wrong job, the
  wrong dates, the wrong degree, and the wrong proof.

Each checker gets two scores, and both matter:

- **caught:** wrong answers it flagged. Each one missed lets a wrong answer through.
- **false alarms:** right answers it flagged. Each one throws away a good answer.

### Two kinds of checker, measured

**1. Rule checks** (`app/rag/faithfulness.py`, `check`) are plain code: instant and free.

- **Every skill the answer names must be in its notes.** Names come from the 227-skill
  catalogue plus your own skills and gaps, with aliases ("JS" counts as JavaScript).
- **"Verified" or "proven" needs proof.** A sentence that calls a skill verified (and
  isn't negated with "not", "no", "yet", "0"…) needs a note whose status really is
  verified. This is the project's core rule, *never invent proof*, applied to the AI.

**2. A judge** (`judge`) is a second model call (**LLM-as-a-judge**) that reads the notes
and the answer and gives a verdict. Three prompts were tried (llama3.2, 3 runs each, the
majority vote counts):

| Checker | Wrong answers caught (of 8) | False alarms (of 8) |
|---|---|---|
| **Rule checks** | 3 | **0** |
| Judge A: "Is the answer faithful? YES/NO" | 8 | **8**: it said NO to everything |
| Judge B: "Does it say anything the notes don't? YES/NO" | 3 | 1 |
| Judge C: check each statement, then "VERDICT: …" | 4 | 1 (and sometimes gives no verdict) |
| Rules **or** judge C | 5 | 1 |

What this shows:

- **Judge A looks perfect if you only count catches.** It caught all 8 by rejecting
  everything. That's why you always measure false alarms too.
- **Asking the model to reason step by step first (C) helps,** but a 3-billion-parameter
  model is a weak judge. Bigger models judge much better; that's why production systems
  usually use a stronger model as the judge.
- **The rules catch only what they're built for** (invented names, false "verified"), but
  they *never* threw away a good answer. A misreading that reuses the notes' own words
  ("Kubernetes is on your CV") passes them.

### The decision

- **The rules run on every AI answer.** If one fails, the chat shows the notes themselves
  with the reason, e.g. "The AI's answer didn't match your notes (it mentions Terraform,
  which isn't in your notes)". Live check: on 18 real llama3.2 answers about your data,
  the rules rejected **none**.
- **The judge stays a measuring tool.** It would catch 2 more mistakes but throw away
  about 1 good answer in 8, and add many seconds per answer on this computer.

### Interview questions you can now answer

- *How do you evaluate a RAG answer, not just retrieval?* Measure **faithfulness**
  (groundedness): is every claim supported by the retrieved context? Also measure
  answer relevance, and citation accuracy.
- *What is LLM-as-a-judge, and what are its pitfalls?* A model grades another model's
  output. Pitfalls: bias towards one verdict (ours said NO to everything), randomness
  (run it several times, take the majority), position and length bias, and a judge that
  is weaker than the task. Always measure it against human labels.
- *Why report both catches and false alarms?* A checker that flags everything catches
  everything. That's precision versus recall: you need both.
- *Rules or a model for guardrails?* Rules for hard, cheap, testable invariants (no
  invented skills, no unproven "verified"); a model for fuzzy meaning, if it measures
  well enough to justify its cost.

## Stage 69: tools, exact answers from the database (tool calling and routing) ✅

**Run it:** `.venv/Scripts/python -m app.rag.router_eval` (from `backend/`).

### Why search isn't enough

Search hands the model the 4 notes that *look* most like the question. That's right for
"Tell me about Python". It's wrong for **list and count questions**:

- "Which skills have no proof yet?" needs **all 23** skills checked, not 4 similar-looking
  notes. In stage 67 the model got the overview and misread *missing* skills as *unproven*.
- "What am I missing for the Acme job?" needs that job's gaps, **all of them**.

A **tool** is a plain function that computes the exact answer from PostgreSQL
(`app/rag/tools.py`):

| Tool | Answers |
|---|---|
| `skills_without_proof` | claimed with no proof, plus on your CV but not claimed |
| `verified_skills` | each verified skill and its proof |
| `skills_on_cv` | what your CV lists |
| `job_gaps` | missing skills, for one named job or all jobs |
| `learn_first` | missing skills, ranked by how many jobs need them |

The tool's result becomes **note [1]**, and search fills the other three. So the model
still only puts notes into words, and the stage-67 citation check and the stage-68
faithfulness check apply unchanged. **Tools are read-only** (tested): the assistant can
look things up, never change your data.

### Routing: which tool, if any?

Two **routers** were built and measured (`app/rag/router.py`):

- **Keyword rules:** "no proof" or "unverified" goes to `skills_without_proof`; a job's name plus
  "missing" or "need" goes to `job_gaps` for that job; and so on.
- **Tool calling:** the model is shown each tool's name and description as a **JSON
  schema** (this is how "function calling" works in every LLM API). It replies with a
  tool and its arguments (`{"name": "job_gaps", "arguments": {"job": "Acme"}}`) or with no tool.

Two question sets: **dev** (drafted while the rules were written) and **held-out**
(different wording written afterwards, never used to change the rules: the honest test).

| Router | Dev right | Held-out right | Wrong tool | Speed |
|---|---|---|---|---|
| **Keyword rules** | 27/27 | 8/16 | **0** | instant |
| llama3.2 tool calling | 24/27 | 12/16 | 3 + 4 | 0.7 s per question |

- **The model understands more phrasings** ("Am I ready for Acme?"), and the rules miss
  half of the held-out set.
- **But the model picks wrong tools.** It answered "Do I know Kubernetes?" with the list
  of unproven skills, "Is TypeScript on my CV?" with the whole CV list, and "How do I add
  evidence?" with the verified skills.
- **The two mistakes cost different things.** A *missed* tool falls back to search,
  which is how the assistant worked before. A *wrong* tool gives an exact-looking answer
  to a different question, which is worse than no tool. So **the keyword rules are used**.
- Note that the rules score 27/27 on dev but only 8/16 on held-out. **Scoring only on the
  questions you tuned on flatters you.** That's why the held-out set exists.

On your real data, "Which skills have no proof yet?" now lists all 23 of your CV skills
exactly, and "What should I learn first?" ranks AWS first (needed by 2 jobs).

### Interview questions you can now answer

- *When is RAG the wrong tool?* For aggregation, counting, filtering and exact lists. Use
  structured queries (SQL) for those, and keep retrieval for open-ended questions.
  Combining both is often called **agentic RAG** or **hybrid structured + unstructured** retrieval.
- *How does function calling work?* You send tool definitions (a name, a description, and a
  JSON schema of arguments); the model replies with a structured call; **your code** runs
  it and feeds the result back. The model never touches the database itself.
- *How do you keep tools safe?* Read-only tools, a fixed allow-list (an unknown tool name
  is ignored), validated arguments, and least privilege.
- *Why a held-out set?* Rules or prompts tuned on the dev set overfit it. Only wording you
  didn't tune on shows real-world accuracy.

## Stage 70: a cascade with guardrails, and a test set you can only use once ✅

**The idea:** combine both routers. The rules decide first; only when they find nothing
is the model asked, and its choice must pass **guardrails** (`router.guard`):

- A question naming a specific skill ("Do I know Kubernetes?") is about that skill, not a
  list, so it gets search. The exception is one job's gaps ("What am I missing for Acme?
  Kubernetes?"), because that job's exact list holds the answer.
- "How do I…" asks for instructions, which no tool gives, so it gets search.
- A job the question never mentions was made up by the model, so all jobs are shown instead.

### Three question sets, and why

| Set | What it's for | Status |
|---|---|---|
| **dev** (27) | tune freely | used for tuning |
| **held-out** (16) | check the tuning | its mistakes inspired this stage, so it's no longer unseen |
| **TEST** (20) | written **and committed before any guard code existed** (commit `5b4f6b3`), run once | the honest score |

**Pre-registration:** before measuring, the bar was written down. The cascade goes live
only if it picks **no wrong tools on TEST** and answers more correctly than the rules.

### The honest results (TEST, first run)

| Router | Right | Wrong tool | Missed tool | Time |
|---|---|---|---|---|
| Keyword rules | 11/20 | 1 | 8 | 0 s |
| llama3.2 alone | 12/20 | **8** | 0 | 0.8 s |
| **Cascade** (rules, then model + guards) | **16/20** | **4** | 0 | 0.6 s |

- **The cascade answers the most questions, but it fails the bar.** It answered "What
  projects have I built?" with the unproven-skills list, and "Tell me about the Acme job"
  with only its gaps. **So it doesn't go live.** Writing the bar down first is what stops
  you lowering it after seeing the numbers.
- **The fresh set found a bug in the rules.** They sent "Why is React not verified?" (one
  skill) to the unproven-skills list. Dev and held-out never showed this.

### What changed

The live router is now **the rules behind the guards** (`guarded_keyword_route`). On dev
it gets 27/27, on held-out 8/16, and it picks **0 wrong tools** on all three sets.

**Honest caveat:** this fix was prompted by TEST, so its TEST score (12/20, 0 wrong) is
**no longer an unbiased estimate**. TEST is now "used". The next change to routing needs a
new, untouched test set.

### Interview questions you can now answer

- *Why do you need separate dev, validation and test sets?* Every time you look at a set's
  mistakes and change something, you fit that set a little. Only a set you never tuned on
  estimates real-world accuracy, and it's spent once you act on it.
- *What is a cascade, and when is it worth it?* Cheap, precise components first; an
  expensive or flexible one only when they abstain. It's worth it when the flexible part's
  errors can be contained (here with guards). It wasn't enough here: 4 wrong tools out of 20.
- *What is pre-registration?* Writing the success criterion before seeing the results, so
  the decision can't drift to fit the numbers.

## Stage 72: speed, cold starts, keep-alive and time to first token ✅

**Run it:** `.venv/Scripts/python -m app.rag.latency_eval` (from `backend/`).

What makes a chat *feel* fast is **time to first token (TTFT)**: how long until the
first word appears. Measure before changing anything.

### What was slow, and why

A local model must be **loaded into memory** before it answers, and Ollama **unloads an
idle model after 5 minutes** (seen in `/api/ps`, which lists loaded models and when they
expire). So a pause of more than 5 minutes meant a **cold start** again:

| Model | Cold | Warm | Memory while loaded |
|---|---|---|---|
| Chat, first word (llama3.2) | 10.0 s | 0.39 s | 2.9 GB |
| Embedding a question (nomic-embed-text) | 8.7 s | 0.45 s | 0.3 GB |

The very first load after installing took 145 s, because Windows hadn't cached the model
file yet.

### Fixes, each measured

1. **Keep-alive.** Every request now asks Ollama to keep the model loaded for
   `OLLAMA_KEEP_ALIVE` (default **30 minutes**; `-1` = always). The trade-off is
   **3.2 GB of memory** held while loaded.
2. **Warm-up at startup** (`app/rag/warmup.py`). With the AI switched on, the backend
   loads both models **in a background thread**, so startup isn't delayed (the server
   answered in about 4 s), and nothing breaks if Ollama is off.
3. **The measurement showed a second cold thing.** With the models warm, the first
   question *still* took 12.3 s to its first word. Timing each step showed why: meaning
   search embeds every note, and the cache starts empty. The first question spent
   **8.7 s embedding 67 notes**; the second needed 0.85 s. So the warm-up also embeds your
   notes (`index_notes`). Search and the warm-up share one function for the note text
   (`note_texts`), because if they differed by even one character, the cache would quietly
   miss. A test catches that (mutation-checked). The cache now has a lock, since the
   warm-up thread and requests can use it at the same time.

### Result: the first question after starting the backend

| | First word appears |
|---|---|
| Before (both models cold) | ~19 s |
| Models warmed only | 12.3 s |
| **Models warmed and notes pre-embedded** | **1.7–3.2 s** |

What's left is ordinary work: building notes from PostgreSQL (0.8 s), search (0.4 s), and
the model reading the prompt and starting to write (0.5 s; it read 556 prompt tokens in
0.03 s and wrote 52 tokens in 1.4 s).

### Interview questions you can now answer

- *What is TTFT, and why stream?* Time to first token. Users judge speed by when text
  starts, so stream tokens and send the sources first.
- *What is a cold start, and how do you avoid it?* Loading weights (or a container, or a
  cache) on the first request. Keep it loaded (keep-alive, min instances), warm it at
  startup in the background, and pre-compute what the first request needs (here, the note
  embeddings).
- *How do you find where latency goes?* Measure each stage separately: retrieval,
  prompt processing (prefill), and generation (decode). Here, the slow part wasn't the
  model at all, but embedding the notes.
- *What's the cost of keeping models warm?* Memory (3.2 GB here) held while idle. It's a
  time-for-memory trade-off you choose with the keep-alive setting.

## Stage 73: follow-up questions and query rewriting ✅

**Run it:** `.venv/Scripts/python -m app.rag.rewrite_eval` (from `backend/`).

"And for Globex?" means nothing to search on its own. Until now, the search text was the
follow-up **glued** to the previous question. That finds the topic, but drags the old one
along (Acme), and it breaks when the follow-up changes topic.

**Query rewriting:** before searching, the model turns the follow-up into a **standalone
question** ("What am I missing for the Globex job?"), at temperature 0
(`app/rag/rewrite.py`). The rewrite is used **only for search and tool routing**. The model
that writes the answer still sees the real question and the history, so a bad rewrite can
at worst fetch the wrong notes, which the citation and faithfulness checks still guard.
With no history, nothing is rewritten. If the rewrite fails or is unusable (empty,
several lines, or too long), the old glued text is used.

### Measured on 20 follow-ups, committed before any rewrite code (commit `3b4e0aa`)

The set includes follow-ups that change topic, and first questions with no history.

| How the follow-up is searched | recall@4 | MRR | Right tool | Wrong tool |
|---|---|---|---|---|
| Alone | 0.700 | 0.546 | 17/20 | 0 |
| Glued to the last question (before) | 0.900 | 0.637 | 17/20 | 0 |
| **Rewritten** | **0.900** | **0.717** | **18/20** | **0** |

The bar was written down in advance: better retrieval than gluing, and no wrong tools.
Recall is tied, MRR is higher (+0.08), and it gets one more right tool, so the rewrite is
live. The cost is about **1.2 s, only on follow-ups**. With 20 cases, +0.08 MRR is about
two questions ranking better: a real but small win.

**Most rewrites are good:**

- "And for Globex?" → "What am I missing for the Globex job?"
- "Is it verified?" → "Is React verified?"

**Some drift:**

- "How do I prove it?" → "Can Docker provide proof of its security and integrity?"

That drift is why the answer still uses the real question. On your data, "How do I learn the
first one?" was correctly resolved to GraphQL, the first gap in the previous answer.

### Interview questions you can now answer

- *How does RAG handle multi-turn chat?* Rewrite the follow-up into a standalone query
  (sometimes called **condense question** or **query rewriting**), retrieve with that,
  and answer with the full history. Simpler fallbacks: concatenate recent turns, or embed
  the conversation.
- *What can go wrong with query rewriting?* Drift (the rewrite changes the meaning),
  extra latency, and a model that fails or rambles. So use it for retrieval only, validate
  its output, fall back to a simpler method, and measure against the simple baseline.

## Stage 74: answer quality, complete and consistent ✅

**Run it:** `.venv/Scripts/python -m app.rag.answer_eval` (from `backend/`).

Earlier stages measured *finding* notes. This one measures the *written answer*.

### Measures (all automatic)

- **Completeness:** the share of the facts an answer must mention that it does mention.
- **Consistency:** asked 3 times, does it give the same facts each time?
- **Forbidden words:** for example, GraphQL in an answer about the Acme job.

They are scored on 15 questions committed before any change (commit `0eebabb`), with
3 runs each.

### Four candidates, measured

| Candidate | Completeness | Same facts every run | Forbidden words | Time per answer |
|---|---|---|---|---|
| A: today (temperature 0.2) | 0.982 | 13/15 | 0 | 1.9 s |
| B: temperature 0 | 0.982 | 14/15 | 0 | 1.5 s |
| **C: exact lists written by code** | **1.000** | **15/15** | 0 | 1.4 s |
| B + C | 0.982 | 14/15 | 0 | 1.3 s |

**C:** when a tool answered (an exact list), **code writes the list word for word**, and
the model writes only a one-sentence introduction. If the introduction misbehaves (it
names a skill, cites, runs to several lines, or is too long), a fixed sentence is used.
Search answers are still written by the model.

### The real test: your data

The made-up career has short lists, so A already reached 98%. Your real lists are long:

| Question | Items in the exact list | A: AI-written, 3 runs | C: code-written |
|---|---|---|---|
| Which skills have no proof yet? | 23 | 23, 22, 22 | **23** |
| What am I missing for my jobs? | 28 | **4**, 25, 24 | **28** |

Small models **drop items from long lists**: once, only 4 of 28. That's not a
hallucination the faithfulness rules can catch, because everything it *did* say was true.
It's an **omission**. **C is live** (`EXACT_LISTS = True`).

**Two lessons:**

- **Temperature 0 isn't fully deterministic.** One answer still varied between runs.
- **Use the model for language, and code for data.** When the answer *is* data, let code
  write it.

### Interview questions you can now answer

- *How do you evaluate generated answers automatically?* Keep a fixed question set with
  required facts (completeness or recall of key facts), forbidden content, and
  consistency across repeated runs. Then add faithfulness checks and human review of
  samples.
- *What's the difference between hallucination and omission?* A hallucination says
  something unsupported; an omission leaves out something required. Faithfulness checks
  catch the first, and completeness metrics catch the second.
- *When should an LLM not write the answer?* When the answer is structured data
  (lists, numbers, tables). Render it with code (this is also called **templated** or
  **structured output**), and let the model add the language around it.

## Stage 75: one scorecard for everything, and a result that didn't reproduce ✅

**Run it:** `.venv/Scripts/python -m app.rag.scorecard` (quick, no Ollama), `--full` (with
the real models), and `--save` to record a new baseline after a deliberate improvement.

Every stage measured *one* thing, but a change that helps one measure can quietly hurt
another. So the scorecard runs **every** measure and compares it with a saved **baseline**
(`app/rag/scorecard_baseline.json`). Anything worse than its tolerance is marked ❌, and
the command exits with code 1. This is **regression testing for AI**: it's how teams
change prompts or models without fear.

- **Quick measures** (no model): keyword retrieval, the faithfulness rules on the labelled
  answers, routing on all three question sets, and follow-up search with the glued
  method. They're deterministic, so their tolerance is **0**, and
  `tests/test_rag_scorecard.py` runs them **with every test run**. Weakening the skill guard
  failed it at once: "routing (test): right: 11 (baseline 12)", "wrong tools: 1
  (baseline 0)".
- **Full measures** (real models): hybrid retrieval, follow-ups (rewritten and glued, side
  by side), and answer completeness and consistency. Models vary, so these get a small
  tolerance, and they're run by hand.

### What the scorecard found: the follow-up rewrite didn't reproduce

Stage 73 measured the rewrite once and switched it on (MRR 0.717 vs 0.637 for gluing).
Re-measured in stage 75 (three runs, identical to each other):

| Follow-ups, hybrid search | recall@4 | MRR | Right tool |
|---|---|---|---|
| Glued (simple) | **0.900** | **0.637** | 17/20 |
| Rewritten (live) | 0.850 | 0.633 | **18/20** |

**The same model, prompt and temperature 0 rewrote two questions differently:**

- "Which job needs it?" → "**Backend Engineer**". The model answered instead of rewriting.
- "What about AWS?" → "Do I have a job opening at **Globex**?" The wrong topic.

**Lessons:**

- **One run isn't evidence for a model-based component.** Measure several times, on
  different days, before switching something on.
- **Temperature 0 doesn't mean reproducible.** Small numeric differences when a model is
  reloaded can change its outputs. (Ollama also takes a fixed `seed`.)
- **A baseline turns a surprise into a visible ❌** instead of a silent change.

The rewrite is still on for now; whether to keep it is an open decision (see
PROJECT_PROGRESS).

### Interview questions you can now answer

- *How do you regression-test an LLM app?* Use a fixed evaluation set with saved baseline
  scores and per-metric tolerances. Run the deterministic parts in CI on every change, and
  the model-based parts on demand or nightly. Fail when any metric drops beyond its
  tolerance.
- *Why did a result fail to reproduce, and what do you do?* Model outputs vary (reloads,
  hardware, versions), and a single measurement is noisy. Repeat the runs, report the
  variance, pin seeds and versions where possible, and only trust gains larger than the
  run-to-run noise.
