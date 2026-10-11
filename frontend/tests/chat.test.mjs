// Checks for the chat's pure helpers (lib/chat.ts).

import assert from "node:assert/strict";
import { test } from "node:test";

import { feedbackBody, forStorage, historyFor, pageTarget, parseNdjson, splitCitations, suggestionsFor } from "../lib/chat.ts";

test("NDJSON: complete lines are parsed, a half line is kept for the next chunk", () => {
  const first = parseNdjson('{"type":"delta","text":"Hel"}\n{"type":"del');
  assert.deepEqual(first.events, [{ type: "delta", text: "Hel" }]);
  assert.equal(first.rest, '{"type":"del');

  const second = parseNdjson(first.rest + 'ta","text":"lo"}\n{"type":"done"}\n');
  assert.deepEqual(second.events, [{ type: "delta", text: "lo" }, { type: "done" }]);
  assert.equal(second.rest, "");
});

test("citations become clickable parts; numbers without a source stay text", () => {
  assert.deepEqual(splitCitations("Learn it [1], then [2]. In [2024] too [3].", 2), [
    { kind: "text", text: "Learn it " },
    { kind: "cite", number: 1 },
    { kind: "text", text: ", then " },
    { kind: "cite", number: 2 },
    { kind: "text", text: ". In [2024] too [3]." },
  ]);
  assert.deepEqual(splitCitations("No sources here.", 0), [{ kind: "text", text: "No sources here." }]);
});

test("suggestions follow the page you're on", () => {
  assert.equal(suggestionsFor({ kind: "job", label: "Backend at Acme" })[0], "What am I missing for Backend at Acme?");
  assert.equal(suggestionsFor({ kind: "skill", name: "Docker" })[1], "How do I prove Docker?");
  assert.equal(suggestionsFor(null)[0], "What am I missing for my jobs?");
});

test("the page is recognised from the address", () => {
  assert.deepEqual(pageTarget("/job-descriptions/7"), { kind: "job", id: 7 });
  assert.deepEqual(pageTarget("/job-descriptions/7/prep"), { kind: "job", id: 7 });
  assert.deepEqual(pageTarget("/skills/3"), { kind: "skill", id: 3 });
  assert.equal(pageTarget("/skills"), null);
  assert.equal(pageTarget("/"), null);
});

test("stored history keeps the newest 50 and never a half-written answer", () => {
  const messages = Array.from({ length: 60 }, (_, i) => ({
    id: String(i), role: "user", text: `m${i}`, at: "", status: i === 59 ? "streaming" : "done",
  }));
  const kept = forStorage(messages);
  assert.equal(kept.length, 50);
  assert.equal(kept[0].text, "m10");
  assert.equal(kept.at(-1).status, "stopped");
});

test("follow-ups send the last 4 finished turns, never a half-written or failed one", () => {
  const messages = [
    ...Array.from({ length: 6 }, (_, i) => ({ id: String(i), role: i % 2 ? "assistant" : "user", text: `t${i}`, at: "", status: "done" })),
    { id: "e", role: "assistant", text: "Could not reach the backend.", at: "", status: "error" },
    { id: "s", role: "assistant", text: "half", at: "", status: "stopped" },
  ];
  assert.deepEqual(historyFor(messages), [
    { role: "user", text: "t2" },
    { role: "assistant", text: "t3" },
    { role: "user", text: "t4" },
    { role: "assistant", text: "t5" },
  ]);
  assert.deepEqual(historyFor([]), []);
});

test("a rating records the answer, the question before it, and what the assistant used", () => {
  const messages = [
    { id: "q1", role: "user", text: "Old question", at: "", status: "done" },
    { id: "a1", role: "assistant", text: "Old answer", at: "", status: "done" },
    { id: "q2", role: "user", text: "Which skills have no proof yet?", at: "", status: "done" },
    {
      id: "a2", role: "assistant", text: "Docker and Git [1].", at: "", status: "done",
      sources: [{ number: 1, kind: "tool", title: "Skills with no proof yet", text: "...", link: "/skills", score: 1 }],
      retrieval: "hybrid", writtenBy: "notes",
    },
    { id: "a3", role: "assistant", text: "half", at: "", status: "stopped" },
  ];
  assert.deepEqual(feedbackBody(messages, "a2", "down", "  left out React  "), {
    message_id: "a2",
    rating: "down",
    question: "Which skills have no proof yet?",
    answer: "Docker and Git [1].",
    sources: [{ number: 1, kind: "tool", title: "Skills with no proof yet" }],
    retrieval: "hybrid",
    written_by: "notes",
    comment: "left out React",
  });
  assert.equal(feedbackBody(messages, "a2", "up").comment, null);
  assert.equal(feedbackBody(messages, "a3", "up"), null); // not finished
  assert.equal(feedbackBody(messages, "q2", "up"), null); // not an answer
  assert.equal(feedbackBody(messages, "nope", "up"), null);
});
