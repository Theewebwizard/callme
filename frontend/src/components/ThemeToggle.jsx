import React, { useEffect, useState, useRef } from 'react';
import { Sun, Moon } from 'lucide-react';

export const THEME_STORAGE_KEY = 'callme_theme';

function readTheme() {
  if (typeof document === 'undefined') return 'dark';
  return document.documentElement.classList.contains('light') ? 'light' : 'dark';
}

function applyThemeClasses(next) {
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

export default function ThemeToggle({ className = '', style = {} }) {
  const [theme, setTheme] = useState(readTheme());
  const containerRef = useRef(null);
  const isTransitioningRef = useRef(false);

  useEffect(() => {
    setTheme(readTheme());

    const handleThemeChange = () => {
      setTheme(readTheme());
    };

    window.addEventListener('callme:theme-changed', handleThemeChange);
    return () => window.removeEventListener('callme:theme-changed', handleThemeChange);
  }, []);

  function chooseTheme(next, event) {
    if (next === theme) return;
    if (isTransitioningRef.current) return;

    setTheme(next);

    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // 1. View Transitions API (Chromium, Edge, modern browsers)
    if (
      typeof document !== 'undefined' &&
      document.startViewTransition &&
      !prefersReducedMotion
    ) {
      isTransitioningRef.current = true;

      // Calculate radial center origin
      let x = window.innerWidth / 2;
      let y = window.innerHeight / 2;

      if (event?.clientX != null && event?.clientY != null && (event.clientX !== 0 || event.clientY !== 0)) {
        x = event.clientX;
        y = event.clientY;
      } else if (event?.currentTarget?.getBoundingClientRect) {
        const rect = event.currentTarget.getBoundingClientRect();
        x = rect.left + rect.width / 2;
        y = rect.top + rect.height / 2;
      } else if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        x = rect.left + rect.width / 2;
        y = rect.top + rect.height / 2;
      }

      const endRadius = Math.hypot(
        Math.max(x, window.innerWidth - x),
        Math.max(y, window.innerHeight - y)
      );

      try {
        const transition = document.startViewTransition(() => {
          applyThemeClasses(next);
        });

        transition.ready
          .then(() => {
            try {
              document.documentElement.classList.add('theme-ripple-active');
              const anim = document.documentElement.animate(
                {
                  clipPath: [
                    `circle(0px at ${x}px ${y}px)`,
                    `circle(${endRadius}px at ${x}px ${y}px)`,
                  ],
                },
                {
                  duration: 480,
                  easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
                  pseudoElement: '::view-transition-new(root)',
                }
              );

              return anim.finished;
            } catch {
              // Browser may not support pseudoElement animation; standard view transition crossfade plays
            }
          })
          .catch(() => {
            /* transition aborted or superseded */
          })
          .finally(() => {
            document.documentElement.classList.remove('theme-ripple-active');
            isTransitioningRef.current = false;
          });

        return;
      } catch {
        document.documentElement.classList.remove('theme-ripple-active');
        isTransitioningRef.current = false;
      }
    }

    // 2. CSS-based smooth transition fallback
    isTransitioningRef.current = true;
    document.documentElement.classList.add('theme-transitioning');
    applyThemeClasses(next);

    setTimeout(() => {
      document.documentElement.classList.remove('theme-transitioning');
      isTransitioningRef.current = false;
    }, 420);
  }

  return (
    <div
      ref={containerRef}
      className={`theme-toggle-container ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '3px',
        padding: '3px',
        borderRadius: 'var(--radius-full)',
        background: 'var(--bg-surface-elevated)',
        border: '1px solid var(--border-medium)',
        position: 'relative',
        transition: 'background-color 0.25s ease, border-color 0.25s ease',
        ...style,
      }}
      role="group"
      aria-label="Theme selection"
    >
      <button
        type="button"
        onClick={(e) => chooseTheme('light', e)}
        aria-pressed={theme === 'light'}
        aria-label="Switch to light theme"
        title="Switch to light theme"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '4px 10px',
          borderRadius: 'var(--radius-full)',
          border: theme === 'light' ? '1px solid var(--color-primary)' : '1px solid transparent',
          fontSize: '0.72rem',
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
          cursor: 'pointer',
          background: theme === 'light' ? 'var(--gradient-primary)' : 'transparent',
          color: theme === 'light' ? '#ffffff' : 'var(--text-secondary)',
          boxShadow: theme === 'light' ? '0 1px 4px rgba(2, 132, 199, 0.25)' : 'none',
          transition: 'all 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        <Sun
          size={12}
          style={{
            transform: theme === 'light' ? 'rotate(15deg) scale(1.08)' : 'rotate(0deg) scale(0.95)',
            transition: 'transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1)',
          }}
        />
        <span>Light</span>
      </button>

      <button
        type="button"
        onClick={(e) => chooseTheme('dark', e)}
        aria-pressed={theme === 'dark'}
        aria-label="Switch to dark theme"
        title="Switch to dark theme"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '4px 10px',
          borderRadius: 'var(--radius-full)',
          border: theme === 'dark' ? '1px solid var(--border-medium)' : '1px solid transparent',
          fontSize: '0.72rem',
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
          cursor: 'pointer',
          background: theme === 'dark' ? 'var(--gradient-primary)' : 'transparent',
          color: theme === 'dark' ? '#07080a' : 'var(--text-secondary)',
          boxShadow: theme === 'dark' ? '0 1px 4px rgba(0, 0, 0, 0.3)' : 'none',
          transition: 'all 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        <Moon
          size={12}
          style={{
            transform: theme === 'dark' ? 'rotate(-12deg) scale(1.08)' : 'rotate(0deg) scale(0.95)',
            transition: 'transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1)',
          }}
        />
        <span>Dark</span>
      </button>
    </div>
  );
}
