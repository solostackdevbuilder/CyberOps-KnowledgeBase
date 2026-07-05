import { useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { TimelineResponse, TimelineEvent } from '../services/api';

interface TimelineChartProps {
  data: TimelineResponse;
  onEventClick?: (event: TimelineEvent) => void;
}

function TimelineChart({ data, onEventClick }: TimelineChartProps) {
  // Transform data for Gantt-style chart
  const chartData = useMemo(() => {
    // Group events by date
    const eventsByDate = new Map<string, TimelineEvent[]>();
    
    data.events.forEach((event) => {
      const date = new Date(event.start_time).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
      
      if (!eventsByDate.has(date)) {
        eventsByDate.set(date, []);
      }
      eventsByDate.get(date)!.push(event);
    });

    // Convert to chart format
    const chartDataArray = Array.from(eventsByDate.entries()).map(([date, events]) => {
      const operations = events.filter((e) => e.type === 'operation').length;
      const sessions = events.filter((e) => e.type === 'session').length;
      
      return {
        date,
        operations,
        sessions,
        total: events.length,
        events, // Store for tooltip
      };
    });

    return chartDataArray.sort((a, b) => 
      new Date(a.date).getTime() - new Date(b.date).getTime()
    );
  }, [data]);

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-lg">
          <p className="text-white font-semibold mb-2">{data.date}</p>
          <p className="text-blue-400 text-sm">Operations: {data.operations}</p>
          <p className="text-green-400 text-sm">Sessions: {data.sessions}</p>
          <p className="text-gray-400 text-sm">Total: {data.total}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <h2 className="text-xl font-semibold text-white mb-4">Timeline Overview</h2>
      
      {/* Event List */}
      <div className="mb-6 space-y-2 max-h-96 overflow-y-auto">
        {data.events.map((event) => (
          <div
            key={event.id}
            onClick={() => onEventClick?.(event)}
            className={`bg-gray-700 rounded-lg p-3 cursor-pointer hover:bg-gray-600 transition-colors ${
              event.type === 'operation' ? 'border-l-4 border-blue-500' : 'border-l-4 border-green-500'
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-1 rounded text-xs font-semibold ${
                      event.type === 'operation'
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'bg-green-500/20 text-green-400'
                    }`}
                  >
                    {event.type === 'operation' ? 'Operation' : 'Session'}
                  </span>
                  <span className="text-white font-medium">{event.title}</span>
                  {event.operation_name && (
                    <span className="text-gray-400 text-sm">
                      ({event.operation_name})
                    </span>
                  )}
                </div>
                <div className="mt-1 text-sm text-gray-400">
                  {new Date(event.start_time).toLocaleString()}
                  {event.end_time && event.end_time !== event.start_time && (
                    <span> → {new Date(event.end_time).toLocaleString()}</span>
                  )}
                </div>
                {event.metadata && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {event.metadata.tools && event.metadata.tools.length > 0 && (
                      <span className="text-xs text-gray-500">
                        Tools: {event.metadata.tools.join(', ')}
                      </span>
                    )}
                    {event.metadata.targets && event.metadata.targets.length > 0 && (
                      <span className="text-xs text-gray-500">
                        Targets: {event.metadata.targets.length}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div className="mt-6">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis
              dataKey="date"
              stroke="#9CA3AF"
              angle={-45}
              textAnchor="end"
              height={80}
              tick={{ fill: '#9CA3AF', fontSize: 12 }}
            />
            <YAxis stroke="#9CA3AF" tick={{ fill: '#9CA3AF' }} />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            <Bar dataKey="operations" fill="#3B82F6" name="Operations" />
            <Bar dataKey="sessions" fill="#10B981" name="Sessions" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default TimelineChart;

