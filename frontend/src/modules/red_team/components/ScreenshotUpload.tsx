import { useState, useRef, useEffect, useCallback } from 'react';
import { Upload, X, Loader2, Image as ImageIcon, Clipboard, Monitor } from 'lucide-react';
import { uploadScreenshot } from '../services/api';
import { getSettings } from '../../../core/services/api';
import type { ScreenshotExtraction } from '../types';
import UploadStatusFooter from './UploadStatusFooter';

interface ScreenshotUploadProps {
  sessionId: string;
  onUploaded: () => void;
}

type UploadState = 'idle' | 'uploading' | 'extracting' | 'complete';

function ScreenshotUpload({ sessionId, onUploaded }: ScreenshotUploadProps) {
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [description, setDescription] = useState('');
  const [extraction, setExtraction] = useState<ScreenshotExtraction | null>(null);
  const [visionSupported, setVisionSupported] = useState<boolean | null>(null);
  const [justPasted, setJustPasted] = useState(false);
  const [justCaptured, setJustCaptured] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const dragCounter = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Check if vision is supported
    const checkVisionSupport = async () => {
      try {
        const settings = await getSettings();
        setVisionSupported(settings.llm_supports_vision ?? false);
      } catch (err) {
        console.error('Failed to load settings:', err);
      }
    };
    checkVisionSupport();
  }, []);

  const handleFileSelect = useCallback((selectedFile: File) => {
    if (!selectedFile.type.startsWith('image/')) {
      setError('Please select an image file');
      return;
    }

    setFile(selectedFile);
    setError(null);

    // Create preview
    const reader = new FileReader();
    reader.onloadend = () => {
      setPreview(reader.result as string);
    };
    reader.readAsDataURL(selectedFile);
  }, []);

  // Paste handler: let operators drop a screenshot in by pressing Ctrl+V (or
  // Cmd+V) anywhere on the Screenshots tab. Skips text pastes into inputs so
  // typing into the Description field still works normally.
  useEffect(() => {
    const isTypingTarget = (target: EventTarget | null): boolean => {
      if (!(target instanceof HTMLElement)) return false;
      if (target.isContentEditable) return true;
      const tag = target.tagName;
      return tag === 'INPUT' || tag === 'TEXTAREA';
    };

    const handlePaste = (event: ClipboardEvent) => {
      if (isTypingTarget(event.target)) return;
      const items = event.clipboardData?.items;
      if (!items) return;
      for (const item of Array.from(items)) {
        if (item.kind === 'file' && item.type.startsWith('image/')) {
          const pasted = item.getAsFile();
          if (pasted) {
            event.preventDefault();
            // Clipboard images come back as image.png with no meaningful name.
            // Stamp with a timestamp so multiple pastes don't collide in the
            // backend's filename-keyed extraction map.
            const ts = new Date().toISOString().replace(/[:.]/g, '-');
            const ext = pasted.type.split('/')[1] || 'png';
            const named = new File([pasted], `pasted-${ts}.${ext}`, { type: pasted.type });
            handleFileSelect(named);
            setJustPasted(true);
            window.setTimeout(() => setJustPasted(false), 1500);
            return;
          }
        }
      }
    };

    document.addEventListener('paste', handlePaste);
    return () => document.removeEventListener('paste', handlePaste);
  }, [handleFileSelect]);

  // Drag-and-drop anywhere on the Screenshots tab. Previously drop only worked
  // over the inner dropzone div - operators had to aim. Now a full-viewport
  // overlay appears the moment a file is dragged over the tab, so you can
  // release anywhere.
  useEffect(() => {
    const hasFiles = (event: DragEvent): boolean => {
      const types = event.dataTransfer?.types;
      if (!types) return false;
      // DataTransferItemList has no Array methods; iterate via for-of.
      for (const t of Array.from(types)) {
        if (t === 'Files') return true;
      }
      return false;
    };

    const handleDragEnter = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      dragCounter.current += 1;
      if (dragCounter.current === 1) setIsDraggingFile(true);
    };

    const handleDragOver = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      // Required for drop to fire when listening at the document level.
      event.preventDefault();
    };

    const handleDragLeave = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      dragCounter.current = Math.max(0, dragCounter.current - 1);
      if (dragCounter.current === 0) setIsDraggingFile(false);
    };

    const handleDocumentDrop = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      dragCounter.current = 0;
      setIsDraggingFile(false);
      const dropped = event.dataTransfer?.files?.[0];
      if (!dropped) return;
      if (!dropped.type.startsWith('image/')) {
        setError('Please drop an image file');
        return;
      }
      handleFileSelect(dropped);
    };

    document.addEventListener('dragenter', handleDragEnter);
    document.addEventListener('dragover', handleDragOver);
    document.addEventListener('dragleave', handleDragLeave);
    document.addEventListener('drop', handleDocumentDrop);
    return () => {
      document.removeEventListener('dragenter', handleDragEnter);
      document.removeEventListener('dragover', handleDragOver);
      document.removeEventListener('dragleave', handleDragLeave);
      document.removeEventListener('drop', handleDocumentDrop);
      dragCounter.current = 0;
    };
  }, [handleFileSelect]);

  // Browser-native screen capture. Triggers the OS picker so the user chooses
  // a window or screen; we grab a single frame and then stop the stream so the
  // browser's "sharing" indicator goes away. There is no truly one-click flow
  // available in the browser - the picker is a mandated permission surface.
  const handleCaptureScreen = useCallback(async () => {
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setError('Screen capture is not supported by this browser.');
      return;
    }
    if (capturing) return;

    setCapturing(true);
    let stream: MediaStream | null = null;
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: 1 },
        audio: false,
      });
    } catch (err) {
      const maybeError = err as { name?: string; message?: string };
      if (maybeError?.name !== 'NotAllowedError' && maybeError?.name !== 'AbortError') {
        setError(maybeError?.message || 'Failed to start screen capture.');
      }
      setCapturing(false);
      return;
    }

    try {
      const video = document.createElement('video');
      video.srcObject = stream;
      video.muted = true;
      await video.play();

      if (!video.videoWidth || !video.videoHeight) {
        await new Promise<void>((resolve) => {
          video.addEventListener('loadeddata', () => resolve(), { once: true });
        });
      }

      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        setError('Could not create canvas for screen capture.');
        return;
      }
      ctx.drawImage(video, 0, 0);

      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, 'image/png'),
      );
      if (!blob) {
        setError('Failed to encode captured screen as PNG.');
        return;
      }

      const ts = new Date().toISOString().replace(/[:.]/g, '-');
      const captured = new File([blob], `captured-${ts}.png`, { type: 'image/png' });
      handleFileSelect(captured);
      setJustCaptured(true);
      window.setTimeout(() => setJustCaptured(false), 1500);
    } finally {
      stream.getTracks().forEach((track) => track.stop());
      setCapturing(false);
    }
  }, [capturing, handleFileSelect]);

  // Keyboard shortcut: Ctrl+Shift+S (or Cmd+Shift+S) for fast screen capture.
  // Ignored when the user is typing so it doesn't fight with normal editing.
  useEffect(() => {
    const isTypingTarget = (target: EventTarget | null): boolean => {
      if (!(target instanceof HTMLElement)) return false;
      if (target.isContentEditable) return true;
      const tag = target.tagName;
      return tag === 'INPUT' || tag === 'TEXTAREA';
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;
      const ctrlKey = event.ctrlKey || event.metaKey;
      if (ctrlKey && event.shiftKey && (event.key === 'S' || event.key === 's')) {
        event.preventDefault();
        handleCaptureScreen();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleCaptureScreen]);

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      handleFileSelect(selectedFile);
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    try {
      setUploadState('uploading');
      setError(null);
      setExtraction(null);
      
      // Upload screenshot
      const session = await uploadScreenshot(sessionId, file, description || undefined);
      
      // Check if extraction result is in the session response
      if (session.screenshot_extractions && session.screenshot_extractions.length > 0) {
        // Find extraction for this file (match by filename)
        const latestExtraction = session.screenshot_extractions.find(
          e => e.filename === file.name
        ) || session.screenshot_extractions[session.screenshot_extractions.length - 1];
        
        if (latestExtraction) {
          setExtraction(latestExtraction);
          setUploadState('complete');
          // Auto-clear after showing result
          setTimeout(() => {
            setFile(null);
            setPreview(null);
            setDescription('');
            setExtraction(null);
            setUploadState('idle');
            onUploaded();
          }, 5000);
          return;
        }
      }
      
      // If no extraction data yet, show extracting state briefly
      // The backend processes extraction asynchronously, so we may need to reload
      setUploadState('extracting');
      
      // Wait a moment, then reload session to get extraction results
      setTimeout(async () => {
        try {
          // Reload session to get extraction results
          const { getSession } = await import('../services/api');
          const updatedSession = await getSession(sessionId);
          
          if (updatedSession.screenshot_extractions && updatedSession.screenshot_extractions.length > 0) {
            const extraction = updatedSession.screenshot_extractions.find(
              e => e.filename === file.name
            ) || updatedSession.screenshot_extractions[updatedSession.screenshot_extractions.length - 1];
            
            if (extraction) {
              setExtraction(extraction);
            }
          }
        } catch (err) {
          console.error('Failed to reload session:', err);
        }
        
        setUploadState('complete');
        // Auto-clear after showing result
        setTimeout(() => {
          setFile(null);
          setPreview(null);
          setDescription('');
          setExtraction(null);
          setUploadState('idle');
          onUploaded();
        }, 3000);
      }, 2000);
      
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to upload screenshot');
      setUploadState('idle');
    }
  };

  const handleCancel = () => {
    setFile(null);
    setPreview(null);
    setDescription('');
    setError(null);
    setExtraction(null);
    setUploadState('idle');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
      {isDraggingFile && (
        <div className="fixed inset-0 z-50 bg-blue-950/80 backdrop-blur-sm flex items-center justify-center pointer-events-none">
          <div className="border-4 border-dashed border-blue-300 rounded-2xl px-16 py-12 text-center bg-blue-900/40">
            <ImageIcon className="h-16 w-16 mx-auto text-blue-200 mb-4" />
            <p className="text-2xl font-semibold text-white">Drop screenshot anywhere</p>
            <p className="text-blue-200 mt-2">Release to upload</p>
          </div>
        </div>
      )}

      <h3 className="text-lg font-semibold text-white mb-4">Upload Screenshot</h3>

      {justPasted && (
        <div className="mb-4 p-3 bg-green-900/50 border border-green-700 rounded-md text-green-200 text-sm flex items-center gap-2">
          <Clipboard className="h-4 w-4" />
          Pasted from clipboard - review and click Upload
        </div>
      )}

      {justCaptured && (
        <div className="mb-4 p-3 bg-green-900/50 border border-green-700 rounded-md text-green-200 text-sm flex items-center gap-2">
          <Monitor className="h-4 w-4" />
          Captured screen - review and click Upload
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded-md text-red-200 text-sm">
          {error}
        </div>
      )}

      {!file ? (
        <div
          className="border-2 border-dashed rounded-lg p-8 text-center transition-colors border-gray-700 hover:border-gray-600"
        >
          <ImageIcon className="h-12 w-12 mx-auto text-gray-500 mb-4" />
          <p className="text-gray-400 mb-2">
            Drag and drop an image here, or click to select
          </p>
          <p className="text-gray-500 text-sm mb-3 flex items-center justify-center gap-1">
            <Clipboard className="h-3.5 w-3.5" />
            or press <kbd className="px-1.5 py-0.5 bg-gray-800 border border-gray-600 rounded text-xs font-mono">Ctrl</kbd>+<kbd className="px-1.5 py-0.5 bg-gray-800 border border-gray-600 rounded text-xs font-mono">V</kbd> to paste from clipboard
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileInputChange}
            className="hidden"
            id="screenshot-upload"
          />
          <div className="inline-flex items-center gap-2 flex-wrap justify-center">
            <label
              htmlFor="screenshot-upload"
              className="inline-block px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md cursor-pointer transition-colors"
            >
              <Upload className="h-4 w-4 inline mr-2" />
              Select File
            </label>
            <button
              type="button"
              onClick={handleCaptureScreen}
              disabled={capturing}
              className="inline-block px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Capture a window or screen (Ctrl+Shift+S)"
            >
              {capturing ? (
                <>
                  <Loader2 className="h-4 w-4 inline mr-2 animate-spin" />
                  Capturing...
                </>
              ) : (
                <>
                  <Monitor className="h-4 w-4 inline mr-2" />
                  Capture Screen
                </>
              )}
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-3">
            <kbd className="px-1.5 py-0.5 bg-gray-800 border border-gray-600 rounded text-xs font-mono">Ctrl</kbd>+<kbd className="px-1.5 py-0.5 bg-gray-800 border border-gray-600 rounded text-xs font-mono">Shift</kbd>+<kbd className="px-1.5 py-0.5 bg-gray-800 border border-gray-600 rounded text-xs font-mono">S</kbd> triggers capture - browser opens its window/screen picker
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {preview && (
            <div className="relative">
              <img
                src={preview}
                alt="Preview"
                className="max-h-64 mx-auto rounded-lg border border-gray-700"
              />
              <button
                onClick={handleCancel}
                className="absolute top-2 right-2 p-2 bg-red-600 hover:bg-red-700 text-white rounded-full transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-300 mb-2">
              Description (optional)
            </label>
            <input
              type="text"
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe this screenshot"
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <div className="flex justify-end space-x-2">
            <button
              onClick={handleCancel}
              disabled={uploadState === 'uploading' || uploadState === 'extracting'}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleUpload}
              disabled={uploadState === 'uploading' || uploadState === 'extracting'}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
            >
              {uploadState === 'uploading' || uploadState === 'extracting' ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  {uploadState === 'uploading' ? 'Uploading...' : 'Extracting text from image...'}
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4 mr-2" />
                  Upload
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Upload/Extraction Status */}
      <UploadStatusFooter
        uploadState={uploadState}
        extraction={extraction}
        visionSupported={visionSupported}
      />
    </div>
  );
}

export default ScreenshotUpload;

