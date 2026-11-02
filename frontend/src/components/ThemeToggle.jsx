import React, { useEffect, useState } from 'react';
import { Sun, Moon } from 'lucide-react';

export const THEME_STORAGE_KEY = 'callme_theme';

function readTheme() {
  if (typeof document === 'undefined') return 'dark';
  return document.documentElement.classList.contains('light') ? 'light' : 'dark';
}

export default function ThemeToggle({ className = '', style = {} }) {
  const [theme, setTheme] = useState(readTheme());

  useEffect(() => {
    setTheme(readTheme());

    const handleThemeChange = () => {
      setTheme(readTheme());
    };

    window.addEventListener('callme:theme-changed', handleThemeChange);
    return () => window.removeEventListener('callme:theme-changed', handleThemeChange);
  }, []);

  function chooseTheme(next) {
    setTheme(next);
    if (next === 'light') {
      document.documentElement.classList.add('light');
      document.documentElement.classList.remove('dark');
    } else {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('light');
    }

    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
      window.dispatchEvent(new CustomEvent('callme:theme-changed', { detail: next }));
    } catch {
      /* storage unavailable in restricted sandbox */
    }
  }

  return (
    <div
      className={`theme-toggle-container ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '2px',
        padding: '2px',
        borderRadius: 'var(--radius-full)',
        background: 'var(--bg-surface-elevated)',
        border: '1px solid var(--border-subtle)',
        ...style,
      }}
      role="group"
      aria-label="Theme selection"
    >
      <button
        type="button"
        onClick={() => chooseTheme('light')}
        aria-pressed={theme === 'light'}
        aria-label="Switch to light theme"
        title="Switch to light theme"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '3px 9px',
          borderRadius: 'var(--radius-full)',
          border: 'none',
          fontSize: '0.72rem',
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
          cursor: 'pointer',
          background: theme === 'light' ? 'var(--gradient-primary)' : 'transparent',
          color: theme === 'light' ? '#ffffff' : 'var(--text-secondary)',
          transition: 'all 0.2s ease',
        }}
      >
        <Sun size={12} />
        <span>Light</span>
      </button>

      <button
        type="button"
        onClick={() => chooseTheme('dark')}
        aria-pressed={theme === 'dark'}
        aria-label="Switch to dark theme"
        title="Switch to dark theme"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '3px 9px',
          borderRadius: 'var(--radius-full)',
          border: 'none',
          fontSize: '0.72rem',
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
          cursor: 'pointer',
          background: theme === 'dark' ? 'var(--gradient-primary)' : 'transparent',
          color: theme === 'dark' ? '#07080a' : 'var(--text-secondary)',
          transition: 'all 0.2s ease',
        }}
      >
        <Moon size={12} />
        <span>Dark</span>
      </button>
    </div>
  );
}
