import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";

export default function DeadLetter() {
  const { project } = useAuth();
  const [entries, setEntries] = useState([]);

  const load = () => project && api.deadLetters(project.id).then(setEntries);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  const replay = async (entry) => {
    await api.replayDeadLetter(project.id, entry.id);
    load();
  };

  return (
    <div className="space-y-6 animate-in">
      <div>
        <h1 className="font-display text-2xl font-semibold">Dead Letter Queue</h1>
        <p className="text-sm text-muted mt-1">Jobs that exhausted their retry budget. Inspect and replay as needed.</p>
      </div>

      <div className="space-y-3">
        {entries.map((e) => (
          <div key={e.id} className="rounded-lg border border-hairline bg-surface p-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="font-mono text-sm">{e.name}</div>
                <div className="text-xs text-muted mt-1">
                  {e.total_attempts} attempts · failed {new Date(e.failed_at).toLocaleString()}
                </div>
              </div>
              <button
                onClick={() => replay(e)}
                disabled={e.replayed}
                className="flex items-center gap-1.5 rounded-md border border-signal/30 px-3 py-1.5 text-xs text-signal hover:bg-signal/10 disabled:opacity-30"
              >
                <RotateCcw size={12} /> {e.replayed ? "Replayed" : "Replay"}
              </button>
            </div>
            <div className="mt-3 rounded-md bg-void p-3 text-xs text-danger font-mono">{e.failure_reason}</div>
          </div>
        ))}
        {entries.length === 0 && <div className="text-sm text-muted">No dead-lettered jobs. 🎉</div>}
      </div>
    </div>
  );
}
