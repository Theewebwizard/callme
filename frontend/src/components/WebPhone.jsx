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
} from 'lucide-react';
import { api } from '../api';

/* ─────────────────────────────────────────────────────────
   Inline style objects — self-contained, no external CSS clash
───────────────────────────────────────────────────────── */
const S = {
  page: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '2rem 1rem 3rem',
    minHeight: '100%',
  },
  pageHeader: { textAlign: 'center', marginBottom: '2rem' },
  pageTitle: { fontSize: '1.5rem', fontWeight: 800, color: 'var(--slate-800)', letterSpacing: '-0.02em', marginBottom: '0.35rem' },
  pageSubtitle: { fontSize: '0.88rem', color: 'var(--slate-500)', fontWeight: 500 },
  errorBanner: {
    width: '100%', maxWidth: '440px', marginBottom: '1rem',
    padding: '0.7rem 1rem', borderRadius: '10px',
    background: '#fff1f2', border: '1px solid #fecdd3',
    color: '#be123c', fontSize: '0.83rem', fontWeight: 600,
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  },
  card: {
    width: '100%', maxWidth: '420px', borderRadius: '24px',
    background: 'linear-gradient(160deg, #0f172a 0%, #1e293b 100%)',
    boxShadow: '0 24px 60px rgba(0,0,0,0.38), 0 8px 24px rgba(0,0,0,0.18)',
    overflow: 'hidden', display: 'flex', flexDirection: 'column',
  },
  topBar: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '14px 18px 10px', borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  topBarLeft: { display: 'flex', alignItems: 'center', gap: '6px' },
  topBarLabel: { fontSize: '0.74rem', fontWeight: 700, letterSpacing: '0.04em', color: 'rgba(255,255,255,0.55)', textTransform: 'uppercase' },
  topBarTimer: { fontSize: '0.8rem', fontWeight: 700, color: 'rgba(255,255,255,0.9)', fontVariantNumeric: 'tabular-nums', letterSpacing: '0.05em', fontFamily: 'monospace' },
  langSwitcher: {
    display: 'flex', alignItems: 'center',
    background: 'rgba(255,255,255,0.06)', borderRadius: '99px',
    padding: '3px', gap: '2px', border: '1px solid rgba(255,255,255,0.1)',
  },
  avatarZone: { display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '2rem 1.5rem 1.25rem', gap: '0.75rem' },
  bizName: { fontSize: '1.2rem', fontWeight: 800, color: 'white', textAlign: 'center', letterSpacing: '-0.01em' },
  waveform: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', height: '36px', padding: '0 1.5rem', marginBottom: '0.25rem' },
  transcriptArea: {
    margin: '0 1rem', borderRadius: '14px',
    background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.07)',
    padding: '0.85rem', height: '200px', overflowY: 'auto',
    display: 'flex', flexDirection: 'column', gap: '0.5rem',
  },
  transcriptEmpty: {
    flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
    flexDirection: 'column', gap: '0.5rem', color: 'rgba(255,255,255,0.25)',
    fontSize: '0.83rem', textAlign: 'center', fontWeight: 500,
  },
  inputRow: { display: 'flex', gap: '8px', margin: '10px 1rem 0' },
  textInput: {
    flex: 1, background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: '12px', color: 'white', fontSize: '0.85rem', padding: '10px 14px', outline: 'none',
  },
  controlsBar: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '1.75rem', padding: '1.5rem 1.5rem 1rem' },
  controlItem: { display: 'flex', flexDirection: 'column', alignItems: 'center' },
  settingsStrip: { borderTop: '1px solid rgba(255,255,255,0.06)', padding: '0.75rem 1.25rem 1.25rem', display: 'flex', flexDirection: 'column', gap: '0.6rem' },
  settingsRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' },
  settingsLabel: { fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' },
  pauseChips: { display: 'flex', gap: '4px' },
  toolBadge: {
    display: 'inline-flex', alignItems: 'center', gap: '3px', marginTop: '4px',
    padding: '2px 7px', borderRadius: '6px', background: 'rgba(255,255,255,0.12)',
    color: 'rgba(255,255,255,0.7)', fontSize: '0.68rem', fontWeight: 700,
  },
  bubbleSpeaker: { fontSize: '0.68rem', fontWeight: 800, opacity: 0.65, marginBottom: '3px', letterSpacing: '0.03em', textTransform: 'uppercase' },
};

function dotColor(isListening, isSpeaking, isTurnLoading, isConnecting, callActive) {
  if (!callActive && !isConnecting) return '#64748b';
  if (isListening)   return '#10b981';
  if (isSpeaking)    return '#818cf8';
  if (isTurnLoading) return '#38bdf8';
  if (isConnecting)  return '#f59e0b';
  return '#0ea5e9';
}

function pillStyle(type) {
  const map = {
    idle:       { bg: 'rgba(255,255,255,0.07)', color: 'rgba(255,255,255,0.45)' },
    connecting: { bg: 'rgba(245,158,11,0.18)',  color: '#fbbf24' },
    listening:  { bg: 'rgba(16,185,129,0.18)',  color: '#34d399' },
    speaking:   { bg: 'rgba(99,102,241,0.2)',   color: '#a78bfa' },
    thinking:   { bg: 'rgba(14,165,233,0.18)',  color: '#38bdf8' },
    active:     { bg: 'rgba(14,165,233,0.12)',  color: '#7dd3fc' },
    muted:      { bg: 'rgba(239,68,68,0.18)',   color: '#f87171' },
  };
  const s = map[type] || map.idle;
  return {
    display: 'inline-flex', alignItems: 'center', gap: '6px',
    padding: '5px 14px', borderRadius: '99px',
    background: s.bg, color: s.color,
    fontSize: '0.78rem', fontWeight: 700, letterSpacing: '0.02em',
    border: `1px solid ${s.color}30`,
  };
}

function langBtnStyle(active) {
  return {
    padding: '4px 14px', borderRadius: '99px', fontSize: '0.74rem', fontWeight: 700,
    border: 'none', cursor: 'pointer',
    background: active ? '#0ea5e9' : 'transparent',
    color: active ? 'white' : 'rgba(255,255,255,0.5)',
    transition: 'all 0.18s ease', letterSpacing: '0.02em',
  };
}

function ctrlBtn(variant) {
  const variants = {
    call:        { w: 72, bg: 'linear-gradient(135deg,#10b981,#059669)', shadow: '0 8px 24px rgba(16,185,129,0.45)' },
    endcall:     { w: 72, bg: 'linear-gradient(135deg,#ef4444,#dc2626)', shadow: '0 8px 24px rgba(239,68,68,0.45)' },
    mic:         { w: 60, bg: 'linear-gradient(135deg,#0ea5e9,#0284c7)', shadow: '0 6px 18px rgba(14,165,233,0.4)' },
    'mic-on':    { w: 60, bg: 'linear-gradient(135deg,#10b981,#059669)', shadow: '0 6px 24px rgba(16,185,129,0.55)' },
    'mic-muted': { w: 60, bg: 'rgba(255,255,255,0.09)', shadow: 'none', border: '1px solid rgba(255,255,255,0.12)' },
    speaker:     { w: 52, bg: 'rgba(255,255,255,0.07)', shadow: 'none', border: '1px solid rgba(255,255,255,0.1)' },
    'spk-active':{ w: 52, bg: 'rgba(129,140,248,0.18)', shadow: 'none', border: '1px solid rgba(129,140,248,0.4)' },
  };
  const v = variants[variant] || variants.speaker;
  return {
    width: `${v.w}px`, height: `${v.w}px`, borderRadius: '50%',
    border: v.border || 'none', cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: v.bg, boxShadow: v.shadow || 'none', color: 'white',
    transition: 'all 0.2s cubic-bezier(0.16,1,0.3,1)', flexShrink: 0,
  };
}

function pauseChipStyle(active) {
  return {
    padding: '3px 9px', borderRadius: '6px', fontSize: '0.69rem', fontWeight: 700,
    border: 'none', cursor: 'pointer',
    background: active ? '#0ea5e9' : 'rgba(255,255,255,0.08)',
    color: active ? 'white' : 'rgba(255,255,255,0.4)',
    transition: 'all 0.15s',
  };
}

function bubbleStyle(role) {
  return {
    maxWidth: '88%',
    alignSelf: role === 'user' ? 'flex-end' : 'flex-start',
    background: role === 'user'
      ? 'linear-gradient(135deg,#0ea5e9,#0284c7)'
      : 'rgba(255,255,255,0.1)',
    color: 'white',
    borderRadius: role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
    padding: '8px 12px', fontSize: '0.83rem', lineHeight: '1.45',
  };
}

/* Animated waveform */
function Waveform({ active }) {
  const heights = [0.5, 0.85, 1, 0.7, 0.9, 0.6, 0.8];
  return (
    <div style={S.waveform}>
      {heights.map((h, i) => (
        <div key={i} style={{
          width: '3px',
          height: active ? `${Math.round(h * 28)}px` : '6px',
          borderRadius: '3px',
          background: active ? `rgba(14,165,233,${0.5 + h * 0.5})` : 'rgba(255,255,255,0.12)',
          transition: `height ${0.18 + i * 0.04}s ease`,
          animation: active ? `wbAnim${i} 0.9s ease-in-out ${i * 0.1}s infinite alternate` : 'none',
        }} />
      ))}
    </div>
  );
}

/* Toggle switch */
function Toggle({ checked, onChange }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
      style={{
        width: '32px', height: '18px', borderRadius: '9px', position: 'relative',
        background: checked ? '#0ea5e9' : 'rgba(255,255,255,0.15)',
        border: 'none', cursor: 'pointer', transition: 'background 0.2s ease', flexShrink: 0,
      }}
    >
      <span style={{
        position: 'absolute', top: '2px', left: checked ? '16px' : '2px',
        width: '14px', height: '14px', borderRadius: '50%', background: 'white',
        transition: 'left 0.2s ease', boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
        display: 'block',
      }} />
    </button>
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
    try { return localStorage.getItem('callme_speech_lang') || 'hi-IN'; } catch { return 'hi-IN'; }
  });

  // Refs (prevent stale closures)
  const callActiveRef       = useRef(false);
  const isStartingCallRef   = useRef(false);
  const currentTurnIdRef    = useRef(0);
  const cooloffTimerRef     = useRef(null);
  const sessionIdRef        = useRef(null);
  const isSpeakingRef       = useRef(false);
  const isListeningRef      = useRef(false);
  const isMicMutedRef       = useRef(false);
  const handsFreeRef        = useRef(true);
  const speechLangRef       = useRef(speechLang);
  const isTurnInFlightRef   = useRef(false);
  const silenceTimerRef     = useRef(null);
  const accumulatedSpeechRef = useRef('');
  const timerRef            = useRef(null);
  const currentAudioRef     = useRef(null);
  const recognitionRef      = useRef(null);
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

  // ── Audio helpers ──────────────────────────────────────────────────────────

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
      // BUG FIX: do NOT gate on isTurnInFlightRef here — onEnd itself resets it.
      // Without this fix the callback never fires and the mic never re-arms.
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

  // ── Speech recognition ─────────────────────────────────────────────────────

  // ── Smart VAD speech listening ────────────────────────────────────────────
  // Uses continuous=false so the browser's own Voice Activity Detection
  // auto-detects when the user STOPS speaking (no fixed pause timer needed).
  // When the browser fires `onend` we check if we collected speech and send it,
  // or restart listening if nothing was captured.
  const startSpeechListening = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { setCallStatus('Browser speech not supported — type below'); return; }
    if (!callActiveRef.current || isTurnInFlightRef.current || isSpeakingRef.current || isMicMutedRef.current) return;
    stopRecognition();

    try {
      const rec = new SR();
      // continuous=false → browser's built-in VAD stops recording when you pause
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
        // Echo guard: if AI started speaking, discard
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
        // Show live interim text in the UI
        const display = (accumulatedSpeechRef.current + ' ' + interim).trim();
        setInterimText(display);
      };

      rec.onerror = (e) => {
        if (e.error === 'no-speech') {
          // No speech detected this round — re-arm silently
          return;
        }
        if (e.error === 'not-allowed') {
          setErrorMsg('Microphone access blocked. Enable mic permissions in browser settings.');
          isListeningRef.current = false; setIsListening(false); return;
        }
        console.warn('SpeechRecognition error:', e.error);
      };

      rec.onend = () => {
        isListeningRef.current = false;
        setIsListening(false);

        // Call was ended or AI is speaking — do nothing
        if (!callActiveRef.current || isSpeakingRef.current || isTurnInFlightRef.current) return;

        const captured = accumulatedSpeechRef.current.trim();

        if (captured && captured.length > 1 && handsFreeRef.current && !isMicMutedRef.current) {
          // Browser VAD detected end-of-speech and we have content → send it
          accumulatedSpeechRef.current = '';
          setInterimText('');
          executeSendTurn(captured);
        } else if (!captured && handsFreeRef.current && !isMicMutedRef.current) {
          // Nothing captured (silence / noise) → re-arm immediately
          accumulatedSpeechRef.current = '';
          setInterimText('');
          setTimeout(() => {
            if (callActiveRef.current && !isSpeakingRef.current && !isTurnInFlightRef.current && !isMicMutedRef.current)
              startSpeechListening();
          }, 80);
        }
        // If not hands-free, just stop (push-to-talk handles its own flow)
      };

      rec.start();
    } catch (e) {
      console.warn('Could not start SpeechRecognition:', e);
      isListeningRef.current = false; setIsListening(false);
    }
  };

  const handleImmediateSendSpeech = () => {
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    const toSend = (accumulatedSpeechRef.current + ' ' + interimText).trim();
    if (toSend && !isTurnInFlightRef.current && callActiveRef.current) {
      accumulatedSpeechRef.current = ''; setInterimText(''); executeSendTurn(toSend);
    }
  };

  // ── Turn ──────────────────────────────────────────────────────────────────

  const executeSendTurn = async (textToSend) => {
    const sid = sessionIdRef.current;
    if (!sid || !textToSend?.trim() || isTurnInFlightRef.current || !callActiveRef.current) return;
    const turnId = ++currentTurnIdRef.current;
    isTurnInFlightRef.current = true; setIsTurnLoading(true);
    stopRecognition(); stopAllAudio();
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    accumulatedSpeechRef.current = ''; setInterimText('');

    const cleanText = textToSend.trim();
    setTranscript(prev => [...prev, { role: 'user', speaker: 'You', text: cleanText }]);
    setCallStatus('thinking');

    try {
      const res = await api.sendWebCallTurn(sid, null, cleanText);
      if (!callActiveRef.current || currentTurnIdRef.current !== turnId) {
        stopAllAudio(); isTurnInFlightRef.current = false; setIsTurnLoading(false); return;
      }
      const aText = res.assistant_text || res.response_text || 'Thank you.';
      const toolUsed = res.tool_used || res.tool_calls?.[0];
      setTranscript(prev => [...prev, { role: 'assistant', speaker: business?.name || 'Receptionist', text: aText, toolUsed }]);
      setIsTurnLoading(false);

      if (res.should_terminate) { playAudio(res.audio_base64, res.audio_mime, aText, () => endCall()); return; }

      playAudio(res.audio_base64, res.audio_mime, aText, () => {
        isTurnInFlightRef.current = false; accumulatedSpeechRef.current = ''; setInterimText('');
        if (callActiveRef.current && handsFreeRef.current && !isMicMutedRef.current) startSpeechListening();
        else setCallStatus('active');
      });
    } catch (err) {
      if (!callActiveRef.current || currentTurnIdRef.current !== turnId) {
        isTurnInFlightRef.current = false; setIsTurnLoading(false); return;
      }
      setErrorMsg(`Turn failed: ${err.message}`);
      setCallStatus('active');
      isTurnInFlightRef.current = false; setIsTurnLoading(false);
      if (callActiveRef.current && handsFreeRef.current && !isMicMutedRef.current) startSpeechListening();
    }
  };

  // ── Call lifecycle ─────────────────────────────────────────────────────────

  const startCall = async () => {
    unlockAudioForMobile();
    if (callActiveRef.current || isStartingCallRef.current) return;
    if (!business) { setErrorMsg('No business selected. Register or select a business first.'); return; }
    isStartingCallRef.current = true;
    setIsConnecting(true); setErrorMsg(null); setCallStatus('connecting');
    isTurnInFlightRef.current = false; accumulatedSpeechRef.current = ''; setInterimText('');
    stopAllAudio(); stopRecognition();

    try {
      const data = await api.startWebCall(business.id);
      if (!isStartingCallRef.current) {
        if (data?.session_id) api.hangupWebCall(data.session_id).catch(() => {}); return;
      }
      sessionIdRef.current = data.session_id; setSessionId(data.session_id);
      callActiveRef.current = true; setCallActive(true); setIsConnecting(false);
      isStartingCallRef.current = false; setDuration(0);
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = setInterval(() => setDuration(prev => prev + 1), 1000);

      const greeting = data.greeting_text || `Namaste and welcome to ${business.name}! How can I help you?`;
      setTranscript([{ role: 'assistant', speaker: data.business_name || business.name, text: greeting }]);
      playAudio(data.audio_base64, data.audio_mime, greeting, () => {
        isTurnInFlightRef.current = false;
        if (callActiveRef.current && handsFreeRef.current && !isMicMutedRef.current) startSpeechListening();
        else setCallStatus('active');
      });
    } catch (err) {
      setErrorMsg(`Failed to start call: ${err.message}`);
      setCallStatus('idle'); callActiveRef.current = false;
      isStartingCallRef.current = false; setIsConnecting(false); setCallActive(false);
    }
  };

  const endCall = async () => {
    isStartingCallRef.current = false; setIsConnecting(false);
    currentTurnIdRef.current++;
    callActiveRef.current = false; setCallActive(false);
    stopAllAudio(); stopRecognition();
    if (timerRef.current) clearInterval(timerRef.current);
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    if (cooloffTimerRef.current) clearTimeout(cooloffTimerRef.current);
    isSpeakingRef.current = false; isListeningRef.current = false; isTurnInFlightRef.current = false;
    accumulatedSpeechRef.current = ''; setInterimText('');
    setIsSpeaking(false); setIsListening(false); setIsTurnLoading(false); setCallStatus('idle');
    const activeId = sessionIdRef.current || sessionId;
    sessionIdRef.current = null; setSessionId(null);
    if (activeId) api.hangupWebCall(activeId).catch(err => console.error('Hangup:', err));
  };

  const handleTextSubmit = (e) => {
    e.preventDefault();
    if (!textInput.trim() || !callActiveRef.current || isTurnInFlightRef.current) return;
    const txt = textInput.trim(); setTextInput('');
    stopAllAudio(); stopRecognition(); executeSendTurn(txt);
  };

  const toggleMute = () => {
    const next = !isMicMutedRef.current; isMicMutedRef.current = next; setIsMicMuted(next);
    if (next) stopRecognition();
    else if (callActiveRef.current && !isSpeakingRef.current) startSpeechListening();
  };

  const handlePTTStart = () => {
    if (!callActiveRef.current || isSpeakingRef.current || isTurnInFlightRef.current || handsFree) return;
    startSpeechListening();
  };
  const handlePTTEnd = () => {
    if (!callActiveRef.current || isSpeakingRef.current || isTurnInFlightRef.current || handsFree) return;
    handleImmediateSendSpeech();
  };

  // ── Derived UI values ──────────────────────────────────────────────────────
  const micVariant = isMicMuted ? 'mic-muted' : isListening ? 'mic-on' : 'mic';
  const spkVariant = isSpeaking ? 'spk-active' : 'speaker';

  const pillType = isMicMuted ? 'muted' : isTurnLoading ? 'thinking' : isSpeaking ? 'speaking' : isListening ? 'listening' : isConnecting ? 'connecting' : callActive ? 'active' : 'idle';
  const pillLabel = isMicMuted ? '🔴 Mic Muted' : isTurnLoading ? '⚡ Thinking...' : isSpeaking ? '🔊 AI Speaking' : isListening ? '🟢 Listening...' : isConnecting ? 'Connecting...' : callActive ? 'Call Active' : 'Ready to Call';
  const dot = dotColor(isListening, isSpeaking, isTurnLoading, isConnecting, callActive);
  const pulsing = isListening || isSpeaking || isTurnLoading || isConnecting;

  return (
    <section style={S.page}>
      {/* Page header */}
      <div style={S.pageHeader}>
        <h1 style={S.pageTitle}>📞 Web Voice Phone</h1>
        <p style={S.pageSubtitle}>Natural back-and-forth AI receptionist with memory & thinking-pause tolerance</p>
      </div>

      {/* Error banner */}
      {errorMsg && (
        <div style={S.errorBanner}>
          <span>⚠️ {errorMsg}</span>
          <button onClick={() => setErrorMsg(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', fontWeight: 800, fontSize: '1rem', lineHeight: 1 }}>✕</button>
        </div>
      )}

      {/* Phone card */}
      <div style={S.card}>

        {/* Top bar */}
        <div style={S.topBar}>
          <div style={S.topBarLeft}>
            <div style={{
              width: '8px', height: '8px', borderRadius: '50%', background: dot, flexShrink: 0,
              boxShadow: pulsing ? `0 0 0 3px ${dot}30` : 'none',
              animation: pulsing ? 'wpPulse 1.5s ease-in-out infinite' : 'none',
            }} />
            <span style={S.topBarLabel}>{isConnecting ? 'Connecting' : callActive ? 'Live' : 'Standby'}</span>
          </div>

          {/* Language switcher */}
          <div style={S.langSwitcher}>
            <button style={langBtnStyle(speechLang === 'hi-IN')} onClick={() => changeSpeechLanguage('hi-IN')}>हिंदी</button>
            <button style={langBtnStyle(speechLang === 'en-IN')} onClick={() => changeSpeechLanguage('en-IN')}>English</button>
          </div>

          {callActive && <span style={S.topBarTimer}>{formatDuration(duration)}</span>}
        </div>

        {/* Avatar zone */}
        <div style={S.avatarZone}>
          <div style={{
            width: '86px', height: '86px', borderRadius: '50%',
            background: (callActive || isConnecting) ? 'linear-gradient(135deg,#0ea5e9 0%,#6366f1 100%)' : 'rgba(255,255,255,0.08)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: (callActive || isConnecting) ? '0 0 0 6px rgba(14,165,233,0.18),0 0 0 12px rgba(14,165,233,0.08)' : 'none',
            transition: 'all 0.4s cubic-bezier(0.16,1,0.3,1)',
          }}>
            {isConnecting
              ? <Loader2 size={38} color="white" style={{ animation: 'wpSpin 1s linear infinite' }} />
              : <Bot size={38} color="white" style={{ opacity: 0.95 }} />
            }
          </div>
          <div style={S.bizName}>{business?.name || 'AI Receptionist'}</div>
          <div style={pillStyle(pillType)}>
            {pulsing && <Radio size={12} style={{ flexShrink: 0, animation: 'wpPulse 1.2s ease-in-out infinite' }} />}
            {pillLabel}
          </div>
        </div>

        {/* Waveform */}
        <Waveform active={isSpeaking || isListening} />

        {/* Transcript */}
        <div style={S.transcriptArea}>
          {transcript.length === 0 ? (
            <div style={S.transcriptEmpty}>
              <Phone size={28} style={{ opacity: 0.3 }} />
              <span>Tap the green call button to speak with your AI receptionist</span>
            </div>
          ) : transcript.map((item, i) => (
            <div key={i} style={bubbleStyle(item.role)}>
              <div style={S.bubbleSpeaker}>{item.speaker}</div>
              <div>{item.text}</div>
              {item.toolUsed && (
                <div style={S.toolBadge}><Sparkles size={10} /> {item.toolUsed}</div>
              )}
            </div>
          ))}

          {interimText && (
            <div style={{
              maxWidth: '88%', alignSelf: 'flex-end',
              background: 'rgba(14,165,233,0.2)', border: '1px solid rgba(14,165,233,0.35)',
              color: '#7dd3fc', borderRadius: '14px 14px 4px 14px',
              padding: '8px 12px', fontSize: '0.83rem', fontStyle: 'italic',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '0.68rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.04em', opacity: 0.7 }}>You (speaking…)</span>
                <button type="button" onClick={handleImmediateSendSpeech} style={{
                  background: '#0ea5e9', color: 'white', border: 'none', borderRadius: '8px',
                  padding: '2px 8px', fontSize: '0.68rem', fontWeight: 700, cursor: 'pointer',
                  display: 'inline-flex', alignItems: 'center', gap: '3px',
                }}>
                  <Zap size={10} /> Send
                </button>
              </div>
              {interimText}
            </div>
          )}
          <div ref={transcriptBottomRef} />
        </div>

        {/* Text input */}
        {callActive && (
          <form onSubmit={handleTextSubmit} style={S.inputRow}>
            <input
              type="text"
              placeholder={speechLang === 'hi-IN' ? 'हिंदी या English में टाइप करें...' : 'Type or speak...'}
              value={textInput}
              onChange={e => setTextInput(e.target.value)}
              style={S.textInput}
            />
            <button type="submit" disabled={!textInput.trim() || isTurnInFlightRef.current}
              style={{ ...S.sendBtn || {}, width: '42px', height: '42px', borderRadius: '12px', background: '#0ea5e9', border: 'none', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0, opacity: !textInput.trim() ? 0.4 : 1, transition: 'opacity 0.15s' }}>
              <Send size={17} />
            </button>
          </form>
        )}

        {/* Controls */}
        <div style={S.controlsBar}>
          {!callActive && !isConnecting && (
            <div style={S.controlItem}>
              <button style={ctrlBtn('call')} onClick={startCall} onTouchStart={unlockAudioForMobile} title="Start Call">
                <Phone size={30} />
              </button>
              <span style={{ fontSize: '0.7rem', fontWeight: 700, color: '#34d399', marginTop: '6px', textAlign: 'center', letterSpacing: '0.03em' }}>Call</span>
            </div>
          )}

          {isConnecting && (
            <div style={S.controlItem}>
              <button style={ctrlBtn('endcall')} onClick={endCall} title="Cancel">
                <PhoneOff size={26} />
              </button>
              <span style={{ fontSize: '0.7rem', fontWeight: 700, color: '#f87171', marginTop: '6px', textAlign: 'center', letterSpacing: '0.03em' }}>Cancel</span>
            </div>
          )}

          {callActive && (
            <>
              {/* Mic */}
              <div style={S.controlItem}>
                <button
                  style={ctrlBtn(micVariant)}
                  onClick={handsFree ? toggleMute : undefined}
                  onMouseDown={!handsFree ? handlePTTStart : undefined}
                  onMouseUp={!handsFree ? handlePTTEnd : undefined}
                  onTouchStart={!handsFree ? handlePTTStart : undefined}
                  onTouchEnd={!handsFree ? handlePTTEnd : undefined}
                  title={handsFree ? (isMicMuted ? 'Unmute' : 'Mute') : 'Hold to Speak'}
                >
                  {isMicMuted ? <MicOff size={24} /> : <Mic size={24} />}
                </button>
                <span style={{ fontSize: '0.7rem', fontWeight: 700, color: isMicMuted ? '#f87171' : isListening ? '#34d399' : 'rgba(255,255,255,0.55)', marginTop: '6px', textAlign: 'center', letterSpacing: '0.03em' }}>
                  {isMicMuted ? 'Muted' : isListening ? 'Listening' : 'Mic'}
                </span>
              </div>

              {/* Speaker indicator */}
              <div style={S.controlItem}>
                <div style={{ ...ctrlBtn(spkVariant), cursor: 'default' }}>
                  <Volume2 size={22} color={isSpeaking ? '#a78bfa' : 'rgba(255,255,255,0.4)'} />
                </div>
                <span style={{ fontSize: '0.7rem', fontWeight: 700, color: isSpeaking ? '#a78bfa' : 'rgba(255,255,255,0.3)', marginTop: '6px', textAlign: 'center', letterSpacing: '0.03em' }}>
                  {isSpeaking ? 'Speaking' : 'Speaker'}
                </span>
              </div>

              {/* End call */}
              <div style={S.controlItem}>
                <button style={ctrlBtn('endcall')} onClick={endCall} title="End Call">
                  <PhoneOff size={26} />
                </button>
                <span style={{ fontSize: '0.7rem', fontWeight: 700, color: '#f87171', marginTop: '6px', textAlign: 'center', letterSpacing: '0.03em' }}>End Call</span>
              </div>
            </>
          )}
        </div>

        {/* Settings strip */}
        {callActive && (
          <div style={S.settingsStrip}>
            <div style={S.settingsRow}>
              <span style={S.settingsLabel}><Mic size={12} /> Hands-Free Auto-Turn</span>
              <Toggle checked={handsFree} onChange={(val) => {
                setHandsFree(val); handsFreeRef.current = val;
                if (val && callActiveRef.current && !isSpeakingRef.current) startSpeechListening();
                else if (!val) stopRecognition();
              }} />
            </div>

            {handsFree && (
              <div style={{ ...S.settingsRow, justifyContent: 'center' }}>
                <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.3)', fontWeight: 600, textAlign: 'center' }}>
                  🧠 Smart VAD — mic auto-stops when you finish speaking
                </span>
              </div>
            )}

            {!handsFree && (
              <div style={{ fontSize: '0.71rem', color: 'rgba(255,255,255,0.35)', textAlign: 'center', fontWeight: 600 }}>
                💡 Hold the mic button to speak, release to send
              </div>
            )}
          </div>
        )}
      </div>

      {/* Keyframe animations */}
      <style>{`
        @keyframes wpPulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
        @keyframes wpSpin  { from { transform:rotate(0deg); } to { transform:rotate(360deg); } }
        @keyframes wbAnim0 { from { height:6px; }  to { height:20px; } }
        @keyframes wbAnim1 { from { height:8px; }  to { height:26px; } }
        @keyframes wbAnim2 { from { height:10px; } to { height:28px; } }
        @keyframes wbAnim3 { from { height:7px; }  to { height:22px; } }
        @keyframes wbAnim4 { from { height:9px; }  to { height:25px; } }
        @keyframes wbAnim5 { from { height:6px; }  to { height:19px; } }
        @keyframes wbAnim6 { from { height:8px; }  to { height:23px; } }
      `}</style>
    </section>
  );
}
