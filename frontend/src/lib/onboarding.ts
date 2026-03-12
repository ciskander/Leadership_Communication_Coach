/**
 * Onboarding state management.
 *
 * All onboarding UI reads/writes go through these helpers so the storage
 * backend can be swapped (e.g. to an API) without touching any component code.
 *
 * Currently backed by localStorage. Every access is wrapped in try/catch so
 * the app degrades gracefully when storage is unavailable (private browsing,
 * restrictive IT policies, etc.) — the user simply sees the onboarding again.
 */

const PREFIX = 'cv_onboarding_';
const WELCOME_KEY = `${PREFIX}welcome_seen`;
const TIP_KEY = (id: string) => `${PREFIX}tip_${id}`;

// ── Helpers ────────────────────────────────────────────────────────────────

function getFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

function setFlag(key: string): void {
  try {
    localStorage.setItem(key, '1');
  } catch {
    // Storage unavailable — silently ignore.
  }
}

// ── Public API ─────────────────────────────────────────────────────────────

export function hasSeenWelcome(): boolean {
  return getFlag(WELCOME_KEY);
}

export function dismissWelcome(): void {
  setFlag(WELCOME_KEY);
}

export function hasDismissedTip(tipId: string): boolean {
  return getFlag(TIP_KEY(tipId));
}

export function dismissTip(tipId: string): void {
  setFlag(TIP_KEY(tipId));
}

/** Clear all onboarding flags so the user can replay the walkthrough. */
export function resetOnboarding(): void {
  try {
    const keysToRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith(PREFIX)) keysToRemove.push(key);
    }
    keysToRemove.forEach((k) => localStorage.removeItem(k));
  } catch {
    // Storage unavailable — nothing to clear.
  }
}
