import { useEffect, useState } from "react";
import { Plus, X, RotateCcw, Ban } from "lucide-react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import StatusBadge from "../components/StatusBadge";

const STATUSES = ["queued", "scheduled", "claimed", "running", "completed", "failed", "retrying", "dead_letter", "cancelled"];
const TYPES = ["immediate", "delayed", "scheduled", "recurring", "batch"];

export default function JobExplorer() {
  const { project } = useAuth();
  const [queues, setQueues] = useState([]);
  const [queueId, setQueueId] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [pageData, setPageData] = useState({ items: [], total: 0, page_size: 25 });
  const [showForm, setShowForm] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [form, setForm] = useState({ name: "", type: "immediate", payload: "{}", run_at: "", cron_expression: "", priority: 0 });

  useEffect(() => {
    if (!project) return;
    api.listQueues(project.id).then((qs) => {
      setQueues(qs);
      if (qs.length && !queueId) setQueueId(qs[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  const load = async () => {
    if (!project || !queueId) return;
    const data = await api.listJobs(project.id, queueId, { status: status || undefined, page, page_size: 25 });
    setPageData(data);
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, queueId, status, page]);

  const createJob = async (e) => {
    e.preventDefault();
    let payload;
    try {
      payload = JSON.parse(form.payload || "{}");
    } catch {
      alert("Payload must be valid JSON");
      return;
    }
    const body = { name: form.name, type: form.type, payload, priority: Number(form.priority) };
    if (["delayed", "scheduled"].includes(form.type)) body.run_at = new Date(form.run_at).toISOString();
    if (form.type === "recurring") body.cron_expression = form.cron_expression;
    await api.createJob(project.id, queueId, body);
    setShowForm(false);
    setForm({ name: "", type: "immediate", payload: "{}", run_at: "", cron_expression: "", priority: 0 });
    setPage(1);
    load();
  };

  const openJob = async (job) => {
    const [executions, logs] = await Promise.all([
      api.jobExecutions(project.id, queueId, job.id),
      api.jobLogs(project.id, queueId, job.id),
    ]);
    setSelectedJob({ ...job, executions, logs });
  };

  const retry = async (job) => {
    await api.retryJob(project.id, queueId, job.id);
    setSelectedJob(null);
    load();
  };
  const cancel = async (job) => {
    await api.cancelJob(project.id, queueId, job.id);
    setSelectedJob(null);
    load();
  };

  const totalPages = Math.max(1, Math.ceil(pageData.total / pageData.page_size));

  return (
    <div className="space-y-6 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold">Job Explorer</h1>
          <p className="text-sm text-muted mt-1">Inspect, filter, retry, and cancel jobs</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          disabled={!queueId}
          className="flex items-center gap-2 rounded-md bg-signal px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-40"
        >
          <Plus size={15} /> New job
        </button>
      </div>

      <div className="flex gap-3">
        <select value={queueId} onChange={(e) => { setQueueId(e.target.value); setPage(1); }}
          className="rounded-md border border-hairline bg-surface px-3 py-2 text-sm outline-none focus:border-signal">
          {queues.map((q) => <option key={q.id} value={q.id}>{q.name}</option>)}
        </select>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          className="rounded-md border border-hairline bg-surface px-3 py-2 text-sm outline-none focus:border-signal">
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {showForm && (
        <form onSubmit={createJob} className="rounded-lg border border-hairline bg-surface p-5 grid grid-cols-2 gap-3 animate-in">
          <TextField label="Job name (handler)" value={form.name} onChange={(v) => setForm({ ...form, name: v })} placeholder="send_email" />
          <SelectField label="Type" value={form.type} onChange={(v) => setForm({ ...form, type: v })} options={TYPES} />
          {["delayed", "scheduled"].includes(form.type) && (
            <TextField label="Run at" type="datetime-local" value={form.run_at} onChange={(v) => setForm({ ...form, run_at: v })} />
          )}
          {form.type === "recurring" && (
            <TextField label="Cron expression" value={form.cron_expression} onChange={(v) => setForm({ ...form, cron_expression: v })} placeholder="*/5 * * * *" />
          )}
          <TextField label="Priority" type="number" value={form.priority} onChange={(v) => setForm({ ...form, priority: v })} />
          <label className="col-span-2 block">
            <span className="mb-1 block text-xs text-muted">Payload (JSON)</span>
            <textarea
              value={form.payload}
              onChange={(e) => setForm({ ...form, payload: e.target.value })}
              rows={3}
              className="w-full rounded-md border border-hairline bg-void px-3 py-2 font-mono text-xs outline-none focus:border-signal"
            />
          </label>
          <div className="col-span-2 flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setShowForm(false)} className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink">Cancel</button>
            <button type="submit" className="rounded-md bg-signal px-4 py-2 text-sm font-medium text-white hover:opacity-90">Create job</button>
          </div>
        </form>
      )}

      <div className="rounded-lg border border-hairline bg-surface overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hairline text-left text-xs uppercase tracking-wide text-muted">
              <th className="px-4 py-3 font-normal">Name</th>
              <th className="px-4 py-3 font-normal">Type</th>
              <th className="px-4 py-3 font-normal">Status</th>
              <th className="px-4 py-3 font-normal">Retries</th>
              <th className="px-4 py-3 font-normal">Created</th>
            </tr>
          </thead>
          <tbody>
            {pageData.items.map((job) => (
              <tr key={job.id} onClick={() => openJob(job)} className="border-b border-hairline last:border-0 hover:bg-white/5 cursor-pointer">
                <td className="px-4 py-3 font-mono text-xs">{job.name}</td>
                <td className="px-4 py-3 text-muted">{job.type}</td>
                <td className="px-4 py-3"><StatusBadge status={job.status} /></td>
                <td className="px-4 py-3 font-mono text-xs text-muted">{job.retry_count}/{job.max_retries}</td>
                <td className="px-4 py-3 text-muted text-xs">{new Date(job.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {pageData.items.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-muted text-sm">No jobs match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm text-muted">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="disabled:opacity-30">Prev</button>
          <span>Page {page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="disabled:opacity-30">Next</button>
        </div>
      )}

      {selectedJob && (
        <JobDrawer job={selectedJob} onClose={() => setSelectedJob(null)} onRetry={retry} onCancel={cancel} />
      )}
    </div>
  );
}

function JobDrawer({ job, onClose, onRetry, onCancel }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="h-full w-full max-w-md overflow-y-auto border-l border-hairline bg-surface p-6 animate-in">
        <div className="flex items-start justify-between">
          <div>
            <div className="font-mono text-xs text-muted">{job.id}</div>
            <h2 className="font-display text-lg font-semibold mt-1">{job.name}</h2>
          </div>
          <button onClick={onClose} className="text-muted hover:text-ink"><X size={18} /></button>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <StatusBadge status={job.status} />
          <span className="text-xs text-muted font-mono">retries {job.retry_count}/{job.max_retries}</span>
        </div>

        <div className="mt-4 flex gap-2">
          {(job.status === "failed" || job.status === "dead_letter") && (
            <button onClick={() => onRetry(job)} className="flex items-center gap-1.5 rounded-md border border-signal/30 px-3 py-1.5 text-xs text-signal hover:bg-signal/10">
              <RotateCcw size={12} /> Retry
            </button>
          )}
          {!["completed", "dead_letter", "cancelled"].includes(job.status) && (
            <button onClick={() => onCancel(job)} className="flex items-center gap-1.5 rounded-md border border-danger/30 px-3 py-1.5 text-xs text-danger hover:bg-danger/10">
              <Ban size={12} /> Cancel
            </button>
          )}
        </div>

        <Section title="Payload">
          <pre className="rounded-md bg-void p-3 text-xs font-mono overflow-x-auto">{JSON.stringify(job.payload, null, 2)}</pre>
        </Section>

        <Section title={`Execution history (${job.executions?.length || 0})`}>
          <div className="space-y-2">
            {job.executions?.map((ex) => (
              <div key={ex.id} className="rounded-md border border-hairline p-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono">attempt {ex.attempt_number}</span>
                  <StatusBadge status={ex.status} />
                </div>
                {ex.duration_ms != null && <div className="mt-1 text-muted">duration {ex.duration_ms}ms</div>}
                {ex.error_message && <div className="mt-1 text-danger font-mono">{ex.error_message}</div>}
              </div>
            ))}
          </div>
        </Section>

        <Section title="Logs">
          <div className="space-y-1 font-mono text-xs">
            {job.logs?.map((l) => (
              <div key={l.id} className="flex gap-2">
                <span className="text-muted shrink-0">{new Date(l.created_at).toLocaleTimeString()}</span>
                <span className={l.level === "error" ? "text-danger" : l.level === "warning" ? "text-warning" : "text-ink"}>{l.message}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="mt-6">
      <h3 className="text-xs uppercase tracking-wide text-muted mb-2">{title}</h3>
      {children}
    </div>
  );
}

function TextField({ label, type = "text", value, onChange, placeholder }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted">{label}</span>
      <input
        required
        type={type}
        value={value}
        placeholder={placeholder}
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
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-hairline bg-void px-3 py-2 text-sm outline-none focus:border-signal capitalize">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
}
