// Checks for the chat's pure helpers (lib/chat.ts).

import assert from "node:assert/strict";
import { test } from "node:test";

import { forStorage, pageTarget, parseNdjson, splitCitations, suggestionsFor } from "../lib/chat.ts";

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
