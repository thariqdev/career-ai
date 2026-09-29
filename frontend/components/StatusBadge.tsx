/**
 * The knowledge-status badge, shared by every page that shows a verification
 * status (originally written once inline on the Skills page, now used there
 * and on the Job Descriptions page too). `status` is one of the four real
 * VerificationStatus values, or null for "no claim at all" — not one of the
 * four real statuses, so it deliberately doesn't reuse any of their colors.
 */
function classesFor(status: string | null): string {
  switch (status) {
    case "verified":
      return "bg-verified-bg text-verified";
    case "partial":
      return "bg-partial-bg text-partial";
    case "provisional":
      return "bg-provisional-bg text-provisional";
    case "not_verified":
      return "bg-not-verified-bg text-not-verified";
    default:
      return "bg-line text-ink-soft";
  }
}

function labelFor(status: string | null): string {
  return status === null ? "no claim" : status.replace("_", " ");
}

export default function StatusBadge({ status }: { status: string | null }) {
  return (
    <span className={`rounded px-2 py-0.5 font-mono text-xs ${classesFor(status)}`}>
      {labelFor(status)}
    </span>
  );
}
