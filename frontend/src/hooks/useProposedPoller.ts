'use client';

import { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import type { Experiment } from '@/lib/types';

const POLL_INTERVAL_MS = 3000;
const MAX_POLLS = 10; // 30 seconds max

export type ProposedPollState = 'idle' | 'polling' | 'found' | 'timeout';

interface ProposedPollerResult {
  proposed: Experiment[];
  pollState: ProposedPollState;
  startPolling: () => void;
  reset: () => void;
}

/**
 * Polls /api/client/experiments/proposed until at least one result appears
 * or MAX_POLLS is reached. Call startPolling() after completing/abandoning
 * an experiment to kick it off.
 */
export function useProposedPoller(): ProposedPollerResult {
  const [proposed, setProposed] = useState<Experiment[]>([]);
  const [pollState, setPollState] = useState<ProposedPollState>('idle');
  const [triggerKey, setTriggerKey] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (triggerKey === null) return;

    let count = 0;
    let cancelled = false;

    const poll = async () => {
      if (cancelled) return;
      count++;

      try {
        const results = await api.getProposedExperiments();
        if (cancelled) return;

        if (results.length > 0) {
          setProposed(results);
          setPollState('found');
          return;
        }

        if (count >= MAX_POLLS) {
          setPollState('timeout');
          return;
        }

        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      } catch {
        if (cancelled) return;
        setPollState('timeout');
      }
    };

    setPollState('polling');
    setProposed([]);
    poll();

    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [triggerKey]);

  const startPolling = () => setTriggerKey((k) => (k === null ? 0 : k + 1));

  const reset = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setPollState('idle');
    setProposed([]);
    setTriggerKey(null);
  };

  return { proposed, pollState, startPolling, reset };
}
