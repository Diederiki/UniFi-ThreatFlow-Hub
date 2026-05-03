"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { BranchForm } from "@/components/branches/BranchForm";
import { branchesApi, type Branch } from "@/lib/branches";

export default function BranchEditPage() {
  const params = useParams<{ id: string }>();
  const [branch, setBranch] = useState<Branch | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    branchesApi.get(params.id)
      .then((b) => { if (!cancelled) setBranch(b); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : "Load failed"); });
    return () => { cancelled = true; };
  }, [params.id]);

  if (error) return (
    <div className="space-y-3">
      <Link href={`/branches/${params.id}`} className="text-xs text-muted hover:text-accent">← back</Link>
      <div className="panel p-4 text-sm text-danger border-danger/30">{error}</div>
    </div>
  );
  if (!branch) return <div className="text-muted text-sm">Loading…</div>;

  return (
    <div className="space-y-4 max-w-5xl">
      <div>
        <Link href={`/branches/${branch.id}`} className="text-xs text-muted hover:text-accent">← {branch.name}</Link>
        <h1 className="text-lg font-semibold mt-1">Edit branch</h1>
      </div>
      <BranchForm mode={{ kind: "edit", branch }} />
    </div>
  );
}
