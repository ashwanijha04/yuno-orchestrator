export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-sm text-[var(--color-muted-foreground)]">
          Create agents, wire them into workflows, and watch runs execute live.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {[
          { label: "Agents", value: "—" },
          { label: "Workflows", value: "—" },
          { label: "Runs today", value: "—" },
        ].map((card) => (
          <div
            key={card.label}
            className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-5"
          >
            <p className="text-sm text-[var(--color-muted-foreground)]">
              {card.label}
            </p>
            <p className="mt-2 font-mono text-2xl">{card.value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-[var(--radius)] border border-[var(--color-border)] bg-[var(--color-card)] p-5">
        <p className="text-sm text-[var(--color-muted-foreground)]">
          Phase 0 scaffold. Data model, runtime, and the live timeline land in
          the next phases.
        </p>
      </div>
    </div>
  );
}
