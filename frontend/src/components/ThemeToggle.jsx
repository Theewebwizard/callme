import React, { useEffect, useState, useRef, useId } from "react";
import { flushSync } from "react-dom";

export const THEME_STORAGE_KEY = "callme_theme";

function readIsDark() {
  if (typeof document === "undefined") return true;
  const saved = localStorage.getItem("theme") || localStorage.getItem(THEME_STORAGE_KEY);
  if (saved) return saved === "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export default function ThemeToggle({ className = "", style = {} }) {
  const [dark, setDark] = useState(true);
  const buttonRef = useRef(null);
  const maskId = useId();

  useEffect(() => {
    const isDark = readIsDark();
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);
    document.documentElement.classList.toggle("light", !isDark);

    const handleThemeChange = (e) => {
      if (e?.detail) {
        setDark(e.detail === "dark");
      } else {
        setDark(readIsDark());
      }
    };

    window.addEventListener("callme:theme-changed", handleThemeChange);
    return () => window.removeEventListener("callme:theme-changed", handleThemeChange);
  }, []);

  const toggle = (e) => {
    const next = !dark;
    const apply = () => {
      flushSync(() => setDark(next));
      document.documentElement.classList.toggle("dark", next);
      document.documentElement.classList.toggle("light", !next);
      try {
        localStorage.setItem("theme", next ? "dark" : "light");
        localStorage.setItem(THEME_STORAGE_KEY, next ? "dark" : "light");
        window.dispatchEvent(
          new CustomEvent("callme:theme-changed", { detail: next ? "dark" : "light" })
        );
      } catch {
        /* storage unavailable in sandbox */
      }
    };

    const doc = document;
    if (!doc.startViewTransition || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      document.documentElement.classList.add("theme-transitioning");
      apply();
      setTimeout(() => {
        document.documentElement.classList.remove("theme-transitioning");
      }, 450);
      return;
    }

    // Determine circular reveal origin
    let x = window.innerWidth / 2;
    let y = window.innerHeight / 2;

    if (e?.clientX != null && e?.clientY != null && (e.clientX !== 0 || e.clientY !== 0)) {
      x = e.clientX;
      y = e.clientY;
    } else if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      x = rect.left + rect.width / 2;
      y = rect.top + rect.height / 2;
    }

    const r = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    const root = document.documentElement.style;
    root.setProperty("--tx", `${x}px`);
    root.setProperty("--ty", `${y}px`);
    root.setProperty("--tr", `${r}px`);

    doc.startViewTransition(apply);
  };

  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      title={dark ? "Switch to daytime planning mode" : "Switch to obsidian night mode"}
      className={`theme-toggle-btn ${className}`}
      style={style}
    >
      <span className={`theme-toggle-thumb ${dark ? "is-dark" : ""}`}>
        <svg viewBox="0 0 24 24" className="theme-toggle-svg" fill="none" strokeWidth="2" strokeLinecap="round">
          {/* sun rays */}
          <g className={`theme-sun-rays ${dark ? "is-dark" : ""}`}>
            {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
              <line key={a} x1="12" y1="2" x2="12" y2="4" transform={`rotate(${a} 12 12)`} />
            ))}
          </g>
          <mask id={maskId}>
            <rect width="24" height="24" fill="white" />
            <circle
              className="theme-moon-cut-circle"
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
            className={`theme-celestial-body ${dark ? "is-dark" : ""}`}
          />
        </svg>
      </span>
    </button>
  );
}
