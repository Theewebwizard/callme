import { useEffect } from 'react';

/**
 * useScrollReveal
 * Attaches an IntersectionObserver to elements matching the selector
 * to trigger CSS reveal transitions as they scroll into view.
 */
export default function useScrollReveal(selector = '.reveal-on-scroll', options = {}) {
  useEffect(() => {
    // If user prefers reduced motion, immediately reveal everything
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mediaQuery.matches) {
      document.querySelectorAll(selector).forEach((el) => {
        el.classList.add('is-revealed');
      });
      return;
    }

    const observer = new IntersectionObserver(
      (entries, obs) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-revealed');
            // Unobserve after revealing to save CPU
            obs.unobserve(entry.target);
          }
        });
      },
      {
        threshold: options.threshold || 0.12,
        rootMargin: options.rootMargin || '0px 0px -40px 0px',
      }
    );

    const elements = document.querySelectorAll(selector);
    elements.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, [selector, options.threshold, options.rootMargin]);
}
