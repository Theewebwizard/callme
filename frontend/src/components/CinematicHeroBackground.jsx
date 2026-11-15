import React, { useEffect, useRef, useState } from 'react';

/**
 * CinematicHeroBackground
 * Raycast-inspired ambient canvas background for Answerly.
 * Renders subtle audio-inspired harmonic wave ribbons, drifting acoustic nodes,
 * soft atmospheric lighting, and a fine film grain noise overlay.
 *
 * Performance & A11y:
 * - Automatically pauses requestAnimationFrame when scrolled out of view (IntersectionObserver).
 * - Pauses when tab is hidden (document.visibilitychange).
 * - Respects prefers-reduced-motion by rendering a single static frame and stopping the animation loop.
 * - Hardware accelerated using canvas 2D with minimal draw calls.
 */
export default function CinematicHeroBackground() {
  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReducedMotion(mediaQuery.matches);

    const handleMotionChange = (e) => setReducedMotion(e.matches);
    mediaQuery.addEventListener('change', handleMotionChange);

    return () => mediaQuery.removeEventListener('change', handleMotionChange);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    let animationFrameId = null;
    let isVisible = true;
    let width = 0;
    let height = 0;
    let time = 0;

    // Drifting acoustic nodes
    const particleCount = 28;
    const particles = [];

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = container.clientWidth;
      height = container.clientHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.scale(dpr, dpr);

      // Initialize or scale particles
      if (particles.length === 0) {
        for (let i = 0; i < particleCount; i++) {
          particles.push({
            x: Math.random() * width,
            y: Math.random() * height,
            radius: Math.random() * 1.5 + 0.8,
            vx: (Math.random() - 0.5) * 0.25,
            vy: (Math.random() - 0.5) * 0.25,
            alpha: Math.random() * 0.35 + 0.15,
            pulseSpeed: Math.random() * 0.02 + 0.01,
            pulsePhase: Math.random() * Math.PI * 2,
          });
        }
      }
    };

    resize();
    window.addEventListener('resize', resize, { passive: true });

    // Render single frame
    const render = () => {
      ctx.clearRect(0, 0, width, height);

      // 1. Soft atmospheric ambient glow
      const radialGlow = ctx.createRadialGradient(
        width * 0.5,
        height * 0.28,
        0,
        width * 0.5,
        height * 0.35,
        width * 0.55
      );
      radialGlow.addColorStop(0, 'rgba(16, 185, 129, 0.07)'); // Emerald accent
      radialGlow.addColorStop(0.35, 'rgba(14, 165, 233, 0.03)'); // Deep Cyan
      radialGlow.addColorStop(0.7, 'rgba(7, 8, 10, 0.0)');
      ctx.fillStyle = radialGlow;
      ctx.fillRect(0, 0, width, height);

      // 2. Harmonic Audio Wave Ribbons
      const waveCount = 3;
      const waveConfigs = [
        {
          baseY: height * 0.35,
          amplitude: 38,
          frequency: 0.0022,
          speed: 0.007,
          color: 'rgba(16, 185, 129, 0.065)', // Emerald
          lineColor: 'rgba(52, 211, 153, 0.22)',
          phase: 0,
        },
        {
          baseY: height * 0.42,
          amplitude: 48,
          frequency: 0.0018,
          speed: 0.005,
          color: 'rgba(56, 189, 248, 0.045)', // Sky / Cyan
          lineColor: 'rgba(56, 189, 248, 0.16)',
          phase: 2.2,
        },
        {
          baseY: height * 0.48,
          amplitude: 32,
          frequency: 0.0028,
          speed: 0.009,
          color: 'rgba(16, 185, 129, 0.035)', // Deep Mint
          lineColor: 'rgba(16, 185, 129, 0.12)',
          phase: 4.5,
        },
      ];

      waveConfigs.forEach((w) => {
        ctx.beginPath();
        ctx.moveTo(0, height);

        for (let x = 0; x <= width; x += 12) {
          const y =
            w.baseY +
            Math.sin(x * w.frequency + time * w.speed + w.phase) * w.amplitude +
            Math.cos(x * w.frequency * 0.5 + time * w.speed * 0.8) * (w.amplitude * 0.4);

          if (x === 0) {
            ctx.lineTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }

        ctx.lineTo(width, height);
        ctx.closePath();
        ctx.fillStyle = w.color;
        ctx.fill();

        // Trace the top edge line
        ctx.beginPath();
        for (let x = 0; x <= width; x += 12) {
          const y =
            w.baseY +
            Math.sin(x * w.frequency + time * w.speed + w.phase) * w.amplitude +
            Math.cos(x * w.frequency * 0.5 + time * w.speed * 0.8) * (w.amplitude * 0.4);

          if (x === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }
        ctx.strokeStyle = w.lineColor;
        ctx.lineWidth = 1;
        ctx.stroke();
      });

      // 3. Drifting Acoustic Frequency Nodes
      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;

        // Wrap around boundaries smoothly
        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;

        const currentAlpha =
          p.alpha * (0.7 + 0.3 * Math.sin(time * p.pulseSpeed + p.pulsePhase));

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(52, 211, 153, ${currentAlpha})`;
        ctx.fill();
      });

      // 4. Subtle Inter-node Hairline Constellations (Voice Net)
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 110) {
            const lineAlpha = (1 - dist / 110) * 0.08;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(52, 211, 153, ${lineAlpha})`;
            ctx.lineWidth = 0.75;
            ctx.stroke();
          }
        }
      }
    };

    // Animation Loop
    const loop = () => {
      if (isVisible && !reducedMotion) {
        time += 1;
        render();
        animationFrameId = requestAnimationFrame(loop);
      }
    };

    // Render initial frame
    render();

    // Start loop if motion is allowed
    if (!reducedMotion) {
      animationFrameId = requestAnimationFrame(loop);
    }

    // Visibility Observer: pause when offscreen
    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;
        isVisible = entry.isIntersecting;
        if (isVisible && !reducedMotion) {
          cancelAnimationFrame(animationFrameId);
          animationFrameId = requestAnimationFrame(loop);
        } else {
          cancelAnimationFrame(animationFrameId);
        }
      },
      { threshold: 0.05 }
    );

    observer.observe(container);

    // Page Visibility API: pause when tab hidden
    const handleVisibility = () => {
      if (document.hidden) {
        isVisible = false;
        cancelAnimationFrame(animationFrameId);
      } else {
        isVisible = true;
        if (!reducedMotion) {
          animationFrameId = requestAnimationFrame(loop);
        }
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', handleVisibility);
      observer.disconnect();
    };
  }, [reducedMotion]);

  return (
    <div
      ref={containerRef}
      className="cinematic-bg-container"
      aria-hidden="true"
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: '100%',
        minHeight: '820px',
        overflow: 'hidden',
        pointerEvents: 'none',
        zIndex: 0,
      }}
    >
      {/* 1. Canvas Harmonic Audio Wave Layer */}
      <canvas
        ref={canvasRef}
        style={{
          width: '100%',
          height: '100%',
          display: 'block',
        }}
      />

      {/* 2. Top-Center Specular Aura (Atmospheric Light) */}
      <div
        style={{
          position: 'absolute',
          top: '-15%',
          left: '50%',
          transform: 'translateX(-50%)',
          width: '780px',
          height: '480px',
          background: 'radial-gradient(ellipse at center, rgba(16, 185, 129, 0.12) 0%, rgba(14, 165, 233, 0.04) 45%, transparent 70%)',
          filter: 'blur(50px)',
          opacity: 0.9,
          pointerEvents: 'none',
        }}
      />

      {/* 3. Bottom Gradient Fog (Seamless Blend into Next Sections) */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: '240px',
          background: 'linear-gradient(to bottom, transparent 0%, var(--bg-app) 100%)',
          pointerEvents: 'none',
        }}
      />

      {/* 4. Fine Noise Film Grain Overlay (Raycast Tactile Texture) */}
      <svg
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          opacity: 0.04,
          pointerEvents: 'none',
        }}
      >
        <filter id="cinematic-noise">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.75"
            numOctaves="3"
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#cinematic-noise)" />
      </svg>
    </div>
  );
}
