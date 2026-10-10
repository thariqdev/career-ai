// Checks for the plain-language checks run before a CV draft is saved (lib/draftValidation.ts).

import assert from "node:assert/strict";
import { test } from "node:test";

import { validateEntry } from "../lib/draftValidation.ts";

const EDUCATION = [
  { key: "institution", label: "School", type: "text", required: true },
  { key: "degree", label: "Degree", type: "text" },
  { key: "start_date", label: "Start", type: "date" },
  { key: "end_date", label: "End", type: "date" },
];
const WORK = [
  { key: "role", label: "Role", type: "text", required: true },
  { key: "company", label: "Company", type: "text", required: true },
  { key: "start_date", label: "Start", type: "date", required: true },
  { key: "end_date", label: "End (empty = current)", type: "date" },
];
const PROJECT = [
  { key: "name", label: "Name", type: "text", required: true },
  { key: "url", label: "Link", type: "text" },
];

test("an empty required box gets a plain message (the user's BCA entry)", () => {
  const errors = validateEntry(
    { institution: "  ", degree: "Bachelor of Computer Applications (BCA)", start_date: "2020-06-01", end_date: "2023-03-01" },
    EDUCATION,
  );

  assert.deepEqual(errors, { institution: "School is required." });
});

test("a complete entry has no problems", () => {
  const errors = validateEntry(
    { role: "Intern", company: "Acme", start_date: "2024-01-01", end_date: "" },
    WORK,
  );

  assert.deepEqual(errors, {});
});

test("every missing required box is reported, with labels cleaned of hints", () => {
  const errors = validateEntry({ role: "", company: "", start_date: "", end_date: "" }, WORK);

  assert.deepEqual(errors, {
    role: "Role is required.",
    company: "Company is required.",
    start_date: "Start is required.",
  });
});

test("an end date before the start date is caught", () => {
  const errors = validateEntry(
    { role: "Intern", company: "Acme", start_date: "2024-05-01", end_date: "2024-01-01" },
    WORK,
  );

  assert.deepEqual(errors, { end_date: "End can't be before Start." });
});

test("a link must be a web address", () => {
  assert.deepEqual(validateEntry({ name: "App", url: "github.com/me/app" }, PROJECT), {
    url: "Link must start with http:// or https://.",
  });
  assert.deepEqual(validateEntry({ name: "App", url: "https://github.com/me/app" }, PROJECT), {});
  assert.deepEqual(validateEntry({ name: "App", url: "" }, PROJECT), {});
});
