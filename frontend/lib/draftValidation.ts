/**
 * Plain-language checks for a profile entry before it's sent, so the user sees "School
 * is required." next to the right box instead of a server error. The backend still
 * enforces the same rules (profile_service); this only explains them up front.
 * No runtime imports, so tests/draftValidation.test.mjs can load this file with Node.
 */

export type FieldRule = {
  key: string;
  label: string;
  type: "text" | "date" | "textarea";
  required?: boolean;
};

/** Field key -> message, for every problem found. Empty means the entry can be saved. */
export function validateEntry(values: Record<string, string>, fields: FieldRule[]): Record<string, string> {
  const errors: Record<string, string> = {};
  const value = (key: string) => (values[key] ?? "").trim();

  for (const field of fields) {
    if (field.required && value(field.key) === "") {
      errors[field.key] = `${field.label.replace(/\s*\(.*\)$/, "")} is required.`;
    }
  }

  const start = value("start_date");
  const end = value("end_date");
  if (start !== "" && end !== "" && end < start && !errors.end_date) {
    errors.end_date = "End can't be before Start.";
  }

  const url = value("url");
  if (url !== "" && !/^https?:\/\/\S+$/i.test(url)) {
    errors.url = "Link must start with http:// or https://.";
  }
  return errors;
}
