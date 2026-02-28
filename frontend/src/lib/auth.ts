// lib/auth.ts — OAuth redirect helpers

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function getGoogleLoginUrl(returnTo?: string): string {
  const params = new URLSearchParams();
  if (returnTo) params.set('return_to', returnTo);
  return `${BASE_URL}/api/auth/login?${params.toString()}`;
}

export function redirectToLogin(returnTo?: string): void {
  window.location.href = getGoogleLoginUrl(returnTo ?? window.location.pathname);
}