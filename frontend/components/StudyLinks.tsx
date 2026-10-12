import type { StudyLink } from "@/lib/types";

const LABEL: Record<string, string> = { theory_interview: "Theory / Interview", technical_practical: "Technical / Practical" };

/** YouTube search links for a skill you haven't saved yet (no saved links to show). */
export default function StudyLinks({ links }: { links: StudyLink[] }) {
  if (links.length === 0) return null;
  return (
    <span className="flex flex-wrap items-center gap-2">
      {links.map((link) => (
        <a
          key={link.mode}
          href={link.url}
          target="_blank"
          rel="noopener noreferrer"
          title={`Search YouTube: ${link.query}`}
          className="rounded border border-line px-2 py-0.5 text-xs text-accent hover:bg-accent-soft"
        >
          {LABEL[link.mode] ?? link.mode} ↗
        </a>
      ))}
    </span>
  );
}
