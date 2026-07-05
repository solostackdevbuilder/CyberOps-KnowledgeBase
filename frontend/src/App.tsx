import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { Code, Search, Activity, Settings, BarChart3, Clock, HelpCircle, Key, Server, Chrome, Loader2 } from 'lucide-react';
import { lazy, Suspense, useState } from 'react';
import GlobalSearch from './components/GlobalSearch';
import KeyboardShortcutsHelp from './components/KeyboardShortcutsHelp';
import { useKeyboardShortcuts, useNavigationShortcuts } from './hooks/useKeyboardShortcuts';

// Route components are lazy-loaded so the initial bundle only pays for the
// shell + nav + global overlays. Each page loads on first visit and is then
// cached by the browser. Modals (GlobalSearch, KeyboardShortcutsHelp) stay
// eager so Ctrl+K and ? feel instant regardless of the current route.
const SettingsPage = lazy(() => import('./components/Settings'));

// Red Team
const SessionList = lazy(() => import('./modules/red_team/components/SessionList'));
const SessionForm = lazy(() => import('./modules/red_team/components/SessionForm'));
const SessionDetail = lazy(() => import('./modules/red_team/components/SessionDetail'));
const QueryInterface = lazy(() => import('./modules/red_team/components/QueryInterface'));
const OperationList = lazy(() => import('./modules/red_team/components/OperationList'));
const OperationForm = lazy(() => import('./modules/red_team/components/OperationForm'));
const OperationDetail = lazy(() => import('./modules/red_team/components/OperationDetail'));
const Insights = lazy(() => import('./modules/red_team/components/Insights'));
const TimelineView = lazy(() => import('./components/TimelineView'));

// Plugin pages - one directory per plugin under src/plugins/ mirrors
// the backend's app/plugins/<id>/ layout.
const HashcatPage = lazy(() => import('./plugins/hashcat/HashcatPage'));
const RemoteServersPage = lazy(() => import('./plugins/remote_servers/RemoteServersPage'));
const BrowserExtensionPage = lazy(() => import('./plugins/browser_extension/BrowserExtensionPage'));

function RouteFallback() {
  return (
    <div className="flex items-center justify-center py-24 text-gray-500">
      <Loader2 className="h-6 w-6 animate-spin" />
    </div>
  );
}

function Navigation({ onSearchOpen, onShortcutsOpen }: { onSearchOpen: () => void; onShortcutsOpen: () => void }) {
  const location = useLocation();

  const isActive = (path: string) => {
    return location.pathname === path;
  };

  const navLinkClass = (active: boolean) =>
    `flex items-center px-3 py-2 text-sm font-medium rounded transition-all duration-200 ${
      active
        ? 'bg-gradient-to-r from-[rgba(0,255,136,0.15)] to-[rgba(0,212,255,0.1)] text-[#00ff88] border-l-2 border-[#00ff88]'
        : 'text-gray-400 hover:text-[#00d4ff] hover:bg-[rgba(0,212,255,0.05)]'
    }`;

  return (
    <nav className="bg-[#0d1117] border-b border-[#30363d] backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-14">
          <div className="flex items-center gap-1">
            <Link
              to="/"
              className="flex items-center px-3 py-2 text-sm font-bold text-[#00ff88] hover:text-white transition-colors mr-4"
            >
              <Code className="h-5 w-5 mr-2" />
              <span className="font-['Orbitron'] tracking-wider cyber-glow-green">CYBEROPS</span>
              <span className="ml-2 px-1.5 py-0.5 text-xs font-bold text-[#ff4757] cyber-glow-red border border-[#ff4757] rounded font-['Orbitron'] tracking-wide animate-glow-pulse">ALPHA</span>
            </Link>
            <Link
              to="/operations"
              className={navLinkClass(isActive('/operations') || isActive('/operations/create') || location.pathname.startsWith('/operations/'))}
            >
              <Activity className="h-4 w-4 mr-1.5" />
              Operations
            </Link>
            <Link
              to="/"
              className={navLinkClass(isActive('/') || location.pathname.startsWith('/session/') || (isActive('/create') && !location.pathname.startsWith('/operations')))}
            >
              Sessions
            </Link>
            <Link
              to="/query"
              className={navLinkClass(isActive('/query'))}
            >
              <Search className="h-4 w-4 mr-1.5" />
              Query
            </Link>
            <Link
              to="/insights"
              className={navLinkClass(isActive('/insights'))}
            >
              <BarChart3 className="h-4 w-4 mr-1.5" />
              Insights
            </Link>
            <Link
              to="/timeline"
              className={navLinkClass(isActive('/timeline'))}
            >
              <Clock className="h-4 w-4 mr-1.5" />
              Timeline
            </Link>
            <Link
              to="/plugins/hashcat"
              className={navLinkClass(isActive('/plugins/hashcat'))}
            >
              <Key className="h-4 w-4 mr-1.5" />
              Hashcat
            </Link>
            <Link
              to="/plugins/remote_servers"
              className={navLinkClass(isActive('/plugins/remote_servers'))}
            >
              <Server className="h-4 w-4 mr-1.5" />
              Servers
            </Link>
            <Link
              to="/plugins/browser_extension"
              className={navLinkClass(isActive('/plugins/browser_extension'))}
            >
              <Chrome className="h-4 w-4 mr-1.5" />
              Extension
            </Link>
            <Link
              to="/settings"
              className={navLinkClass(isActive('/settings'))}
            >
              <Settings className="h-4 w-4 mr-1.5" />
              Settings
            </Link>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onShortcutsOpen}
              className="p-2 text-gray-500 hover:text-[#00d4ff] hover:bg-[rgba(0,212,255,0.1)] rounded transition-colors"
              title="Keyboard Shortcuts (?)"
            >
              <HelpCircle className="h-5 w-5" />
            </button>
            <button
              onClick={onSearchOpen}
              className="flex items-center px-3 py-1.5 bg-[#161b22] hover:bg-[#21262d] text-gray-400 hover:text-[#00d4ff] rounded border border-[#30363d] hover:border-[#00d4ff] transition-all text-sm"
              title="Search (Ctrl+K / Cmd+K)"
            >
              <Search className="h-4 w-4 mr-2" />
              <span className="hidden sm:inline">Search</span>
              <kbd className="hidden sm:inline ml-2 px-1.5 py-0.5 text-xs bg-[#0d1117] rounded border border-[#30363d] font-mono">
                {navigator.platform.includes('Mac') ? '⌘K' : 'Ctrl+K'}
              </kbd>
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}

function AppContent() {
  const [searchOpen, setSearchOpen] = useState(false);
  const [shortcutsHelpOpen, setShortcutsHelpOpen] = useState(false);

  // Navigation shortcuts (G + S/O/Q/I)
  useNavigationShortcuts();

  // Global keyboard shortcuts
  useKeyboardShortcuts([
    {
      key: 'k',
      ctrl: true,
      meta: true,
      action: () => setSearchOpen(true),
      description: 'Open global search',
      global: true,
    },
    {
      key: '/',
      shift: true,
      action: () => {
        const target = document.activeElement as HTMLElement;
        // Only trigger if not in an input/textarea
        if (
          target.tagName !== 'INPUT' &&
          target.tagName !== 'TEXTAREA' &&
          !target.isContentEditable
        ) {
          setShortcutsHelpOpen(true);
        }
      },
      description: 'Show keyboard shortcuts',
      global: true,
    },
    {
      key: 'Escape',
      action: () => {
        setSearchOpen(false);
        setShortcutsHelpOpen(false);
      },
      description: 'Close search/modal',
      global: true,
    },
  ]);

  return (
    <div className="min-h-screen hex-pattern">
      <Navigation 
        onSearchOpen={() => setSearchOpen(true)} 
        onShortcutsOpen={() => setShortcutsHelpOpen(true)}
      />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<SessionList />} />
            <Route path="/create" element={<SessionForm />} />
            <Route path="/session/:id" element={<SessionDetail />} />
            <Route path="/session/:id/edit" element={<SessionForm />} />
            <Route path="/operations" element={<OperationList />} />
            <Route path="/operations/create" element={<OperationForm />} />
            <Route path="/operations/:id" element={<OperationDetail />} />
            <Route path="/operations/:id/edit" element={<OperationForm />} />
            <Route path="/query" element={<QueryInterface />} />
            <Route path="/insights" element={<Insights />} />
            <Route path="/timeline" element={<TimelineView />} />
            <Route path="/plugins/hashcat" element={<HashcatPage />} />
            <Route path="/plugins/remote_servers" element={<RemoteServersPage />} />
            <Route path="/plugins/browser_extension" element={<BrowserExtensionPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </Suspense>
      </main>
      <GlobalSearch isOpen={searchOpen} onClose={() => setSearchOpen(false)} />
      <KeyboardShortcutsHelp
        isOpen={shortcutsHelpOpen}
        onClose={() => setShortcutsHelpOpen(false)}
      />
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}

export default App;


