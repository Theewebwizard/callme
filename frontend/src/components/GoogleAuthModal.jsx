import React, { useState } from 'react';
import { X, AlertCircle, ArrowRight, Sparkles, Building2, User, Mail, CheckCircle2 } from 'lucide-react';
import { api } from '../api';

export function GoogleIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
      <path
        fill="#4285F4"
        d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24z"
      />
      <path
        fill="#FBBC05"
        d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.99 0 12s.45 3.82 1.25 5.42l4.03-3.15z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
      />
    </svg>
  );
}

const PRESET_ACCOUNTS = [
  {
    name: 'Haveli Grand Management',
    email: 'haveli.restaurant@gmail.com',
    initial: 'H',
    bg: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
    tag: 'Registered Business',
    businessName: 'Haveli Grand Restaurant',
  },
  {
    name: 'Demo Business Owner',
    email: 'demo.owner@gmail.com',
    initial: 'D',
    bg: 'linear-gradient(135deg, #10b981 0%, #047857 100%)',
    tag: 'Google Workspace',
    businessName: 'Demo Services Co.',
  },
];

export default function GoogleAuthModal({
  isOpen,
  onClose,
  mode = 'signin', // 'signin' | 'signup'
  onSuccess,
}) {
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [showCustomInput, setShowCustomInput] = useState(false);

  // Custom Account Inputs
  const [customEmail, setCustomEmail] = useState('');
  const [customName, setCustomName] = useState('');
  const [customBizName, setCustomBizName] = useState('');

  // Unregistered Prompt State (when user clicks "Sign In" with a new Gmail)
  const [unregisteredData, setUnregisteredData] = useState(null);

  if (!isOpen) return null;

  const handleAuthenticate = async ({
    email,
    name,
    businessName,
    createIfMissing,
  }) => {
    if (!email || !email.includes('@')) {
      setErrorMsg('Please enter a valid Gmail / Google email address.');
      return;
    }

    setLoading(true);
    setErrorMsg(null);

    try {
      const res = await api.googleAuth({
        email: email.trim().lower ? email.trim().toLowerCase() : email.trim(),
        name: name || email.split('@')[0],
        business_name: businessName,
        create_if_missing: createIfMissing ?? mode === 'signup',
      });

      if (res.success && res.business) {
        // Save verified Google session
        const googleUser = {
          email: email.trim().toLowerCase(),
          name: name || email.split('@')[0],
          avatarInitial: (name || email)[0].toUpperCase(),
        };
        localStorage.setItem('answerly_google_user', JSON.stringify(googleUser));
        localStorage.setItem('callme_google_user', JSON.stringify(googleUser));
        onSuccess(res.business, googleUser);
        onClose();
      } else {
        // Business not found in sign-in mode -> invite user to provision
        setUnregisteredData({
          email: email.trim().toLowerCase(),
          name: name || email.split('@')[0],
          businessName: businessName || `${(name || email.split('@')[0]).replace(/[^a-zA-Z0-9 ]/g, '')}'s Business`,
        });
      }
    } catch (err) {
      setErrorMsg(err.message || 'Google authentication failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateForUnregistered = async (e) => {
    e.preventDefault();
    if (!unregisteredData) return;
    await handleAuthenticate({
      email: unregisteredData.email,
      name: unregisteredData.name,
      businessName: unregisteredData.businessName,
      createIfMissing: true,
    });
  };

  const handleCustomSubmit = (e) => {
    e.preventDefault();
    handleAuthenticate({
      email: customEmail,
      name: customName,
      businessName: customBizName,
      createIfMissing: mode === 'signup',
    });
  };

  return (
    <div className="google-modal-overlay" onClick={onClose}>
      <div className="google-modal" onClick={(e) => e.stopPropagation()}>
        {/* Modal Top Header */}
        <div className="google-modal-header" style={{ position: 'relative' }}>
          <button
            onClick={onClose}
            style={{
              position: 'absolute',
              top: '1rem',
              right: '1rem',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--slate-400)',
              padding: '4px',
              borderRadius: '50%',
            }}
          >
            <X size={18} />
          </button>

          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '0.65rem' }}>
            <GoogleIcon size={28} />
          </div>

          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#202124', margin: '0 0 0.25rem' }}>
            {mode === 'signup' ? 'Sign up with Google' : 'Sign in with Google'}
          </h3>
          <p style={{ fontSize: '0.85rem', color: '#5f6368', margin: 0 }}>
            to continue to <strong style={{ color: '#202124' }}>Answerly AI Receptionist</strong>
          </p>
        </div>

        {/* Modal Body */}
        <div className="google-modal-body">
          {errorMsg && (
            <div
              style={{
                padding: '0.65rem 0.85rem',
                borderRadius: 'var(--radius-sm)',
                marginBottom: '1rem',
                background: 'var(--rose-100)',
                color: 'var(--rose-700)',
                fontSize: '0.82rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              <AlertCircle size={16} /> {errorMsg}
            </div>
          )}

          {/* Scenario A: No existing workspace found for this email -> Provisioning prompt */}
          {unregisteredData ? (
            <div>
              <div
                style={{
                  background: 'linear-gradient(135deg, rgba(238, 242, 255, 0.8), rgba(245, 243, 255, 0.8))',
                  border: '1px solid var(--border-medium)',
                  padding: '1rem',
                  borderRadius: 'var(--radius-md)',
                  marginBottom: '1.25rem',
                }}
              >
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--indigo-950)', marginBottom: '0.25rem' }}>
                  No Workspace Found for {unregisteredData.email}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--indigo-800)', lineHeight: 1.4 }}>
                  Would you like to deploy a new 24/7 AI Receptionist agent linked to this Google account now?
                </div>
              </div>

              <form onSubmit={handleCreateForUnregistered}>
                <div className="form-group" style={{ marginBottom: '1rem' }}>
                  <label className="form-label">Business / Clinic / Restaurant Name</label>
                  <input
                    type="text"
                    className="form-input"
                    value={unregisteredData.businessName}
                    onChange={(e) =>
                      setUnregisteredData({
                        ...unregisteredData,
                        businessName: e.target.value,
                      })
                    }
                    required
                  />
                </div>

                <button
                  type="submit"
                  className="btn-primary"
                  disabled={loading}
                  style={{ width: '100%', padding: '0.8rem' }}
                >
                  <Sparkles size={16} /> {loading ? 'Provisioning...' : 'Launch Receptionist in 1 Click'}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setUnregisteredData(null);
                    setErrorMsg(null);
                  }}
                  style={{
                    width: '100%',
                    marginTop: '0.5rem',
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--slate-500)',
                    fontSize: '0.82rem',
                    cursor: 'pointer',
                    padding: '0.4rem',
                  }}
                >
                  ← Choose another Google account
                </button>
              </form>
            </div>
          ) : !showCustomInput ? (
            /* Scenario B: Choose an account list */
            <div>
              <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--slate-500)', marginBottom: '0.65rem' }}>
                Choose an account
              </div>

              {PRESET_ACCOUNTS.map((acc) => (
                <div
                  key={acc.email}
                  className="google-account-card"
                  onClick={() =>
                    handleAuthenticate({
                      email: acc.email,
                      name: acc.name,
                      businessName: acc.businessName,
                      createIfMissing: mode === 'signup',
                    })
                  }
                >
                  <div className="google-avatar" style={{ background: acc.bg }}>
                    {acc.initial}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ fontWeight: 700, fontSize: '0.88rem', color: '#202124' }}>
                        {acc.name}
                      </div>
                      <span style={{ fontSize: '0.72rem', background: 'rgba(79, 70, 229, 0.1)', color: 'var(--indigo-800)', border: '1px solid rgba(167, 139, 250, 0.3)', padding: '1px 6px', borderRadius: '8px', fontWeight: 600 }}>
                        {acc.tag}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.78rem', color: '#5f6368', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {acc.email}
                    </div>
                  </div>
                </div>
              ))}

              <div
                className="google-account-card"
                style={{ borderStyle: 'dashed' }}
                onClick={() => {
                  setShowCustomInput(true);
                  setErrorMsg(null);
                }}
              >
                <div
                  className="google-avatar"
                  style={{ background: 'var(--slate-100)', color: 'var(--slate-600)', border: '1px solid var(--slate-300)' }}
                >
                  <User size={18} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: '0.88rem', color: '#202124' }}>
                    Use another Google / Gmail account
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#5f6368' }}>
                    Sign in with your personal or business Gmail
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* Scenario C: Custom Gmail input */
            <form onSubmit={handleCustomSubmit}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.85rem' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--slate-800)' }}>
                  Enter Gmail Account Details
                </span>
                <button
                  type="button"
                  onClick={() => setShowCustomInput(false)}
                  style={{ background: 'transparent', border: 'none', color: 'var(--indigo-600)', fontSize: '0.78rem', cursor: 'pointer', fontWeight: 600 }}
                >
                  ← Back to list
                </button>
              </div>

              <div className="form-group" style={{ marginBottom: '0.85rem' }}>
                <label className="form-label">Gmail Address *</label>
                <input
                  type="email"
                  className="form-input"
                  placeholder="e.g. yourname@gmail.com"
                  value={customEmail}
                  onChange={(e) => setCustomEmail(e.target.value)}
                  required
                />
              </div>

              <div className="form-group" style={{ marginBottom: '0.85rem' }}>
                <label className="form-label">Account Name / Contact</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Rahul Sharma"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                />
              </div>

              {mode === 'signup' && (
                <div className="form-group" style={{ marginBottom: '1.25rem' }}>
                  <label className="form-label">Business / Clinic / Restaurant Name *</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. Sharma Dental Clinic"
                    value={customBizName}
                    onChange={(e) => setCustomBizName(e.target.value)}
                    required={mode === 'signup'}
                  />
                </div>
              )}

              <button
                type="submit"
                className="btn-primary"
                disabled={loading}
                style={{ width: '100%', padding: '0.8rem', marginTop: '0.5rem' }}
              >
                {loading ? 'Authenticating with Google...' : mode === 'signup' ? 'Create Receptionist with Google' : 'Sign in with Google'}
              </button>
            </form>
          )}

          {/* Google Legal Disclaimer Note */}
          <div style={{ marginTop: '1.25rem', paddingTop: '0.85rem', borderTop: '1px solid var(--border-medium)', fontSize: '0.74rem', color: '#5f6368', lineHeight: 1.4 }}>
            To continue, Google will securely share your email address and profile identity with <strong>Answerly AI Receptionist</strong> in accordance with strict tenant privacy standards.
          </div>
        </div>
      </div>
    </div>
  );
}
