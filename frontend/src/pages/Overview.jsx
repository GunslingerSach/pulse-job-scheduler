import { useEffect, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import StatCard from "../components/StatCard";

export default function Overview() {
  const { project } = useAuth();
  const [stats, setStats] = useState(null);
  const [throughput, setThroughput] = useState([]);

  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    const load = async () => {
      const [ov, tp] = await Promise.all([api.overview(project.id), api.throughput(project.id, 24)]);
      if (!cancelled) {
        setStats(ov);
        setThroughput(
          tp.buckets.map((b) => ({
            ...b,
            label: new Date(b.timestamp).toLocaleTimeString([], { hour: "2-digit" }),
          }))
        );
      }
    };
    load();
    const id = setInterval(load, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [project]);

  if (!stats) return <div className="text-muted text-sm">Loading...</div>;

  return (
    <div className="space-y-8 animate-in">
      <div>
        <h1 className="font-display text-2xl font-semibold">System Overview</h1>
        <p className="text-sm text-muted mt-1">Real-time view of {project?.name}'s scheduling activity</p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label="Queued" value={stats.queued} />
        <StatCard label="Scheduled" value={stats.scheduled} tone="signal" />
        <StatCard label="Running" value={stats.running} tone="signal" />
        <StatCard label="Completed" value={stats.completed} tone="success" />
        <StatCard label="Dead Letter" value={stats.dead_letter} tone="danger" />
        <StatCard label="Workers" value={`${stats.active_workers}/${stats.total_workers}`} tone={stats.active_workers > 0 ? "success" : "warning"} />
      </div>

      <div className="rounded-lg border border-hairline bg-surface p-5">
        <h2 className="font-display text-sm font-semibold text-muted uppercase tracking-wide mb-4">
          Throughput — last 24h
        </h2>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={throughput}>
            <defs>
              <linearGradient id="completedGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#34D399" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#34D399" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="failedGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#F0554A" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#F0554A" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#232B36" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" stroke="#8A97A6" fontSize={11} tickLine={false} axisLine={false} />
            <YAxis stroke="#8A97A6" fontSize={11} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={{ background: "#131922", border: "1px solid #232B36", borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: "#8A97A6" }}
            />
            <Area type="monotone" dataKey="completed" stroke="#34D399" fill="url(#completedGrad)" strokeWidth={2} name="Completed" />
            <Area type="monotone" dataKey="failed" stroke="#F0554A" fill="url(#failedGrad)" strokeWidth={2} name="Failed" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
