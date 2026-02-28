'use client';

import { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import type { RunStatus } from '@/lib/types';

const POLL_INTERVAL_MS = 3000;
const MAX_POLLS = 60;

export type PollState = 'polling' | 'complete' | 'error' | 'timeout';

interface RunPollerResult {
  run: RunStatus | null;
  pollState: PollState;
  pollCount: number;
  retry: () => void;
}

export function useRunPoller(runId: string | null): RunPollerResult {
  const [run, setRun] = useState<RunStatus | null>(null);
  const [pollState, setPollState] = useState<PollState>('polling');
  const [pollCount, setPollCount] = useState(0);
  const [retryKey, setRetryKey] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!runId) return;

    let count = 0;
    let cancelled = false;

    const poll = async () => {
      if (cancelled) return;
      count++;
      setPollCount(count);

      try {
        const result = await api.getRun(runId);
        if (cancelled) return;

        setRun(result);

        if (result.status === 'complete' || result.status === 'error') {
          setPollState(result.status === 'complete' ? 'complete' : 'error');
          return;
        }

        if (count >= MAX_POLLS) {
          setPollState('timeout');
          return;
        }

        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      } catch {
        if (cancelled) return;
        setPollState('error');
      }
    };

    setPollState('polling');
    setPollCount(0);
    setRun(null);
    poll();

    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [runId, retryKey]);

  const retry = () => setRetryKey((k) => k + 1);

  return { run, pollState, pollCount, retry };
}
