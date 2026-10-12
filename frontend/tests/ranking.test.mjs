// Checks for the "Skills to learn" ranking (lib/ranking.ts). Run with `npm test`.
// Node 24 loads the TypeScript file directly (its type-only imports are stripped).

import assert from "node:assert/strict";
import { test } from "node:test";

import { rankSkillsToLearn } from "../lib/ranking.ts";

let nextId = 1;

// A gap for one skill. Only the fields the ranking reads are filled in.
function gap(skillId, name) {
  return { key: `k${nextId++}`, skill_id: skillId, skill_name: name, study_links: [] };
}

const PYTHON = [1, "Python"];
const DOCKER = [2, "Docker"];
const RUST = [3, "Rust"];

function names(ranked) {
  return ranked.map((s) => s.name);
}

test("a skill for an active application beats a skill more saved jobs want", () => {
  const ranked = rankSkillsToLearn(
    [
      { status: "applied", gaps: [gap(...RUST)] },
      { status: "saved", gaps: [gap(...DOCKER)] },
      { status: "saved", gaps: [gap(...DOCKER)] },
    ],
    8,
  );

  assert.deepEqual(names(ranked), ["Rust", "Docker"]);
  assert.deepEqual(ranked[0], { key: "3", skillId: 3, name: "Rust", studyLinks: [], jobs: 1, activeJobs: 1 });
  assert.deepEqual(ranked[1], { key: "2", skillId: 2, name: "Docker", studyLinks: [], jobs: 2, activeJobs: 0 });
});

test("interviewing counts as active too", () => {
  const ranked = rankSkillsToLearn(
    [
      { status: "saved", gaps: [gap(...DOCKER)] },
      { status: "interviewing", gaps: [gap(...PYTHON)] },
    ],
    8,
  );

  assert.deepEqual(names(ranked), ["Python", "Docker"]);
});

test("finished jobs (offer, rejected, withdrawn) don't rank anything", () => {
  const ranked = rankSkillsToLearn(
    [
      { status: "rejected", gaps: [gap(...RUST)] },
      { status: "withdrawn", gaps: [gap(...RUST)] },
      { status: "offer", gaps: [gap(...RUST), gap(...DOCKER)] },
      { status: "saved", gaps: [gap(...DOCKER)] },
    ],
    8,
  );

  assert.deepEqual(ranked, [{ key: "2", skillId: 2, name: "Docker", studyLinks: [], jobs: 1, activeJobs: 0 }]);
});

test("a skill is counted once per job, and unmapped gaps are skipped", () => {
  const ranked = rankSkillsToLearn(
    [{ status: "applied", gaps: [gap(...PYTHON), gap(...PYTHON), gap(null, null)] }],
    8,
  );

  assert.deepEqual(ranked, [{ key: "1", skillId: 1, name: "Python", studyLinks: [], jobs: 1, activeJobs: 1 }]);
});

test("ties are broken by name, and the limit applies", () => {
  const ranked = rankSkillsToLearn(
    [{ status: "saved", gaps: [gap(...RUST), gap(...PYTHON), gap(...DOCKER)] }],
    2,
  );

  assert.deepEqual(names(ranked), ["Docker", "Python"]);
});

test("no jobs means nothing to learn", () => {
  assert.deepEqual(rankSkillsToLearn([], 8), []);
});

test("a skill you haven't saved still counts, by name, across jobs", () => {
  const aws = { key: "x", skill_id: null, skill_name: "AWS", study_links: [{ mode: "theory_interview", query: "AWS interview questions", url: "u" }] };
  const ranked = rankSkillsToLearn(
    [
      { status: "saved", gaps: [aws, gap(...PYTHON)] },
      { status: "saved", gaps: [{ ...aws, skill_name: "aws" }] },
    ],
    8,
  );

  assert.deepEqual(names(ranked), ["AWS", "Python"]); // AWS: needed by 2 jobs
  assert.equal(ranked[0].skillId, null);
  assert.equal(ranked[0].jobs, 2);
  assert.equal(ranked[0].studyLinks.length, 1);
});
