export default function StatCard({ label, value, tone = "ink", sub }) {
  const toneClass = {
    ink: "text-ink",
    signal: "text-signal",
    success: "text-success",
    warning: "text-warning",
    danger: "text-danger",
  }[tone];

  return (
    <div className="rounded-lg border border-hairline bg-surface p-4">
      <div className="text-xs uppercase tracking-wide text-muted font-mono">{label}</div>
      <div className={`mt-2 font-display text-3xl font-semibold ${toneClass}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  );
}
