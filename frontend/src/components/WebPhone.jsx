import React, { useState, useEffect, useRef } from 'react';
import {
  Phone,
  PhoneOff,
  Mic,
  MicOff,
  Send,
  Bot,
  Radio,
  Sparkles,
  Zap,
  Volume2,
  Loader2,
  User,
  ShieldCheck,
  Languages,
  Clock,
  Layers,
  ArrowRight,
} from 'lucide-react';
import { api } from '../api';

/* Toggle switch */
function Toggle({ checked, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`webphone-toggle-switch ${checked ? 'checked' : ''}`}
      style={{
        width: '38px',
        height: '22px',
        borderRadius: '11px',
        position: 'relative',
        cursor: 'pointer',
        transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
        flexShrink: 0,
        padding: 0,
        outline: 'none',
        display: 'inline-flex',
        alignItems: 'center',
        boxSizing: 'border-box',
      }}
    >
      <span
        className="webphone-toggle-knob"
        style={{
          position: 'absolute',
          top: '2px',
          left: checked ? '18px' : '2px',
          width: '14px',
          height: '14px',
          borderRadius: '50%',
          background: '#ffffff',
          transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.25)',
          display: 'block',
        }}
      />
    </button>
  );
}

/* Dynamic State-Driven Waveform */
function DynamicAudioWaveform({ state }) {
  // state: 'idle' | 'connecting' | 'listening' | 'speaking' | 'loading'
  const isSpeaking = state === 'speaking';
  const isListening = state === 'listening';
  const isConnecting = state === 'connecting';
  const isTurnLoading = state === 'loading';

  const barCount = 26;
  const bars = Array.from({ length: barCount }, (_, i) => i);

  return (
    <div
      className="webphone-waveform-container"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '4px',
        height: '46px',
        width: '100%',
        padding: '0.4rem 0',
      }}
    >
      {bars.map((i) => {
        let height = Math.round(8 + Math.sin((i / barCount) * Math.PI) * 14);
        let color = i % 2 === 0 ? 'var(--sky-500, #0ea5e9)' : 'var(--sky-400, #38bdf8)';
        let anim = `waveIdleBreath 2s ease-in-out infinite alternate`;
        let delay = `${((i % 13) * 0.1).toFixed(2)}s`;

        if (isSpeaking) {
          height = Math.round(10 + Math.sin(i * 0.6) * 16 + 8);
          color = '#10b981';
          anim = `waveSpeakingDance 0.65s ease-in-out infinite alternate`;
          delay = `${(i * 0.04).toFixed(2)}s`;
        } else if (isListening) {
          height = Math.round(8 + Math.sin(i * 0.8) * 14 + 6);
          color = '#0ea5e9';
          anim = `waveListeningRipple 0.5s ease-in-out infinite alternate`;
          delay = `${(i * 0.035).toFixed(2)}s`;
        } else if (isConnecting || isTurnLoading) {
          height = Math.round(6 + (i % 5) * 5);
          color = '#f59e0b';
          anim = `waveLoadingBounce 0.8s ease-in-out infinite alternate`;
          delay = `${(i * 0.06).toFixed(2)}s`;
        }

        return (
          <div
            key={i}
            className="waveform-bar"
            style={{
              width: '3.5px',
              height: `${height}px`,
              borderRadius: '4px',
              background: color,
              transition: 'height 0.2s ease, background 0.2s ease',
              animation: anim,
              animationDelay: delay,
              flexShrink: 0,
            }}
          />
        );
      })}
    </div>
  );
}

export default function WebPhone({ business }) {
  const [callActive, setCallActive] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [callStatus, setCallStatus] = useState('idle');
  const [sessionId, setSessionId] = useState(null);
  const [duration, setDuration] = useState(0);
  const [transcript, setTranscript] = useState([]);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [interimText, setInterimText] = useState('');
  const [handsFree, setHandsFree] = useState(true);
  const [isMicMuted, setIsMicMuted] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [errorMsg, setErrorMsg] = useState(null);
  const [isTurnLoading, setIsTurnLoading] = useState(false);

  const [speechLang, setSpeechLang] = useState(() => {
    try {
      return localStorage.getItem('callme_speech_lang') || 'hi-IN';
    } catch {
      return 'hi-IN';
    }
  });

  // Refs (prevent stale closures)
  const callActiveRef = useRef(false);
  const isStartingCallRef = useRef(false);
  const currentTurnIdRef = useRef(0);
  const cooloffTimerRef = useRef(null);
  const sessionIdRef = useRef(null);
  const isSpeakingRef = useRef(false);
  const isListeningRef = useRef(false);
  const isMicMutedRef = useRef(false);
  const handsFreeRef = useRef(true);
  const speechLangRef = useRef(speechLang);
  const isTurnInFlightRef = useRef(false);
  const silenceTimerRef = useRef(null);
  const accumulatedSpeechRef = useRef('');
  const timerRef = useRef(null);
  const currentAudioRef = useRef(null);
  const recognitionRef = useRef(null);
  const transcriptBottomRef = useRef(null);

  useEffect(() => { callActiveRef.current = callActive; }, [callActive]);
  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);
  useEffect(() => { isMicMutedRef.current = isMicMuted; }, [isMicMuted]);
  useEffect(() => { handsFreeRef.current = handsFree; }, [handsFree]);
  useEffect(() => { speechLangRef.current = speechLang; }, [speechLang]);

  useEffect(() => {
    transcriptBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript, interimText]);

  useEffect(() => {
    return () => {
      callActiveRef.current = false;
      isStartingCallRef.current = false;
      if (timerRef.current) clearInterval(timerRef.current);
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      if (cooloffTimerRef.current) clearTimeout(cooloffTimerRef.current);
      stopAllAudio();
      stopRecognition();
    };
  }, []);

  const formatDuration = (secs) => {
    const m = Math.floor(secs / 60).toString().padStart(2, '0');
    const s = (secs % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  const changeSpeechLanguage = (lang) => {
    setSpeechLang(lang);
    speechLangRef.current = lang;
    try { localStorage.setItem('callme_speech_lang', lang); } catch {}
    if (callActiveRef.current && isListeningRef.current) {
      stopRecognition();
      setTimeout(() => {
        if (callActiveRef.current && !isSpeakingRef.current && !isTurnInFlightRef.current) startSpeechListening();
      }, 150);
    }
  };

  const stopRecognition = () => {
    if (recognitionRef.current) {
      try { recognitionRef.current.onend = null; recognitionRef.current.abort(); } catch {}
      recognitionRef.current = null;
    }
    isListeningRef.current = false;
    setIsListening(false);
  };

  const unlockAudioForMobile = () => {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        if (!window._callmeAudioCtx) window._callmeAudioCtx = new AudioCtx();
        if (window._callmeAudioCtx.state === 'suspended') window._callmeAudioCtx.resume();
        const buf = window._callmeAudioCtx.createBuffer(1, 1, 22050);
        const src = window._callmeAudioCtx.createBufferSource();
        src.buffer = buf; src.connect(window._callmeAudioCtx.destination); src.start(0);
      }
    } catch {}
    try {
      const silent = new Audio('data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA');
      silent.volume = 0.01;
      silent.play().then(() => silent.pause()).catch(() => {});
    } catch {}
    try {
      if (window.speechSynthesis) { const u = new SpeechSynthesisUtterance(''); u.volume = 0; window.speechSynthesis.speak(u); }
    } catch {}
  };

  const stopAllAudio = () => {
    if (cooloffTimerRef.current) { clearTimeout(cooloffTimerRef.current); cooloffTimerRef.current = null; }
    if (currentAudioRef.current) {
      try {
        currentAudioRef.current.onended = null; currentAudioRef.current.onerror = null;
        currentAudioRef.current.pause(); currentAudioRef.current.currentTime = 0; currentAudioRef.current.src = '';
      } catch {}
      currentAudioRef.current = null;
    }
    if (window.speechSynthesis) { try { window.speechSynthesis.pause(); window.speechSynthesis.cancel(); } catch {} }
    isSpeakingRef.current = false;
    setIsSpeaking(false);
  };

  const playAudio = (base64Audio, mimeType, fallbackText, onEnd) => {
    stopRecognition();
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    accumulatedSpeechRef.current = '';
    setInterimText('');
    stopAllAudio();
    if (!callActiveRef.current) return;

    const onAudioComplete = () => {
      if (!callActiveRef.current) { stopAllAudio(); return; }
      isSpeakingRef.current = false; setIsSpeaking(false); currentAudioRef.current = null;
      if (cooloffTimerRef.current) clearTimeout(cooloffTimerRef.current);
      cooloffTimerRef.current = setTimeout(() => {
        if (callActiveRef.current && !isSpeakingRef.current && onEnd) onEnd();
      }, 350);
    };

    const speakFallback = (txt) => {
      if (!callActiveRef.current) return;
      if (window.speechSynthesis && txt) {
        isSpeakingRef.current = true; setIsSpeaking(true);
        const utter = new SpeechSynthesisUtterance(txt);
        utter.rate = 1.05;
        utter.lang = /[\u0900-\u097F]/.test(txt) || (speechLangRef.current || '').startsWith('hi') ? 'hi-IN' : 'en-IN';
        utter.onend = onAudioComplete; utter.onerror = onAudioComplete;
        window.speechSynthesis.speak(utter);
      } else { onAudioComplete(); }
    };

    if (!base64Audio) { speakFallback(fallbackText); return; }
    isSpeakingRef.current = true; setIsSpeaking(true);
    const mime = mimeType || (base64Audio.startsWith('UklGR') ? 'audio/wav' : 'audio/mp3');
    const audio = new Audio(`data:${mime};base64,${base64Audio}`);
    currentAudioRef.current = audio;
    audio.onended = onAudioComplete;
    audio.onerror = () => speakFallback(fallbackText);
    audio.play().catch(() => speakFallback(fallbackText));
  };

  const startSpeechListening = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { setCallStatus('Browser speech not supported — type below'); return; }
    if (!callActiveRef.current || isTurnInFlightRef.current || isSpeakingRef.current || isMicMutedRef.current) return;
    stopRecognition();

    try {
      const rec = new SR();
      rec.continuous = false;
      rec.interimResults = true;
      rec.lang = speechLangRef.current || 'hi-IN';
      recognitionRef.current = rec;

      rec.onstart = () => {
        if (isSpeakingRef.current || !callActiveRef.current || isTurnInFlightRef.current) {
          stopRecognition(); return;
        }
        isListeningRef.current = true;
        setIsListening(true);
        setCallStatus('listening');
      };

      rec.onresult = (event) => {
        if (isSpeakingRef.current || !callActiveRef.current || isTurnInFlightRef.current) {
          accumulatedSpeechRef.current = ''; setInterimText(''); return;
        }
        let interim = '', finalChunk = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const item = event.results[i];
          if (item.isFinal) finalChunk += item[0].transcript;
          else interim += item[0].transcript;
        }
        if (finalChunk) accumulatedSpeechRef.current += ' ' + finalChunk;
        const display = (accumulatedSpeechRef.current + ' ' + interim).trim();
        setInterimText(display);
      };

      rec.onerror = (e) => {
        if (e.error === 'no-speech') return;
        if (e.error === 'not-allowed') {
          setErrorMsg('Microphone access blocked. Enable mic permissions in browser settings.');
          isListeningRef.current = false; setIsListening(false); return;
        }
      };

      rec.onend = () => {
        isListeningRef.current = false;
        setIsListening(false);
        if (!callActiveRef.current || isSpeakingRef.current || isTurnInFlightRef.current) return;
        const captured = accumulatedSpeechRef.current.trim();
        if (captured && captured.length > 1 && handsFreeRef.current && !isMicMutedRef.current) {
          accumulatedSpeechRef.current = '';
          setInterimText('');
          executeSendTurn(captured);
        } else {
          accumulatedSpeechRef.current = '';
          setInterimText('');
          if (callActiveRef.current && !isSpeakingRef.current && !isTurnInFlightRef.current && !isMicMutedRef.current && handsFreeRef.current) {
            setTimeout(startSpeechListening, 200);
          }
        }
      };

      rec.start();
    } catch {
      isListeningRef.current = false;
      setIsListening(false);
    }
  };

  const executeSendTurn = async (textToSend) => {
    if (!textToSend || !callActiveRef.current || isTurnInFlightRef.current) return;
    isTurnInFlightRef.current = true;
    setIsTurnLoading(true);
    setCallStatus('thinking');
    stopRecognition();

    const turnId = ++currentTurnIdRef.current;
    setTranscript((prev) => [
      ...prev,
      { id: turnId, role: 'user', text: textToSend, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) },
    ]);

    try {
      const resp = await api.sendWebCallTurn(sessionIdRef.current, null, textToSend);
      if (!callActiveRef.current) return;

      const aiText = resp.text || resp.message || 'I hear you.';
      setTranscript((prev) => [
        ...prev,
        {
          id: ++currentTurnIdRef.current,
          role: 'assistant',
          text: aiText,
          tool: resp.tool_executed || null,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);

      setCallStatus('speaking');
      playAudio(resp.audio_base64, resp.audio_mime, aiText, () => {
        isTurnInFlightRef.current = false;
        setIsTurnLoading(false);
        if (callActiveRef.current && handsFreeRef.current && !isMicMutedRef.current) {
          startSpeechListening();
        } else if (callActiveRef.current) {
          setCallStatus('active');
        }
      });
    } catch (err) {
      isTurnInFlightRef.current = false;
      setIsTurnLoading(false);
      setErrorMsg(err.message || 'Turn error');
      if (callActiveRef.current && handsFreeRef.current && !isMicMutedRef.current) {
        startSpeechListening();
      }
    }
  };

  const startCall = async () => {
    if (callActive || isConnecting) return;
    setErrorMsg(null);
    setIsConnecting(true);
    setCallStatus('connecting');
    unlockAudioForMobile();

    try {
      const resp = await api.startWebCall(business.id);
      setSessionId(resp.session_id);
      sessionIdRef.current = resp.session_id;
      setCallActive(true);
      callActiveRef.current = true;
      setIsConnecting(false);

      const greetingText = resp.greeting_text || business.greeting_message || 'Namaste! How can I help?';
      setTranscript([
        {
          id: 0,
          role: 'assistant',
          text: greetingText,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);

      // Timer
      timerRef.current = setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);

      setCallStatus('speaking');
      playAudio(resp.greeting_audio_base64, resp.greeting_audio_mime, greetingText, () => {
        if (callActiveRef.current && handsFreeRef.current && !isMicMutedRef.current) {
          startSpeechListening();
        } else if (callActiveRef.current) {
          setCallStatus('active');
        }
      });
    } catch (err) {
      setIsConnecting(false);
      setCallActive(false);
      callActiveRef.current = false;
      setErrorMsg(err.message || 'Call initialization failed');
      setCallStatus('idle');
    }
  };

  const endCall = async () => {
    callActiveRef.current = false;
    setCallActive(false);
    setIsConnecting(false);
    if (timerRef.current) clearInterval(timerRef.current);
    stopAllAudio();
    stopRecognition();
    setCallStatus('ended');

    if (sessionIdRef.current) {
      try {
        await api.hangupWebCall(sessionIdRef.current);
      } catch {}
    }
  };

  const toggleMute = () => {
    const next = !isMicMuted;
    setIsMicMuted(next);
    isMicMutedRef.current = next;
    if (next) {
      stopRecognition();
      setCallStatus('muted');
    } else if (callActive && !isSpeaking && !isTurnLoading) {
      startSpeechListening();
    }
  };

  const handleTextSubmit = (e) => {
    e.preventDefault();
    if (!textInput.trim() || isTurnLoading) return;
    const txt = textInput.trim();
    setTextInput('');
    executeSendTurn(txt);
  };

  const handleImmediateSendSpeech = () => {
    if (interimText.trim()) {
      const txt = interimText.trim();
      accumulatedSpeechRef.current = '';
      setInterimText('');
      executeSendTurn(txt);
    }
  };

  // Derive active waveform state
  const waveformState = (() => {
    if (isSpeaking) return 'speaking';
    if (isListening) return 'listening';
    if (isConnecting) return 'connecting';
    if (isTurnLoading) return 'loading';
    return 'idle';
  })();

  return (
    <section className="main-content" aria-label="Web Voice Telephony Console" style={{ padding: '1.75rem 2rem 2.5rem' }}>
      {/* 1. Header with Breadcrumb and Inbound DID badge */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.2rem 0.6rem',
              borderRadius: 'var(--radius-full)',
              background: 'var(--bg-surface-elevated)',
              border: '1px solid var(--border-medium)',
              color: 'var(--text-secondary)',
              fontSize: '0.72rem',
              fontWeight: 600,
              marginBottom: '0.35rem',
            }}
          >
            <Radio size={12} className={callActive ? 'animate-pulse text-emerald-400' : ''} /> Low-Latency WebRTC Gateway
          </div>
          <h1 className="section-title" style={{ margin: 0 }}>
            Inbound Voice Phone Console
          </h1>
          <p className="section-subtitle" style={{ margin: '3px 0 0' }}>
            Direct bidirectional WebRTC acoustic phone link with <strong>{business?.name}</strong>'s AI receptionist.
          </p>
        </div>

        {errorMsg && (
          <div
            style={{
              background: 'rgba(244, 63, 94, 0.1)',
              border: '1px solid rgba(244, 63, 94, 0.3)',
              color: '#fb7185',
              padding: '0.35rem 0.75rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.76rem',
              fontWeight: 500,
            }}
          >
            {errorMsg}
          </div>
        )}
      </div>

      {/* 2. Two-Column Telephony Station Layout */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(340px, 400px) minmax(0, 1fr)',
          gap: '1.75rem',
          alignItems: 'start',
        }}
      >
        {/* Left Column: Voice Phone Controller */}
        <div
          className="card"
          style={{
            display: 'flex',
            flexDirection: 'column',
            padding: '1.5rem',
            gap: '1.25rem',
            boxShadow: 'var(--shadow-md), var(--specular-top)',
          }}
        >
          {/* Controller Top Bar: State & Timer */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                padding: '3px 9px',
                borderRadius: 'var(--radius-full)',
                fontSize: '0.72rem',
                fontFamily: 'var(--font-mono)',
                fontWeight: 600,
                background: callActive ? 'rgba(16, 185, 129, 0.12)' : 'var(--bg-surface-elevated)',
                color: callActive ? 'var(--mint-400)' : 'var(--text-tertiary)',
                border: '1px solid',
                borderColor: callActive ? 'rgba(16, 185, 129, 0.3)' : 'var(--border-medium)',
              }}
            >
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  background: callActive ? 'var(--mint-500)' : 'var(--text-tertiary)',
                }}
              />
              {callActive ? 'LIVE WEBRTC CALL' : isConnecting ? 'CONNECTING...' : 'STANDBY'}
            </span>

            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.85rem',
                fontWeight: 700,
                color: callActive ? '#ffffff' : 'var(--text-tertiary)',
              }}
            >
              {formatDuration(duration)}
            </span>
          </div>

          {/* Business Identity & Line */}
          <div style={{ textAlign: 'center', padding: '0.5rem 0' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.02em', margin: '0 0 4px 0' }}>
              {business?.name || 'Reception Line'}
            </h2>
            <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
              Inbound DID: {business?.phone_number || '+91 80 4123 5678'}
            </div>
          </div>

          {/* Acoustic Waveform & Telemetry Display Card */}
          <div
            className="webphone-acoustic-card"
            style={{
              background: 'var(--bg-surface-elevated, #f0f7ff)',
              border: '1.5px solid var(--border-medium, #bae6fd)',
              borderRadius: '12px',
              padding: '0.9rem 1.15rem',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              boxShadow: 'inset 0 1px 3px rgba(2, 132, 199, 0.04)',
              transition: 'all 0.2s ease',
            }}
          >
            {/* Top Telemetry Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                width: '100%',
                marginBottom: '6px',
                paddingBottom: '6px',
                borderBottom: '1px solid var(--border-subtle, rgba(182, 213, 242, 0.5))',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  fontSize: '0.68rem',
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 600,
                  color: isSpeaking ? '#059669' : isListening ? '#0284c7' : 'var(--text-secondary, #0369a1)',
                }}
              >
                <Radio size={11} className={callActive ? 'spin' : ''} style={{ color: isSpeaking ? '#10b981' : isListening ? '#0ea5e9' : 'var(--sky-500, #0ea5e9)' }} />
                <span>{callActive ? 'VOICE LINE ACTIVE • 24kHz OPUS' : 'VOICE LINE READY • 24kHz OPUS'}</span>
              </div>
              <div
                style={{
                  fontSize: '0.66rem',
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 700,
                  color: isSpeaking ? '#059669' : isListening ? '#0284c7' : 'var(--text-tertiary, #64748b)',
                  background: 'var(--bg-card, #ffffff)',
                  padding: '1px 6px',
                  borderRadius: '4px',
                  border: '1px solid var(--border-medium, #b6d5f2)',
                }}
              >
                {callActive ? (callDuration || '00:00') : 'STANDBY'}
              </div>
            </div>

            {/* Active Undulating Audio Waveform */}
            <DynamicAudioWaveform state={waveformState} />

            {/* Spoken Turn Status Headline */}
            <div style={{ textAlign: 'center', marginTop: '4px' }}>
              <div
                style={{
                  fontSize: '0.84rem',
                  fontWeight: 700,
                  color: isSpeaking ? '#059669' : isListening ? '#0284c7' : 'var(--text-primary, #0c4a6e)',
                  letterSpacing: '-0.01em',
                }}
              >
                {isSpeaking
                  ? 'AI Receptionist is Speaking...'
                  : isListening
                  ? 'Listening to Caller Microphone...'
                  : isTurnLoading
                  ? 'Reasoning & Querying Database...'
                  : callActive
                  ? 'Voice Link Established • Hands-Free Active'
                  : 'AI Spoken Receptionist Standing By'}
              </div>
              <div
                style={{
                  fontSize: '0.7rem',
                  color: 'var(--text-tertiary, #64748b)',
                  marginTop: '2px',
                }}
              >
                {callActive
                  ? 'Turn-taking enabled • Speak naturally into your microphone'
                  : 'Click the green phone button below to begin live test conversation'}
              </div>
            </div>

            {/* Bottom Capability Highlights */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '12px',
                marginTop: '8px',
                paddingTop: '6px',
                borderTop: '1px solid var(--border-subtle, rgba(182, 213, 242, 0.5))',
                width: '100%',
                flexWrap: 'wrap',
              }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.66rem', color: 'var(--text-secondary, #475569)', fontFamily: 'var(--font-mono)' }}>
                <Sparkles size={10} style={{ color: '#0ea5e9' }} />
                <span>Zero-Latency Turn Taking</span>
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.66rem', color: 'var(--text-secondary, #475569)', fontFamily: 'var(--font-mono)' }}>
                <Languages size={10} style={{ color: '#0ea5e9' }} />
                <span>Hindi & English Code-Switch</span>
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.66rem', color: 'var(--text-secondary, #475569)', fontFamily: 'var(--font-mono)' }}>
                <Zap size={10} style={{ color: '#0ea5e9' }} />
                <span>Live Table Booking</span>
              </span>
            </div>
          </div>

          {/* Primary Action Button (Call / End Call) */}
          <div style={{ display: 'flex', justifyContent: 'center', padding: '0.5rem 0' }}>
            {!callActive && !isConnecting && (
              <button
                type="button"
                onClick={startCall}
                onTouchStart={unlockAudioForMobile}
                style={{
                  width: '68px',
                  height: '68px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #059669, #10b981)',
                  boxShadow: '0 8px 24px rgba(16, 185, 129, 0.45)',
                  border: 'none',
                  color: '#ffffff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                }}
                title="Start Live Voice Call"
              >
                <Phone size={28} />
              </button>
            )}

            {isConnecting && (
              <button
                type="button"
                onClick={endCall}
                style={{
                  width: '68px',
                  height: '68px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                  border: 'none',
                  color: '#ffffff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                }}
                title="Cancel Connection"
              >
                <PhoneOff size={26} />
              </button>
            )}

            {callActive && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
                <button
                  type="button"
                  onClick={toggleMute}
                  style={{
                    width: '52px',
                    height: '52px',
                    borderRadius: '50%',
                    background: isMicMuted ? 'rgba(239, 68, 68, 0.2)' : 'var(--bg-surface-elevated)',
                    border: '1px solid',
                    borderColor: isMicMuted ? '#ef4444' : 'var(--border-medium)',
                    color: isMicMuted ? '#ef4444' : 'var(--text-primary)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                  }}
                  title={isMicMuted ? 'Unmute Microphone' : 'Mute Microphone'}
                >
                  {isMicMuted ? <MicOff size={20} /> : <Mic size={20} />}
                </button>

                <button
                  type="button"
                  onClick={endCall}
                  style={{
                    width: '64px',
                    height: '64px',
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                    boxShadow: '0 8px 20px rgba(239, 68, 68, 0.45)',
                    border: 'none',
                    color: '#ffffff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                  }}
                  title="Hang Up Call"
                >
                  <PhoneOff size={26} />
                </button>
              </div>
            )}
          </div>

          {/* Language & Voice Settings */}
          <div
            style={{
              borderTop: '1px solid var(--border-medium)',
              paddingTop: '0.85rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '5px' }}>
                <Languages size={13} style={{ color: 'var(--text-tertiary)' }} />
                <span>Call Language:</span>
              </span>

              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  background: 'var(--bg-surface-elevated, #f0f7ff)',
                  border: '1.5px solid var(--border-medium, #bae6fd)',
                  borderRadius: '8px',
                  padding: '2px',
                  gap: '2px',
                }}
              >
                {[
                  { id: 'hi-IN', label: 'Hindi' },
                  { id: 'en-IN', label: 'English' },
                ].map((l) => {
                  const isActive = speechLang === l.id;
                  return (
                    <button
                      key={l.id}
                      type="button"
                      onClick={() => changeSpeechLanguage(l.id)}
                      style={{
                        background: isActive ? '#0ea5e9' : 'transparent',
                        color: isActive ? '#ffffff' : 'var(--text-secondary, #475569)',
                        border: 'none',
                        borderRadius: '6px',
                        padding: '4px 11px',
                        fontSize: '0.74rem',
                        fontWeight: isActive ? 700 : 600,
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                        boxShadow: isActive ? '0 1px 4px rgba(14, 165, 233, 0.3)' : 'none',
                      }}
                    >
                      {l.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '5px' }}>
                <Mic size={13} style={{ color: 'var(--text-tertiary)' }} />
                <span>Hands-Free Auto-Turn:</span>
              </span>

              <Toggle
                checked={handsFree}
                onChange={(val) => {
                  setHandsFree(val);
                  handsFreeRef.current = val;
                  if (val && callActiveRef.current && !isSpeakingRef.current) startSpeechListening();
                  else if (!val) stopRecognition();
                }}
              />
            </div>
          </div>
        </div>

        {/* Right Column: Live Turn-by-Turn Acoustic Transcript */}
        <div
          className="card"
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 190px)',
            minHeight: '560px',
            padding: 0,
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '1rem 1.25rem',
              borderBottom: '1px solid var(--border-medium)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div>
              <div style={{ fontSize: '0.86rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                Live Spoken Turn Transcript
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                {sessionId ? `Session: ${sessionId}` : 'Awaiting incoming call connection'}
              </div>
            </div>

            {callActive && (
              <span style={{ fontSize: '0.72rem', color: 'var(--mint-400)', fontFamily: 'var(--font-mono)' }}>
                ● WEBRTC ACTIVE
              </span>
            )}
          </div>

          {/* Transcript Scroll Area */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '1.25rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
            }}
          >
            {transcript.length === 0 ? (
              <div
                style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--text-tertiary)',
                  textAlign: 'center',
                  padding: '2rem',
                }}
              >
                <Phone size={32} style={{ marginBottom: '0.75rem', opacity: 0.4 }} />
                <div style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Voice Telephony Ready
                </div>
                <p style={{ fontSize: '0.78rem', maxWidth: '340px', marginTop: '0.4rem', lineHeight: 1.5 }}>
                  Click the green Call button to start a bidirectional voice session. Caller and AI turn transcriptions will appear here in real time.
                </p>
              </div>
            ) : (
              transcript.map((t) => {
                const isAssistant = t.role === 'assistant';
                return (
                  <div
                    key={t.id}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: isAssistant ? 'flex-start' : 'flex-end',
                      maxWidth: '85%',
                      alignSelf: isAssistant ? 'flex-start' : 'flex-end',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.4rem',
                        marginBottom: '3px',
                        fontSize: '0.7rem',
                        color: 'var(--text-tertiary)',
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {isAssistant ? (
                        <>
                          <Bot size={11} style={{ color: 'var(--mint-400)' }} />
                          <span style={{ color: 'var(--mint-400)', fontWeight: 600 }}>{business?.name || 'Receptionist'}</span>
                        </>
                      ) : (
                        <>
                          <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>Caller</span>
                          <User size={11} style={{ color: 'var(--text-secondary)' }} />
                        </>
                      )}
                      <span>• {t.time}</span>
                    </div>

                    <div
                      style={{
                        padding: '0.7rem 0.95rem',
                        borderRadius: isAssistant ? '4px 14px 14px 14px' : '14px 4px 14px 14px',
                        background: isAssistant ? 'var(--bg-surface-elevated)' : 'color-mix(in oklab, var(--color-primary) 12%, var(--bg-card))',
                        border: '1px solid',
                        borderColor: isAssistant ? 'var(--border-medium)' : 'var(--border-medium)',
                        color: 'var(--text-primary)',
                        fontSize: '0.84rem',
                        lineHeight: 1.5,
                      }}
                    >
                      {t.text}
                    </div>

                    {t.tool && (
                      <div
                        style={{
                          marginTop: '4px',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          fontSize: '0.68rem',
                          fontFamily: 'var(--font-mono)',
                          color: '#38bdf8',
                          background: 'rgba(56, 189, 248, 0.1)',
                          border: '1px solid rgba(56, 189, 248, 0.25)',
                          padding: '1px 6px',
                          borderRadius: '4px',
                        }}
                      >
                        <Zap size={10} />
                        <span>Executed: {t.tool}</span>
                      </div>
                    )}
                  </div>
                );
              })
            )}

            {/* Interim live spoken speech */}
            {interimText && (
              <div
                style={{
                  maxWidth: '85%',
                  alignSelf: 'flex-end',
                  background: 'rgba(56, 189, 248, 0.15)',
                  border: '1px solid rgba(56, 189, 248, 0.35)',
                  borderRadius: '14px 4px 14px 14px',
                  padding: '0.7rem 0.95rem',
                  fontSize: '0.84rem',
                  color: '#7dd3fc',
                  fontStyle: 'italic',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <span style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>
                    Speaking...
                  </span>
                  <button
                    type="button"
                    onClick={handleImmediateSendSpeech}
                    style={{
                      background: '#0ea5e9',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      padding: '2px 6px',
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    Send Now
                  </button>
                </div>
                {interimText}
              </div>
            )}

            <div ref={transcriptBottomRef} />
          </div>

          {/* Text input fallback during call */}
          {callActive && (
            <form
              onSubmit={handleTextSubmit}
              style={{
                padding: '0.75rem 1rem',
                borderTop: '1px solid var(--border-medium)',
                background: 'var(--bg-card)',
                display: 'flex',
                gap: '0.65rem',
              }}
            >
              <input
                type="text"
                placeholder={speechLang === 'hi-IN' ? 'हिंदी या English में टाइप करें...' : 'Type text fallback...'}
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                className="form-input"
                style={{ flex: 1 }}
              />
              <button
                type="submit"
                className="btn-primary"
                disabled={!textInput.trim() || isTurnLoading}
                style={{ padding: '0.45rem 0.85rem' }}
              >
                <Send size={14} />
              </button>
            </form>
          )}
        </div>
      </div>

      <style>{`
        @keyframes wbAnim0 { from { height: 6px; } to { height: 20px; } }
        @keyframes wbAnim1 { from { height: 8px; } to { height: 26px; } }
        @keyframes wbAnim2 { from { height: 10px; } to { height: 28px; } }
        @keyframes wbAnim3 { from { height: 7px; } to { height: 22px; } }
        @keyframes wbAnim4 { from { height: 9px; } to { height: 25px; } }
        @keyframes wbAnim5 { from { height: 6px; } to { height: 19px; } }
        @keyframes wbAnim6 { from { height: 8px; } to { height: 23px; } }
      `}</style>
    </section>
  );
}
