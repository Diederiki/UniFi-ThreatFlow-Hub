"use client";

/**
 * SVG ring gauge — single-color stroke, dark backplate, big centered label.
 * Mimics the "Live host monitors" tiles (CPU / MEMORY / DISK / NETWORK).
 */
export function Ring({
  percent,
  label,
  sublabel,
  size = 168,
  stroke = 10,
  color = "#22d3ee",
}: {
  percent: number;
  label: string;
  sublabel?: string;
  size?: number;
  stroke?: number;
  color?: string;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, percent));
  const dash = (clamped / 100) * c;

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke="#1f2a44" strokeWidth={stroke}
        />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke={color} strokeWidth={stroke}
          strokeDasharray={`${dash} ${c - dash}`}
          strokeDashoffset={c / 4}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 400ms ease" }}
        />
        <text
          x="50%" y="50%" textAnchor="middle" dominantBaseline="central"
          style={{ fill: "#dde4f1", fontWeight: 700, fontSize: size * 0.22 }}
        >
          {label}
        </text>
      </svg>
      {sublabel && <div className="mt-2 text-xs text-muted">{sublabel}</div>}
    </div>
  );
}
