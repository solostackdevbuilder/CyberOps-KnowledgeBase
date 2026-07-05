import { useMemo } from 'react';
import { Network, Target, Activity } from 'lucide-react';
import type { NetworkDiagramResponse, NetworkNode } from '../services/api';

interface NetworkDiagramProps {
  data: NetworkDiagramResponse;
  onNodeClick?: (node: NetworkNode) => void;
}

function NetworkDiagram({ data, onNodeClick }: NetworkDiagramProps) {
  // Group nodes by type
  const nodesByType = useMemo(() => {
    const grouped: Record<string, NetworkNode[]> = {
      operation: [],
      session: [],
      target: [],
    };
    
    data.nodes.forEach((node) => {
      if (grouped[node.type]) {
        grouped[node.type].push(node);
      }
    });
    
    return grouped;
  }, [data.nodes]);

  const getNodeIcon = (type: string) => {
    switch (type) {
      case 'operation':
        return <Activity className="h-4 w-4" />;
      case 'session':
        return <Network className="h-4 w-4" />;
      case 'target':
        return <Target className="h-4 w-4" />;
      default:
        return null;
    }
  };

  const getNodeColor = (type: string) => {
    switch (type) {
      case 'operation':
        return 'bg-blue-500/20 border-blue-500 text-blue-400';
      case 'session':
        return 'bg-green-500/20 border-green-500 text-green-400';
      case 'target':
        return 'bg-purple-500/20 border-purple-500 text-purple-400';
      default:
        return 'bg-gray-500/20 border-gray-500 text-gray-400';
    }
  };

  // Build connections map
  const connections = useMemo(() => {
    const map = new Map<string, string[]>();
    
    data.edges.forEach((edge) => {
      if (!map.has(edge.from_id)) {
        map.set(edge.from_id, []);
      }
      map.get(edge.from_id)!.push(edge.to_id);
    });
    
    return map;
  }, [data.edges]);

  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <h2 className="text-xl font-semibold text-white mb-4">Network Diagram</h2>
      
      <div className="mb-4 flex gap-4 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-blue-500/20 border border-blue-500 rounded"></div>
          <span className="text-gray-400">Operations: {nodesByType.operation.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-green-500/20 border border-green-500 rounded"></div>
          <span className="text-gray-400">Sessions: {nodesByType.session.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-purple-500/20 border border-purple-500 rounded"></div>
          <span className="text-gray-400">Targets: {nodesByType.target.length}</span>
        </div>
      </div>

      {/* Network Visualization */}
      <div className="space-y-6">
        {/* Operations */}
        {nodesByType.operation.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-gray-400 mb-3">Operations</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {nodesByType.operation.map((node) => {
                const connectedSessions = connections.get(node.id) || [];
                return (
                  <div
                    key={node.id}
                    onClick={() => onNodeClick?.(node)}
                    className={`${getNodeColor(node.type)} border rounded-lg p-4 cursor-pointer hover:opacity-80 transition-opacity`}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      {getNodeIcon(node.type)}
                      <span className="font-semibold">{node.label}</span>
                    </div>
                    {node.metadata?.description && (
                      <p className="text-xs text-gray-400 mt-1 line-clamp-2">
                        {node.metadata.description}
                      </p>
                    )}
                    <div className="mt-2 text-xs text-gray-500">
                      {connectedSessions.length} session{connectedSessions.length !== 1 ? 's' : ''}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Sessions */}
        {nodesByType.session.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-gray-400 mb-3">Sessions</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
              {nodesByType.session.map((node) => {
                const connectedTargets = connections.get(node.id) || [];
                return (
                  <div
                    key={node.id}
                    onClick={() => onNodeClick?.(node)}
                    className={`${getNodeColor(node.type)} border rounded-lg p-3 cursor-pointer hover:opacity-80 transition-opacity`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      {getNodeIcon(node.type)}
                      <span className="font-medium text-sm">{node.label}</span>
                    </div>
                    {node.metadata?.operator && (
                      <p className="text-xs text-gray-500">by {node.metadata.operator}</p>
                    )}
                    {connectedTargets.length > 0 && (
                      <div className="mt-2 text-xs text-gray-500">
                        {connectedTargets.length} target{connectedTargets.length !== 1 ? 's' : ''}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Targets */}
        {nodesByType.target.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-gray-400 mb-3">Targets</h3>
            <div className="flex flex-wrap gap-2">
              {nodesByType.target.map((node) => (
                <div
                  key={node.id}
                  className={`${getNodeColor(node.type)} border rounded-lg px-3 py-2 cursor-pointer hover:opacity-80 transition-opacity`}
                >
                  <div className="flex items-center gap-2">
                    {getNodeIcon(node.type)}
                    <span className="text-sm font-medium">{node.label}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Connections Visualization */}
        {data.edges.length > 0 && (
          <div className="mt-6 pt-6 border-t border-gray-700">
            <h3 className="text-sm font-semibold text-gray-400 mb-3">Connections</h3>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {data.edges.map((edge, idx) => {
                const fromNode = data.nodes.find((n) => n.id === edge.from_id);
                const toNode = data.nodes.find((n) => n.id === edge.to_id);
                
                if (!fromNode || !toNode) return null;
                
                return (
                  <div
                    key={idx}
                    className="flex items-center gap-2 text-sm text-gray-400 bg-gray-700/50 rounded px-3 py-2"
                  >
                    <span className="font-medium text-blue-400">{fromNode.label}</span>
                    <span className="text-gray-600">→</span>
                    <span className="font-medium text-green-400">{toNode.label}</span>
                    {edge.label && (
                      <span className="ml-auto text-xs text-gray-500">({edge.label})</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default NetworkDiagram;





