import React, { useEffect, useState, useRef, useId } from 'react';
import { flushSync } from 'react-dom';

export const THEME_STORAGE_KEY = 'callme_theme';

export function ThemeToggle({ className = '', style = {} }) {
  const [dark, setDark] = useState(() => {
    if (typeof document === 'undefined') return false;
    const saved = localStorage.getItem(THEME_STORAGE_KEY) || localStorage.getItem('theme');
    return saved ? saved === 'dark' : !document.documentElement.classList.contains('light');
  });

  const uniqueId = useId ? useId().replace(/[^a-zA-Z0-9_-]/g, '') : 'moon-cut';
  const maskId = `moon-cut-${uniqueId}`;
  const isTransitioningRef = useRef(false);

  useEffect(() => {
    const saved = localStorage.getItem(THEME_STORAGE_KEY) || localStorage.getItem('theme');
    const isDark = saved ? saved === 'dark' : document.documentElement.classList.contains('dark');
    document.documentElement.classList.toggle('dark', isDark);
    document.documentElement.classList.toggle('light', !isDark);
    setDark(isDark);

    const handleThemeChange = (e) => {
      const isNextDark = e?.detail ? e.detail === 'dark' : document.documentElement.classList.contains('dark');
      setDark(isNextDark);
    };

    window.addEventListener('callme:theme-changed', handleThemeChange);
    return () => window.removeEventListener('callme:theme-changed', handleThemeChange);
  }, []);

  const toggle = (e) => {
    if (isTransitioningRef.current) return;
    const next = !dark;

    const apply = () => {
      flushSync(() => setDark(next));
      document.documentElement.classList.toggle('dark', next);
      document.documentElement.classList.toggle('light', !next);
      try {
        localStorage.setItem(THEME_STORAGE_KEY, next ? 'dark' : 'light');
        localStorage.setItem('theme', next ? 'dark' : 'light');
        window.dispatchEvent(new CustomEvent('callme:theme-changed', { detail: next ? 'dark' : 'light' }));
      } catch {
        /* storage sandbox */
      }
    };

    const doc = document;
    if (!doc.startViewTransition || (typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches)) {
      document.documentElement.classList.add('theme-transitioning');
      apply();
      setTimeout(() => {
        document.documentElement.classList.remove('theme-transitioning');
      }, 450);
      return;
    }

    let x = e?.clientX;
    let y = e?.clientY;
    if ((x == null || y == null) || (x === 0 && y === 0)) {
      const rect = e?.currentTarget?.getBoundingClientRect();
      x = rect ? rect.left + rect.width / 2 : window.innerWidth / 2;
      y = rect ? rect.top + rect.height / 2 : window.innerHeight / 2;
    }

    const r = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    const root = document.documentElement.style;
    root.setProperty('--tx', `${x}px`);
    root.setProperty('--ty', `${y}px`);
    root.setProperty('--tr', `${r}px`);

    isTransitioningRef.current = true;
    try {
      const transition = doc.startViewTransition(apply);
      if (transition && typeof transition.finished?.finally === 'function') {
        transition.finished.finally(() => {
          isTransitioningRef.current = false;
        });
      } else {
        setTimeout(() => {
          isTransitioningRef.current = false;
        }, 950);
      }
    } catch {
      apply();
      isTransitioningRef.current = false;
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      className={`theme-switch-btn ${className}`}
      style={style}
    >
      <span className={`theme-switch-knob ${dark ? 'is-dark' : ''}`}>
        <svg viewBox="0 0 24 24" className="theme-toggle-svg" fill="none" strokeWidth="2" strokeLinecap="round">
          {/* sun rays */}
          <g className={`theme-toggle-rays ${dark ? 'is-dark' : ''}`}>
            {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
              <line key={a} x1="12" y1="2" x2="12" y2="4" transform={`rotate(${a} 12 12)`} />
            ))}
          </g>
          <mask id={maskId}>
            <rect width="24" height="24" fill="white" />
            <circle
              className="theme-toggle-mask-circle"
              cx={dark ? 16 : 26}
              cy={dark ? 8 : 2}
              r="6"
              fill="black"
            />
          </mask>
          <circle
            cx="12"
            cy="12"
            r={dark ? 8 : 5}
            mask={`url(#${maskId})`}
            className={`theme-toggle-circle ${dark ? 'is-dark' : ''}`}
          />
        </svg>
      </span>
    </button>
  );
}

export default ThemeToggle;
