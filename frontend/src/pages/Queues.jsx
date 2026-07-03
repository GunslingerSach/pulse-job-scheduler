import { useEffect, useState } from "react";
import { Plus, Pause, Play, ChevronRight } from "lucide-react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";

export default function Queues() {
  const { project } = useAuth();
  const [queues, setQueues] = useState([]);
  const [statsByQueue, setStatsByQueue] = useState({});
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", priority: 0, max_concurrency: 5, strategy: "exponential", max_retries: 3, base_delay_seconds: 5 });

  const load = async () => {
    if (!project) return;
    const qs = await api.listQueues(project.id);
    setQueues(qs);
    const entries = await Promise.all(qs.map(async (q) => [q.id, await api.queueStats(project.id, q.id)]));
    setStatsByQueue(Object.fromEntries(entries));
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  const createQueue = async (e) => {
    e.preventDefault();
    await api.createQueue(project.id, {
      name: form.name,
      priority: Number(form.priority),
      max_concurrency: Number(form.max_concurrency),
      retry_policy: {
        name: `${form.name}-policy`,
        strategy: form.strategy,
        max_retries: Number(form.max_retries),
        base_delay_seconds: Number(form.base_delay_seconds),
        max_delay_seconds: 3600,
        multiplier: 2.0,
      },
    });
    setShowForm(false);
    setForm({ name: "", priority: 0, max_concurrency: 5, strategy: "exponential", max_retries: 3, base_delay_seconds: 5 });
    load();
  };

  const togglePause = async (queue) => {
    if (queue.is_paused) await api.resumeQueue(project.id, queue.id);
    else await api.pauseQueue(project.id, queue.id);
    load();
  };

  return (
    <div className="space-y-6 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold">Queues</h1>
          <p className="text-sm text-muted mt-1">Configure concurrency, priority, and retry behavior per queue</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-2 rounded-md bg-signal px-3 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          <Plus size={15} /> New queue
        </button>
      </div>

      {showForm && (
        <form onSubmit={createQueue} className="rounded-lg border border-hairline bg-surface p-5 grid grid-cols-2 gap-3 animate-in">
          <TextField label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
          <TextField label="Priority" type="number" value={form.priority} onChange={(v) => setForm({ ...form, priority: v })} />
          <TextField label="Max concurrency" type="number" value={form.max_concurrency} onChange={(v) => setForm({ ...form, max_concurrency: v })} />
          <SelectField label="Retry strategy" value={form.strategy} onChange={(v) => setForm({ ...form, strategy: v })}
            options={["fixed", "linear", "exponential", "none"]} />
          <TextField label="Max retries" type="number" value={form.max_retries} onChange={(v) => setForm({ ...form, max_retries: v })} />
          <TextField label="Base delay (s)" type="number" value={form.base_delay_seconds} onChange={(v) => setForm({ ...form, base_delay_seconds: v })} />
          <div className="col-span-2 flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setShowForm(false)} className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink">
              Cancel
            </button>
            <button type="submit" className="rounded-md bg-signal px-4 py-2 text-sm font-medium text-white hover:opacity-90">
              Create
            </button>
          </div>
        </form>
      )}

      <div className="space-y-3">
        {queues.map((q) => {
          const s = statsByQueue[q.id];
          return (
            <div key={q.id} className="rounded-lg border border-hairline bg-surface p-4 flex items-center gap-6">
              <div className="w-40 shrink-0">
                <div className="font-medium">{q.name}</div>
                <div className="text-xs text-muted font-mono mt-0.5">
                  priority {q.priority} · conc {q.max_concurrency}
                </div>
              </div>

              {s && (
                <div className="flex flex-1 gap-6 text-sm">
                  <Mini label="queued" value={s.queued} />
                  <Mini label="running" value={s.running} tone="signal" />
                  <Mini label="completed" value={s.completed} tone="success" />
                  <Mini label="failed" value={s.failed} tone="warning" />
                  <Mini label="dead letter" value={s.dead_letter} tone="danger" />
                  <Mini label="avg dur" value={s.avg_duration_ms ? `${Math.round(s.avg_duration_ms)}ms` : "—"} />
                </div>
              )}

              <button
                onClick={() => togglePause(q)}
                className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium ${
                  q.is_paused ? "border-success/30 text-success hover:bg-success/10" : "border-warning/30 text-warning hover:bg-warning/10"
                }`}
              >
                {q.is_paused ? <Play size={12} /> : <Pause size={12} />}
                {q.is_paused ? "Resume" : "Pause"}
              </button>
              <ChevronRight size={16} className="text-muted" />
            </div>
          );
        })}
        {queues.length === 0 && <div className="text-sm text-muted">No queues yet — create one to get started.</div>}
      </div>
    </div>
  );
}

function Mini({ label, value, tone = "ink" }) {
  const toneClass = { ink: "text-ink", signal: "text-signal", success: "text-success", warning: "text-warning", danger: "text-danger" }[tone];
  return (
    <div>
      <div className={`font-mono font-semibold ${toneClass}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
    </div>
  );
}

function TextField({ label, type = "text", value, onChange }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted">{label}</span>
      <input
        required
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-hairline bg-void px-3 py-2 text-sm outline-none focus:border-signal"
      />
    </label>
  );
}

function SelectField({ label, value, onChange, options }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-hairline bg-void px-3 py-2 text-sm outline-none focus:border-signal capitalize"
      >
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </label>
  );
}
