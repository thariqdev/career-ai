// Stage 85: the Leitner boxes behind the interview flashcards.

import assert from "node:assert/strict";
import { test } from "node:test";

import { BOXES, boxCounts, boxOf, cleanProgress, nextCard, record } from "../lib/leitner.ts";

test("knowing a card moves it up a box (to the top at most); missing it sends it back to box 1", () => {
  let p = {};
  for (let i = 0; i < 7; i++) p = record(p, "a", true);
  assert.equal(boxOf(p, "a"), BOXES);
  assert.equal(p.a.seen, 7);
  p = record(p, "a", false);
  assert.equal(boxOf(p, "a"), 1);
  assert.equal(boxOf({}, "never-seen"), 1);
});

test("the next card comes from the lowest box, least seen first, never the one just answered", () => {
  const cards = [{ id: "a" }, { id: "b" }, { id: "c" }];
  const progress = { a: { box: 3, seen: 3 }, b: { box: 1, seen: 2 }, c: { box: 1, seen: 1 } };
  assert.equal(nextCard(cards, progress).id, "c");
  assert.equal(nextCard(cards, progress, "c").id, "b");
  assert.equal(nextCard([{ id: "only" }], {}, "only").id, "only");
  assert.equal(nextCard([], {}), null);
});

test("cards are counted per box, and bad saved data is ignored", () => {
  const cards = [{ id: "a" }, { id: "b" }, { id: "c" }];
  assert.deepEqual(boxCounts(cards, { a: { box: 2, seen: 1 } }), [2, 1, 0, 0, 0]);
  assert.deepEqual(
    cleanProgress({ a: { box: 2, seen: 1 }, b: { box: 9, seen: 1 }, c: "junk", d: { box: 1 } }),
    { a: { box: 2, seen: 1 } },
  );
  assert.deepEqual(cleanProgress(null), {});
});
