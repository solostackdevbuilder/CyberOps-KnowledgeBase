import { useState } from 'react';
import { FileText, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { retryExtraction } from '../services/api';
import ExtractionResult from './ExtractionResult';
import type { ScreenshotExtraction } from '../types';

interface ExtractButtonProps {
  sessionId: string;
  filename: string;
  extraction?: ScreenshotExtraction;
  onExtracted?: (extraction: ScreenshotExtraction) => void;
  variant?: 'default' | 'small' | 'icon';
}

function ExtractButton({ 
  sessionId, 
  filename, 
  extraction,
  onExtracted,
  variant = 'default'
}: ExtractButtonProps) {
  const [extracting, setExtracting] = useState(false);
  const [result, setResult] = useState<ScreenshotExtraction | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExtract = async () => {
    try {
      setExtracting(true);
      setError(null);
      setResult(null);
      
      const extractionResult = await retryExtraction(sessionId, filename);
      setResult(extractionResult);
      
      if (onExtracted) {
        onExtracted(extractionResult);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to extract text');
    } finally {
      setExtracting(false);
    }
  };

  // If extraction already exists and is successful, show result
  if (extraction && extraction.extraction_status === 'success' && !result) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-green-400 text-sm">
          <CheckCircle2 className="h-4 w-4" />
          <span>Text already extracted</span>
        </div>
        <ExtractionResult extraction={extraction} />
      </div>
    );
  }

  // If we have a result, show it
  if (result) {
    return (
      <div className="space-y-2">
        <ExtractionResult 
          extraction={result} 
          onRetry={handleExtract}
        />
      </div>
    );
  }

  // Show button based on variant
  if (variant === 'icon') {
    return (
      <button
        onClick={handleExtract}
        disabled={extracting}
        className="p-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        title="Extract text from screenshot"
        aria-label="Extract text from screenshot"
      >
        {extracting ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <FileText className="h-4 w-4" />
        )}
      </button>
    );
  }

  if (variant === 'small') {
    return (
      <button
        onClick={handleExtract}
        disabled={extracting}
        className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        aria-label="Extract text from screenshot"
      >
        {extracting ? (
          <>
            <Loader2 className="h-3 w-3 animate-spin" />
            Extracting...
          </>
        ) : (
          <>
            <FileText className="h-3 w-3" />
            Extract Text
          </>
        )}
      </button>
    );
  }

  return (
    <div className="space-y-2">
      <button
        onClick={handleExtract}
        disabled={extracting}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        aria-label="Extract text from screenshot"
      >
        {extracting ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Analyzing image...
          </>
        ) : (
          <>
            <FileText className="h-4 w-4" />
            Extract Text
          </>
        )}
      </button>
      
      {error && (
        <div className="p-2 bg-red-900/50 border border-red-700 rounded-md text-red-200 text-sm flex items-center gap-2">
          <XCircle className="h-4 w-4" />
          {error}
        </div>
      )}
    </div>
  );
}

export default ExtractButton;

