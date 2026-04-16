// lib/auth.ts — OAuth redirect helpers

export function getGoogleLoginUrl(returnTo?: string, inviteToken?: string): string {
  const params = new URLSearchParams();
  if (returnTo) params.set('return_to', returnTo);
  if (inviteToken) params.set('invite_token', inviteToken);
  return `/api/auth/login?${params.toString()}`;
}

export function getMicrosoftLoginUrl(returnTo?: string, inviteToken?: string): string {
  const params = new URLSearchParams();
  if (returnTo) params.set('return_to', returnTo);
  if (inviteToken) params.set('invite_token', inviteToken);
  return `/api/auth/login/microsoft?${params.toString()}`;
}

export function redirectToLogin(returnTo?: string): void {
  window.location.href = getGoogleLoginUrl(returnTo ?? window.location.pathname);
}
