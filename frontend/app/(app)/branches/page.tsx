export default function BranchesPage() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Branches</h1>
        <button className="btn btn-primary opacity-50 cursor-not-allowed" disabled>+ Add branch</button>
      </div>
      <div className="panel p-6 text-sm text-muted">
        Phase 2 will land branch CRUD, credential encryption, and the Test-Connection / Discover-Sites flow.
      </div>
    </div>
  );
}
