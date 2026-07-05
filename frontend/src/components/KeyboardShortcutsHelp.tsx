import { X } from 'lucide-react';

interface KeyboardShortcutsHelpProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function KeyboardShortcutsHelp({
  isOpen,
  onClose,
}: KeyboardShortcutsHelpProps) {
  if (!isOpen) return null;

  const isMac = navigator.platform.includes('Mac');
  const modKey = isMac ? '⌘' : 'Ctrl';

  const shortcuts = [
    {
      category: 'Navigation',
      items: [
        { keys: [`${modKey}`, 'K'], description: 'Open global search' },
        { keys: ['G', 'S'], description: 'Go to Sessions' },
        { keys: ['G', 'O'], description: 'Go to Operations' },
        { keys: ['G', 'Q'], description: 'Go to Query' },
        { keys: ['G', 'I'], description: 'Go to Insights' },
      ],
    },
    {
      category: 'Sessions',
      items: [
        { keys: ['N'], description: 'New session (on session list)' },
        { keys: ['E'], description: 'Edit current session' },
        { keys: ['Delete'], description: 'Delete session (with confirmation)' },
      ],
    },
    {
      category: 'Terminal Viewer',
      items: [
        { keys: [`${modKey}`, 'F'], description: 'Find in terminal' },
        { keys: ['Enter'], description: 'Next search result' },
        { keys: ['Esc'], description: 'Close search / Close modals' },
      ],
    },
    {
      category: 'General',
      items: [
        { keys: ['?'], description: 'Show keyboard shortcuts (or click help icon)' },
        { keys: ['Esc'], description: 'Close modals, cancel actions' },
      ],
    },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-gray-800 border border-gray-700 rounded-lg shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-gray-800 border-b border-gray-700 px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white">Keyboard Shortcuts</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-700 rounded transition-colors"
          >
            <X className="h-5 w-5 text-gray-400" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {shortcuts.map((category) => (
            <div key={category.category}>
              <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
                {category.category}
              </h3>
              <div className="space-y-2">
                {category.items.map((item, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between py-2 border-b border-gray-700/50"
                  >
                    <span className="text-gray-300">{item.description}</span>
                    <div className="flex items-center gap-1">
                      {item.keys.map((key, keyIndex) => (
                        <span key={keyIndex}>
                          {keyIndex > 0 && (
                            <span className="text-gray-500 mx-1">+</span>
                          )}
                          <kbd className="px-2 py-1 text-xs bg-gray-700 text-gray-300 rounded border border-gray-600">
                            {key}
                          </kbd>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="px-6 py-4 border-t border-gray-700 text-sm text-gray-400">
          <p>
            Tip: Keyboard shortcuts are disabled when typing in input fields or text areas.
          </p>
        </div>
      </div>
    </div>
  );
}



