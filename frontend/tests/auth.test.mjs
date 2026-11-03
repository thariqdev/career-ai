// Checks for the account-page rules (lib/auth.ts, stage 99).

import assert from "node:assert/strict";
import { test } from "node:test";

import { emailProblem, isAuthPage, loginUrl, passwordProblem, safeNext } from "../lib/auth.ts";

test("only the account pages are open without logging in", () => {
  for (const page of ["/login", "/signup", "/forgot-password", "/reset-password"]) assert.equal(isAuthPage(page), true);
  for (const page of ["/", "/skills", "/account", "/login-help", "/job-descriptions/3"]) assert.equal(isAuthPage(page), false);
});

test("after logging in you only ever go to a page of this site", () => {
  assert.equal(safeNext("/skills/3?tab=proof"), "/skills/3?tab=proof");
  assert.equal(safeNext(null), "/");
  assert.equal(safeNext("https://evil.example.com"), "/");
  assert.equal(safeNext("//evil.example.com"), "/");
  assert.equal(safeNext("/\\evil.example.com"), "/");
  assert.equal(safeNext("/login?next=/x"), "/"); // never back to an account page
});

test("the login link remembers where you were going", () => {
  assert.equal(loginUrl("/job-descriptions/4"), "/login?next=%2Fjob-descriptions%2F4");
  assert.equal(loginUrl("/"), "/login");
  assert.equal(loginUrl("/signup"), "/login");
});

test("password and email checks match the backend's rules", () => {
  assert.equal(passwordProblem("short"), "Use at least 8 characters.");
  assert.equal(passwordProblem("long enough"), null);
  assert.equal(passwordProblem("x".repeat(129)), "Use at most 128 characters.");
  assert.equal(emailProblem("  "), "Email is required.");
  assert.equal(emailProblem("not-an-email"), "Please enter a valid email address.");
  assert.equal(emailProblem(" thariq@example.com "), null);
});
