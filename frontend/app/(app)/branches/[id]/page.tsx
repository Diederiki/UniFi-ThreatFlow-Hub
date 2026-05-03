"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { BranchForm } from "@/components/branches/BranchForm";
import { branchesApi, type Branch } from "@/lib/branches";

export default function BranchDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [branch, setBranch] = useState<Branch | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    branchesApi.get(id)
      .then((b) => { if (!cancelled) setBranch(b); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : "Load failed"); });
    return () => { cancelled = true; };
  }, [id]);

  if (error) {
    return (
      <div className="space-y-3">
        <Link href="/branches" className="text-xs text-muted hover:text-accent">← Branches</Link>
        <div className="panel p-4 text-sm text-danger border-danger/30">{error}</div>
      </div>
    );
  }

  if (!branch) {
    return <div className="text-muted text-sm">Loading branch…</div>;
  }

  return (
    <div className="space-y-4 max-w-5xl">
      <div>
        <Link href="/branches" className="text-xs text-muted hover:text-accent">← Branches</Link>
        <h1 className="text-lg font-semibold mt-1">{branch.name}</h1>
        <p className="text-xs text-muted num">{branch.branch_code} · created {new Date(branch.created_at).toLocaleString()}</p>
      </div>
      <BranchForm mode={{ kind: "edit", branch }} />
    </div>
  );
}
