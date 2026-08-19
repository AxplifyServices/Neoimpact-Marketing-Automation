import { useEffect, useMemo, useRef, useCallback, useState, type CSSProperties } from 'react';
import ReactFlow, {
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type ReactFlowInstance,
  type Connection,
  type NodeProps,
  type NodeDragHandler,
  useReactFlow,
  Handle,
  Position,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from 'reactflow';
import type { WorkflowLayout, NodePosition, HandleSide, EdgeEndpoint, EdgeHandles } from '@/types/modele.types';
import 'reactflow/dist/style.css';
import { useQuery } from '@tanstack/react-query';
import { getApiClient } from '@/lib/api/api-client';
import { dashboardApi } from '@/lib/api/definitions/dashboard.api';
import type { DashboardComputeByCampaignResponse, CampaignGraphNode, ChannelTableRow } from '@/types/dashboard.types';

let elkPromise: Promise<any> | null = null;

const getElk = async () => {
  if (!elkPromise) {
    elkPromise = import('elkjs/lib/elk.bundled.js').then(({ default: ELK }) => new ELK());
  }
  return elkPromise;
};

// Estimate edge label dimensions for ELK layout
const estimateLabelWidth = (conditions: string[]): number => {
  if (conditions.length === 0) return 0;
  const maxLength = Math.max(...conditions.map(c => c.length));
  // ~9px per char (text-sm font) + 32px padding (px-4 = 16px * 2)
  return Math.max(120, maxLength * 9 + 40);
};

const estimateLabelHeight = (conditions: string[]): number => {
  if (conditions.length === 0) return 0;
  return conditions.length * 20 + 20; // ~20px per line + padding
};

// ELK layout function
const getLayoutedElements = async (
  nodes: Node[],
  edges: Edge[],
  nodeWidth: number = 260,
  nodeHeight: number = 160
): Promise<{ nodes: Node[]; edges: Edge[] }> => {
  // Calculate max label width to set proper spacing
  const maxLabelWidth = Math.max(
    100,
    ...edges.map(e => {
      const conditions = (e.data?.conditions as string[]) || [];
      return estimateLabelWidth(conditions);
    })
  );

  const graph = {
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'RIGHT',
      'elk.edgeRouting': 'SPLINES',
      'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
      'elk.spacing.nodeNode': '100',
      // Dynamic spacing based on max label width
      'elk.layered.spacing.nodeNodeBetweenLayers': String(maxLabelWidth + 100),
      'elk.spacing.edgeLabel': '20',
      'elk.layered.spacing.edgeEdgeBetweenLayers': '50',
      'elk.layered.spacing.edgeNodeBetweenLayers': '80',
    },
    children: nodes.map(n => ({
      id: n.id,
      width: (n.style?.width as number) || nodeWidth,
      height: nodeHeight,
    })),
    edges: edges.map(e => {
      const conditions = (e.data?.conditions as string[]) || [];
      return {
        id: e.id,
        sources: [e.source],
        targets: [e.target],
        labels: conditions.length > 0 ? [{
          width: estimateLabelWidth(conditions),
          height: estimateLabelHeight(conditions),
        }] : [],
      };
    }),
  };

  const elk = await getElk();
  const layoutedGraph = await elk.layout(graph);

  return {
    nodes: nodes.map(node => {
      const elkNode = layoutedGraph.children?.find(n => n.id === node.id);
      return {
        ...node,
        position: { x: elkNode?.x || 0, y: elkNode?.y || 0 },
      };
    }),
    edges,
  };
};

interface Block {
  id: string;
  canal: string;
  delai: number;
  parents: string[];
  objet?: string;
  contenu?: string;
  conditionsByParent: Record<string, BlockCondition[]>;
  isObjectif: boolean;
  objectiveConditions: BlockCondition[];
  objectiveOperator: 'AND' | 'OR';
  valideObjectif?: 'Oui' | 'Non';
}

interface BlockCondition {
  id: string;
  type: 'days_since_last' | 'flag_resultat' | 'counter' | 'client_filter' | 'client_field' | 'campaign_field';
  operator?: string;
  daysSinceLastAction?: number | string;
  flagResultat?: string;
  counterValue?: number | string;
  // Legacy client_field support
  clientField?: string;
  clientFieldType?: 'text' | 'numeric';
  clientFieldValue?: string | number;
  // Current client_filter support
  column?: string;
  min?: string;
  max?: string;
  values?: string[];
  fieldLabel?: string;
  // Campaign field support (e.g. NB jours depuis début campagne)
  campaignField?: string;
  campaignFieldValue?: number;
  nextBlockId: string | null;
}

interface WorkflowAnalyticsData {
  graph?: { nodes?: CampaignGraphNode[] };
  tables?: { by_channel?: ChannelTableRow[] };
}

interface WorkflowPreviewProps {
  blocks: Block[];
  getBlockDisplayNumber: (blockId: string) => number;
  campaignId?: string;
  analyticsData?: WorkflowAnalyticsData;
  etatsCampagne?: string[];
  dateMin?: string | null;
  dateMax?: string | null;
  onSelectBlock?: (blockId: string) => void;
  onAddChildBlock?: (blockId: string) => void;
  onAddObjectiveChildBlock?: (blockId: string) => void;
  onDuplicateBlock?: (blockId: string) => void;
  onDeleteBlock?: (blockId: string) => void;
  onDeleteEdge?: (sourceId: string, targetId: string) => void;
  fitViewSignal?: number;
  modalOpen?: boolean;
  showHeader?: boolean;
  showFrame?: boolean;
  containerClassName?: string;
  height?: number | string;
  onLinkBlocks?: (sourceId: string, targetId: string) => void;
  onSelectionChange?: (selectedBlockIds: string[]) => void;
  selectedBlockIds?: string[];
  blockValidation?: Record<string, number>;
  edgeValidation?: Record<string, number>;
  layout?: WorkflowLayout | null;
  onLayoutChange?: (layout: WorkflowLayout) => void;
  onClearLayout?: () => void;
  onEdgeBendPointsChange?: (edgeKey: string, points: NodePosition[]) => void;
  onEdgeHandlesChange?: (edgeKey: string, handles: EdgeHandles) => void;
}

interface WorkflowEdgeData {
  conditions?: string[];
  sourceId?: string;
  targetId?: string;
  warningCount?: number;
  onDeleteEdge?: (sourceId: string, targetId: string) => void;
  bendPoints?: NodePosition[];
  onBendPointsChange?: (edgeKey: string, points: NodePosition[]) => void;
  sourceEndpoint?: EdgeEndpoint;
  targetEndpoint?: EdgeEndpoint;
  onHandlesChange?: (edgeKey: string, handles: EdgeHandles) => void;
}

const normalizeBlockId = (value: string): string => {
  if (!value) return value;
  return value.startsWith('block_') ? value.slice('block_'.length) : value;
};

const formatConditionLabel = (condition: BlockCondition): string => {
  const op = condition.operator || (condition.type === 'flag_resultat' ? '=' : '>');

  if (condition.type === 'days_since_last') {
    const value = condition.daysSinceLastAction ?? '';
    const label = condition.fieldLabel || 'Jours';
    if (value === '') {
      return label;
    }
    const suffix = condition.fieldLabel ? '' : 'j';
    return `${label} ${op} ${value}${suffix}`;
  }
  if (condition.type === 'flag_resultat') {
    return condition.flagResultat ?? (condition.fieldLabel || 'Flag');
  }
  if (condition.type === 'client_filter') {
    const fieldName = condition.column || condition.fieldLabel || 'Client';
    const values = (condition.values || []).filter(Boolean);
    const min = (condition.min ?? '').toString().trim();
    const max = (condition.max ?? '').toString().trim();
    if (values.length > 0) {
      return `${fieldName}: ${values.join(', ')}`;
    }
    if (min && max) {
      return `${fieldName}: ${min}-${max}`;
    }
    if (min) {
      return `${fieldName} >= ${min}`;
    }
    if (max) {
      return `${fieldName} <= ${max}`;
    }
    return fieldName;
  }
  if (condition.type === 'client_field') {
    const fieldName = condition.clientField || 'Client';
    const value = condition.clientFieldValue ?? '';
    if (value === '') {
      return fieldName;
    }
    return `${fieldName} ${op} ${value}`;
  }
  if (condition.type === 'campaign_field') {
    const value = condition.campaignFieldValue ?? '';
    return `NB jours début campagne ${op} ${value}`;
  }
  const counterValue = condition.counterValue ?? '';
  const label = condition.fieldLabel || 'Compteur';
  if (counterValue === '') {
    return label;
  }
  return `${label} ${op} ${counterValue}`;
};

// Compute pixel position on a node's border given an EdgeEndpoint
const computeBorderPosition = (
  endpoint: EdgeEndpoint,
  nodeX: number,
  nodeY: number,
  nodeW: number,
  nodeH: number,
): NodePosition => {
  const { side, offset } = endpoint;
  switch (side) {
    case 'top': return { x: nodeX + nodeW * offset, y: nodeY };
    case 'right': return { x: nodeX + nodeW, y: nodeY + nodeH * offset };
    case 'bottom': return { x: nodeX + nodeW * (1 - offset), y: nodeY + nodeH };
    case 'left': return { x: nodeX, y: nodeY + nodeH * (1 - offset) };
  }
};

// Snap a cursor position to the closest point on a node's border, returning side + offset
const snapToBorder = (
  cursor: NodePosition,
  nodeX: number,
  nodeY: number,
  nodeW: number,
  nodeH: number,
): EdgeEndpoint => {
  // Clamp cursor to node bounds
  const cx = Math.max(nodeX, Math.min(nodeX + nodeW, cursor.x));
  const cy = Math.max(nodeY, Math.min(nodeY + nodeH, cursor.y));

  // Distance to each side
  const dTop = Math.abs(cy - nodeY);
  const dBottom = Math.abs(cy - (nodeY + nodeH));
  const dLeft = Math.abs(cx - nodeX);
  const dRight = Math.abs(cx - (nodeX + nodeW));
  const minDist = Math.min(dTop, dBottom, dLeft, dRight);

  if (minDist === dTop) return { side: 'top', offset: Math.max(0, Math.min(1, (cx - nodeX) / nodeW)) };
  if (minDist === dRight) return { side: 'right', offset: Math.max(0, Math.min(1, (cy - nodeY) / nodeH)) };
  if (minDist === dBottom) return { side: 'bottom', offset: Math.max(0, Math.min(1, 1 - (cx - nodeX) / nodeW)) };
  return { side: 'left', offset: Math.max(0, Math.min(1, 1 - (cy - nodeY) / nodeH)) };
};

// Build a smooth SVG path through a series of points using Catmull-Rom → cubic bezier
const buildSmoothPath = (points: { x: number; y: number }[]): string => {
  if (points.length < 2) return '';
  if (points.length === 2) {
    const [p0, p1] = points;
    const midX = (p0.x + p1.x) / 2;
    return `M ${p0.x},${p0.y} C ${midX},${p0.y} ${midX},${p1.y} ${p1.x},${p1.y}`;
  }

  let path = `M ${points[0].x},${points[0].y}`;
  const tension = 6;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];
    const cp1x = p1.x + (p2.x - p0.x) / tension;
    const cp1y = p1.y + (p2.y - p0.y) / tension;
    const cp2x = p2.x - (p3.x - p1.x) / tension;
    const cp2y = p2.y - (p3.y - p1.y) / tension;
    path += ` C ${cp1x},${cp1y} ${cp2x},${cp2y} ${p2.x},${p2.y}`;
  }
  return path;
};

// Find the midpoint along a polyline path
const getPolylineMidpoint = (points: { x: number; y: number }[]): { x: number; y: number } => {
  if (points.length < 2) return points[0] || { x: 0, y: 0 };
  let totalLength = 0;
  const segments: number[] = [];
  for (let i = 1; i < points.length; i++) {
    const dx = points[i].x - points[i - 1].x;
    const dy = points[i].y - points[i - 1].y;
    const len = Math.sqrt(dx * dx + dy * dy);
    segments.push(len);
    totalLength += len;
  }
  let target = totalLength / 2;
  for (let i = 0; i < segments.length; i++) {
    if (target <= segments[i]) {
      const t = segments[i] > 0 ? target / segments[i] : 0;
      return {
        x: points[i].x + (points[i + 1].x - points[i].x) * t,
        y: points[i].y + (points[i + 1].y - points[i].y) * t,
      };
    }
    target -= segments[i];
  }
  return points[points.length - 1];
};

// Find the best index to insert a new bend point based on proximity to segments
const findInsertIndex = (
  allPoints: { x: number; y: number }[],
  clickPoint: { x: number; y: number },
): number => {
  let bestIndex = 1;
  let bestDist = Infinity;
  for (let i = 0; i < allPoints.length - 1; i++) {
    const a = allPoints[i];
    const b = allPoints[i + 1];
    const abx = b.x - a.x;
    const aby = b.y - a.y;
    const len2 = abx * abx + aby * aby;
    const t = len2 > 0 ? Math.max(0, Math.min(1, ((clickPoint.x - a.x) * abx + (clickPoint.y - a.y) * aby) / len2)) : 0;
    const projX = a.x + t * abx;
    const projY = a.y + t * aby;
    const dist = Math.sqrt((clickPoint.x - projX) ** 2 + (clickPoint.y - projY) ** 2);
    if (dist < bestDist) {
      bestDist = dist;
      bestIndex = i + 1;
    }
  }
  return bestIndex;
};

// Custom edge component to display multiple condition labels vertically
function MultiConditionEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  style,
}: EdgeProps<WorkflowEdgeData>) {
  const [isHovered, setIsHovered] = useState(false);
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  const [localBendPoints, setLocalBendPoints] = useState<NodePosition[] | null>(null);
  const [draggingEndpoint, setDraggingEndpoint] = useState<{ role: 'source' | 'target'; localPos: NodePosition } | null>(null);
  const hideHoverTimerRef = useRef<number | null>(null);
  const { screenToFlowPosition, getNode } = useReactFlow();

  const clearHoverTimer = useCallback(() => {
    if (hideHoverTimerRef.current !== null) {
      window.clearTimeout(hideHoverTimerRef.current);
      hideHoverTimerRef.current = null;
    }
  }, []);
  const showHover = useCallback(() => {
    clearHoverTimer();
    setIsHovered(true);
  }, [clearHoverTimer]);
  const scheduleHideHover = useCallback(() => {
    clearHoverTimer();
    hideHoverTimerRef.current = window.setTimeout(() => {
      hideHoverTimerRef.current = null;
      setIsHovered(false);
    }, 140);
  }, [clearHoverTimer]);

  useEffect(() => () => clearHoverTimer(), [clearHoverTimer]);

  const bendPoints = localBendPoints ?? data?.bendPoints;
  const hasBendPoints = bendPoints && bendPoints.length > 0;
  const editable = Boolean(data?.onBendPointsChange);
  const sourceId = data?.sourceId || '';
  const targetId = data?.targetId || '';
  const edgeKey = `${sourceId}->${targetId}`;

  // Compute actual edge start/end positions from stored endpoints
  let sx = sourceX, sy = sourceY, sp = sourcePosition;
  let tx = targetX, ty = targetY, tp = targetPosition;
  const srcEndpoint = data?.sourceEndpoint;
  const tgtEndpoint = data?.targetEndpoint;
  const srcNode = srcEndpoint ? getNode(sourceId) : undefined;
  const tgtNode = tgtEndpoint ? getNode(targetId) : undefined;
  if (srcEndpoint && srcNode?.width != null && srcNode?.height != null) {
    const pos = computeBorderPosition(srcEndpoint, srcNode.position.x, srcNode.position.y, srcNode.width, srcNode.height);
    sx = pos.x;
    sy = pos.y;
    sp = SIDE_POSITION[srcEndpoint.side];
  }
  if (tgtEndpoint && tgtNode?.width != null && tgtNode?.height != null) {
    const pos = computeBorderPosition(tgtEndpoint, tgtNode.position.x, tgtNode.position.y, tgtNode.width, tgtNode.height);
    tx = pos.x;
    ty = pos.y;
    tp = SIDE_POSITION[tgtEndpoint.side];
  }

  // Live update: override edge path with snapped drag position so line follows in real-time
  let dragSnapPos: NodePosition | null = null;
  let dragNodeRect: { x: number; y: number; w: number; h: number } | null = null;
  if (draggingEndpoint) {
    const nodeId = draggingEndpoint.role === 'source' ? sourceId : targetId;
    const node = getNode(nodeId);
    if (node && node.width != null && node.height != null) {
      const snapped = snapToBorder(draggingEndpoint.localPos, node.position.x, node.position.y, node.width, node.height);
      dragSnapPos = computeBorderPosition(snapped, node.position.x, node.position.y, node.width, node.height);
      dragNodeRect = { x: node.position.x, y: node.position.y, w: node.width, h: node.height };
      if (draggingEndpoint.role === 'source') {
        sx = dragSnapPos.x; sy = dragSnapPos.y; sp = SIDE_POSITION[snapped.side];
      } else {
        tx = dragSnapPos.x; ty = dragSnapPos.y; tp = SIDE_POSITION[snapped.side];
      }
    }
  }

  let edgePath: string;
  let labelX: number;
  let labelY: number;

  if (hasBendPoints) {
    const allPoints = [{ x: sx, y: sy }, ...bendPoints, { x: tx, y: ty }];
    edgePath = buildSmoothPath(allPoints);
    const mid = getPolylineMidpoint(allPoints);
    labelX = mid.x;
    labelY = mid.y;
  } else {
    [edgePath, labelX, labelY] = getBezierPath({ sourceX: sx, sourceY: sy, sourcePosition: sp, targetX: tx, targetY: ty, targetPosition: tp });
  }

  const conditions = data?.conditions || [];

  const styleStroke = typeof style?.stroke === 'string' ? style.stroke : '#94a3b8';
  const rawStrokeWidth = typeof style?.strokeWidth === 'number' ? style.strokeWidth : Number(style?.strokeWidth) || 2;
  const strokeColor = isHovered ? '#334155' : styleStroke;
  const strokeWidth = isHovered ? Math.max(rawStrokeWidth, 2.8) : rawStrokeWidth;
  const showQuickDelete = Boolean(data?.onDeleteEdge && sourceId && targetId && isHovered);

  const handleEdgeDoubleClick = useCallback((event: React.MouseEvent) => {
    if (!editable || !data?.onBendPointsChange) return;
    event.stopPropagation();
    const flowPos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const currentPoints = data.bendPoints || [];
    const allPoints = [{ x: sx, y: sy }, ...currentPoints, { x: tx, y: ty }];
    const insertIdx = findInsertIndex(allPoints, flowPos);
    // insertIdx is relative to allPoints which includes source at 0, so bend point index is insertIdx - 1
    const newPoints = [...currentPoints];
    newPoints.splice(insertIdx - 1, 0, { x: flowPos.x, y: flowPos.y });
    data.onBendPointsChange(edgeKey, newPoints);
  }, [editable, data, sourceX, sourceY, targetX, targetY, edgeKey, screenToFlowPosition]);

  const handleBendPointDoubleClick = useCallback((event: React.MouseEvent, index: number) => {
    if (!editable || !data?.onBendPointsChange) return;
    event.stopPropagation();
    const currentPoints = data.bendPoints || [];
    const newPoints = currentPoints.filter((_, i) => i !== index);
    data.onBendPointsChange(edgeKey, newPoints);
  }, [editable, data, edgeKey]);

  const handleBendPointPointerDown = useCallback((event: React.PointerEvent, index: number) => {
    if (!editable) return;
    event.stopPropagation();
    event.preventDefault();
    (event.target as SVGElement).setPointerCapture(event.pointerId);
    setDraggingIndex(index);
    setLocalBendPoints(data?.bendPoints || []);
  }, [editable, data?.bendPoints]);

  const handleBendPointPointerMove = useCallback((event: React.PointerEvent) => {
    if (draggingIndex === null || !localBendPoints) return;
    event.stopPropagation();
    const flowPos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const updated = [...localBendPoints];
    updated[draggingIndex] = { x: flowPos.x, y: flowPos.y };
    setLocalBendPoints(updated);
  }, [draggingIndex, localBendPoints, screenToFlowPosition]);

  const handleBendPointPointerUp = useCallback((event: React.PointerEvent) => {
    if (draggingIndex === null || !localBendPoints || !data?.onBendPointsChange) {
      setDraggingIndex(null);
      setLocalBendPoints(null);
      return;
    }
    event.stopPropagation();
    (event.target as SVGElement).releasePointerCapture(event.pointerId);
    data.onBendPointsChange(edgeKey, localBendPoints);
    setDraggingIndex(null);
    setLocalBendPoints(null);
  }, [draggingIndex, localBendPoints, data, edgeKey]);

  const activeBendPoints = localBendPoints ?? data?.bendPoints ?? [];
  const endpointEditable = Boolean(data?.onHandlesChange);
  const isDraggingAnything = draggingIndex !== null || draggingEndpoint !== null;

  const snapEndpoint = useCallback((cursorPos: NodePosition, nodeId: string): EdgeEndpoint => {
    const node = getNode(nodeId);
    if (!node || node.width == null || node.height == null) return { side: 'left', offset: 0.5 };
    return snapToBorder(cursorPos, node.position.x, node.position.y, node.width, node.height);
  }, [getNode]);

  const handleEndpointPointerDown = useCallback((role: 'source' | 'target', event: React.PointerEvent) => {
    if (!endpointEditable) return;
    event.stopPropagation();
    event.preventDefault();
    (event.target as HTMLElement).setPointerCapture(event.pointerId);
    const flowPos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    setDraggingEndpoint({ role, localPos: flowPos });
  }, [endpointEditable, screenToFlowPosition]);

  const handleEndpointPointerMove = useCallback((event: React.PointerEvent) => {
    if (!draggingEndpoint) return;
    event.stopPropagation();
    const flowPos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    setDraggingEndpoint(prev => prev ? { ...prev, localPos: flowPos } : null);
  }, [draggingEndpoint, screenToFlowPosition]);

  const handleEndpointPointerUp = useCallback((event: React.PointerEvent) => {
    if (!draggingEndpoint || !data?.onHandlesChange) {
      setDraggingEndpoint(null);
      return;
    }
    event.stopPropagation();
    (event.target as HTMLElement).releasePointerCapture(event.pointerId);
    const nodeId = draggingEndpoint.role === 'source' ? sourceId : targetId;
    const snapped = snapEndpoint(draggingEndpoint.localPos, nodeId);
    const currentSource = data.sourceEndpoint ?? { side: 'right' as HandleSide, offset: 0.5 };
    const currentTarget = data.targetEndpoint ?? { side: 'left' as HandleSide, offset: 0.5 };
    data.onHandlesChange(edgeKey, {
      source: draggingEndpoint.role === 'source' ? snapped : currentSource,
      target: draggingEndpoint.role === 'target' ? snapped : currentTarget,
    });
    setDraggingEndpoint(null);
  }, [draggingEndpoint, data, sourceId, targetId, edgeKey, snapEndpoint]);

  return (
    <>
      {isHovered && (
        <path
          d={edgePath}
          fill="none"
          stroke={strokeColor}
          strokeWidth={strokeWidth + 6}
          opacity={0.12}
          style={{ pointerEvents: 'none' }}
        />
      )}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          ...style,
          stroke: strokeColor,
          strokeWidth,
          transition: isDraggingAnything ? 'none' : 'stroke 160ms ease, stroke-width 160ms ease',
        }}
      />
      {isHovered && !isDraggingAnything && (
        <path
          d={edgePath}
          fill="none"
          stroke={strokeColor}
          strokeWidth={Math.max(strokeWidth - 0.6, 2)}
          strokeDasharray="8 6"
          opacity={0.75}
          style={{ pointerEvents: 'none' }}
        >
          <animate attributeName="stroke-dashoffset" from="14" to="0" dur="0.85s" repeatCount="indefinite" />
        </path>
      )}
      <path
        d={edgePath}
        fill="none"
        stroke="#000"
        strokeOpacity={0}
        strokeWidth={30}
        className="react-flow__edge-interaction"
        style={{ cursor: editable ? 'crosshair' : 'pointer', pointerEvents: 'all' }}
        onPointerEnter={showHover}
        onPointerLeave={scheduleHideHover}
        onDoubleClick={handleEdgeDoubleClick}
      />
      <circle
        cx={labelX}
        cy={labelY}
        r={20}
        fill="#000"
        fillOpacity={0}
        style={{ pointerEvents: 'all' }}
        onPointerEnter={showHover}
        onPointerLeave={scheduleHideHover}
      />
      {/* Draggable bend point handles */}
      {editable && activeBendPoints.map((bp, idx) => (
        <circle
          key={idx}
          cx={bp.x}
          cy={bp.y}
          r={5}
          fill={draggingIndex === idx ? '#3b82f6' : '#64748b'}
          stroke="#fff"
          strokeWidth={2}
          style={{ cursor: 'grab', pointerEvents: 'all' }}
          onPointerDown={(e) => handleBendPointPointerDown(e, idx)}
          onPointerMove={handleBendPointPointerMove}
          onPointerUp={handleBendPointPointerUp}
          onDoubleClick={(e) => handleBendPointDoubleClick(e, idx)}
        />
      ))}
      <EdgeLabelRenderer>
        {/* Node border highlight during endpoint drag */}
        {draggingEndpoint && dragNodeRect && (
          <div
            style={{
              position: 'absolute',
              transform: `translate(${dragNodeRect.x}px, ${dragNodeRect.y}px)`,
              width: dragNodeRect.w,
              height: dragNodeRect.h,
              border: '2px solid rgba(59, 130, 246, 0.4)',
              borderRadius: 12,
              pointerEvents: 'none',
              boxShadow: '0 0 12px rgba(59, 130, 246, 0.15)',
            }}
          />
        )}
        {/* Draggable endpoint handles (rendered in HTML layer above nodes) */}
        {endpointEditable && (isHovered || draggingEndpoint) && (
          <>
            <div
              className="nodrag nopan"
              style={{
                position: 'absolute',
                transform: `translate(-50%, -50%) translate(${draggingEndpoint?.role === 'source' && dragSnapPos ? dragSnapPos.x : sx}px,${draggingEndpoint?.role === 'source' && dragSnapPos ? dragSnapPos.y : sy}px)`,
                width: 14,
                height: 14,
                borderRadius: '50%',
                background: draggingEndpoint?.role === 'source' ? '#3b82f6' : '#64748b',
                border: '2px solid #fff',
                cursor: draggingEndpoint?.role === 'source' ? 'grabbing' : 'grab',
                pointerEvents: 'all',
                boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                zIndex: 10,
              }}
              onPointerDown={(e) => handleEndpointPointerDown('source', e)}
              onPointerMove={handleEndpointPointerMove}
              onPointerUp={handleEndpointPointerUp}
              onPointerEnter={showHover}
              onPointerLeave={scheduleHideHover}
            />
            <div
              className="nodrag nopan"
              style={{
                position: 'absolute',
                transform: `translate(-50%, -50%) translate(${draggingEndpoint?.role === 'target' && dragSnapPos ? dragSnapPos.x : tx}px,${draggingEndpoint?.role === 'target' && dragSnapPos ? dragSnapPos.y : ty}px)`,
                width: 14,
                height: 14,
                borderRadius: '50%',
                background: draggingEndpoint?.role === 'target' ? '#3b82f6' : '#64748b',
                border: '2px solid #fff',
                cursor: draggingEndpoint?.role === 'target' ? 'grabbing' : 'grab',
                pointerEvents: 'all',
                boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                zIndex: 10,
              }}
              onPointerDown={(e) => handleEndpointPointerDown('target', e)}
              onPointerMove={handleEndpointPointerMove}
              onPointerUp={handleEndpointPointerUp}
              onPointerEnter={showHover}
              onPointerLeave={scheduleHideHover}
            />
          </>
        )}
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
            zIndex: editable ? -1 : undefined,
          }}
          className="nodrag nopan flex flex-col items-center gap-1.5"
          onPointerEnter={showHover}
          onPointerLeave={scheduleHideHover}
        >
          {conditions.length > 0 && (
            <div className={`bg-[#eff6ff] border border-blue-200 rounded-lg px-4 py-2.5 text-sm font-semibold text-blue-700 transition-all duration-150 ${isHovered ? 'shadow-md ring-1 ring-slate-300' : 'shadow-sm'}`}>
              {conditions.map((condition, idx) => (
                <div key={idx} className="whitespace-nowrap">
                  {condition}
                </div>
              ))}
            </div>
          )}
          {showQuickDelete && (
            <button
              type="button"
              className="nodrag nopan inline-flex h-6 w-6 items-center justify-center rounded-full border border-red-300 bg-white text-sm font-bold text-red-600 shadow-sm transition-all duration-150 hover:scale-110 hover:bg-red-50"
              title="Supprimer lien"
              onPointerDown={(event) => event.stopPropagation()}
              onPointerEnter={showHover}
              onPointerLeave={scheduleHideHover}
              onClick={(event) => {
                event.stopPropagation();
                data?.onDeleteEdge?.(sourceId, targetId);
              }}
            >
              x
            </button>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const edgeTypes = {
  workflowEdge: MultiConditionEdge,
  multiCondition: MultiConditionEdge,
};

const HANDLE_HIT_SIZE = 18;

const SIDE_POSITION: Record<HandleSide, Position> = {
  top: Position.Top,
  right: Position.Right,
  bottom: Position.Bottom,
  left: Position.Left,
};

const ALL_SIDES: HandleSide[] = ['top', 'right', 'bottom', 'left'];

const getHandleStyle = (
  side: HandleSide,
  visible: boolean,
): CSSProperties => {
  const style: CSSProperties = {
    width: HANDLE_HIT_SIZE,
    height: HANDLE_HIT_SIZE,
    borderRadius: '9999px',
    border: 'none',
    background: visible
      ? 'radial-gradient(circle, rgba(100,116,139,0.9) 0 3px, rgba(100,116,139,0) 4px)'
      : 'transparent',
    boxShadow: 'none',
    opacity: visible ? 0.9 : 0,
    pointerEvents: visible ? 'auto' : 'none',
  };

  if (side === 'left') {
    style.top = '50%';
    style.left = -(HANDLE_HIT_SIZE / 2);
    style.transform = 'translateY(-50%)';
  } else if (side === 'right') {
    style.top = '50%';
    style.right = -(HANDLE_HIT_SIZE / 2);
    style.transform = 'translateY(-50%)';
  } else if (side === 'top') {
    style.left = '50%';
    style.top = -(HANDLE_HIT_SIZE / 2);
    style.transform = 'translateX(-50%)';
  } else {
    style.left = '50%';
    style.bottom = -(HANDLE_HIT_SIZE / 2);
    style.transform = 'translateX(-50%)';
  }

  return style;
};

function MultiHandleNode({ data, isConnectable }: NodeProps) {
  return (
    <div className="relative">
      {ALL_SIDES.map(side => (
        <Handle
          key={`tgt-${side}`}
          id={`tgt-${side}`}
          type="target"
          position={SIDE_POSITION[side]}
          isConnectable={isConnectable && side === 'left'}
          style={getHandleStyle(side, isConnectable && side === 'left')}
        />
      ))}
      {data.label}
      {ALL_SIDES.map(side => (
        <Handle
          key={`src-${side}`}
          id={`src-${side}`}
          type="source"
          position={SIDE_POSITION[side]}
          isConnectable={isConnectable && side === 'right'}
          style={getHandleStyle(side, isConnectable && side === 'right')}
        />
      ))}
    </div>
  );
}

const nodeTypes = { action: MultiHandleNode, diamond: MultiHandleNode };

export default function WorkflowPreview({
  blocks,
  getBlockDisplayNumber,
  campaignId,
  analyticsData: providedAnalyticsData,
  etatsCampagne,
  dateMin,
  dateMax,
  onSelectBlock,
  onAddChildBlock,
  onAddObjectiveChildBlock,
  onDuplicateBlock,
  onDeleteBlock,
  onDeleteEdge,
  fitViewSignal,
  modalOpen,
  showHeader = true,
  showFrame = true,
  containerClassName = 'workflow-preview border-t pt-6',
  height = 400,
  onLinkBlocks,
  onSelectionChange,
  selectedBlockIds = [],
  blockValidation,
  edgeValidation,
  layout,
  onLayoutChange,
  onClearLayout,
  onEdgeBendPointsChange,
  onEdgeHandlesChange,
}: WorkflowPreviewProps) {
  const apiClient = getApiClient();

  // Fetch campaign analytics only when the caller has not already supplied them.
  // DashboardPage already owns the same graph/table data, so reusing it avoids
  // a second expensive dashboard computation for the same campaign.
  const { data: fetchedAnalyticsData } = useQuery<DashboardComputeByCampaignResponse>({
    queryKey: ['campaign-analytics-by-campaign', campaignId, etatsCampagne, dateMin, dateMax],
    queryFn: () => apiClient.request<DashboardComputeByCampaignResponse>(
      dashboardApi.computeByCampaign({
        campagne_ids: campaignId ? [campaignId] : [],
        etats_campagne: etatsCampagne,
        date_min: dateMin,
        date_max: dateMax,
      })
    ),
    enabled: !!campaignId && !providedAnalyticsData,
    staleTime: 5 * 60 * 1000,
  });

  const analyticsData = providedAnalyticsData ?? fetchedAnalyticsData;

  // Build lookup map: graph node id -> graph node (for per-node Clients/Closed/Taux)
  const graphNodeMap = useMemo(() => {
    if (!analyticsData?.graph?.nodes) return new Map<string, CampaignGraphNode>();

    const map = new Map<string, CampaignGraphNode>();
    analyticsData.graph.nodes.forEach(node => {
      map.set(String(node.id), node);
    });
    return map;
  }, [analyticsData]);

  // Build lookup map: canal name -> channel stats (for Contacté per channel)
  const channelStatsMap = useMemo(() => {
    if (!analyticsData?.tables?.by_channel) return new Map<string, ChannelTableRow>();
    const map = new Map<string, ChannelTableRow>();
    analyticsData.tables.by_channel.forEach(row => {
      if (row.Canal && row.Canal !== 'Total') {
        map.set(row.Canal, row);
      }
    });
    return map;
  }, [analyticsData]);

  const selectedBlockIdSet = useMemo(() => new Set(selectedBlockIds), [selectedBlockIds]);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    // Helper functions for node styling
    const getCanalAccent = (canal: string): string => {
      const normalized = canal.trim().toLowerCase();
      if (normalized === 'sms') return '#f59e0b';
      if (normalized === 'mail' || normalized === 'email') return '#3b82f6';
      if (normalized === 'appel') return '#10b981';
      return '#6366f1';
    };

    const hexToRgba = (hex: string, alpha: number): string => {
      const normalized = hex.replace('#', '');
      if (normalized.length !== 6) {
        return `rgba(99, 102, 241, ${alpha})`;
      }
      const value = parseInt(normalized, 16);
      const r = (value >> 16) & 255;
      const g = (value >> 8) & 255;
      const b = value & 255;
      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    };

    // Build from blocks
    if (blocks.length === 0) {
      return { nodes: [], edges: [] };
    }

    const nodes: Node[] = [];
    const edges: Edge[] = [];

    // Create nodes (positions will be set by ELK)
    blocks.forEach(block => {
      const blockNumber = getBlockDisplayNumber(block.id);
      const warningCount = blockValidation?.[block.id] ?? 0;
      const isSelectedNode = selectedBlockIdSet.has(block.id);
      const accentColor = block.isObjectif ? '#10b981' : getCanalAccent(block.canal);
      const accentSoft = hexToRgba(accentColor, 0.14);
      const accentBorder = hexToRgba(accentColor, 0.4);
      const accentShadow = hexToRgba(accentColor, 0.16);
      const rawDescription = block.isObjectif ? '' : ((block.objet || '').trim() || (block.contenu || '').trim());
      const descriptionText = rawDescription || (block.delai ? `Delai: ${block.delai}j` : '');

      // Match block to graph node for per-node stats + channel stats
      const nodeId = block.id.replace(/^block_/, '');
      const graphNode = graphNodeMap.get(nodeId);
      const channelStats = channelStatsMap.get(block.canal);

      if (block.isObjectif) {
        const objectiveDetails = block.objectiveConditions.map(cond => {
          if (cond.type === 'client_field' && cond.clientField) {
            const name = cond.fieldLabel || cond.clientField;
            return { name, value: cond.clientFieldValue != null ? String(cond.clientFieldValue) : '' };
          }
          if (cond.type === 'client_filter' && cond.column) {
            const name = cond.fieldLabel || cond.column;
            const values = (cond.values || []).filter(Boolean);
            const min = (cond.min ?? '').toString().trim();
            const max = (cond.max ?? '').toString().trim();
            if (values.length > 0) return { name, value: values.join(', ') };
            if (min && max) return { name, value: `${min}-${max}` };
            if (min) return { name, value: `>= ${min}` };
            if (max) return { name, value: `<= ${max}` };
            return { name, value: '' };
          }
          const name = cond.fieldLabel || cond.column || cond.clientField || '?';
          return { name, value: '' };
        });

        nodes.push({
          id: block.id,
          type: 'diamond',
          position: { x: 0, y: 0 },
          sourcePosition: 'right',
          targetPosition: 'left',
          data: {
            label: (
              <div className="group relative px-3 py-2">
                <span className="pointer-events-none absolute right-2 top-1 text-3xl font-black text-emerald-200/70 select-none">
                  {blockNumber}
                </span>
                {warningCount > 0 && (
                  <span className="absolute right-2 top-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-bold text-white">
                    {warningCount}
                  </span>
                )}
                {(onAddChildBlock || onAddObjectiveChildBlock || onDuplicateBlock || onDeleteBlock) && (
                  <div className="absolute left-2 top-2 z-10 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    {onAddChildBlock && (
                      <button
                        type="button"
                        onClick={(event) => { event.stopPropagation(); onAddChildBlock(block.id); }}
                        onPointerDown={(event) => event.stopPropagation()}
                        className="nodrag rounded bg-white/95 px-1.5 py-0.5 text-[10px] font-semibold text-slate-700 shadow"
                        title="Ajouter un enfant action"
                      >
                        +A
                      </button>
                    )}
                    {onAddObjectiveChildBlock && (
                      <button
                        type="button"
                        onClick={(event) => { event.stopPropagation(); onAddObjectiveChildBlock(block.id); }}
                        onPointerDown={(event) => event.stopPropagation()}
                        className="nodrag rounded bg-white/95 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 shadow"
                        title="Ajouter un enfant objectif"
                      >
                        +O
                      </button>
                    )}
                    {onDuplicateBlock && (
                      <button
                        type="button"
                        onClick={(event) => { event.stopPropagation(); onDuplicateBlock(block.id); }}
                        onPointerDown={(event) => event.stopPropagation()}
                        className="nodrag rounded bg-white/95 px-1.5 py-0.5 text-[10px] font-semibold text-slate-700 shadow"
                        title="Dupliquer"
                      >
                        Dup
                      </button>
                    )}
                    {onDeleteBlock && (
                      <button
                        type="button"
                        onClick={(event) => { event.stopPropagation(); onDeleteBlock(block.id); }}
                        onPointerDown={(event) => event.stopPropagation()}
                        className="nodrag rounded bg-white/95 px-1.5 py-0.5 text-[10px] font-semibold text-red-600 shadow"
                        title="Supprimer"
                      >
                        Del
                      </button>
                    )}
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-emerald-500 text-sm">&#9670;</span>
                  <span className="text-sm font-semibold text-emerald-800 leading-tight">Objectif</span>
                </div>
                {objectiveDetails.length > 0 && (
                  <div className="mt-1.5 space-y-1">
                    {objectiveDetails.map((detail, idx) => (
                      <div key={idx}>
                        {idx > 0 && (
                          <span className="inline-block mb-1 rounded-full bg-emerald-100 px-1.5 py-0 text-[9px] font-semibold text-emerald-600">
                            {block.objectiveOperator}
                          </span>
                        )}
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="text-emerald-600 font-medium">{detail.name}</span>
                          {detail.value && <span className="text-emerald-900 font-semibold ml-2">{detail.value}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {graphNode && (
                  <div className="mt-2 rounded-lg bg-emerald-50 border border-emerald-200 px-2 py-1.5 space-y-0.5">
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-emerald-600 font-medium">Clients:</span>
                      <span className="text-emerald-900 font-semibold">{graphNode.count}</span>
                    </div>
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-emerald-600 font-medium">Convertis:</span>
                      <span className="text-emerald-900 font-semibold">{graphNode.converted_count}</span>
                    </div>
                    {graphNode.count > 0 && (
                      <div className="flex items-center justify-between text-[10px] pt-0.5 border-t border-emerald-300 mt-0.5">
                        <span className="text-emerald-600 font-medium">Taux:</span>
                        <span className="text-green-700 font-bold">
                          {((graphNode.converted_count / graphNode.count) * 100).toFixed(1)}%
                        </span>
                      </div>
                    )}
                  </div>
                )}
                {onAddChildBlock && (
                  <div className="mt-1.5 flex">
                    <button
                      type="button"
                      onClick={(event) => { event.stopPropagation(); onAddChildBlock(block.id); }}
                      onPointerDown={(event) => event.stopPropagation()}
                      onPointerDownCapture={(event) => event.stopPropagation()}
                      onMouseDownCapture={(event) => event.stopPropagation()}
                      className="nodrag inline-flex items-center rounded-md border border-emerald-400 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 bg-white"
                    >
                      + Ajouter enfant
                    </button>
                  </div>
                )}
              </div>
            ),
          },
          style: {
            background: `radial-gradient(circle at 90% 18%, ${accentSoft}, transparent 55%), linear-gradient(180deg, #ffffff 0%, #f0fdf4 100%)`,
            border: isSelectedNode ? '2px solid #0f172a' : warningCount > 0 ? '2px dashed #f59e0b' : `2px dashed ${accentBorder}`,
            borderRadius: '18px',
            fontSize: '12px',
            width: graphNode ? 260 : 240,
            cursor: onSelectBlock ? 'pointer' : 'default',
            boxShadow: isSelectedNode
              ? '0 0 0 3px rgba(15, 23, 42, 0.16), 0 12px 24px rgba(15, 23, 42, 0.12)'
              : `0 12px 24px rgba(15, 23, 42, 0.08), 0 6px 14px ${accentShadow}`,
          },
        } as Node);
      } else {
        // Regular rectangular node for action blocks
        nodes.push({
          id: block.id,
          type: 'action',
          position: { x: 0, y: 0 },
          sourcePosition: 'right',
          targetPosition: 'left',
          data: {
            label: (
              <div className="group relative px-3 py-2">
                <span className="pointer-events-none absolute right-2 top-1 text-3xl font-black text-slate-200/70 select-none">
                  {blockNumber}
                </span>
                {warningCount > 0 && (
                  <span className="absolute right-2 top-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-bold text-white">
                    {warningCount}
                  </span>
                )}
                {(onAddChildBlock || onAddObjectiveChildBlock || onDuplicateBlock || onDeleteBlock) && (
                  <div className="absolute left-2 top-2 z-10 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    {onAddChildBlock && (
                      <button
                        type="button"
                        onClick={(event) => { event.stopPropagation(); onAddChildBlock(block.id); }}
                        onPointerDown={(event) => event.stopPropagation()}
                        className="nodrag rounded bg-white/95 px-1.5 py-0.5 text-[10px] font-semibold text-slate-700 shadow"
                        title="Ajouter un enfant action"
                      >
                        +A
                      </button>
                    )}
                    {onAddObjectiveChildBlock && (
                      <button
                        type="button"
                        onClick={(event) => { event.stopPropagation(); onAddObjectiveChildBlock(block.id); }}
                        onPointerDown={(event) => event.stopPropagation()}
                        className="nodrag rounded bg-white/95 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 shadow"
                        title="Ajouter un enfant objectif"
                      >
                        +O
                      </button>
                    )}
                    {onDuplicateBlock && (
                      <button
                        type="button"
                        onClick={(event) => { event.stopPropagation(); onDuplicateBlock(block.id); }}
                        onPointerDown={(event) => event.stopPropagation()}
                        className="nodrag rounded bg-white/95 px-1.5 py-0.5 text-[10px] font-semibold text-slate-700 shadow"
                        title="Dupliquer"
                      >
                        Dup
                      </button>
                    )}
                    {onDeleteBlock && (
                      <button
                        type="button"
                        onClick={(event) => { event.stopPropagation(); onDeleteBlock(block.id); }}
                        onPointerDown={(event) => event.stopPropagation()}
                        className="nodrag rounded bg-white/95 px-1.5 py-0.5 text-[10px] font-semibold text-red-600 shadow"
                        title="Supprimer"
                      >
                        Del
                      </button>
                    )}
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: accentColor }} />
                  <span className="text-sm font-semibold text-slate-900 leading-tight">{block.canal}</span>
                </div>
                {descriptionText && (
                  <div className="mt-1 text-[10px] text-slate-500 truncate" title={descriptionText}>
                    {descriptionText}
                  </div>
                )}
                {(graphNode || channelStats) && (
                  <div className="mt-2 rounded-lg bg-slate-100 border border-slate-200 px-2 py-1.5 space-y-0.5">
                    {graphNode && (
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="text-slate-600 font-medium">Clients:</span>
                        <span className="text-slate-900 font-semibold">{graphNode.count}</span>
                      </div>
                    )}
                    {channelStats && (
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="text-slate-600 font-medium">Contacté:</span>
                        <span className="text-slate-900 font-semibold">{channelStats.Clients_contactes}</span>
                      </div>
                    )}
                  </div>
                )}
                {onAddChildBlock && (
                  <div className="mt-1.5 flex">
                    <button
                      type="button"
                      onClick={(event) => { event.stopPropagation(); onAddChildBlock(block.id); }}
                      onPointerDown={(event) => event.stopPropagation()}
                      onPointerDownCapture={(event) => event.stopPropagation()}
                      onMouseDownCapture={(event) => event.stopPropagation()}
                      className="nodrag inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold"
                      style={{ borderColor: accentBorder, color: accentColor, backgroundColor: '#ffffff' }}
                    >
                      + Ajouter enfant
                    </button>
                  </div>
                )}
              </div>
            ),
          },
          style: {
            background: `radial-gradient(circle at 90% 18%, ${accentSoft}, transparent 55%), linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)`,
            border: isSelectedNode ? '2px solid #0f172a' : warningCount > 0 ? '2px dashed #f59e0b' : `2px dashed ${accentBorder}`,
            borderRadius: '18px',
            fontSize: '12px',
            width: graphNode ? 260 : 220,
            cursor: onSelectBlock ? 'pointer' : 'default',
            boxShadow: isSelectedNode
              ? '0 0 0 3px rgba(15, 23, 42, 0.16), 0 12px 24px rgba(15, 23, 42, 0.12)'
              : `0 12px 24px rgba(15, 23, 42, 0.08), 0 6px 14px ${accentShadow}`,
          },
        } as Node);
      }

      // Add edges from each parent to this block
      for (const parentId of (block.parents || [])) {
        const parentConds = (block.conditionsByParent || {})[parentId] || [];
        const conditionLabels = parentConds.map(formatConditionLabel).filter(Boolean);
        const parentBlock = blocks.find(b => b.id === parentId);
        if (parentBlock?.isObjectif && block.valideObjectif) {
          conditionLabels.unshift(block.valideObjectif === 'Oui' ? 'Objectif: Oui' : 'Objectif: Non');
        }
        const edgeKey = `${parentId}->${block.id}`;
        const edgeWarningCount = edgeValidation?.[edgeKey] ?? 0;
        const strokeColor = edgeWarningCount > 0 ? '#f59e0b' : '#94a3b8';
        const strokeWidth = 2;
        const edgeBendPoints = layout?.edgeBendPoints?.[edgeKey];
        const savedHandles = layout?.edgeHandles?.[edgeKey];
        const srcSide: HandleSide = savedHandles?.source?.side ?? 'right';
        const tgtSide: HandleSide = savedHandles?.target?.side ?? 'left';

        edges.push({
          id: `e-${parentId}-${block.id}`,
          source: parentId,
          target: block.id,
          sourceHandle: `src-${srcSide}`,
          targetHandle: `tgt-${tgtSide}`,
          type: 'workflowEdge',
          animated: false,
          style: { stroke: strokeColor, strokeWidth },
          data: {
            conditions: conditionLabels.length > 0 ? conditionLabels : undefined,
            sourceId: parentId,
            targetId: block.id,
            warningCount: edgeWarningCount,
            onDeleteEdge,
            bendPoints: edgeBendPoints,
            onBendPointsChange: onEdgeBendPointsChange,
            sourceEndpoint: savedHandles?.source,
            targetEndpoint: savedHandles?.target,
            onHandlesChange: onEdgeHandlesChange,
          },
        });
      }
    });

    return { nodes, edges };
  }, [
    blocks,
    getBlockDisplayNumber,
    onAddChildBlock,
    onAddObjectiveChildBlock,
    onDuplicateBlock,
    onDeleteBlock,
    onDeleteEdge,
    onSelectBlock,
    graphNodeMap,
    channelStatsMap,
    analyticsData,
    campaignId,
    blockValidation,
    edgeValidation,
    selectedBlockIdSet,
    layout,
    onEdgeBendPointsChange,
    onEdgeHandlesChange,
  ]);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const flowInstanceRef = useRef<ReactFlowInstance | null>(null);
  const prevModalOpen = useRef<boolean | null>(null);
  const lastSelectionKeyRef = useRef<string>('');
  const initialNodesRef = useRef(initialNodes);
  const initialEdgesRef = useRef(initialEdges);
  initialNodesRef.current = initialNodes;
  initialEdgesRef.current = initialEdges;

  const handleConnect = useCallback((connection: Connection) => {
    if (onLinkBlocks && connection.source && connection.target) {
      onLinkBlocks(connection.source, connection.target);
    }
  }, [onLinkBlocks]);

  const handleNodeDragStop: NodeDragHandler = useCallback((_event, _node, draggedNodes) => {
    if (!onLayoutChange) return;
    const nodePositions: Record<string, NodePosition> = {};
    const allNodes = flowInstanceRef.current?.getNodes() || draggedNodes;
    for (const n of allNodes) {
      nodePositions[n.id] = { x: n.position.x, y: n.position.y };
    }
    onLayoutChange({ nodePositions, edgeBendPoints: layout?.edgeBendPoints, edgeHandles: layout?.edgeHandles });
  }, [onLayoutChange, layout?.edgeBendPoints, layout?.edgeHandles]);

  const handleSelectionUpdate = useCallback((params: { nodes: Node[] }) => {
    if (!onSelectionChange) return;
    const ids = params.nodes.map(node => node.id);
    const selectionKey = [...ids].sort().join('|');
    if (selectionKey === lastSelectionKeyRef.current) {
      return;
    }
    lastSelectionKeyRef.current = selectionKey;
    onSelectionChange(ids);
  }, [onSelectionChange]);

  const scheduleFitView = useCallback(() => {
    const instance = flowInstanceRef.current;
    if (!instance) {
      return;
    }
    requestAnimationFrame(() => {
      instance.fitView({ padding: 0.2, duration: 300 });
    });
    setTimeout(() => {
      instance.fitView({ padding: 0.2, duration: 300 });
    }, 60);
  }, []);

  // Apply ELK layout or saved layout when blocks/layout change
  useEffect(() => {
    const currentNodes = initialNodesRef.current;
    const currentEdges = initialEdgesRef.current;

    if (currentNodes.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    // If a saved layout exists and covers all blocks, use it directly
    if (layout?.nodePositions) {
      const positions = layout.nodePositions;
      const allCovered = currentNodes.every(n => positions[n.id]);
      if (allCovered) {
        setNodes(currentNodes.map(n => ({ ...n, position: positions[n.id] })));
        setEdges(currentEdges);
        return;
      }
    }

    // Otherwise run ELK auto-layout
    getLayoutedElements(currentNodes, currentEdges).then(({ nodes: layoutedNodes, edges: layoutedEdges }) => {
      setNodes(layoutedNodes);
      setEdges(layoutedEdges);
    }).catch((err) => {
      console.error('[WorkflowPreview] ELK layout failed:', err);
      setNodes(currentNodes.map(n => ({ ...n, position: { x: 0, y: 0 } })));
      setEdges(currentEdges);
    });
  }, [blocks, layout, setNodes, setEdges]);

  useEffect(() => {
    if (fitViewSignal === undefined || !flowInstanceRef.current || nodes.length === 0) {
      return;
    }
    if (nodes.length > 0) {
      scheduleFitView();
    }
  }, [fitViewSignal, nodes.length, scheduleFitView]);

  useEffect(() => {
    if (modalOpen === undefined) {
      return;
    }
    if (prevModalOpen.current && !modalOpen) {
      scheduleFitView();
    }
    prevModalOpen.current = modalOpen;
  }, [modalOpen, scheduleFitView]);

  if (blocks.length === 0) {
    return null;
  }

  const frameClassName = showFrame
    ? 'border border-gray-300 rounded-lg overflow-hidden'
    : '';
  const frameStyle = {
    height: typeof height === 'number' ? `${height}px` : height,
    width: '100%'
  };

  return (
    <div className={containerClassName} style={showFrame ? {} : frameStyle}>
      {showHeader && (
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Apercu du workflow</h3>
      )}
      <div
        className={frameClassName}
        style={{
          ...(showFrame ? frameStyle : { width: '100%', height: '100%' }),
        }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={
            onSelectBlock
              ? (_event, node) => onSelectBlock(node.id)
              : undefined
          }
          onInit={(instance) => {
            flowInstanceRef.current = instance;
          }}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.5}
          maxZoom={1.5}
          onConnect={onLinkBlocks ? handleConnect : undefined}
          onSelectionChange={onSelectionChange ? handleSelectionUpdate : undefined}
          connectionLineStyle={{ stroke: '#94a3b8', strokeWidth: 2 }}
          connectionRadius={36}
          nodesDraggable={!!onLayoutChange}
          onNodeDragStop={onLayoutChange ? handleNodeDragStop : undefined}
          nodesConnectable={!!onLinkBlocks}
          elementsSelectable={false}
          edgesFocusable={false}
          attributionPosition="bottom-right"
        >
          <Background color="#f1f5f9" gap={16} />
          <Controls />
          {onClearLayout && layout && (
            <div className="absolute top-2 right-2 z-10">
              <button
                type="button"
                onClick={onClearLayout}
                className="rounded-lg bg-white/90 border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50 transition-colors"
              >
                Reset positions
              </button>
            </div>
          )}
        </ReactFlow>
      </div>
    </div>
  );
}


