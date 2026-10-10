"use client";

import { useEffect, useState, type FormEvent } from "react";
import { apiGet, apiPatch, ApiError } from "@/lib/api";
import { Button, Card, FieldError, SectionHeading, inputClasses, invalidClasses } from "@/components/ui";
import type { User } from "@/lib/types";

const MAX_NAME_CHARS = 100;

/**
 * Your name (PATCH /me). Adding your CV fills it in from the top of the CV when it's
 * empty; here you can check or change it. The assistant uses it for "what is my name?".
 */
export default function YourName({ reloadKey }: { reloadKey: number }) {
  const [saved, setSaved] = useState<string | null | undefined>(undefined); // undefined = loading
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiGet<User>("/me")
      .then((user) => {
        if (!active) return;
        setSaved(user.full_name);
        setValue(user.full_name ?? "");
      })
      .catch(() => {
        if (active) setSaved(null);
      });
    return () => {
      active = false;
    };
  }, [reloadKey]);

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    const name = value.trim();
    if (name.length > MAX_NAME_CHARS) {
      setFieldError(`Keep it under ${MAX_NAME_CHARS} characters.`);
      return;
    }
    setBusy(true);
    try {
      const user = await apiPatch<User>("/me", { full_name: name });
      setSaved(user.full_name);
      setValue(user.full_name ?? "");
      setMessage(user.full_name ? "✓ Saved." : "✓ Name cleared.");
    } catch (error) {
      setFieldError(error instanceof ApiError ? error.message : "Could not reach the backend.");
    } finally {
      setBusy(false);
    }
  }

  const unchanged = value.trim() === (saved ?? "");

  return (
    <Card>
      <SectionHeading title="Your name" hint="Read from the top of your CV when you add it. Check it or change it here." />
      <form onSubmit={handleSave} noValidate className="mt-3 flex flex-col gap-1">
        <div className="flex flex-wrap items-start gap-2">
          <input
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
              setFieldError(null);
              setMessage(null);
            }}
            aria-label="Your name"
            aria-invalid={fieldError !== null}
            placeholder={saved === undefined ? "Loading…" : "e.g. Jane Doe"}
            disabled={saved === undefined}
            className={`${inputClasses} min-w-0 flex-1 ${fieldError ? invalidClasses : ""}`}
          />
          <Button type="submit" variant="primary" disabled={busy || saved === undefined || unchanged}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
        <FieldError message={fieldError} />
        {message && <p className="text-sm text-verified">{message}</p>}
      </form>
    </Card>
  );
}
