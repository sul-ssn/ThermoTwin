"use client";
export type Sample = { timestamp: string; value: number };
export default function TelemetryChart({
  samples,
  unit,
}: {
  samples: Sample[];
  unit: string;
}) {
  const points = samples.slice(-60);
  if (!points.length)
    return <div className="empty small">Показаний пока нет</div>;
  const low = Math.min(...points.map((p) => p.value)) - 0.25,
    high = Math.max(...points.map((p) => p.value)) + 0.25;
  const xy = points.map((p, i) => [
    42 + (i / Math.max(points.length - 1, 1)) * 490,
    140 - ((p.value - low) / (high - low)) * 112,
  ]);
  const path = xy.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" ");
  return (
    <div className="chart">
      <div className="chart-caption">
        <span>История показаний</span>
        <span>
          {unit} · {points.length} измерений
        </span>
      </div>
      <svg
        viewBox="0 0 550 178"
        role="img"
        aria-label="График фактических показаний виртуального датчика"
      >
        <defs>
          <linearGradient id="chart-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2f6fed" stopOpacity=".16" />
            <stop offset="100%" stopColor="#2f6fed" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line
              x1="42"
              x2="532"
              y1={140 - f * 112}
              y2={140 - f * 112}
              stroke="#e9eef5"
              strokeDasharray="3 3"
            />
            <text x="0" y={144 - f * 112} fill="#94a3b8" fontSize="10">
              {(low + (high - low) * f).toFixed(1)}
            </text>
          </g>
        ))}
        {points.length > 1 && (
          <path d={`${path} L532,140 L42,140 Z`} fill="url(#chart-area)" />
        )}
        <path d={path} stroke="#2f6fed" strokeWidth="2" fill="none" />
        {xy.map(([x, y], i) => (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={points.length === 1 ? 4 : 1.5}
            fill="#2f6fed"
          />
        ))}
        <text x="42" y="167" fill="#94a3b8" fontSize="10">
          {new Date(points[0].timestamp).toLocaleTimeString("ru-RU", {
            timeZone: "Asia/Almaty",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </text>
        <text x="492" y="167" fill="#94a3b8" fontSize="10">
          {new Date(points[points.length - 1].timestamp).toLocaleTimeString(
            "ru-RU",
            { timeZone: "Asia/Almaty", hour: "2-digit", minute: "2-digit" },
          )}
        </text>
      </svg>
    </div>
  );
}
