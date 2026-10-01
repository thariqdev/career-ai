// For user-typed URLs the backend doesn't validate (a job's source_url, evidence url):
// only render them as <a href> when they're real http(s) links, so a value like
// "javascript:..." is shown as plain text and can never run.
export function isWebLink(url: string): boolean {
  return /^https?:\/\//i.test(url.trim());
}
