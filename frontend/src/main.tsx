import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';

// Global styles - ReportPulse theme
const style = document.createElement('style');
style.textContent = `
  :root {
    --rp-primary: #6366f1;
    --rp-primary-dark: #4f46e5;
    --rp-accent: #06b6d4;
    --rp-success: #10b981;
    --rp-warning: #f59e0b;
    --rp-danger: #ef4444;
    --rp-bg-dark: #0f172a;
    --rp-bg-sidebar: #1e293b;
    --rp-bg-card: #ffffff;
    --rp-bg-main: #f1f5f9;
    --rp-text: #334155;
    --rp-text-light: #94a3b8;
    --rp-border: #e2e8f0;
    --rp-gradient: linear-gradient(135deg, #6366f1 0%, #06b6d4 100%);
  }
  *, *::before, *::after { box-sizing: border-box; }
  body { margin: 0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: var(--rp-text); }
  a { color: var(--rp-primary); text-decoration: none; }
  a:hover { text-decoration: underline; }
  table th, table td { padding: 0.6rem 0.75rem; text-align: left; border-bottom: 1px solid var(--rp-border); }
  table th { background: #f8fafc; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; color: var(--rp-text-light); }
  ::selection { background: var(--rp-primary); color: white; }
  input:focus, select:focus { border-color: var(--rp-primary) !important; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); outline: none; }
`;
document.head.appendChild(style);

// Load Inter font
const link = document.createElement('link');
link.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap';
link.rel = 'stylesheet';
document.head.appendChild(link);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
