const STYLES = {
  queued: "text-muted bg-white/5 border-hairline",
  scheduled: "text-recurring border-recurring/30 bg-recurring/10",
  claimed: "text-signal border-signal/30 bg-signal/10",
  running: "text-signal border-signal/30 bg-signal/10",
  completed: "text-success border-success/30 bg-success/10",
  failed: "text-warning border-warning/30 bg-warning/10",
  retrying: "text-warning border-warning/30 bg-warning/10",
  dead_letter: "text-danger border-danger/30 bg-danger/10",
  cancelled: "text-muted border-hairline bg-white/5",
  paused: "text-muted border-hairline bg-white/5",
  active: "text-success border-success/30 bg-success/10",
  idle: "text-muted border-hairline bg-white/5",
  draining: "text-warning border-warning/30 bg-warning/10",
  offline: "text-danger border-danger/30 bg-danger/10",
};

export default function StatusBadge({ status }) {
  const style = STYLES[status] || STYLES.queued;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-mono uppercase tracking-wide ${style}`}
    >
      {status?.replace("_", " ")}
    </span>
  );
}
