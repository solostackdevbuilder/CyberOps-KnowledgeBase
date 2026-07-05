import { ArrowLeft, Edit, Trash2, Loader2, Activity, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { Session, Operation } from '../types';

interface SessionHeaderProps {
  session: Session;
  operation: Operation | null;
  deleting: boolean;
  onEdit: () => void;
  onDelete: () => void;
}

/**
 * Header card for SessionDetail - title, operation link, operator,
 * targets, tools, findings, tags, created/updated timestamps, and
 * the Edit + Delete action buttons.
 *
 * Pure presentational. State (fetch, loading, deleting) stays in the
 * parent; this component only receives what it needs to render and
 * two callbacks for the action buttons. Back-to-sessions is handled
 * via its own internal useNavigate because the arrow lives visually
 * above the card and has always navigated that way.
 *
 * Split out of SessionDetail in Phase 4.2-followup so the parent
 * file stays focused on data-fetching + tabs.
 */
function SessionHeader({ session, operation, deleting, onEdit, onDelete }: SessionHeaderProps) {
  const navigate = useNavigate();

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <>
      <button
        onClick={() => navigate('/')}
        className="mb-4 flex items-center text-gray-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Sessions
      </button>

      <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-6">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">{session.title}</h1>

            <div className="mb-3 flex items-center gap-4 text-sm">
              {operation && (
                <a
                  href={`/operations/${session.operation_id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    navigate(`/operations/${session.operation_id}`);
                  }}
                  className="flex items-center text-blue-400 hover:text-blue-300 transition-colors"
                >
                  <Activity className="h-4 w-4 mr-1" />
                  {operation.name}
                </a>
              )}
              <div className="flex items-center text-gray-400">
                <User className="h-4 w-4 mr-1" />
                {session.operator_name}
              </div>
            </div>

            {session.description && (
              <p className="text-gray-400 mb-4 whitespace-pre-wrap">{session.description}</p>
            )}

            {(session.target && session.target.length > 0) && (
              <div className="mb-3">
                <div className="text-xs text-gray-500 mb-1">Targets:</div>
                <div className="flex flex-wrap gap-2">
                  {session.target.map((target, index) => (
                    <span
                      key={index}
                      className="px-2 py-1 bg-blue-600/20 text-blue-300 rounded text-xs border border-blue-600/30"
                    >
                      {target}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {(session.tools && session.tools.length > 0) && (
              <div className="mb-3">
                <div className="text-xs text-gray-500 mb-1">Tools:</div>
                <div className="flex flex-wrap gap-2">
                  {session.tools.map((tool, index) => (
                    <span
                      key={index}
                      className="px-2 py-1 bg-green-600/20 text-green-300 rounded text-xs border border-green-600/30"
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {(session.findings && session.findings.length > 0) && (
              <div className="mb-3">
                <div className="text-xs text-gray-500 mb-1">Findings:</div>
                <ul className="list-disc list-inside text-gray-300 text-sm space-y-1">
                  {session.findings.map((finding, index) => (
                    <li key={index}>{finding}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex flex-wrap gap-2 mb-4">
              {session.tags.map((tag, index) => (
                <span
                  key={index}
                  className="px-3 py-1 bg-gray-700 text-gray-300 rounded-md text-sm"
                >
                  {tag}
                </span>
              ))}
            </div>
            <div className="text-sm text-gray-500">
              <div>Created: {formatDate(session.created_at)}</div>
              <div>Updated: {formatDate(session.updated_at)}</div>
            </div>
          </div>
          <div className="flex space-x-2">
            <button
              onClick={onEdit}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors flex items-center"
              title="Edit session"
            >
              <Edit className="h-4 w-4 mr-2" />
              Edit
            </button>
            <button
              onClick={onDelete}
              disabled={deleting}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md transition-colors flex items-center disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {deleting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export default SessionHeader;
