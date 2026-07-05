import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import ErrorBoundary from './components/ErrorBoundary'
import './index.css'

try {
  const rootElement = document.getElementById('root');
  if (!rootElement) {
    throw new Error('Root element not found');
  }
  
  console.log('Rendering app...');
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </React.StrictMode>,
  );
  console.log('App rendered successfully');
} catch (error) {
  console.error('Failed to render app:', error);
  document.body.innerHTML = `
    <div style="padding: 20px; font-family: monospace; background: #1a1a1a; color: #ff4444; min-height: 100vh;">
      <h1>Fatal Error</h1>
      <pre>${error instanceof Error ? error.message : String(error)}</pre>
      <pre>${error instanceof Error ? error.stack : ''}</pre>
    </div>
  `;
}

