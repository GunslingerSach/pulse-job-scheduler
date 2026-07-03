import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import StatusBadge from "../components/StatusBadge";
import Pulse from "../components/Pulse";

export default function Workers() {
  const { project } = useAuth();
  const [workers, setWorkers] = useState([]);
  const [showKey, setShowKey] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!project) return;
    const load = () => api.listWorkers(project.api_key).then(setWorkers);
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [project]);

  const copyCommand = () => {
    const cmd = `python -m app.worker.runner --api-key ${project?.api_key || "<YOUR_API_KEY>"}`;
    navigator.clipboard.writeText(cmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6 animate-in">
      <div>
        <h1 className="font-display text-2xl font-semibold">Workers</h1>
        <div className="text-sm text-muted mt-2 flex flex-wrap items-center gap-2">
          <span>Register a worker with:</span>
          <code className="rounded bg-void px-2 py-1 font-mono text-xs text-signal border border-hairline">
            python -m app.worker.runner --api-key {showKey ? project?.api_key : "<YOUR_API_KEY>"}
          </code>
          <button
            onClick={() => setShowKey(!showKey)}
            className="rounded border border-hairline bg-surface px-2 py-1 text-xs text-muted hover:text-ink transition-colors"
          >
            {showKey ? "Hide Key" : "Reveal Key"}
          </button>
          <button
            onClick={copyCommand}
            className="rounded border border-hairline bg-surface px-2 py-1 text-xs text-muted hover:text-ink transition-colors"
          >
            {copied ? "Copied!" : "Copy Command"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {workers.map((w) => {
          const alive = w.status === "active" || w.status === "idle";
          return (
            <div key={w.id} className="rounded-lg border border-hairline bg-surface p-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-medium">{w.name}</div>
                  <div className="text-xs text-muted font-mono">{w.hostname || "unknown host"}</div>
                </div>
                <StatusBadge status={w.status} />
              </div>

              <Pulse alive={alive} className="mt-3 h-6 w-full" />

              <div className="mt-3 flex justify-between text-xs text-muted font-mono">
                <span>load {w.current_load}/{w.concurrency}</span>
                <span>{w.last_heartbeat_at ? new Date(w.last_heartbeat_at).toLocaleTimeString() : "never"}</span>
              </div>
            </div>
          );
        })}
        {workers.length === 0 && (
          <div className="col-span-full text-sm text-muted">
            No workers registered yet. Start one with the command above.
          </div>
        )}
      </div>
    </div>
  );
}
