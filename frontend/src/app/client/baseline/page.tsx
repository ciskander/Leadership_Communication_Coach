'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

export default function BaselineIndexPage() {
  const router = useRouter();

  useEffect(() => {
    api.clientSummary().then((summary) => {
      const bpStatus = summary?.baseline_pack_status ?? 'none';
      if (bpStatus === 'none') {
        router.replace('/client/baseline/new');
      } else {
        // There's an active baseline pack — but we don't have its ID from the
        // summary endpoint yet. For now, send to /new which will show existing
        // transcripts for selection. We can improve this once the summary
        // endpoint returns the baseline_pack_id.
        router.replace('/client/baseline/new');
      }
    }).catch(() => {
      router.replace('/client/baseline/new');
    });
  }, [router]);

  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600" />
    </div>
  );
}
