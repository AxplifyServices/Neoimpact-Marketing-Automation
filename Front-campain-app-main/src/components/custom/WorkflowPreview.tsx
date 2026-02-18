import { useEffect, useMemo, useRef, useCallback, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type ReactFlowInstance,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from 'reactflow';
import 'reactflow/dist/style.css';
import ELK from 'elkjs/lib/elk.bundled.js';
import { useQuery } from '@tanstack/react-query';
import { getApiClient } from '@/lib/api/api-client';
import { dashboardApi } from '@/lib/api/definitions/dashboard.api';
import type { DashboardComputeByCampaignResponse, ChannelTableRow } from '@/types/dashboard.types';

const elk = new ELK();

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
  parentBlockId: string | null;
  objet?: string;
  contenu?: string;
  conditions: BlockCondition[];
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

interface WorkflowPreviewProps {
  blocks: Block[];
  getBlockDisplayNumber: (blockId: string) => number;
  campaignId?: string;
  onSelectBlock?: (blockId: string) => void;
  onAddChildBlock?: (blockId: string) => void;
  fitViewSignal?: number;
  modalOpen?: boolean;
  showHeader?: boolean;
  showFrame?: boolean;
  containerClassName?: string;
  height?: number | string;
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
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const conditions = data?.conditions as string[] || [];

  return (
    <>
      <BaseEdge id={id} path={edgePath} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="nodrag nopan w-fit"
        >
          <div className="bg-[#eff6ff] border border-blue-200 rounded-lg px-4 py-2.5 text-sm font-semibold text-blue-700 shadow-sm">
            {conditions.map((condition, idx) => (
              <div key={idx} className="whitespace-nowrap">
                {condition}
              </div>
            ))}
          </div>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const edgeTypes = {
  multiCondition: MultiConditionEdge,
};

export default function WorkflowPreview({
  blocks,
  getBlockDisplayNumber,
  campaignId,
  onSelectBlock,
  onAddChildBlock,
  fitViewSignal,
  modalOpen,
  showHeader = true,
  showFrame = true,
  containerClassName = 'workflow-preview border-t pt-6',
  height = 400,
}: WorkflowPreviewProps) {
  const apiClient = getApiClient();

  // Fetch campaign analytics when campaignId is provided
  const { data: analyticsData } = useQuery<DashboardComputeByCampaignResponse>({
    queryKey: ['campaign-analytics-by-campaign', campaignId],
    queryFn: () => apiClient.request<DashboardComputeByCampaignResponse>(
      dashboardApi.computeByCampaign({
        campagne_ids: campaignId ? [campaignId] : [],
      })
    ),
    enabled: !!campaignId,
    staleTime: 5 * 60 * 1000,
  });

  // Build lookup map: canal -> stats
  const channelStatsMap = useMemo(() => {
    if (!analyticsData?.tables?.by_channel) return new Map<string, ChannelTableRow>();

    const map = new Map<string, ChannelTableRow>();
    analyticsData.tables.by_channel.forEach(row => {
      if (row.Canal !== 'Total') {
        map.set(row.Canal.toLowerCase(), row);
      }
    });
    return map;
  }, [analyticsData]);

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

    // If we have graph data from API, use it directly
    if (analyticsData?.graph && campaignId) {
      const apiNodes: Node[] = [];
      const apiEdges: Edge[] = [];

      const { nodes: graphNodes, edges: graphEdges } = analyticsData.graph;

      // Create React Flow nodes from API graph nodes (positions will be set by ELK)
      graphNodes.forEach(graphNode => {
        const accentColor = getCanalAccent(graphNode.canal);
        const accentSoft = hexToRgba(accentColor, 0.14);
        const accentBorder = hexToRgba(accentColor, 0.4);
        const accentShadow = hexToRgba(accentColor, 0.16);

        apiNodes.push({
          id: graphNode.id,
          type: 'default',
          position: { x: 0, y: 0 }, // ELK will calculate positions
          sourcePosition: 'right',
          targetPosition: 'left',
          data: {
            label: (
              <div className="relative px-3 py-2">
                <span className="pointer-events-none absolute right-2 top-1 text-3xl font-black text-slate-200/70 select-none">
                  {graphNode.id}
                </span>
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: accentColor }} />
                  <span className="text-sm font-semibold text-slate-900 leading-tight">{graphNode.canal}</span>
                </div>
                <div className="mt-1 text-[10px] text-slate-500 truncate" title={graphNode.action}>
                  {graphNode.action}
                </div>
                <div className="mt-2 rounded-lg bg-slate-100 border border-slate-200 px-2 py-1.5 space-y-0.5">
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="text-slate-600 font-medium">Clients:</span>
                    <span className="text-slate-900 font-semibold">{graphNode.count}</span>
                  </div>
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="text-slate-600 font-medium">Closed:</span>
                    <span className="text-slate-900 font-semibold">{graphNode.closed_count}</span>
                  </div>
                  {graphNode.count > 0 && (
                    <div className="flex items-center justify-between text-[10px] pt-0.5 border-t border-slate-300 mt-0.5">
                      <span className="text-slate-600 font-medium">Taux:</span>
                      <span className="text-green-700 font-bold">
                        {((graphNode.closed_count / graphNode.count) * 100).toFixed(1)}%
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ),
          },
          style: {
            background: `radial-gradient(circle at 90% 18%, ${accentSoft}, transparent 55%), linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)`,
            border: `2px dashed ${accentBorder}`,
            borderRadius: '18px',
            fontSize: '12px',
            width: 260,
            cursor: onSelectBlock ? 'pointer' : 'default',
            boxShadow: `0 12px 24px rgba(15, 23, 42, 0.08), 0 6px 14px ${accentShadow}`,
          },
        } as Node);
      });

      const blockMap = new Map<string, Block>();
      blocks.forEach(block => {
        blockMap.set(block.id, block);
        blockMap.set(normalizeBlockId(block.id), block);
      });

      // Create edges from API graph edges
      graphEdges.forEach(edge => {
        const matchedBlock = blockMap.get(edge.to) || blockMap.get(normalizeBlockId(edge.to));
        const conditionLabels = (matchedBlock?.conditions || []).map(formatConditionLabel).filter(Boolean);

        apiEdges.push({
          id: `e-${edge.from}-${edge.to}`,
          source: edge.from,
          target: edge.to,
          type: conditionLabels.length > 0 ? 'multiCondition' : 'default',
          animated: false,
          style: { stroke: '#94a3b8', strokeWidth: 2 },
          data: conditionLabels.length > 0 ? { conditions: conditionLabels } : undefined,
        });
      });

      return { nodes: apiNodes, edges: apiEdges };
    }

    // Fallback: build from blocks if no API data
    if (blocks.length === 0) {
      return { nodes: [], edges: [] };
    }

    const nodes: Node[] = [];
    const edges: Edge[] = [];

    // Create nodes (positions will be set by ELK)
    blocks.forEach(block => {
      const blockNumber = getBlockDisplayNumber(block.id);
      const accentColor = getCanalAccent(block.canal);
      const accentSoft = hexToRgba(accentColor, 0.14);
      const accentBorder = hexToRgba(accentColor, 0.4);
      const accentShadow = hexToRgba(accentColor, 0.16);
      const rawDescription = (block.objet || '').trim() || (block.contenu || '').trim();
      const descriptionText = rawDescription || (block.delai ? `Delai: ${block.delai}j` : '');

      // Fetch stats for current block's channel
      const canalNormalized = block.canal.toLowerCase();
      const stats = channelStatsMap.get(canalNormalized);

      nodes.push({
        id: block.id,
        type: 'default',
        position: { x: 0, y: 0 }, // ELK will calculate positions
        sourcePosition: 'right',
        targetPosition: 'left',
        data: {
          label: (
            <div className="relative px-3 py-2">
              <span className="pointer-events-none absolute right-2 top-1 text-3xl font-black text-slate-200/70 select-none">
                {blockNumber}
              </span>
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: accentColor }} />
                <span className="text-sm font-semibold text-slate-900 leading-tight">{block.canal}</span>
              </div>
              {descriptionText && (
                <div className="mt-1 text-[10px] text-slate-500 truncate" title={descriptionText}>
                  {descriptionText}
                </div>
              )}
              {stats && (
                <div className="mt-2 rounded-lg bg-slate-100 border border-slate-200 px-2 py-1.5 space-y-0.5">
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="text-slate-600 font-medium">Traitements:</span>
                    <span className="text-slate-900 font-semibold">{stats.Traitements}</span>
                  </div>
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="text-slate-600 font-medium">Contactés:</span>
                    <span className="text-slate-900 font-semibold">{stats.Clients_contactes}</span>
                  </div>
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="text-slate-600 font-medium">Conversions:</span>
                    <span className="text-slate-900 font-semibold">{stats.Closing}</span>
                  </div>
                  {stats.Taux_closing_sur_traitements > 0 && (
                    <div className="flex items-center justify-between text-[10px] pt-0.5 border-t border-slate-300 mt-0.5">
                      <span className="text-slate-600 font-medium">Taux:</span>
                      <span className="text-green-700 font-bold">
                        {(stats.Taux_closing_sur_traitements * 100).toFixed(1)}%
                      </span>
                    </div>
                  )}
                </div>
              )}
              {onAddChildBlock && (
                <div className="mt-1.5 flex">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onAddChildBlock(block.id);
                    }}
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
          border: `2px dashed ${accentBorder}`,
          borderRadius: '18px',
          fontSize: '12px',
          width: stats ? 260 : 220,
          cursor: onSelectBlock ? 'pointer' : 'default',
          boxShadow: `0 12px 24px rgba(15, 23, 42, 0.08), 0 6px 14px ${accentShadow}`,
        },
      } as Node);

      // Add edge from parent to this block
      if (block.parentBlockId) {
        const conditionLabels = (block.conditions || []).map(formatConditionLabel).filter(Boolean);

        if (conditionLabels.length > 0) {
          // Use custom edge type to display multiple conditions vertically
          edges.push({
            id: `e-${block.parentBlockId}-${block.id}`,
            source: block.parentBlockId,
            target: block.id,
            type: 'multiCondition',
            animated: false,
            style: { stroke: '#94a3b8', strokeWidth: 2 },
            data: { conditions: conditionLabels },
          });
        } else {
          // No conditions, just create a single edge
          edges.push({
            id: `e-${block.parentBlockId}-${block.id}`,
            source: block.parentBlockId,
            target: block.id,
            type: 'default',
            animated: false,
            style: { stroke: '#94a3b8', strokeWidth: 2 },
            sourceHandle: null,
            targetHandle: null,
          });
        }
      }
    });

    return { nodes, edges };
  }, [blocks, getBlockDisplayNumber, onAddChildBlock, onSelectBlock, channelStatsMap, analyticsData, campaignId]);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [layoutReady, setLayoutReady] = useState(false);
  const flowInstanceRef = useRef<ReactFlowInstance | null>(null);
  const prevModalOpen = useRef<boolean | null>(null);

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

  // Apply ELK layout when nodes/edges change
  useEffect(() => {
    if (initialNodes.length === 0) {
      setNodes([]);
      setEdges([]);
      setLayoutReady(true);
      return;
    }

    setLayoutReady(false);

    getLayoutedElements(initialNodes, initialEdges).then(({ nodes: layoutedNodes, edges: layoutedEdges }) => {
      setNodes(layoutedNodes);
      setEdges(layoutedEdges);
      setLayoutReady(true);
      // Fit view after layout is applied
      setTimeout(() => {
        flowInstanceRef.current?.fitView({ padding: 0.2, duration: 300 });
      }, 50);
    });
  }, [initialNodes, initialEdges, setNodes, setEdges]);

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
          opacity: layoutReady ? 1 : 0,
          transition: 'opacity 0.2s ease-in-out',
        }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
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
          nodesDraggable={false}
          nodesConnectable={false}
          attributionPosition="bottom-right"
        >
          <Background color="#f1f5f9" gap={16} />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}

