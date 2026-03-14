'use client';

import { useState } from 'react';
import { hasDismissedTip, dismissTip } from '@/lib/onboarding';
import { STRINGS } from '@/config/strings';

interface OnboardingTipProps {
  tipId: string;
  message: string;
}

/**
 * OnboardingTip — contextual coaching nudge that persists until dismissed.
 *
 * Design:
 *   - Amber accent (cv-amber) to distinguish from teal primary actions
 *   - Subtle warm-100 bg with amber-300 border — feels informational, not alarming
 *   - Lightbulb icon instead of generic info-circle
 */
export function OnboardingTip({ tipId, message }: OnboardingTipProps) {
  const [visible, setVisible] = useState(() => !hasDismissedTip(tipId));

  if (!visible) return null;

  function handleDismiss() {
    dismissTip(tipId);
    setVisible(false);
  }

  return (
    <div className="mb-4 flex items-start gap-3 bg-cv-amber-50 border border-cv-amber-200 rounded px-4 py-3">

      {/* Lightbulb icon */}
      <svg
        viewBox="0 0 20 20"
        fill="currentColor"
        className="w-4 h-4 text-cv-amber-500 mt-0.5 shrink-0"
        aria-hidden="true"
      >
        <path d="M10 2a6 6 0 00-3.819 10.602A2 2 0 006 14v1a2 2 0 002 2h4a2 2 0 002-2v-1a2 2 0 00-.181-1.398A6 6 0 0010 2zm0 2a4 4 0 012.573 7.1A2 2 0 0011 12.874V13H9v-.126A2 2 0 007.427 11.1 4 4 0 0110 4zm-1 10h2v1H9v-1z" />
      </svg>

      <p className="flex-1 text-sm text-cv-stone-700 leading-relaxed">{message}</p>

      {/* Dismiss */}
      <button
        onClick={handleDismiss}
        className="text-cv-amber-400 hover:text-cv-stone-500 transition-colors shrink-0 mt-0.5"
        aria-label={STRINGS.onboarding.tipDismissLabel}
      >
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5" aria-hidden="true">
          <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
        </svg>
      </button>
    </div>
  );
}
