import type { Variable } from "./types";

/** The same stand-in the backend shows, so a saved secret re-hides identically. */
export function maskValue(value: string): string {
  if (!value) return "";
  if (value.length <= 8) return "•".repeat(value.length);
  return `${value.slice(0, 3)}${"•".repeat(8)}${value.slice(-2)}`;
}

/**
 * Writes come back with the value in full, because you just typed it. Put a
 * secret back behind its mask before it goes into the list everyone can see.
 */
export function rehide(variable: Variable): Variable {
  if (!variable.is_secret) return variable;
  return { ...variable, value: maskValue(variable.value), revealed: false };
}

export function asDotenvLine(key: string, value: string): string {
  return value === "" || /[\s#"']/.test(value) ? `${key}="${value}"` : `${key}=${value}`;
}

/** A replacement value, for rotating a credential envless itself can mint. */
export function generateSecret(bytes = 32): string {
  const raw = new Uint8Array(bytes);
  crypto.getRandomValues(raw);
  return btoa(String.fromCharCode(...raw))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}
