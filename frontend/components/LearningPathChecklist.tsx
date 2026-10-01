import Link from "next/link";
import type { LearningPath } from "@/lib/types";

const MARK = { done: "✓", current: "→", todo: "○" } as const;

/**
 * The four-step path for one skill. Which steps are done, and which one is current,
 * is decided by the backend (learning_path_service) from facts the user recorded;
 * this only displays it. Studying never ticks "Prove it" or "Verified".
 */
export default function LearningPathChecklist({ path }: { path: LearningPath }) {
  return (
    <section className="mt-6 rounded border border-line p-4">
      <h2 className="font-display text-lg text-ink">Your path</h2>
      <p className="mt-1 text-sm text-ink-soft">
        {path.next_step ? `Next step: ${path.next_step}.` : "All steps done. Nice work."}
      </p>
      <ol className="mt-3 flex flex-col gap-3">
        {path.steps.map((step) => (
          <li
            key={step.key}
            className={`flex gap-3 text-sm ${step.state === "current" ? "rounded bg-accent-soft p-2" : ""}`}
          >
            <span
              aria-label={step.state}
              className={`font-mono ${
                step.state === "done"
                  ? "text-verified"
                  : step.state === "current"
                    ? "text-accent"
                    : "text-ink-soft"
              }`}
            >
              {MARK[step.state]}
            </span>
            <div>
              <p className={step.state === "todo" ? "text-ink-soft" : "text-ink"}>{step.title}</p>
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
    </section>
  );
}
