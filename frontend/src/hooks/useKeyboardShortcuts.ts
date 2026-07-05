import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

export interface KeyboardShortcut {
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
  alt?: boolean;
  action: () => void;
  description: string;
  global?: boolean; // If true, works everywhere; if false, only on specific pages
}

export function useKeyboardShortcuts(
  shortcuts: KeyboardShortcut[],
  enabled: boolean = true
) {
  useEffect(() => {
    if (!enabled) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      // Don't trigger shortcuts when typing in inputs, textareas, or contenteditable elements
      const target = event.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable ||
        (target.tagName === 'INPUT' && (target as HTMLInputElement).type === 'text')
      ) {
        // Allow Ctrl+K / Cmd+K for search even in inputs
        if (event.key === 'k' && (event.ctrlKey || event.metaKey)) {
          // Let it through
        } else {
          return;
        }
      }

      for (const shortcut of shortcuts) {
        try {
          const keyMatches = event.key.toLowerCase() === shortcut.key.toLowerCase();
          
          // Check modifiers
          const ctrlRequired = shortcut.ctrl || false;
          const metaRequired = shortcut.meta || false;
          const shiftRequired = shortcut.shift || false;
          const altRequired = shortcut.alt || false;

          // For Ctrl/Cmd, accept either (cross-platform)
          const modifierPressed = event.ctrlKey || event.metaKey;
          const modifierRequired = ctrlRequired || metaRequired;
          const modifierMatches = modifierRequired ? modifierPressed : !modifierPressed;

          // Check individual modifiers
          const ctrlMatches = ctrlRequired ? event.ctrlKey : !event.ctrlKey;
          const metaMatches = metaRequired ? event.metaKey : !event.metaKey;
          const shiftMatches = shiftRequired ? event.shiftKey : !event.shiftKey;
          const altMatches = altRequired ? event.altKey : !event.altKey;

          // For Ctrl/Cmd shortcuts, we accept either modifier
          if (modifierRequired) {
            if (
              keyMatches &&
              modifierMatches &&
              shiftMatches &&
              altMatches
            ) {
              event.preventDefault();
              shortcut.action();
              break;
            }
          } else {
            // For non-modifier shortcuts, check all individually
            if (
              keyMatches &&
              ctrlMatches &&
              metaMatches &&
              shiftMatches &&
              altMatches
            ) {
              event.preventDefault();
              shortcut.action();
              break;
            }
          }
        } catch (err) {
          console.error('Error in keyboard shortcut handler:', err);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [shortcuts, enabled]);
}

// Helper hook for common navigation shortcuts
export function useNavigationShortcuts() {
  const navigate = useNavigate();
  const [navMode, setNavMode] = useState(false);

  useEffect(() => {
    if (!navMode) return;

    const handleSecondKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        setNavMode(false);
        return;
      }

      if (e.key.toLowerCase() === 's') {
        e.preventDefault();
        navigate('/');
        setNavMode(false);
      } else if (e.key.toLowerCase() === 'o') {
        e.preventDefault();
        navigate('/operations');
        setNavMode(false);
      } else if (e.key.toLowerCase() === 'q') {
        e.preventDefault();
        navigate('/query');
        setNavMode(false);
      } else if (e.key.toLowerCase() === 'i') {
        e.preventDefault();
        navigate('/insights');
        setNavMode(false);
      } else {
        setNavMode(false);
      }
    };

    window.addEventListener('keydown', handleSecondKey);
    return () => {
      window.removeEventListener('keydown', handleSecondKey);
      setNavMode(false);
    };
  }, [navMode, navigate]);

  useKeyboardShortcuts([
    {
      key: 'g',
      ctrl: false,
      action: () => {
        const target = document.activeElement as HTMLElement;
        if (
          target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable
        ) {
          return;
        }
        setNavMode(true);
        // Auto-cancel after 2 seconds
        setTimeout(() => setNavMode(false), 2000);
      },
      description: 'Go to... (then S= Sessions, O= Operations, Q= Query, I= Insights)',
      global: true,
    },
  ]);
}

