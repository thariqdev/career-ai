# Career AI — Project Rules

> **Status:** Foundation phase. No application code exists yet. All changes beyond these documents require explicit approval.

## 1. Purpose

Career AI is a personal career and technical-knowledge system. It stores verified professional data, compares job descriptions against that data, identifies gaps, recommends learning resources, and supports interview preparation.

## 2. Anti-Hallucination Principle (Non-Negotiable)

The system must never invent facts about the user's background.

### 2.1 Database = Source of Truth

PostgreSQL is the only source of truth for personal career information. The LLM is not the source of truth. The LLM may only extract, structure, compare, suggest, and assist with reasoning. It must never independently decide what the user knows, how many years of experience they have, what projects they worked on, what responsibilities they held, or whether a skill is verified.

### 2.2 What the system may claim

The AI may only state as fact information that exists as verified evidence in the database:

- Verified technical skills
- Verified proficiency levels
- Verified work experience
- Verified projects and evidence
- Verified education and certifications

### 2.3 What the system must never do

- Infer years of experience from a technology appearing in a project.
- Automatically mark an unknown technology as a skill.
- Automatically add a technology to a CV or profile.
- Upgrade `PARTIAL` or `PROVISIONAL` to `VERIFIED` without supporting evidence.
- Use self-assessment alone as proof of professional experience.
- Override backend verification rules.

### 2.4 Default response for missing data

If the system does not have verified information about a requirement, skill, or claim, it must respond with:

> "Not enough verified information."

## 3. Verification Statuses

| Status | Definition |
|--------|------------|
| `VERIFIED` | Sufficient supporting evidence exists that the user has actually worked with or demonstrated the skill. |
| `PARTIAL` | Some supporting evidence exists, but it is insufficient to claim strong/full proficiency. |
| `PROVISIONAL` | The user has reported or is learning the skill, but sufficient supporting evidence has not yet been recorded. |
| `NOT_VERIFIED` | No relevant evidence exists in the system. |

Only `VERIFIED` evidence may be used when making factual claims about the user's professional background. The AI may read `PROVISIONAL` data for context, but it must never use it as proof of professional experience.

## 4. Evidence Requirements

### 4.1 Acceptable evidence for VERIFIED

A skill or experience is `VERIFIED` only when backed by at least one piece of concrete, reviewable evidence:

- Documented work experience
- Documented project contribution
- GitHub/public repository or other public artifact
- Deployed application or demo
- Certification or official credential
- Documented technical responsibility
- Other objectively reviewable evidence

### 4.2 Self-assessment rule

The user may record their own confidence or knowledge level, but self-assessment alone must **never** result in `VERIFIED`. It should be represented as `PROVISIONAL` or `PARTIAL` until supporting evidence exists.

The system must never convert:

```text
Self-assessment → VERIFIED
```

without supporting evidence.

## 5. CV Skills vs Actual Knowledge

The application must distinguish between:

- **Skills the user has verified knowledge/evidence for.**
- **Skills currently listed on the user's CV.**
- **Skills required by a job description.**

These are not the same thing.

Examples:

- User has verified Docker experience, but Docker is not on the current CV.
  - Knowledge status: `VERIFIED`
  - CV status: `MISSING_FROM_CV`
  - Recommendation: "Consider adding Docker to your CV."

- Job requires AWS. User has no verified AWS evidence.
  - Knowledge status: `NOT_VERIFIED`
  - CV status: `NOT_PRESENT`
  - Recommendation: "Do not claim AWS experience on your CV. Learn and gain evidence first."

The system must never automatically add a skill to the CV.

## 6. Skill Taxonomy and Canonical Skills

Do not rely on simple literal keyword matching. Use a canonical skill taxonomy.

Each skill conceptually supports:

- Canonical name
- Aliases
- Category
- Optional related skills
- Optional parent/child relationships

Examples:

- Canonical skill: `React.js`
  - Aliases: `React`, `ReactJS`, `React.js`
- Canonical skill: `PostgreSQL`
  - Aliases: `PostgreSQL`, `Postgres`
- Canonical skill: `REST API`
  - Aliases: `REST APIs`, `RESTful API`, `REST API development`

Related technologies must **not** automatically be treated as equivalent:

- `Next.js` ≠ `Node.js`
- `React.js` ≠ `React Native`
- `PostgreSQL` ≠ `MySQL`
- `FastAPI` ≠ `Django`
- `JavaScript` ≠ `TypeScript`

The LLM can assist in extracting and normalizing job requirements, but the backend must validate the final mapping against the canonical skill taxonomy.

## 7. Job Requirement Matching

The job analysis flow is:

```text
JOB DESCRIPTION
        ↓
LLM extracts structured requirements
        ↓
Normalize requirements to canonical skills
        ↓
Backend validates canonical skill mapping
        ↓
Compare against user's stored evidence
        ↓
Determine status
        ↓
Generate explanation
```

The LLM must not directly decide the final `VERIFIED`/`PARTIAL`/`PROVISIONAL`/`NOT_VERIFIED` status. The backend verification/comparison logic determines it.

A skill is never considered matched merely because a keyword appears. Every user-skill match must be traceable to stored evidence.

## 8. Evidence Traceability

Every verified skill must be traceable to one or more evidence records.

Example:

```text
Python
    ↓
VERIFIED
    ↓
Evidence:
    FundsApp
    Python
    FastAPI
    SQLAlchemy
    PostgreSQL
```

When the application says "You have Python experience," it must be able to show why. Comparison results must contain references/IDs to the underlying evidence records. The frontend should eventually display:

> "Why is this marked VERIFIED?"

and show the relevant project, work experience, or artifact.

## 9. AI / LLM Boundary

LLM = assistant, NOT authority.

The AI can:

- Parse job descriptions
- Normalize terminology
- Explain technical concepts
- Generate interview questions
- Suggest learning resources
- Generate learning plans
- Assist with reasoning

The AI cannot:

- Invent user experience
- Invent projects
- Invent responsibilities
- Invent years of experience
- Invent proficiency
- Mark a skill `VERIFIED`
- Add skills to the CV automatically
- Override backend verification rules

All structured AI outputs must be validated by Pydantic/backend validation before being accepted.

## 10. Technology Direction

| Layer | Stack |
|-------|-------|
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, SQLAlchemy, PostgreSQL |
| AI/LLM | LLM API with structured outputs |
| Database | PostgreSQL (`pgvector` to be introduced later) |
| Search/RAG | To be introduced later |
| Dev Tools | VS Code, Git, Bionic |

## 11. Development Principles

This is a learning project. The codebase must be professional enough for a portfolio but understandable enough to explain in an interview.

- Prefer simple architecture.
- Avoid premature abstractions.
- Avoid unnecessary dependencies.
- Keep business logic explicit.
- Document important decisions.
- Build incrementally.
- Write tests for important verification rules.

## 12. Verification Workflow

1. User adds or imports career data.
2. Data is stored as `PROVISIONAL` by default.
3. User links concrete evidence.
4. The verification layer promotes records to `VERIFIED`, `PARTIAL`, or keeps them `PROVISIONAL`.
5. AI comparisons use only verified records, clearly labeled.

## 13. Comparison Rules

- Extract requirements from a pasted job description using structured LLM output.
- Normalize requirements to canonical skills.
- Compare each requirement against verified evidence.
- Categorize as `VERIFIED`, `PARTIAL`, `PROVISIONAL`, or `NOT_VERIFIED`.
- Provide reasoning tied to specific stored records.
- Never assume a requirement is met because of a keyword match alone.

## 14. Learning System

Maintain two learning modes:

- **THEORY / INTERVIEW**
- **TECHNICAL / PRACTICAL**

For each identified skill gap, the application should eventually support:

- Skill explanation
- Interview concepts
- Interview questions
- Practical concepts
- Hands-on tasks
- Project exercises
- Recommended resources
- Learning progress

Learning completion must be explicitly recorded by the user. The AI must not infer mastery from viewing a tutorial.

## 15. Learning Resources

- Recommendations can be AI-suggested but must be reviewable and editable by the user.
- Prioritize official documentation, reputable YouTube channels, established learning platforms, and high-quality technical resources.
- The architecture should allow curated resources in addition to AI-generated recommendations.

## 16. Progress Tracking

- Learning plans are derived from gaps identified in comparisons.
- Progress is stored explicitly; the system does not infer completion.

## 17. Change Control

- This file, `ARCHITECTURE.md`, and `FOLDER_STRUCTURE.md` are the foundation contract.
- Any material change to architecture, data model, or anti-hallucination rules must be documented here before implementation.
- Do not proceed to the next phase without explicit approval.
