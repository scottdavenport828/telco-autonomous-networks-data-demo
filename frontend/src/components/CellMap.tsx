import type { ViolationRow } from "../api/client";

type Props = {
  rows: ViolationRow[];
  onSelect?: (row: ViolationRow) => void;
};

// Lightweight SVG topology — places cells in a grid, sizes the circle by violation count.
export default function CellMap({ rows, onSelect }: Props) {
  if (!rows.length) {
    return <div className="text-slate-500 text-sm">No KPI violations detected.</div>;
  }

  const max = Math.max(...rows.map((r) => r.violation_windows));
  const cols = Math.ceil(Math.sqrt(rows.length));
  const rowsCount = Math.ceil(rows.length / cols);

  const w = 600;
  const h = Math.max(180, rowsCount * 80);
  const stepX = w / (cols + 1);
  const stepY = h / (rowsCount + 1);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} className="bg-white rounded-lg border border-slate-200">
      {rows.map((row, i) => {
        const cx = stepX * ((i % cols) + 1);
        const cy = stepY * (Math.floor(i / cols) + 1);
        const r = 8 + (row.violation_windows / max) * 22;
        const fill = row.avg_erab_success_rate < 90 ? "#E63946" : row.avg_retainability > 4 ? "#F4A261" : "#FFB703";
        return (
          <g key={`${row.enodeb_id}/${row.cell_id}`} onClick={() => onSelect?.(row)} style={{ cursor: "pointer" }}>
            <circle cx={cx} cy={cy} r={r} fill={fill} fillOpacity={0.7} stroke="#1F4068" />
            <text x={cx} y={cy - r - 4} textAnchor="middle" fontSize={10} fill="#1F4068">
              {row.enodeb_id}/{row.cell_id}
            </text>
            <text x={cx} y={cy + 3} textAnchor="middle" fontSize={9} fill="#fff" fontWeight="bold">
              {row.violation_windows}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
