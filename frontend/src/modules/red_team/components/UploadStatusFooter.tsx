import { Loader2, CheckCircle2, AlertTriangle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import ExtractionResult from './ExtractionResult';
import type { ScreenshotExtraction } from '../types';

type UploadState = 'idle' | 'uploading' | 'extracting' | 'complete';

interface UploadStatusFooterProps {
  uploadState: UploadState;
  extraction: ScreenshotExtraction | null;
  visionSupported: boolean | null;
}

/**
 * Status footer for ScreenshotUpload. Renders whichever of the four status
 * cards applies to the current (uploadState, extraction, visionSupported)
 * tuple:
 *
 *   - uploading       → blue card with spinner + "Uploading screenshot..."
 *   - extracting      → blue card with spinner + "Extracting text from image..."
 *   - complete + extraction            → ExtractionResult card
 *   - complete + no extraction + vision unsupported → orange card pointing at Settings
 *   - complete + no extraction + vision supported   → green success card
 *
 * Kept as a pure presentational component: no state, no event handlers
 * on anything except the "Settings" link (which navigates via the
 * router). Extracted from ScreenshotUpload in Phase 2.4 so the parent
 * file stays focused on upload orchestration.
 */
function UploadStatusFooter({
  uploadState,
  extraction,
  visionSupported,
}: UploadStatusFooterProps) {
  const navigate = useNavigate();

  if (uploadState === 'uploading') {
    return (
      <div className="mt-4 p-3 bg-blue-900/50 border border-blue-700 rounded-md">
        <div className="flex items-center gap-2 text-blue-200">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Uploading screenshot...</span>
        </div>
      </div>
    );
  }

  if (uploadState === 'extracting') {
    return (
      <div className="mt-4 p-3 bg-blue-900/50 border border-blue-700 rounded-md">
        <div className="flex items-center gap-2 text-blue-200">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Extracting text from image...</span>
        </div>
      </div>
    );
  }

  if (uploadState === 'complete' && extraction) {
    return (
      <div className="mt-4 animate-fade-in">
        <ExtractionResult extraction={extraction} />
      </div>
    );
  }

  if (uploadState === 'complete' && !extraction && visionSupported === false) {
    return (
      <div className="mt-4 p-3 bg-orange-900/50 border border-orange-700 rounded-md">
        <div className="flex items-start gap-2">
          <AlertTriangle className="h-5 w-5 text-orange-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm text-orange-200">
              ⚠️ Current LLM model does not support vision. Screenshot saved but text not extracted. Switch to Claude, OpenAI GPT-4, or Ollama LLaVA in{' '}
              <button
                onClick={() => navigate('/settings')}
                className="underline hover:text-orange-100 font-medium"
              >
                Settings
              </button>
              {' '}to enable this feature.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (uploadState === 'complete' && !extraction && visionSupported !== false) {
    return (
      <div className="mt-4 p-3 bg-green-900/50 border border-green-700 rounded-md animate-fade-in">
        <div className="flex items-center gap-2 text-green-200">
          <CheckCircle2 className="h-5 w-5" />
          <span className="text-sm">Screenshot uploaded successfully</span>
        </div>
      </div>
    );
  }

  return null;
}

export default UploadStatusFooter;
