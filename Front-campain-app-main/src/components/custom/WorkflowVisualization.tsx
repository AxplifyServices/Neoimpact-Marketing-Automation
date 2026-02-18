import { useMemo, useState, useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import {
  ReactFlow,
  Controls,
  Background,
  BackgroundVariant,
  Panel,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  BaseEdge,
  getSmoothStepPath,
  type Node,
  type Edge,
  type EdgeProps,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import ELK from 'elkjs/lib/elk.bundled.js';
import { parseObjectif, formatObjectifSummary } from '@/lib/utils';

interface WorkflowAction {
  ID: number;
  Bloc_mère: string;
  Canal: string;
  Action: string;
  Objet: string;
  Contenu: string;
  Conditions: Array<{
    field: string;
    op: string;
    value: string;
  }>;
}

interface WorkflowVisualizationProps {
  listeActionJson: string;
  variableCible?: string;
  objectif?: string;
  compact?: boolean;
}

/* ----------------------- Nodes ----------------------- */
function CustomNode({ data }: { data: any }) {
  return (
    <>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div
        className={`px-6 py-2 bg-white rounded-full font-medium text-sm whitespace-nowrap ${
          data.isStart ? 'border-2 border-gray-900' : 'border-2 border-gray-300'
        }`}
      >
        {data.label}
      </div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </>
  );
}

/* ----------------------- Edges ----------------------- */
function CustomEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  label,
  markerEnd,
  style,
  sourcePosition,
  targetPosition,
}: EdgeProps) {
  // compute path
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  // Position label near target node (85% along the edge)
  const labelX = sourceX + 0.85 * (targetX - sourceX);
  const labelY = sourceY + 0.85 * (targetY - sourceY);

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />
      {label && (
        <foreignObject
          width={1}
          height={1}
          x={labelX}
          y={labelY}
          style={{ overflow: 'visible' }}
        >
          <div
            style={{
              position: 'absolute',
              transform: 'translate(-50%, -50%)',
              pointerEvents: 'all',
            }}
            className="bg-white px-3 py-1.5 rounded-md shadow-md border-2 border-blue-300 text-xs font-medium text-gray-700 whitespace-pre-line text-center"
          >
            {label}
          </div>
        </foreignObject>
      )}
    </>
  );
}

const nodeTypes = { custom: CustomNode };
const edgeTypes = { custom: CustomEdge };

/* ----------------------- Component ----------------------- */
export function WorkflowVisualization({
  listeActionJson,
  variableCible,
  objectif,
  compact = false,
}: WorkflowVisualizationProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const flowInstanceRef = useRef<ReactFlowInstance | null>(null);

  // Handle ESC key to close modal
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false);
      }
    };

    if (isFullscreen) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isFullscreen]);

  const actions = useMemo<WorkflowAction[]>(() => {
    try {
      return JSON.parse(listeActionJson);
    } catch {
      return [];
    }
  }, [listeActionJson]);

  const workflowTree = useMemo(() => [...actions].sort((a, b) => a.ID - b.ID), [
    actions,
  ]);

  const parsedObjectif = useMemo(() => objectif ? parseObjectif(objectif) : null, [objectif]);
  const hasStart = Boolean(objectif && parsedObjectif && parsedObjectif.kind !== 'empty');

  /* ----------------------- Nodes & Edges ----------------------- */
  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    if (hasStart && parsedObjectif) {
      // For multi-objectif, use formatted summary; for single, show variable = value
      const startLabel = parsedObjectif.kind === 'multi'
        ? formatObjectifSummary(parsedObjectif)
        : variableCible
          ? `${variableCible} = ${formatObjectifSummary(parsedObjectif)}`
          : formatObjectifSummary(parsedObjectif);

      nodes.push({
        id: 'start',
        type: 'custom',
        position: { x: 0, y: 0 },
        data: { label: startLabel, isStart: true },
      });
    }

    workflowTree.forEach((action) => {
      const nodeId = `action-${action.ID}`;

      nodes.push({
        id: nodeId,
        type: 'custom',
        position: { x: 0, y: 0 },
        data: { label: action.Canal, isStart: false },
      });

      const sourceId =
        action.Bloc_mère && action.Bloc_mère !== 'start'
          ? `action-${action.Bloc_mère}`
          : 'start';

      if (sourceId === 'start' && !hasStart) return;

      // --------- Build human-friendly label -----------
      const edgeLabel =
        action.Conditions?.length > 0
          ? action.Conditions
              .map((c) => {
                if (c.field.startsWith('Flag '))
                  return `${c.value}`;
                if (c.field.startsWith('NB jours'))
                  return `jours ${c.op.replace('>=', '≥').replace('<=', '<=')}${c.value ? ` ${c.value}` : ''}`.replace('<= ', '< ').replace('>= ', '≥ ');
                const parts = c.field.split(' ');
                return `${parts[parts.length - 1]} ${c.op} ${c.value}`;
              })
              .join('\n')
          : '';

      edges.push({
        id: `edge-${sourceId}-${nodeId}`,
        source: sourceId,
        target: nodeId,
        type: 'custom',
        label: edgeLabel,
        style: { stroke: '#9ca3af', strokeWidth: 2 },
        markerEnd: { type: 'arrowclosed', width: 20, height: 20, color: '#9ca3af' },
      });
    });

    return { nodes, edges };
  }, [workflowTree, variableCible, parsedObjectif, hasStart]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  /* ----------------------- ELK Layout ----------------------- */
  useEffect(() => {
    const elk = new ELK();

    const graph = {
      id: 'root',
      layoutOptions: {
        'elk.algorithm': 'layered',
        'elk.direction': 'RIGHT',
        'elk.edgeRouting': 'SPLINES',
        'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
        'elk.spacing.nodeNode': '100',
        'elk.layered.spacing.nodeNodeBetweenLayers': '300',
      },
      children: initialNodes.map((n) => ({ id: n.id, width: 220, height: 44 })),
      edges: initialEdges.map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })),
    };

    elk.layout(graph).then((layouted) => {
      setNodes((nds) =>
        nds.map((n) => {
          const ln = layouted.children?.find((c) => c.id === n.id);
          return { ...n, position: { x: ln?.x ?? 0, y: ln?.y ?? 0 } };
        })
      );
    });
  }, [initialNodes, initialEdges, setNodes]);

  /* ----------------------- Empty state ----------------------- */
  if (actions.length === 0) {
    return (
      <div className="h-full bg-gray-100 flex items-center justify-center rounded">
        <span className="text-gray-400 text-sm">No workflow data</span>
      </div>
    );
  }

  /* ----------------------- Flow Props ----------------------- */
  const flowProps = {
    nodes,
    edges,
    nodeTypes,
    edgeTypes,
    onNodesChange,
    onEdgesChange,
    nodesDraggable: false,
    nodesConnectable: false,
    elementsSelectable: false,
    nodesFocusable: false,
    edgesFocusable: false,
    attributionPosition: 'bottom-right' as const,
    proOptions: { hideAttribution: true },
  };
  const fitViewOptions = useMemo(() => ({ padding: 0.6, maxZoom: 0.8 }), []);

  const handleInit = (instance: ReactFlowInstance) => {
    flowInstanceRef.current = instance;
    requestAnimationFrame(() => {
      instance.fitView(fitViewOptions);
    });
  };

  useEffect(() => {
    if (!flowInstanceRef.current || nodes.length === 0) return;
    const frame = requestAnimationFrame(() => {
      flowInstanceRef.current?.fitView(fitViewOptions);
    });
    return () => cancelAnimationFrame(frame);
  }, [nodes, edges, isFullscreen, fitViewOptions]);

  /* ----------------------- Compact Mode ----------------------- */
  if (compact) {
    return (
      <>
        <div className="cursor-pointer h-full bg-white rounded-lg overflow-hidden" onClick={() => setIsFullscreen(true)}>
          <ReactFlow {...flowProps} fitView fitViewOptions={fitViewOptions} minZoom={0.1} maxZoom={2} zoomOnScroll={false} onInit={handleInit}>
            <Background variant={BackgroundVariant.Dots} gap={12} size={1} color="#e5e7eb" />
          </ReactFlow>
        </div>

        {isFullscreen && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-8" onClick={() => setIsFullscreen(false)}>
            <div className="relative bg-white rounded-2xl shadow-2xl w-full h-full max-w-[95vw] max-h-[95vh]" onClick={(e) => e.stopPropagation()}>
              <button
                onClick={() => setIsFullscreen(false)}
                className="absolute top-6 right-6 z-10 p-2 hover:bg-gray-100 rounded-full transition-colors"
                aria-label="Close"
              >
                <X className="w-6 h-6 text-gray-600" />
              </button>
              <div className="w-full h-full">
                <ReactFlow {...flowProps} fitView fitViewOptions={fitViewOptions} minZoom={0.1} maxZoom={2} onInit={handleInit}>
                  <Controls />
                  <Background variant={BackgroundVariant.Dots} gap={12} size={1} color="#e5e7eb" />
                  <Panel position="top-left" className="bg-white p-4 rounded-lg shadow-lg m-4">
                    <h2 className="text-xl font-bold text-gray-900">Workflow Détaillé</h2>
                    <p className="text-sm text-gray-500 mt-1">{workflowTree.length} étape{workflowTree.length > 1 ? 's' : ''}</p>
                  </Panel>
                </ReactFlow>
              </div>
            </div>
          </div>
        )}
      </>
    );
  }

  /* ----------------------- Full Mode ----------------------- */
  return (
    <div className="w-full h-full bg-white rounded-lg">
      <ReactFlow {...flowProps} fitView fitViewOptions={fitViewOptions} minZoom={0.1} maxZoom={2} onInit={handleInit}>
        <Controls />
        <Background variant={BackgroundVariant.Dots} gap={12} size={1} color="#e5e7eb" />
      </ReactFlow>
    </div>
  );
}
