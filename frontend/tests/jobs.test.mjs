// Checks for job description helpers (lib/jobs.ts).

import assert from "node:assert/strict";
import { test } from "node:test";

import { jobLabel, matchBand, sameText } from "../lib/jobs.ts";

test("the same posting is recognised despite case, spaces and line breaks", () => {
  assert.equal(sameText("We need Python.\n\nAnd Docker.", "  we NEED python. and   docker. "), true);
  assert.equal(sameText("We need Python.", "We need Python and Go."), false);
  assert.equal(sameText("   ", "   "), false);
});

test("an untitled job is named by the start of its posting", () => {
  assert.equal(jobLabel({ title: "Backend Engineer", raw_text: "anything" }), "Backend Engineer");
  assert.equal(jobLabel({ title: null, raw_text: "Senior   React developer\nwanted" }), "Senior React developer wanted");
  assert.equal(jobLabel({ title: "  ", raw_text: "x".repeat(80) }, 10), "xxxxxxxxxx…");
  assert.equal(jobLabel({ title: null, raw_text: "" }), "Untitled job");
});

test("match bands: strong from 70%, partial from 40%, and null means not compared yet", () => {
  assert.equal(matchBand(100), "strong");
  assert.equal(matchBand(70), "strong");
  assert.equal(matchBand(69), "partial");
  assert.equal(matchBand(40), "partial");
  assert.equal(matchBand(39), "low");
  assert.equal(matchBand(0), "low");
  assert.equal(matchBand(null), "none");
});
