import { useState } from "react";
import Pulse from "../components/Pulse";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "", organization_name: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(form.email, form.password);
      } else {
        await register(form);
      }
    } catch (err) {
      setError(err?.response?.data?.detail || "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-void text-ink">
      <div className="w-full max-w-sm animate-in">
        <div className="mb-8 flex flex-col items-center gap-3">
          <Pulse className="h-6 w-16" />
          <h1 className="font-display text-2xl font-semibold">Pulse</h1>
          <p className="text-sm text-muted">Distributed job scheduling console</p>
        </div>

        <div className="rounded-lg border border-hairline bg-surface p-6">
          <div className="mb-5 flex gap-1 rounded-md bg-white/5 p-1 text-sm">
            {["login", "register"].map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`flex-1 rounded px-3 py-1.5 capitalize transition-colors ${
                  mode === m ? "bg-signal/20 text-signal" : "text-muted"
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-3">
            {mode === "register" && (
              <>
                <Field label="Full name" value={form.full_name} onChange={(v) => setForm({ ...form, full_name: v })} />
                <Field label="Organization" value={form.organization_name} onChange={(v) => setForm({ ...form, organization_name: v })} />
              </>
            )}
            <Field label="Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} />
            <Field label="Password" type="password" value={form.password} onChange={(v) => setForm({ ...form, password: v })} />

            {error && <div className="text-xs text-danger">{error}</div>}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md bg-signal py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {busy ? "Working..." : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function Field({ label, type = "text", value, onChange }) {
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
