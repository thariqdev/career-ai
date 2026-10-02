import Link from "next/link";
import { Card, SectionHeading } from "@/components/ui";
import type { LearningPath } from "@/lib/types";

const MARK = { done: "✓", current: "→", todo: "" } as const;

const MARK_CLASSES = {
  done: "border-verified bg-verified text-surface",
  current: "border-accent bg-accent-soft text-accent",
  todo: "border-line bg-surface text-ink-soft",
} as const;

/**
 * The four-step path for one skill. Which steps are done, and which one is current,
 * is decided by the backend (learning_path_service) from facts the user recorded;
 * this only displays it. Studying never ticks "Prove it" or "Verified".
 */
export default function LearningPathChecklist({ path }: { path: LearningPath }) {
  return (
    <Card>
      <SectionHeading
        title="Your path"
        hint={path.next_step ? `Next step: ${path.next_step}.` : "All steps done. Nice work."}
      />
      <ol className="mt-4 flex flex-col gap-2">
        {path.steps.map((step, index) => (
          <li
            key={step.key}
            className={`flex gap-3 rounded-md p-2 text-sm ${
              step.state === "current" ? "bg-accent-soft/60 ring-1 ring-accent-soft" : ""
            }`}
          >
            <span
              aria-label={step.state}
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border font-mono text-xs ${MARK_CLASSES[step.state]}`}
            >
              {MARK[step.state] || index + 1}
            </span>
            <div className="pt-0.5">
              <p
                className={
                  step.state === "todo"
                    ? "text-ink-soft"
                    : step.state === "done"
                      ? "text-ink-soft line-through decoration-line"
                      : "font-medium text-ink"
                }
              >
                {step.title}
              </p>
              {step.state !== "done" && (
                <>
                  <p className="mt-0.5 text-ink-soft">{step.detail}</p>
                  {(step.links.length > 0 || step.key === "prove") && (
                    <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                      {step.links.map((link) => (
                        <a
                          key={link.url}
                          href={link.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent underline"
                        >
                          {link.label}
                        </a>
                      ))}
                      {step.key === "prove" && (
                        <>
                          <Link href="/profile" className="text-accent underline">
                            Add the project on My Profile
                          </Link>
                          <span className="text-ink-soft">then link it as evidence below</span>
                        </>
                      )}
                    </p>
                  )}
                </>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
