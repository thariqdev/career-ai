"""The action detector's test set (RAG stage 78), written BEFORE the detector existed.

Over the fixed made-up career in app/rag/evaluate.py (saved skills: Docker, Git,
PostgreSQL, Python, React, TypeScript; Kubernetes is only a job's gap, not a skill).

Each case: a chat message and what the detector must return:
- ("progress", skill, status)   propose setting learning progress
- ("link", skill, mode)         propose saving a learning link
- ("refused", skill)            explain this isn't done through the chat (verify, evidence, delete)
- None                          no action: it's a question (search answers it), or unclear

A WRONG action (proposing something not asked for) is the worst outcome, so the bar is
zero; a missed action is only an inconvenience (the chat answers normally).
"""

ActionExpectation = tuple | None

ACTION_CASES: list[tuple[str, ActionExpectation]] = [
    # --- should propose an action -----------------------------------------------------------
    ("Mark React as studying", ("progress", "React", "studying")),
    ("I'm learning Docker now", ("progress", "Docker", "studying")),
    ("I started studying TypeScript", ("progress", "TypeScript", "studying")),
    ("I finished learning Docker", ("progress", "Docker", "finished")),
    ("Mark Git as finished", ("progress", "Git", "finished")),
    ("Set PostgreSQL to not started", ("progress", "PostgreSQL", "not_started")),
    ("Can you mark Python as done?", ("progress", "Python", "finished")),
    ("Please mark TypeScript as in progress", ("progress", "TypeScript", "studying")),
    ("Save https://youtu.be/abc123 as a Docker tutorial", ("link", "Docker", "technical_practical")),
    ("Add this React interview video: https://www.youtube.com/watch?v=xyz", ("link", "React", "theory_interview")),
    # --- must be refused (not done through the chat) ----------------------------------------
    ("Verify my Python skill", ("refused", "Python")),
    ("Mark React as verified", ("refused", "React")),
    ("Delete Docker", ("refused", "Docker")),
    ("Can you add evidence for Git?", ("refused", "Git")),
    # --- must do nothing ----------------------------------------------------------------------
    ("Is React studied?", None),
    ("Am I learning React?", None),
    ("Which skills am I studying?", None),
    ("Mark Kubernetes as studying", None),  # not one of the saved skills
    ("Mark React and Docker as studying", None),  # two skills: unclear which
    ("What should I learn first?", None),
    ("Save this link for later", None),  # no skill, no link
    ("How do I verify Docker?", None),  # a question about how, not a request
]
