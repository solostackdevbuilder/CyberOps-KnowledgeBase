import { useState } from 'react';
import { X } from 'lucide-react';
import type { FAAItemCreate } from '../types';

interface FAAAddModalProps {
  sessionId: string;
  onClose: () => void;
  onSave: (item: FAAItemCreate) => Promise<void>;
}

function FAAAddModal({ sessionId, onClose, onSave }: FAAAddModalProps) {
  const [classification, setClassification] = useState<'action' | 'finding'>('action');
  const [content, setContent] = useState('');
  const [output, setOutput] = useState('');
  const [mitreTechnique, setMitreTechnique] = useState('');
  const [mitreTactic, setMitreTactic] = useState('');
  const [severity, setSeverity] = useState<'critical' | 'high' | 'medium' | 'low' | ''>('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!content.trim()) return;

    setSaving(true);
    try {
      const item: FAAItemCreate = {
        session_id: sessionId,
        classification,
        content: content.trim(),
        output: output.trim() || undefined,
        mitre_technique: mitreTechnique.trim() || undefined,
        mitre_tactic: mitreTactic.trim() || undefined,
        severity: (severity || undefined) as 'critical' | 'high' | 'medium' | 'low' | undefined,
        timestamp: new Date().toISOString(),
        source: 'manual',
        notes: notes.trim() || undefined,
      };
      await onSave(item);
      onClose();
    } catch (error) {
      console.error('Failed to save:', error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-800 border border-gray-700 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-gray-800 border-b border-gray-700 p-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white">Add Manual FAA Item</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Classification *
            </label>
            <select
              value={classification}
              onChange={(e) => setClassification(e.target.value as 'action' | 'finding')}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="action">Action</option>
              <option value="finding">Finding</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Content *
            </label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
              placeholder="Describe the activity or finding..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Output
            </label>
            <textarea
              value={output}
              onChange={(e) => setOutput(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Command output or finding details..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              MITRE Technique
            </label>
            <input
              type="text"
              value={mitreTechnique}
              onChange={(e) => setMitreTechnique(e.target.value)}
              placeholder="e.g., T1046 - Network Service Discovery"
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              MITRE Tactic
            </label>
            <input
              type="text"
              value={mitreTactic}
              onChange={(e) => setMitreTactic(e.target.value)}
              placeholder="e.g., Discovery, Credential Access"
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {classification === 'finding' && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Severity
              </label>
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value as typeof severity)}
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">None</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Additional context or notes..."
            />
          </div>
        </div>

        <div className="sticky bottom-0 bg-gray-800 border-t border-gray-700 p-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !content.trim()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? 'Saving...' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default FAAAddModal;





