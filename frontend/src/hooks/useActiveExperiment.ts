'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { ActiveExperiment } from '@/lib/types';

export function useActiveExperiment() {
  const [data, setData] = useState<ActiveExperiment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchExperiment = async () => {
    setLoading(true);
    try {
      const result = await api.getActiveExperiment();
      setData(result);
      setError(null);
    } catch {
      setError('Failed to load experiment');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExperiment();
  }, []);

  return { data, loading, error, refetch: fetchExperiment };
}
