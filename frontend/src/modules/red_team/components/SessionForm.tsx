import { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Loader2, Save, Sparkles, X, AlertCircle } from 'lucide-react';
import { createSession, getSession, updateSession, getOperations, extractMetadata } from '../services/api';
import type { SessionCreate, SessionUpdate, Operation, ExtractedMetadata } from '../types';

type FormStep = 'initial' | 'extracting' | 'review';

function SessionForm() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const isEditMode = !!id;
  const [step, setStep] = useState<FormStep>('initial');
  const [loading, setLoading] = useState(false);
  const [loadingSession, setLoadingSession] = useState(isEditMode);
  const [loadingOperations, setLoadingOperations] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [showNoOperationsModal, setShowNoOperationsModal] = useState(false);

  const [operations, setOperations] = useState<Operation[]>([]);
  const [formData, setFormData] = useState<Partial<SessionCreate>>({
    title: '',
    tags: [],
    terminal_content: '',
    operation_id: searchParams.get('operation_id') || '',
    operator_name: '',
  });

  const [tagsInput, setTagsInput] = useState('');
  const [, setExtractedMetadata] = useState<ExtractedMetadata>({
    targets: [],
    tools: [],
    findings: [],
  });
  const [targetsInput, setTargetsInput] = useState('');
  const [toolsInput, setToolsInput] = useState('');
  const [findingsInput, setFindingsInput] = useState('');

  useEffect(() => {
    loadOperations();
    if (isEditMode && id) {
      loadSession();
    }
  }, [id, isEditMode]);

  const loadOperations = async () => {
    try {
      setLoadingOperations(true);
      const data = await getOperations();
      setOperations(data);
      // If operation_id is in URL params and operations are loaded, set it
      if (searchParams.get('operation_id') && data.length > 0) {
        const opId = searchParams.get('operation_id');
        if (data.find(op => op.id === opId)) {
          setFormData(prev => ({ ...prev, operation_id: opId || '' }));
        }
      }
      // Check if no operations exist and user is trying to create (not edit)
      if (!isEditMode && data.length === 0) {
        setShowNoOperationsModal(true);
      }
    } catch (err: any) {
      console.error('Failed to load operations:', err);
    } finally {
      setLoadingOperations(false);
    }
  };

  const loadSession = async () => {
    try {
      setLoadingSession(true);
      const session = await getSession(id!);
      setFormData({
        title: session.title,
        description: session.description || '',
        tags: session.tags,
        terminal_content: session.terminal_content,
        operation_id: session.operation_id,
        operator_name: session.operator_name,
        target: session.target,
        tools: session.tools,
        findings: session.findings,
        primary_tool: session.primary_tool ?? undefined,
        documentation_time_minutes: session.documentation_time_minutes ?? undefined,
      });
      setTagsInput(session.tags.join(', '));
      setTargetsInput(session.target?.join(', ') || '');
      setToolsInput(session.tools?.join(', ') || '');
      setFindingsInput(session.findings?.join('\n') || '');
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load session');
    } finally {
      setLoadingSession(false);
    }
  };

  const handleInitialSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.operation_id) {
      setError('Please select an operation');
      return;
    }

    if (!formData.terminal_content?.trim()) {
      setError('Terminal content is required');
      return;
    }

    // In edit mode, skip extraction and go straight to save
    if (isEditMode) {
      await handleFinalSave();
      return;
    }

    // In create mode, proceed to extraction
    setStep('extracting');
    setError(null);

    try {
      const metadata = await extractMetadata(formData.terminal_content);
      setExtractedMetadata(metadata);
      setTargetsInput(metadata.targets.join(', '));
      setToolsInput(metadata.tools.join(', '));
      setFindingsInput(metadata.findings.join('\n'));
      setStep('review');
    } catch (err: any) {
      // If extraction fails, show empty fields and allow manual entry
      setError('AI extraction failed. You can manually enter the information below.');
      setExtractedMetadata({ targets: [], tools: [], findings: [] });
      setTargetsInput('');
      setToolsInput('');
      setFindingsInput('');
      setStep('review');
    }
  };

  const handleFinalSave = async () => {
    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      const tags = tagsInput
        .split(',')
        .map((tag) => tag.trim())
        .filter((tag) => tag.length > 0);

      const targets = targetsInput
        .split(',')
        .map((t) => t.trim())
        .filter((t) => t.length > 0);

      const tools = toolsInput
        .split(',')
        .map((t) => t.trim())
        .filter((t) => t.length > 0);

      const findings = findingsInput
        .split('\n')
        .map((f) => f.trim())
        .filter((f) => f.length > 0);

      const primaryTool = formData.primary_tool?.trim() || undefined;
      const docMinutes =
        typeof formData.documentation_time_minutes === 'number' &&
        Number.isFinite(formData.documentation_time_minutes) &&
        formData.documentation_time_minutes >= 0
          ? formData.documentation_time_minutes
          : undefined;

      if (isEditMode && id) {
        const updateData: SessionUpdate = {
          title: formData.title,
          description: formData.description,
          tags,
          terminal_content: formData.terminal_content,
          target: targets.length > 0 ? targets : undefined,
          tools: tools.length > 0 ? tools : undefined,
          findings: findings.length > 0 ? findings : undefined,
          primary_tool: primaryTool,
          documentation_time_minutes: docMinutes,
        };
        await updateSession(id, updateData);
        setSuccess(true);
        setTimeout(() => {
          navigate(`/session/${id}`);
        }, 1000);
      } else {
        const sessionData: SessionCreate = {
          title: formData.title!,
          description: formData.description,
          tags,
          terminal_content: formData.terminal_content!,
          operation_id: formData.operation_id!,
          operator_name: formData.operator_name!,
          target: targets.length > 0 ? targets : undefined,
          tools: tools.length > 0 ? tools : undefined,
          findings: findings.length > 0 ? findings : undefined,
          primary_tool: primaryTool,
          documentation_time_minutes: docMinutes,
        };
        const session = await createSession(sessionData);
        setSuccess(true);
        setTimeout(() => {
          navigate(`/session/${session.id}`);
        }, 1000);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || `Failed to ${isEditMode ? 'update' : 'create'} session`);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    if (step === 'review') {
      setStep('initial');
      setError(null);
    } else {
      navigate('/');
    }
  };

  if (loadingSession || loadingOperations) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  // Modal for no operations
  if (showNoOperationsModal && !isEditMode) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="bg-gray-800 border border-yellow-700 rounded-lg p-8">
          <div className="flex items-start mb-4">
            <AlertCircle className="h-6 w-6 text-yellow-400 mr-3 mt-0.5" />
            <div className="flex-1">
              <h2 className="text-2xl font-bold text-white mb-2">No Operations Found</h2>
              <p className="text-gray-300 mb-6">
                You need to create an operation before you can create a session. Operations help organize your red team activities.
              </p>
              <div className="flex space-x-4">
                <button
                  onClick={() => navigate('/operations/create')}
                  className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors flex items-center"
                >
                  <Save className="h-4 w-4 mr-2" />
                  Create Operation
                </button>
                <button
                  onClick={() => navigate('/operations')}
                  className="px-6 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md transition-colors"
                >
                  View Operations
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Step 2: AI Extraction (loading)
  if (step === 'extracting') {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="flex flex-col items-center justify-center min-h-[400px]">
          <Loader2 className="h-12 w-12 animate-spin text-blue-500 mb-4" />
          <h2 className="text-2xl font-bold text-white mb-2 flex items-center">
            <Sparkles className="h-6 w-6 mr-2 text-blue-400" />
            Analyzing terminal content with AI...
          </h2>
          <p className="text-gray-400">Extracting targets, tools, and findings from your terminal session</p>
        </div>
      </div>
    );
  }

  // Step 3: Review extracted metadata
  if (step === 'review') {
    return (
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-white mb-6">Review Extracted Information</h1>

        {error && (
          <div className="mb-4 p-4 bg-yellow-900/50 border border-yellow-700 rounded-md text-yellow-200">
            {error}
          </div>
        )}

        <div className="mb-6 p-4 bg-blue-900/20 border border-blue-700 rounded-md">
          <p className="text-blue-200">
            Review the extracted information below. You can edit any fields before saving the session.
          </p>
        </div>

        <div className="space-y-6">
          <div>
            <label htmlFor="targets" className="block text-sm font-medium text-gray-300 mb-2">
              Targets
            </label>
            <textarea
              id="targets"
              rows={3}
              value={targetsInput}
              onChange={(e) => setTargetsInput(e.target.value)}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y"
              placeholder="e.g., 192.168.1.0/24, example.com, 10.0.0.1"
            />
            <p className="text-xs text-gray-500 mt-1">Comma-separated list of targets</p>
          </div>

          <div>
            <label htmlFor="tools" className="block text-sm font-medium text-gray-300 mb-2">
              Tools Used
            </label>
            <textarea
              id="tools"
              rows={3}
              value={toolsInput}
              onChange={(e) => setToolsInput(e.target.value)}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y"
              placeholder="e.g., nmap, metasploit, burp suite, sqlmap"
            />
            <p className="text-xs text-gray-500 mt-1">Comma-separated list of tools</p>
          </div>

          <div>
            <label htmlFor="findings" className="block text-sm font-medium text-gray-300 mb-2">
              Findings
            </label>
            <textarea
              id="findings"
              rows={6}
              value={findingsInput}
              onChange={(e) => setFindingsInput(e.target.value)}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y"
              placeholder="Key findings and observations (one per line)"
            />
            <p className="text-xs text-gray-500 mt-1">One finding per line</p>
          </div>
        </div>

        {success && (
          <div className="mt-6 p-4 bg-green-900/50 border border-green-700 rounded-md text-green-200">
            Session {isEditMode ? 'updated' : 'created'} successfully! Redirecting...
          </div>
        )}

        <div className="flex justify-end space-x-4 mt-6">
          <button
            type="button"
            onClick={handleCancel}
            className="px-6 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md transition-colors flex items-center"
          >
            <X className="h-4 w-4 mr-2" />
            Cancel
          </button>
          <button
            type="button"
            onClick={handleFinalSave}
            disabled={loading}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Save Session
              </>
            )}
          </button>
        </div>
      </div>
    );
  }

  // Step 1: Initial form
  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold text-white mb-6">
        {isEditMode ? 'Edit Session' : 'Create New Session'}
      </h1>

      {error && (
        <div className="mb-4 p-4 bg-red-900/50 border border-red-700 rounded-md text-red-200">
          {error}
        </div>
      )}

      <form onSubmit={handleInitialSubmit} className="space-y-6">
        <div>
          <label htmlFor="operation_id" className="block text-sm font-medium text-gray-300 mb-2">
            Operation *
          </label>
          <select
            id="operation_id"
            required
            value={formData.operation_id}
            onChange={(e) => setFormData({ ...formData, operation_id: e.target.value })}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            disabled={isEditMode}
          >
            <option value="">Select an operation</option>
            {operations.map((op) => (
              <option key={op.id} value={op.id}>
                {op.name}
              </option>
            ))}
          </select>
          {operations.length === 0 && (
            <p className="text-sm text-yellow-400 mt-1">
              No operations available. <a href="/operations/create" className="underline">Create one first</a>.
            </p>
          )}
        </div>

        <div>
          <label htmlFor="title" className="block text-sm font-medium text-gray-300 mb-2">
            Title *
          </label>
          <input
            type="text"
            id="title"
            required
            value={formData.title}
            onChange={(e) => setFormData({ ...formData, title: e.target.value })}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="Enter session title"
          />
        </div>

        <div>
          <label htmlFor="operator_name" className="block text-sm font-medium text-gray-300 mb-2">
            Operator Name *
          </label>
          <input
            type="text"
            id="operator_name"
            required
            value={formData.operator_name}
            onChange={(e) => setFormData({ ...formData, operator_name: e.target.value })}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="e.g., operator name"
          />
        </div>

        <div>
          <label htmlFor="tags" className="block text-sm font-medium text-gray-300 mb-2">
            Tags (comma-separated)
          </label>
          <input
            type="text"
            id="tags"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="e.g., recon, nmap, scanning, web"
          />
        </div>

        <div>
          <label htmlFor="terminal_content" className="block text-sm font-medium text-gray-300 mb-2">
            Terminal Content *
          </label>
          <textarea
            id="terminal_content"
            required
            rows={20}
            value={formData.terminal_content}
            onChange={(e) => setFormData({ ...formData, terminal_content: e.target.value })}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white font-mono text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y"
            placeholder="Paste your terminal session content here..."
          />
        </div>

        {isEditMode && (
          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-300 mb-2">
              Additional Description
            </label>
            <textarea
              id="description"
              rows={4}
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y"
              placeholder="Additional notes or description"
            />
          </div>
        )}

        {isEditMode && (
          <div className="rounded-md border border-gray-700 bg-gray-900/40 p-4 space-y-4">
            <p className="text-xs uppercase tracking-wide text-gray-400">
              Session metadata - edit before running Analyze
            </p>
            <div>
              <label htmlFor="edit-targets" className="block text-sm font-medium text-gray-300 mb-2">
                Targets
              </label>
              <textarea
                id="edit-targets"
                rows={3}
                value={targetsInput}
                onChange={(e) => setTargetsInput(e.target.value)}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y"
                placeholder="e.g., 192.168.1.0/24, example.com, 10.0.0.1"
              />
              <p className="text-xs text-gray-500 mt-1">Comma-separated list of targets</p>
            </div>
            <div>
              <label htmlFor="edit-tools" className="block text-sm font-medium text-gray-300 mb-2">
                Tools Used
              </label>
              <textarea
                id="edit-tools"
                rows={3}
                value={toolsInput}
                onChange={(e) => setToolsInput(e.target.value)}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y"
                placeholder="e.g., nmap, metasploit, burp suite, sqlmap"
              />
              <p className="text-xs text-gray-500 mt-1">Comma-separated list of tools</p>
            </div>
            <div>
              <label htmlFor="edit-findings" className="block text-sm font-medium text-gray-300 mb-2">
                Findings
              </label>
              <textarea
                id="edit-findings"
                rows={6}
                value={findingsInput}
                onChange={(e) => setFindingsInput(e.target.value)}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y"
                placeholder="Key findings and observations (one per line)"
              />
              <p className="text-xs text-gray-500 mt-1">One finding per line - edit these preliminary bullets before Analyze generates structured FAA items</p>
            </div>
          </div>
        )}

        <div className="rounded-md border border-gray-700 bg-gray-900/40 p-4 space-y-3">
          <p className="text-xs uppercase tracking-wide text-gray-400">
            Measurement week (optional) - helps pick which tool we integrate next
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label htmlFor="primary_tool" className="block text-sm font-medium text-gray-300 mb-1">
                Primary tool
              </label>
              <input
                id="primary_tool"
                type="text"
                list="primary-tool-suggestions"
                value={formData.primary_tool ?? ''}
                onChange={(e) => setFormData({ ...formData, primary_tool: e.target.value || undefined })}
                placeholder="bloodhound, crackmapexec, burp, nmap, impacket, manual, ..."
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <datalist id="primary-tool-suggestions">
                <option value="bloodhound" />
                <option value="crackmapexec" />
                <option value="impacket" />
                <option value="burp" />
                <option value="nmap" />
                <option value="rubeus" />
                <option value="mimikatz" />
                <option value="responder" />
                <option value="sqlmap" />
                <option value="manual" />
                <option value="other" />
              </datalist>
            </div>
            <div>
              <label htmlFor="documentation_time_minutes" className="block text-sm font-medium text-gray-300 mb-1">
                Documentation time (minutes)
              </label>
              <input
                id="documentation_time_minutes"
                type="number"
                min={0}
                max={1440}
                value={formData.documentation_time_minutes ?? ''}
                onChange={(e) => {
                  const raw = e.target.value;
                  setFormData({
                    ...formData,
                    documentation_time_minutes: raw === '' ? undefined : Number(raw),
                  });
                }}
                placeholder="e.g. 15"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end space-x-4">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="px-6 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading || operations.length === 0}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                {isEditMode ? 'Updating...' : 'Creating...'}
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                {isEditMode ? 'Update Session' : 'Create Session'}
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}

export default SessionForm;
