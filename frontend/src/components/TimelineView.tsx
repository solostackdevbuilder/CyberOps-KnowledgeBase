import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Calendar, Network, Target, Filter, Loader2 } from 'lucide-react';
import {
  getOperationsTimeline,
  getNetworkDiagram,
} from '../services/api';
import { getOperations } from '../modules/red_team/services/api';
import type { Operation } from '../modules/red_team/types';
import type { TimelineResponse, NetworkDiagramResponse } from '../services/api';
import TimelineChart from './TimelineChart';
import NetworkDiagram from './NetworkDiagram';
import KillChainVisualization from './KillChainVisualization';

function TimelineView() {
  const navigate = useNavigate();
  const [timelineData, setTimelineData] = useState<TimelineResponse | null>(null);
  const [networkData, setNetworkData] = useState<NetworkDiagramResponse | null>(null);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [selectedOperationId, setSelectedOperationId] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'timeline' | 'network' | 'killchain'>('timeline');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadOperations();
  }, []);

  useEffect(() => {
    loadTimelineData();
    loadNetworkData();
  }, [selectedOperationId]);

  const loadOperations = async () => {
    try {
      const data = await getOperations();
      setOperations(data);
    } catch (err: any) {
      console.error('Failed to load operations:', err);
    }
  };

  const loadTimelineData = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getOperationsTimeline(
        selectedOperationId || undefined
      );
      setTimelineData(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load timeline');
    } finally {
      setLoading(false);
    }
  };

  const loadNetworkData = async () => {
    try {
      const data = await getNetworkDiagram(selectedOperationId || undefined);
      setNetworkData(data);
    } catch (err: any) {
      console.error('Failed to load network diagram:', err);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Timeline & Visualization</h1>
          <p className="text-gray-400 mt-1">
            Interactive timeline, network diagrams, and kill chain visualization
          </p>
        </div>
      </div>

      {/* Filter */}
      <div className="bg-gray-800 rounded-lg p-4">
        <div className="flex items-center gap-4">
          <Filter className="h-5 w-5 text-gray-400" />
          <label className="text-sm font-medium text-gray-300">Filter by Operation:</label>
          <select
            value={selectedOperationId}
            onChange={(e) => setSelectedOperationId(e.target.value)}
            className="bg-gray-700 text-white border border-gray-600 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Operations</option>
            {operations.map((op) => (
              <option key={op.id} value={op.id}>
                {op.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-700">
        <nav className="flex space-x-8">
          <button
            onClick={() => setActiveTab('timeline')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'timeline'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-gray-400 hover:text-gray-300'
            }`}
          >
            <Calendar className="h-4 w-4 inline mr-2" />
            Timeline
          </button>
          <button
            onClick={() => setActiveTab('network')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'network'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-gray-400 hover:text-gray-300'
            }`}
          >
            <Network className="h-4 w-4 inline mr-2" />
            Network Diagram
          </button>
          <button
            onClick={() => setActiveTab('killchain')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'killchain'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-gray-400 hover:text-gray-300'
            }`}
          >
            <Target className="h-4 w-4 inline mr-2" />
            Kill Chain
          </button>
        </nav>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
          <span className="ml-3 text-gray-400">Loading visualization data...</span>
        </div>
      ) : error ? (
        <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
          <p className="text-red-400">{error}</p>
        </div>
      ) : (
        <>
          {activeTab === 'timeline' && timelineData && (
            <div className="space-y-4">
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="grid grid-cols-4 gap-4 text-sm">
                  <div>
                    <span className="text-gray-400">Total Operations:</span>
                    <span className="ml-2 text-white font-semibold">
                      {timelineData.total_operations}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-400">Total Sessions:</span>
                    <span className="ml-2 text-white font-semibold">
                      {timelineData.total_sessions}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-400">Start Date:</span>
                    <span className="ml-2 text-white">
                      {formatDate(timelineData.start_date)}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-400">End Date:</span>
                    <span className="ml-2 text-white">
                      {formatDate(timelineData.end_date)}
                    </span>
                  </div>
                </div>
              </div>
              <TimelineChart data={timelineData} onEventClick={(event) => {
                if (event.type === 'session') {
                  navigate(`/session/${event.id}`);
                } else if (event.type === 'operation') {
                  navigate(`/operations/${event.id}`);
                }
              }} />
            </div>
          )}

          {activeTab === 'network' && networkData && (
            <NetworkDiagram data={networkData} onNodeClick={(node) => {
              if (node.type === 'operation' && node.metadata?.operation_id) {
                navigate(`/operations/${node.metadata.operation_id}`);
              } else if (node.type === 'session' && node.metadata?.session_id) {
                navigate(`/session/${node.metadata.session_id}`);
              }
            }} />
          )}

          {activeTab === 'killchain' && selectedOperationId && (
            <KillChainVisualization operationId={selectedOperationId} />
          )}

          {activeTab === 'killchain' && !selectedOperationId && (
            <div className="bg-gray-800 rounded-lg p-8 text-center">
              <Target className="h-12 w-12 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400">
                Please select an operation to view kill chain visualization
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default TimelineView;

