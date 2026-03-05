'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

export default function BaselineIndexPage() {
  const router = useRouter();

  useEffect(() => {
    api.clientSummary().then((summary) => {
      const bpStatus = summary?.baseline_pack_status ?? 'none';
      const bpId = summary?.baseline_pack_id ?? null;

      if (bpStatus === 'none' || !bpId) {
        router.replace('/client/baseline/new');
      } else {
        router.replace(`/client/baseline/${bpId}`);
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
