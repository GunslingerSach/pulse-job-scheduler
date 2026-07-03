/** A small EKG-style pulse line. `alive` controls color + animation;
 * this is the app's signature visual motif, echoing the domain concept of
 * worker heartbeats and job throughput as literal "pulses" of the system. */
export default function Pulse({ alive = true, className = "" }) {
  const color = alive ? "var(--color-success)" : "var(--color-hairline)";
  return (
    <svg viewBox="0 0 120 24" className={className} preserveAspectRatio="none">
      <path
        d="M0 12 H28 L34 4 L42 20 L48 12 H62 L68 6 L74 18 L80 12 H120"
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={alive ? "pulse-line" : ""}
        opacity={alive ? 1 : 0.5}
      />
    </svg>
  );
}
