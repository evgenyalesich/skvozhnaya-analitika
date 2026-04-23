import React from "react";
import Box from "@mui/material/Box";

interface MiniSparklineProps {
  values: number[];
  color?: string;
  width?: number;
  height?: number;
  fill?: string;
}

const MiniSparkline: React.FC<MiniSparklineProps> = ({
  values,
  color = "var(--c-blue)",
  width = 78,
  height = 24,
  fill = "transparent",
}) => {
  const safe = values.filter((value) => Number.isFinite(value));
  if (!safe.length || safe.every((value) => value === 0)) {
    return (
      <Box
        sx={{
          width,
          height,
          borderRadius: "999px",
          border: "1px dashed var(--app-table-divider)",
          opacity: 0.7,
          flexShrink: 0,
        }}
      />
    );
  }

  const min = Math.min(...safe);
  const max = Math.max(...safe);
  const range = max - min || 1;
  const step = safe.length <= 1 ? width : width / (safe.length - 1);
  const points = safe.map((value, index) => {
    const x = Number((index * step).toFixed(2));
    const y = Number((height - ((value - min) / range) * (height - 4) - 2).toFixed(2));
    return `${x},${y}`;
  });

  const areaPoints = [`0,${height}`, ...points, `${width},${height}`].join(" ");
  const linePoints = points.join(" ");
  const last = points[points.length - 1]?.split(",") || ["0", `${height / 2}`];

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-hidden="true">
      <polygon points={areaPoints} fill={fill} />
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={linePoints}
      />
      <circle cx={last[0]} cy={last[1]} r="2.7" fill={color} />
    </svg>
  );
};

export default MiniSparkline;
