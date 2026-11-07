import React from 'react';

export default function AmbientAuroraField() {
  return (
    <div aria-hidden="true" className="aurora-field" style={{ overflow: 'hidden' }}>
      {/* Background Grid with radial fade mask from anim */}
      <div className="bg-grid" />

      {/* Floating Glow Orbs from anim */}
      <div
        className="orb animate-float"
        style={{
          width: '28rem',
          height: '28rem',
          top: '5rem',
          left: '-8rem',
        }}
      />
      <div
        className="orb animate-float"
        style={{
          width: '24rem',
          height: '24rem',
          bottom: '0',
          right: '-5rem',
          animationDelay: '-6s',
        }}
      />
    </div>
  );
}
