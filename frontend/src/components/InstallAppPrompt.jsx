import React, { useState, useEffect } from 'react';
import { Download, Smartphone, X, Share, PlusSquare } from 'lucide-react';

export default function InstallAppPrompt({ variant = 'badge' }) {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [isInstallable, setIsInstallable] = useState(false);
  const [isIOS, setIsIOS] = useState(false);
  const [showIOSModal, setShowIOSModal] = useState(false);
  const [isStandalone, setIsStandalone] = useState(false);

  useEffect(() => {
    // 1. Detect if already installed as standalone PWA
    const standaloneMode =
      window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true;
    setIsStandalone(standaloneMode);

    if (standaloneMode) return;

    // 2. Detect iOS Safari
    const userAgent = window.navigator.userAgent.toLowerCase();
    const isAppleDevice = /iphone|ipad|ipod/.test(userAgent);
    const isSafari = /safari/.test(userAgent) && !/chrome|crios|fxios/.test(userAgent);
    if (isAppleDevice && isSafari) {
      setIsIOS(true);
      setIsInstallable(true);
    }

    // 3. Listen for Chromium beforeinstallprompt event
    const handleBeforeInstall = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setIsInstallable(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
    };
  }, []);

  const handleInstallClick = async () => {
    if (isIOS) {
      setShowIOSModal(true);
      return;
    }

    if (!deferredPrompt) return;

    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted') {
      setIsInstallable(false);
    }
    setDeferredPrompt(null);
  };

  if (isStandalone || !isInstallable) {
    return null;
  }

  // Header Pill / Badge Variant
  if (variant === 'badge') {
    return (
      <>
        <button
          onClick={handleInstallClick}
          className="btn-pwa-install"
          title="Install CallMe as an App on your Mobile or Desktop"
        >
          <Download size={13} strokeWidth={2.5} />
          <span>Install App</span>
        </button>

        {showIOSModal && (
          <div className="ios-install-backdrop" onClick={() => setShowIOSModal(false)}>
            <div className="ios-install-card" onClick={(e) => e.stopPropagation()}>
              <div className="ios-card-header">
                <div className="ios-badge">
                  <Smartphone size={18} color="#6366f1" />
                  <strong>Install CallMe on iPhone / iPad</strong>
                </div>
                <button className="btn-close" onClick={() => setShowIOSModal(false)}>
                  <X size={16} />
                </button>
              </div>
              <p className="ios-desc">
                Install CallMe directly to your home screen for instant full-screen access:
              </p>
              <ol className="ios-steps">
                <li>
                  <Share size={15} color="#38bdf8" /> Tap the <strong>Share</strong> button at the bottom of Safari.
                </li>
                <li>
                  <PlusSquare size={15} color="#a855f7" /> Scroll down and select <strong>'Add to Home Screen'</strong>.
                </li>
                <li>
                  Tap <strong>Add</strong> in the top right corner.
                </li>
              </ol>
              <button className="btn-primary w-full" onClick={() => setShowIOSModal(false)}>
                Got it
              </button>
            </div>
          </div>
        )}
      </>
    );
  }

  return null;
}
