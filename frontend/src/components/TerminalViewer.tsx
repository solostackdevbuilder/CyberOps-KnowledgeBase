import { useState, useRef, useEffect } from 'react';
import { Copy, Search, X, Maximize2, Minimize2, Type, AlignJustify } from 'lucide-react';

interface TerminalViewerProps {
  content: string;
  title?: string;
}

export default function TerminalViewer({ content, title = 'Terminal Content' }: TerminalViewerProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [wordWrap, setWordWrap] = useState(true);
  const [fontSize, setFontSize] = useState(14);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [searchIndex, setSearchIndex] = useState(0);
  const [searchMatches, setSearchMatches] = useState<number[]>([]);
  const contentRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const lines = content.split('\n');

  // Find search matches
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchMatches([]);
      setSearchIndex(0);
      return;
    }

    const query = searchQuery.toLowerCase();
    const matches: number[] = [];
    lines.forEach((line, index) => {
      if (line.toLowerCase().includes(query)) {
        matches.push(index);
      }
    });
    setSearchMatches(matches);
    setSearchIndex(0);
  }, [searchQuery, lines]);

  // Highlight search matches in line
  const highlightLine = (line: string, lineIndex: number) => {
    if (!searchQuery.trim() || !searchMatches.includes(lineIndex)) {
      return line;
    }

    const query = searchQuery;
    const parts = line.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'));
    return parts.map((part, index) => {
      if (part.toLowerCase() === query.toLowerCase()) {
        return (
          <mark
            key={index}
            className="bg-yellow-500/50 text-yellow-100 px-0.5 rounded"
          >
            {part}
          </mark>
        );
      }
      return part;
    });
  };

  // Scroll to search match
  useEffect(() => {
    if (searchMatches.length > 0 && contentRef.current) {
      const lineIndex = searchMatches[searchIndex];
      const lineElement = contentRef.current.querySelector(`[data-line="${lineIndex}"]`);
      if (lineElement) {
        lineElement.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    }
  }, [searchIndex, searchMatches]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl+F / Cmd+F for search
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        setShowSearch(true);
        setTimeout(() => searchInputRef.current?.focus(), 100);
      }
      // Escape to close search
      if (e.key === 'Escape' && showSearch) {
        setShowSearch(false);
        setSearchQuery('');
      }
      // Enter to find next
      if (e.key === 'Enter' && showSearch && searchMatches.length > 0) {
        e.preventDefault();
        setSearchIndex((prev) => (prev + 1) % searchMatches.length);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showSearch, searchMatches.length]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      // Show brief feedback
      const button = document.activeElement as HTMLElement;
      const originalText = button.title;
      button.title = 'Copied!';
      setTimeout(() => {
        button.title = originalText;
      }, 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleNextMatch = () => {
    if (searchMatches.length > 0) {
      setSearchIndex((prev) => (prev + 1) % searchMatches.length);
    }
  };

  const handlePrevMatch = () => {
    if (searchMatches.length > 0) {
      setSearchIndex((prev) => (prev - 1 + searchMatches.length) % searchMatches.length);
    }
  };

  return (
    <div className={`bg-gray-800 border border-gray-700 rounded-lg overflow-hidden ${isFullscreen ? 'fixed inset-4 z-50' : ''}`}>
      {/* Header with controls */}
      <div className="bg-gray-900 border-b border-gray-700 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          <span className="text-xs text-gray-500">
            {lines.length} line{lines.length !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Font size control */}
          <div className="flex items-center gap-2">
            <Type className="h-4 w-4 text-gray-400" />
            <input
              type="range"
              min="10"
              max="18"
              value={fontSize}
              onChange={(e) => setFontSize(Number(e.target.value))}
              className="w-20"
            />
            <span className="text-xs text-gray-400 w-8">{fontSize}px</span>
          </div>

          {/* Word wrap toggle */}
          <button
            onClick={() => setWordWrap(!wordWrap)}
            className={`p-1.5 rounded transition-colors ${
              wordWrap
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:bg-gray-700'
            }`}
            title="Toggle word wrap"
          >
            <AlignJustify className="h-4 w-4" />
          </button>

          {/* Search button */}
          <button
            onClick={() => {
              setShowSearch(!showSearch);
              if (!showSearch) {
                setTimeout(() => searchInputRef.current?.focus(), 100);
              }
            }}
            className={`p-1.5 rounded transition-colors ${
              showSearch
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:bg-gray-700'
            }`}
            title="Search (Ctrl+F / Cmd+F)"
          >
            <Search className="h-4 w-4" />
          </button>

          {/* Copy button */}
          <button
            onClick={handleCopy}
            className="p-1.5 text-gray-400 hover:bg-gray-700 rounded transition-colors"
            title="Copy all content"
          >
            <Copy className="h-4 w-4" />
          </button>

          {/* Fullscreen toggle */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 text-gray-400 hover:bg-gray-700 rounded transition-colors"
            title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          >
            {isFullscreen ? (
              <Minimize2 className="h-4 w-4" />
            ) : (
              <Maximize2 className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>

      {/* Search bar */}
      {showSearch && (
        <div className="bg-gray-900 border-b border-gray-700 px-4 py-2 flex items-center gap-2">
          <Search className="h-4 w-4 text-gray-400" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search in terminal..."
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {searchQuery && (
            <>
              <span className="text-xs text-gray-500">
                {searchMatches.length > 0
                  ? `${searchIndex + 1} / ${searchMatches.length}`
                  : '0 matches'}
              </span>
              {searchMatches.length > 0 && (
                <>
                  <button
                    onClick={handlePrevMatch}
                    className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
                  >
                    ↑ Prev
                  </button>
                  <button
                    onClick={handleNextMatch}
                    className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
                  >
                    Next ↓
                  </button>
                </>
              )}
              <button
                onClick={() => {
                  setSearchQuery('');
                  setShowSearch(false);
                }}
                className="p-1 text-gray-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </>
          )}
        </div>
      )}

      {/* Terminal content */}
      <div
        ref={contentRef}
        className="bg-gray-900 text-gray-100 font-mono overflow-auto"
        style={{
          fontSize: `${fontSize}px`,
          maxHeight: isFullscreen ? 'calc(100vh - 200px)' : '600px',
        }}
      >
        <pre
          className={`p-4 ${wordWrap ? 'whitespace-pre-wrap' : 'whitespace-pre'} ${
            wordWrap ? '' : 'overflow-x-auto'
          }`}
        >
          {lines.map((line, index) => (
            <div
              key={index}
              data-line={index}
              className={`flex ${wordWrap ? 'flex-wrap' : ''} ${
                searchMatches.includes(index) && searchQuery
                  ? 'bg-yellow-500/10'
                  : ''
              } ${searchMatches[searchIndex] === index ? 'bg-blue-500/20' : ''}`}
            >
              <span className="text-gray-600 mr-4 select-none text-right min-w-[3rem]">
                {index + 1}
              </span>
              <span className="flex-1">{highlightLine(line, index)}</span>
            </div>
          ))}
        </pre>
      </div>
    </div>
  );
}

