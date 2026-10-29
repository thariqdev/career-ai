/**
 * Shown on every page of the public portfolio demo (stage 94), never locally.
 * NEXT_PUBLIC_DEMO_MODE is baked in at build time, so this is a plain server component.
 */
export default function DemoBanner() {
  if (process.env.NEXT_PUBLIC_DEMO_MODE !== "true") return null;
  return (
    <div className="bg-warm-soft px-4 py-2 text-center text-sm text-ink print:hidden">
      <strong className="font-semibold">Demo</strong> with made-up data, reset daily. Feel free to click
      around and change things. The Assistant uses free AI models, so when they&rsquo;re busy it answers
      with your notes instead.
    </div>
  );
}
