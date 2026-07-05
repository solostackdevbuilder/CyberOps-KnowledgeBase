import { useState } from 'react';
import { 
  CheckCircle2, 
  XCircle, 
  Info, 
  AlertTriangle, 
  ChevronDown, 
  ChevronUp, 
  Copy,
  Loader2,
  Terminal,
  Globe,
  FileText
} from 'lucide-react';
import type { ScreenshotExtraction } from '../types';

interface ExtractionResultProps {
  extraction: ScreenshotExtraction;
  onRetry?: () => void;
}

function ExtractionResult({ extraction, onRetry }: ExtractionResultProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const getStatusIcon = () => {
    switch (extraction.extraction_status) {
      case 'success':
        return <CheckCircle2 className="h-5 w-5 text-green-400" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-400" />;
      case 'no_text':
        return <Info className="h-5 w-5 text-yellow-400" />;
      case 'not_supported':
        return <AlertTriangle className="h-5 w-5 text-orange-400" />;
      default:
        return null;
    }
  };

  const getStatusColor = () => {
    switch (extraction.extraction_status) {
      case 'success':
        return 'border-green-600 bg-green-900/20';
      case 'failed':
        return 'border-red-600 bg-red-900/20';
      case 'no_text':
        return 'border-yellow-600 bg-yellow-900/20';
      case 'not_supported':
        return 'border-orange-600 bg-orange-900/20';
      default:
        return 'border-gray-600 bg-gray-900/20';
    }
  };

  const getStatusText = () => {
    switch (extraction.extraction_status) {
      case 'success':
        return 'Text extracted successfully';
      case 'failed':
        return 'Extraction failed';
      case 'no_text':
        return 'No text detected';
      case 'not_supported':
        return 'Vision not supported';
      default:
        return 'Unknown status';
    }
  };

  const handleCopy = async () => {
    if (extraction.extracted_text) {
      try {
        await navigator.clipboard.writeText(extraction.extracted_text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (err) {
        console.error('Failed to copy text:', err);
      }
    }
  };

  const getAnalysisIcon = () => {
    if (!extraction.analysis) return null;
    const analysisLower = extraction.analysis.toLowerCase();
    if (analysisLower.includes('terminal') || analysisLower.includes('command')) {
      return <Terminal className="h-4 w-4 text-blue-400" />;
    }
    if (analysisLower.includes('browser') || analysisLower.includes('web')) {
      return <Globe className="h-4 w-4 text-blue-400" />;
    }
    return <FileText className="h-4 w-4 text-gray-400" />;
  };

  const previewText = extraction.extracted_text 
    ? (extraction.extracted_text.length > 50 
        ? extraction.extracted_text.substring(0, 50) + '...' 
        : extraction.extracted_text)
    : '';

  return (
    <div className={`border rounded-lg p-4 ${getStatusColor()}`}>
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3 flex-1">
          {getStatusIcon()}
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-medium text-white">
                {getStatusText()}
              </span>
            </div>
            
            {extraction.extraction_status === 'success' && previewText && (
              <p className="text-xs text-gray-400 mb-2">
                Text extracted: {previewText}
              </p>
            )}

            {extraction.extraction_status === 'failed' && extraction.error_message && (
              <p className="text-xs text-red-300 mb-2">
                {extraction.error_message}
              </p>
            )}

            {extraction.extraction_status === 'not_supported' && (
              <p className="text-xs text-orange-300 mb-2">
                Current LLM model does not support vision. Switch to Claude, OpenAI GPT-4, or Ollama LLaVA in Settings.
              </p>
            )}

            {extraction.extraction_status === 'no_text' && (
              <p className="text-xs text-yellow-300 mb-2">
                No text detected in this image
              </p>
            )}
          </div>
        </div>

        {extraction.extracted_text && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-2 p-1 text-gray-400 hover:text-white transition-colors"
            aria-label={expanded ? 'Collapse' : 'Expand'}
          >
            {expanded ? (
              <ChevronUp className="h-5 w-5" />
            ) : (
              <ChevronDown className="h-5 w-5" />
            )}
          </button>
        )}
      </div>

      {expanded && extraction.extracted_text && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-medium text-gray-300">
              Extracted Text (click to expand)
            </h4>
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded transition-colors"
              aria-label="Copy text"
            >
              {copied ? (
                <>
                  <CheckCircle2 className="h-3 w-3" />
                  Copied
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  Copy
                </>
              )}
            </button>
          </div>
          <div className="bg-gray-900 border border-gray-700 rounded-md p-3 max-h-64 overflow-y-auto">
            <pre className="text-xs font-mono text-gray-300 whitespace-pre-wrap">
              {extraction.extracted_text}
            </pre>
          </div>
        </div>
      )}

      {extraction.analysis && (
        <div className="mt-3 pt-3 border-t border-gray-700">
          <div className="flex items-start gap-2">
            {getAnalysisIcon()}
            <p className="text-xs italic text-gray-400 flex-1">
              {extraction.analysis}
            </p>
          </div>
        </div>
      )}

      {onRetry && extraction.extraction_status === 'failed' && (
        <div className="mt-3 pt-3 border-t border-gray-700">
          <button
            onClick={onRetry}
            className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors flex items-center gap-2"
          >
            <Loader2 className="h-4 w-4" />
            Retry Extraction
          </button>
        </div>
      )}
    </div>
  );
}

export default ExtractionResult;

