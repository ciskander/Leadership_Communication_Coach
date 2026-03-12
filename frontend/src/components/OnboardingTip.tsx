'use client';

import { useState } from 'react';
import { hasDismissedTip, dismissTip } from '@/lib/onboarding';
import { STRINGS } from '@/config/strings';

interface OnboardingTipProps {
  tipId: string;
  message: string;
}

export function OnboardingTip({ tipId, message }: OnboardingTipProps) {
  const [visible, setVisible] = useState(() => !hasDismissedTip(tipId));

  if (!visible) return null;

  function handleDismiss() {
    dismissTip(tipId);
    setVisible(false);
  }

  return (
    <div className="mb-4 flex items-start gap-3 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
      {/* Info icon */}
      <svg
        className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0"
        viewBox="0 0 20 20"
        fill="currentColor"
      >
        <path
          fillRule="evenodd"
          d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
          clipRule="evenodd"
        />
      </svg>

      <p className="flex-1 text-sm text-emerald-800 leading-relaxed">{message}</p>

      {/* Dismiss button */}
      <button
        onClick={handleDismiss}
        className="text-emerald-400 hover:text-emerald-600 transition-colors flex-shrink-0"
        aria-label={STRINGS.onboarding.tipDismissLabel}
      >
        <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
          <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
        </svg>
      </button>
    </div>
  );
}
