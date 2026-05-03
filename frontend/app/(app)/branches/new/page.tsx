import { BranchForm } from "@/components/branches/BranchForm";
import Link from "next/link";

export default function NewBranchPage() {
  return (
    <div className="space-y-4 max-w-5xl">
      <div>
        <Link href="/branches" className="text-xs text-muted hover:text-accent">← Branches</Link>
        <h1 className="text-lg font-semibold mt-1">Add branch</h1>
        <p className="text-xs text-muted">After saving you can run Test Connection / Discover Sites against it.</p>
      </div>
      <BranchForm mode={{ kind: "create" }} />
    </div>
  );
}
