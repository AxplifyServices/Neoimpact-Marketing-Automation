import { useMemo } from 'react';
import {
  ComposedChart,
  LabelList,
  Line,
  ResponsiveContainer,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import type { CampaignGraph as CampaignGraphType } from '@/types/dashboard.types';

interface CampaignGraphProps {
  graph: CampaignGraphType;
}

type PositionedNode = {
  id: string;
  canal: string;
  action: string;
  count: number;
  x: number;
  y: number;
  size: number;
  labelText: string;
};

type EdgeLine = {
  id: string;
  data: Array<{ x: number; y: number }>;
};

const EDGE_COLOR = '#0068c9';
const NODE_FILL = '#83c9ff';
const NODE_STROKE = '#ffffff';
const NODE_LABEL_COLOR = '#6b7280';
const NODE_SIZE_RANGE: [number, number] = [140, 420];

const buildSeededRandom = (seed: number) => {
  let value = seed;
  return () => {
    value = (value + 0x6d2b79f5) | 0;
    let t = Math.imul(value ^ (value >>> 15), 1 | value);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

const computeSpringLayout = (
  nodes: CampaignGraphType['nodes'],
  edges: CampaignGraphType['edges']
) => {
  const count = nodes.length;
  const rand = buildSeededRandom(7);
  const positions = nodes.map(() => ({
    x: rand(),
    y: rand(),
  }));

  const nodeIndex = new Map(nodes.map((node, index) => [node.id, index]));
  const k = Math.sqrt(1 / Math.max(count, 1));
  const iterations = 50;
  let temperature = 0.1;
  const deltaTemp = temperature / (iterations + 1);

  for (let iter = 0; iter < iterations; iter += 1) {
    const disp = positions.map(() => ({ x: 0, y: 0 }));

    for (let i = 0; i < count; i += 1) {
      for (let j = i + 1; j < count; j += 1) {
        const dx = positions[i].x - positions[j].x;
        const dy = positions[i].y - positions[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy) + 0.01;
        const force = (k * k) / dist;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        disp[i].x += fx;
        disp[i].y += fy;
        disp[j].x -= fx;
        disp[j].y -= fy;
      }
    }

    edges.forEach((edge) => {
      const sourceIndex = nodeIndex.get(edge.from);
      const targetIndex = nodeIndex.get(edge.to);
      if (sourceIndex === undefined || targetIndex === undefined) return;

      const dx = positions[sourceIndex].x - positions[targetIndex].x;
      const dy = positions[sourceIndex].y - positions[targetIndex].y;
      const dist = Math.sqrt(dx * dx + dy * dy) + 0.01;
      const force = (dist * dist) / k;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;

      disp[sourceIndex].x -= fx;
      disp[sourceIndex].y -= fy;
      disp[targetIndex].x += fx;
      disp[targetIndex].y += fy;
    });

    for (let i = 0; i < count; i += 1) {
      const dx = disp[i].x;
      const dy = disp[i].y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const step = Math.min(dist, temperature);
      positions[i].x += (dx / dist) * step;
      positions[i].y += (dy / dist) * step;
    }

    temperature = Math.max(0, temperature - deltaTemp);
  }

  return positions;
};

const buildLayout = (graph: CampaignGraphType) => {
  const nodes = graph.nodes ?? [];
  const edges = graph.edges ?? [];

  if (nodes.length === 0) {
    return {
      nodes: [] as PositionedNode[],
      edges: [] as EdgeLine[],
      xDomain: [0, 1] as [number, number],
      yDomain: [0, 1] as [number, number],
      minSize: 0,
      maxSize: 0,
    };
  }

  const rawPositions = computeSpringLayout(nodes, edges);
  const sizes = nodes.map(node => Math.max(12, Math.min(45, 12 + Math.sqrt(node.count || 0))));
  const minSize = Math.min(...sizes);
  const maxSize = Math.max(...sizes);

  let centerX = 0;
  let centerY = 0;
  rawPositions.forEach((point) => {
    centerX += point.x;
    centerY += point.y;
  });
  centerX /= Math.max(rawPositions.length, 1);
  centerY /= Math.max(rawPositions.length, 1);

  const centeredPositions = rawPositions.map((point) => ({
    x: point.x - centerX,
    y: point.y - centerY,
  }));

  const maxAbs = Math.max(
    1,
    ...centeredPositions.map((point) => Math.max(Math.abs(point.x), Math.abs(point.y)))
  );
  const positions = centeredPositions.map((point) => ({
    x: point.x / maxAbs,
    y: point.y / maxAbs,
  }));

  const positionedNodes: PositionedNode[] = nodes.map((node, index) => {
    const position = positions[index] ?? { x: 0, y: 0 };
    const size = sizes[index];

    return {
      id: node.id,
      canal: node.canal,
      action: node.action,
      count: node.count,
      x: position.x,
      y: position.y,
      size,
      labelText: `${node.id} ${node.canal}`.trim(),
    };
  });

  const positionsById = new Map(positionedNodes.map(node => [node.id, node]));
  const edgeLines: EdgeLine[] = edges.flatMap((edge, index) => {
    const from = positionsById.get(edge.from);
    const to = positionsById.get(edge.to);
    if (!from || !to) return [];

    return [
      {
        id: `edge-${edge.from}-${edge.to}-${index}`,
        data: [
          { x: from.x, y: from.y },
          { x: to.x, y: to.y },
        ],
      },
    ];
  });

  const bound = 1.1;
  const minX = -bound;
  const maxX = bound;
  const minY = -bound;
  const maxY = bound;

  return {
    nodes: positionedNodes,
    edges: edgeLines,
    xDomain: [minX, maxX] as [number, number],
    yDomain: [minY, maxY] as [number, number],
    minSize,
    maxSize,
  };
};

export default function CampaignGraph({ graph }: CampaignGraphProps) {
  const layout = useMemo(() => buildLayout(graph), [graph]);

  if (!graph || !graph.nodes || graph.nodes.length === 0) {
    return (
      <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
        <h2 className="text-xl font-bold text-gray-900 mb-4">Graphe campagne</h2>
        <div className="text-center py-12 text-gray-500">
          Aucun graphe disponible
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
      <h2 className="text-xl font-bold text-gray-900 mb-4">
        Graphe campagne (1 campagne selectionnee)
      </h2>
      <div className="text-sm text-gray-600 mb-4">
        Modele: <span className="font-medium">{graph.modele_nom}</span>
      </div>
      <div style={{ width: '100%', height: '300px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={layout.nodes} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
            <XAxis type="number" dataKey="x" hide domain={layout.xDomain} />
            <YAxis type="number" dataKey="y" hide domain={layout.yDomain} />
            <ZAxis type="number" dataKey="size" domain={[layout.minSize, layout.maxSize]} range={NODE_SIZE_RANGE} />
            {layout.edges.map(edge => (
              <Line
                key={edge.id}
                data={edge.data}
                dataKey="y"
                dot={false}
                activeDot={false}
                isAnimationActive={false}
                stroke={EDGE_COLOR}
                strokeWidth={1}
                type="linear"
              />
            ))}
            <Scatter
              data={layout.nodes}
              fill={NODE_FILL}
              stroke={NODE_STROKE}
              strokeWidth={1}
              fillOpacity={0.7}
              isAnimationActive={false}
            >
              <LabelList dataKey="labelText" position="top" offset={10} fill={NODE_LABEL_COLOR} fontSize={12} />
            </Scatter>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
