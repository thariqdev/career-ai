import Link from "next/link";
import { MODE_LABEL } from "@/lib/learning";
import type { SkillLearningResources } from "@/lib/types";

/** One skill's YouTube search buttons (one per mode) plus a link to its page. */
export default function LearnLinks({ learning }: { learning: SkillLearningResources }) {
  const savedCount = learning.modes.reduce((sum, mode) => sum + mode.resources.length, 0);

  return (
    <span className="flex flex-wrap items-center gap-2">
      {learning.modes.map((mode) => (
        <a
          key={mode.mode}
          href={mode.search_url}
          target="_blank"
          rel="noopener noreferrer"
          title={`Search YouTube: ${mode.search_query}`}
          className="rounded border border-line px-2 py-0.5 text-xs text-accent hover:bg-accent-soft"
        >
          {MODE_LABEL[mode.mode]}
        </a>
      ))}
      <Link href={`/skills/${learning.skill_id}`} className="text-xs text-ink-soft underline">
        {savedCount > 0 ? `Skill page (${savedCount} saved)` : "Skill page"}
      </Link>
    </span>
  );
}
