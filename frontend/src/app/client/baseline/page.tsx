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
      <div className="animate-spin rounded-full h-6 w-6 border-2 border-cv-teal-400 border-t-transparent" />
    </div>
  );
}
