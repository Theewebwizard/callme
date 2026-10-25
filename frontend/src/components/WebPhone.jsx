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
  Clock,
} from 'lucide-react';
import { api } from '../api';

export default function WebPhone({ business }) {
  const [callActive, setCallActive] = useState(false);
  const [callStatus, setCallStatus] = useState('Ready to Call');
  const [sessionId, setSessionId] = useState(null);
  const [duration, setDuration] = useState(0);
  const [transcript, setTranscript] = useState([]);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [interimText, setInterimText] = useState('');
  const [handsFree, setHandsFree] = useState(true);
  const [pauseDuration, setPauseDuration] = useState(2500); // 2.5s generous thinking pause default
  const [isMicMuted, setIsMicMuted] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [errorMsg, setErrorMsg] = useState(null);

  // Spoken Language State: 'hi-IN' (Hindi) or 'en-IN' (English)
  const [speechLang, setSpeechLang] = useState(() => {
    try {
      return localStorage.getItem('callme_speech_lang') || 'hi-IN';
    } catch {
      return 'hi-IN';
    }
  });

  // Synchronous refs to prevent stale closures across turn callbacks
  const callActiveRef = useRef(false);
  const sessionIdRef = useRef(null);
  const isSpeakingRef = useRef(false);
  const isListeningRef = useRef(false);
  const isMicMutedRef = useRef(false);
  const handsFreeRef = useRef(true);
  const pauseDurationRef = useRef(2500);
  const speechLangRef = useRef(speechLang);
  const isTurnInFlightRef = useRef(false);
  const silenceTimerRef = useRef(null);
  const accumulatedSpeechRef = useRef('');

  const timerRef = useRef(null);
  const currentAudioRef = useRef(null);
  const recognitionRef = useRef(null);
  const transcriptBottomRef = useRef(null);

  // Synchronize state with refs
  useEffect(() => {
    callActiveRef.current = callActive;
  }, [callActive]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    isMicMutedRef.current = isMicMuted;
  }, [isMicMuted]);

  useEffect(() => {
    handsFreeRef.current = handsFree;
  }, [handsFree]);

  useEffect(() => {
    pauseDurationRef.current = pauseDuration;
  }, [pauseDuration]);

  useEffect(() => {
    speechLangRef.current = speechLang;
  }, [speechLang]);

  const changeSpeechLanguage = (newLang) => {
    setSpeechLang(newLang);
    speechLangRef.current = newLang;
    try {
      localStorage.setItem('callme_speech_lang', newLang);
    } catch {}

    // If currently listening, smoothly restart recognition with new language
    if (callActiveRef.current && isListeningRef.current) {
      stopRecognition();
      setTimeout(() => {
        if (callActiveRef.current && !isSpeakingRef.current && !isTurnInFlightRef.current) {
          startSpeechListening();
        }
      }, 150);
    }
  };

  // Auto-scroll transcript to bottom
  useEffect(() => {
    transcriptBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript, interimText]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      callActiveRef.current = false;
      if (timerRef.current) clearInterval(timerRef.current);
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      if (currentAudioRef.current) currentAudioRef.current.pause();
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      stopRecognition();
    };
  }, []);

  const formatDuration = (secs) => {
    const mins = Math.floor(secs / 60);
    const remaining = secs % 60;
    return `${mins.toString().padStart(2, '0')}:${remaining.toString().padStart(2, '0')}`;
  };

  // Stop active speech recognition safely
  const stopRecognition = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.onend = null;
        recognitionRef.current.abort();
      } catch (e) {
        // Ignore already aborted
      }
      recognitionRef.current = null;
    }
    isListeningRef.current = false;
    setIsListening(false);
  };

  // Synchronously unlock and prime audio subsystem on mobile (iOS Safari / Android Chrome)
  const unlockAudioForMobile = () => {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        if (!window._callmeAudioCtx) {
          window._callmeAudioCtx = new AudioCtx();
        }
        if (window._callmeAudioCtx.state === 'suspended') {
          window._callmeAudioCtx.resume();
        }
        const buffer = window._callmeAudioCtx.createBuffer(1, 1, 22050);
        const source = window._callmeAudioCtx.createBufferSource();
        source.buffer = buffer;
        source.connect(window._callmeAudioCtx.destination);
        source.start(0);
      }
    } catch (e) {
      // Non-blocking
    }

    try {
      const silentAudio = new Audio('data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA');
      silentAudio.volume = 0.01;
      silentAudio.play().then(() => silentAudio.pause()).catch(() => {});
    } catch (e) {}

    try {
      if (window.speechSynthesis) {
        const utter = new SpeechSynthesisUtterance('');
        utter.volume = 0;
        window.speechSynthesis.speak(utter);
      }
    } catch (e) {}
  };

  // Audio Playback with dual audio/mp3 + WAV + Web Speech fallback
  const playAudio = (base64Audio, mimeType, fallbackText, onEnd) => {
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }

    const onAudioComplete = () => {
      isSpeakingRef.current = false;
      setIsSpeaking(false);
      currentAudioRef.current = null;
      if (onEnd) onEnd();
    };

    const speakFallback = (txt) => {
      if (window.speechSynthesis && txt) {
        isSpeakingRef.current = true;
        setIsSpeaking(true);
        setCallStatus('🔊 Receptionist Speaking...');
        const utter = new SpeechSynthesisUtterance(txt);
        utter.rate = 1.05;
        if (/[\u0900-\u097F]/.test(txt) || (speechLangRef.current || '').startsWith('hi')) {
          utter.lang = 'hi-IN';
        } else {
          utter.lang = 'en-IN';
        }
        utter.onend = onAudioComplete;
        utter.onerror = onAudioComplete;
        window.speechSynthesis.speak(utter);
      } else {
        onAudioComplete();
      }
    };

    if (!base64Audio) {
      speakFallback(fallbackText);
      return;
    }

    isSpeakingRef.current = true;
    setIsSpeaking(true);
    setCallStatus('🔊 Receptionist Speaking...');

    const mime = mimeType || (base64Audio.startsWith('UklGR') ? 'audio/wav' : 'audio/mp3');
    const audio = new Audio(`data:${mime};base64,${base64Audio}`);
    currentAudioRef.current = audio;

    audio.onended = onAudioComplete;
    audio.onerror = () => speakFallback(fallbackText);
    audio.play().catch(() => speakFallback(fallbackText));
  };

  // Start continuous Web Speech recognition
  const startSpeechListening = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setCallStatus('Mic active (WebSpeech not supported in browser, type inquiry below)');
      return;
    }

    if (
      !callActiveRef.current ||
      isTurnInFlightRef.current ||
      isSpeakingRef.current ||
      isMicMutedRef.current
    ) {
      return;
    }

    stopRecognition();

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = speechLangRef.current || 'hi-IN';
      recognitionRef.current = recognition;

      recognition.onstart = () => {
        isListeningRef.current = true;
        setIsListening(true);
        const isHindi = (speechLangRef.current || '').startsWith('hi');
        setCallStatus(
          accumulatedSpeechRef.current.trim()
            ? (isHindi ? '🟢 सुन रहा हूँ... (सोचिए, पॉज़ लीजिए)' : '🟢 Listening... (thinking pause)')
            : (isHindi ? '🟢 सुन रहा हूँ... बोलिए (Hindi Active)' : '🟢 Listening... Speak now (English Active)')
        );
      };

      recognition.onresult = (event) => {
        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current);
        }

        let interim = '';
        let finalChunk = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const item = event.results[i];
          if (item.isFinal) {
            finalChunk += item[0].transcript;
          } else {
            interim += item[0].transcript;
          }
        }

        if (finalChunk) {
          accumulatedSpeechRef.current += ' ' + finalChunk;
        }

        const currentDisplay = (accumulatedSpeechRef.current + ' ' + interim).trim();
        setInterimText(currentDisplay);

        // Auto-endpoint: wait for configurable pause duration (default 2.5s) to allow thinking
        if (handsFreeRef.current) {
          silenceTimerRef.current = setTimeout(() => {
            const toSend = accumulatedSpeechRef.current.trim() || interim.trim();
            if (toSend && toSend.length > 1 && !isTurnInFlightRef.current) {
              accumulatedSpeechRef.current = '';
              setInterimText('');
              executeSendTurn(toSend);
            }
          }, pauseDurationRef.current);
        }
      };

      recognition.onerror = (e) => {
        if (e.error === 'no-speech') {
          return;
        }
        if (e.error === 'not-allowed') {
          setErrorMsg('Microphone access blocked. Please enable mic permissions in your browser.');
          isListeningRef.current = false;
          setIsListening(false);
          return;
        }
        console.warn('Speech recognition status:', e.error);
      };

      recognition.onend = () => {
        isListeningRef.current = false;
        setIsListening(false);

        // If the call is still active and we're not speaking or waiting for response:
        // Do NOT lose accumulated speech! Automatically re-arm recognition to keep listening.
        if (
          callActiveRef.current &&
          !isSpeakingRef.current &&
          !isTurnInFlightRef.current &&
          !isMicMutedRef.current &&
          handsFreeRef.current
        ) {
          setTimeout(() => {
            if (
              callActiveRef.current &&
              !isSpeakingRef.current &&
              !isTurnInFlightRef.current &&
              !isMicMutedRef.current
            ) {
              startSpeechListening();
            }
          }, 120);
        }
      };

      recognition.start();
    } catch (e) {
      console.warn('Could not start SpeechRecognition:', e);
      isListeningRef.current = false;
      setIsListening(false);
    }
  };

  // Immediate send of spoken query (bypassing the pause timer)
  const handleImmediateSendSpeech = () => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
    }
    const toSend = (accumulatedSpeechRef.current + ' ' + interimText).trim();
    if (toSend && !isTurnInFlightRef.current) {
      accumulatedSpeechRef.current = '';
      setInterimText('');
      executeSendTurn(toSend);
    }
  };

  // Send conversation turn to backend
  const executeSendTurn = async (textToSend) => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId || !textToSend || !textToSend.trim() || isTurnInFlightRef.current) {
      return;
    }

    isTurnInFlightRef.current = true;
    stopRecognition();
    const cleanUserText = textToSend.trim();

    // Render user speech bubble in transcript immediately
    setTranscript((prev) => [
      ...prev,
      { role: 'user', speaker: 'You', text: cleanUserText },
    ]);
    setCallStatus('⚡ Receptionist thinking...');

    try {
      const res = await api.sendWebCallTurn(activeSessionId, null, cleanUserText);
      const assistantText = res.assistant_text || res.response_text || 'Thank you.';
      const toolUsed = res.tool_used || (res.tool_calls && res.tool_calls[0]);

      setTranscript((prev) => [
        ...prev,
        {
          role: 'assistant',
          speaker: business?.name || 'Receptionist',
          text: assistantText,
          toolUsed: toolUsed,
        },
      ]);

      if (res.should_terminate) {
        playAudio(res.audio_base64, res.audio_mime, assistantText, () => {
          endCall();
        });
        return;
      }

      // Play reply and re-arm microphone as soon as agent finishes speaking
      playAudio(res.audio_base64, res.audio_mime, assistantText, () => {
        isTurnInFlightRef.current = false;
        accumulatedSpeechRef.current = '';
        setInterimText('');
        if (callActiveRef.current && handsFreeRef.current && !isMicMutedRef.current) {
          startSpeechListening();
        } else {
          setCallStatus('Call in Progress');
        }
      });
    } catch (err) {
      setErrorMsg(`Turn failed: ${err.message}`);
      setCallStatus('Call in Progress');
      isTurnInFlightRef.current = false;
      if (callActiveRef.current && handsFreeRef.current && !isMicMutedRef.current) {
        startSpeechListening();
      }
    }
  };

  // Start Call
  const startCall = async () => {
    unlockAudioForMobile();
    if (!business) {
      setErrorMsg('No business selected. Register or select a business first.');
      return;
    }

    setErrorMsg(null);
    setCallStatus('Connecting to AI Receptionist...');
    isTurnInFlightRef.current = false;
    accumulatedSpeechRef.current = '';
    setInterimText('');

    try {
      const data = await api.startWebCall(business.id);
      const activeId = data.session_id;

      sessionIdRef.current = activeId;
      setSessionId(activeId);
      callActiveRef.current = true;
      setCallActive(true);
      setDuration(0);

      // Start duration timer
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);

      // Add opening greeting to transcript
      const greeting = data.greeting_text || `Namaste and welcome to ${business.name}! How can I help you?`;
      setTranscript([
        {
          role: 'assistant',
          speaker: data.business_name || business.name,
          text: greeting,
        },
      ]);

      // Play greeting and then open mic
      playAudio(data.audio_base64, data.audio_mime, greeting, () => {
        isTurnInFlightRef.current = false;
        if (handsFreeRef.current && !isMicMutedRef.current) {
          startSpeechListening();
        } else {
          setCallStatus('Call in Progress');
        }
      });
    } catch (err) {
      setErrorMsg(`Failed to start call: ${err.message}`);
      setCallStatus('Ready to Call');
      callActiveRef.current = false;
      setCallActive(false);
    }
  };

  // Hangup Call
  const endCall = async () => {
    callActiveRef.current = false;
    isSpeakingRef.current = false;
    isListeningRef.current = false;
    isTurnInFlightRef.current = false;
    accumulatedSpeechRef.current = '';
    setInterimText('');

    if (timerRef.current) clearInterval(timerRef.current);
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    if (currentAudioRef.current) currentAudioRef.current.pause();
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    stopRecognition();

    const activeId = sessionIdRef.current || sessionId;
    setCallActive(false);
    setIsSpeaking(false);
    setIsListening(false);
    setCallStatus('Call Ended');

    if (activeId) {
      try {
        await api.hangupWebCall(activeId);
      } catch (err) {
        console.error('Hangup error:', err);
      }
    }

    setTimeout(() => {
      setCallStatus('Ready to Call');
      sessionIdRef.current = null;
      setSessionId(null);
    }, 2000);
  };

  // Manual Text Submit
  const handleTextSubmit = (e) => {
    e.preventDefault();
    if (!textInput.trim() || !callActive || isTurnInFlightRef.current) return;
    const txt = textInput.trim();
    setTextInput('');
    executeSendTurn(txt);
  };

  // Toggle Mute / Mic
  const toggleMute = () => {
    const nextMuted = !isMicMutedRef.current;
    isMicMutedRef.current = nextMuted;
    setIsMicMuted(nextMuted);

    if (nextMuted) {
      stopRecognition();
      setCallStatus('Mic Muted');
    } else {
      if (callActiveRef.current && !isSpeakingRef.current) {
        startSpeechListening();
      }
    }
  };

  // Push to Talk mouse/touch handlers for manual mode
  const handlePushToTalkStart = () => {
    if (!callActiveRef.current || isSpeakingRef.current || isTurnInFlightRef.current) return;
    if (!handsFree) {
      startSpeechListening();
    }
  };

  const handlePushToTalkEnd = () => {
    if (!callActiveRef.current || isSpeakingRef.current || isTurnInFlightRef.current) return;
    if (!handsFree) {
      handleImmediateSendSpeech();
    }
  };

  return (
    <section className="main-content">
      <div className="section-header" style={{ textAlign: 'center', marginBottom: '1.25rem' }}>
        <h1 className="section-title">📞 Direct Web Voice Phone</h1>
        <p className="section-subtitle">
          Natural back-and-forth conversational AI receptionist with context memory and thinking pause tolerance.
        </p>
      </div>

      {errorMsg && (
        <div
          style={{
            maxWidth: '460px',
            margin: '0 auto 1.25rem',
            padding: '0.75rem 1rem',
            background: 'var(--rose-100)',
            color: 'var(--rose-700)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.85rem',
            fontWeight: 600,
          }}
        >
          {errorMsg}
        </div>
      )}

      {/* Modern Smartphone Mockup */}
      <div className="phone-container" style={{ maxWidth: '440px', margin: '0 auto', padding: '1.5rem' }}>
        {/* Calling Header Avatar */}
        <div className={`phone-avatar-wrapper ${isSpeaking ? 'active' : ''}`}>
          <Bot size={44} />
        </div>

        <div className="phone-biz-name" style={{ marginTop: '0.5rem' }}>
          {business?.name || 'AI Voice Receptionist'}
        </div>

        {/* Live Call Status Pill */}
        <div
          className="phone-status"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 12px',
            borderRadius: '12px',
            background: callActive ? 'var(--sky-50)' : 'var(--slate-100)',
            color: callActive ? 'var(--sky-800)' : 'var(--slate-600)',
            fontWeight: 700,
            fontSize: '0.82rem',
            marginTop: '0.5rem',
            border: '1px solid var(--sky-200)',
          }}
        >
          {callActive && <Radio size={14} className={isSpeaking || isListening ? 'animate-pulse' : ''} />}
          {callActive ? `${callStatus} • ${formatDuration(duration)}` : callStatus}
        </div>

        {/* Real-time Language Selector Pill Switcher */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.4rem',
            background: 'var(--slate-100)',
            padding: '3px 4px',
            borderRadius: 'var(--radius-full)',
            marginTop: '0.65rem',
            border: '1px solid var(--slate-200)',
          }}
          title="Switch the language the receptionist listens and replies in"
        >
          <span style={{ fontSize: '0.74rem', color: 'var(--slate-500)', fontWeight: 700, paddingLeft: '6px' }}>
            Language:
          </span>
          <button
            type="button"
            onClick={() => changeSpeechLanguage('hi-IN')}
            style={{
              padding: '0.22rem 0.65rem',
              borderRadius: 'var(--radius-full)',
              fontSize: '0.76rem',
              fontWeight: 700,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '3px',
              transition: 'var(--transition)',
              background: speechLang === 'hi-IN' ? 'var(--sky-500)' : 'transparent',
              color: speechLang === 'hi-IN' ? 'white' : 'var(--slate-700)',
              boxShadow: speechLang === 'hi-IN' ? '0 2px 6px rgba(14, 165, 233, 0.35)' : 'none',
            }}
          >
            🇮🇳 हिंदी (Hindi)
          </button>
          <button
            type="button"
            onClick={() => changeSpeechLanguage('en-IN')}
            style={{
              padding: '0.22rem 0.65rem',
              borderRadius: 'var(--radius-full)',
              fontSize: '0.76rem',
              fontWeight: 700,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '3px',
              transition: 'var(--transition)',
              background: speechLang === 'en-IN' ? 'var(--sky-500)' : 'transparent',
              color: speechLang === 'en-IN' ? 'white' : 'var(--slate-700)',
              boxShadow: speechLang === 'en-IN' ? '0 2px 6px rgba(14, 165, 233, 0.35)' : 'none',
            }}
          >
            🌐 English
          </button>
        </div>

        {/* Dynamic Waveform Display */}
        <div className={`phone-waveform ${isSpeaking || isListening ? 'active' : ''}`} style={{ margin: '1rem 0' }}>
          <div className="wave-bar" />
          <div className="wave-bar" />
          <div className="wave-bar" />
          <div className="wave-bar" />
          <div className="wave-bar" />
        </div>

        {/* Live Conversation Transcript */}
        <div className="phone-transcript" style={{ height: '260px', borderRadius: '12px', padding: '0.85rem' }}>
          {transcript.length === 0 ? (
            <div style={{ textAlign: 'center', margin: 'auto', color: 'var(--slate-400)', fontSize: '0.88rem' }}>
              👋 Press the green call button below to start talking back-and-forth with your AI Receptionist!
            </div>
          ) : (
            transcript.map((item, i) => (
              <div key={i} className={`chat-bubble ${item.role}`}>
                <div style={{ fontSize: '0.72rem', fontWeight: 800, marginBottom: '2px', opacity: 0.85 }}>
                  {item.speaker}
                </div>
                <div>{item.text}</div>
                {item.toolUsed && (
                  <div
                    style={{
                      fontSize: '0.7rem',
                      background: 'rgba(255,255,255,0.8)',
                      color: 'var(--sky-800)',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      marginTop: '4px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    <Sparkles size={11} /> Executed: {item.toolUsed}
                  </div>
                )}
              </div>
            ))
          )}

          {/* Real-time Interim Speech Bubble with instant Send Now button */}
          {interimText && (
            <div
              className="chat-bubble user"
              style={{
                background: 'var(--sky-400)',
                opacity: 0.95,
                animation: 'pulse 1.8s infinite',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '0.72rem', fontWeight: 800 }}>You (speaking...)</span>
                <button
                  type="button"
                  onClick={handleImmediateSendSpeech}
                  style={{
                    background: 'white',
                    color: 'var(--sky-800)',
                    border: 'none',
                    borderRadius: '12px',
                    padding: '2px 8px',
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '3px',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                  }}
                  title="Click to send immediately without waiting for pause timeout"
                >
                  <Zap size={11} /> Send Now
                </button>
              </div>
              <div style={{ fontStyle: 'italic' }}>{interimText}</div>
            </div>
          )}

          <div ref={transcriptBottomRef} />
        </div>

        {/* Text fallback input during active call */}
        {callActive && (
          <form
            onSubmit={handleTextSubmit}
            style={{ width: '100%', display: 'flex', gap: '0.5rem', marginBottom: '1.25rem' }}
          >
            <input
              type="text"
              className="form-input"
              placeholder={speechLang === 'hi-IN' ? "हिंदी या Hinglish में टाइप करें या बोलें..." : "Type in English or speak into mic..."}
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              style={{ flex: 1, padding: '0.55rem 0.85rem', fontSize: '0.85rem' }}
            />
            <button
              type="submit"
              className="btn-secondary"
              style={{ padding: '0.55rem 0.85rem' }}
              disabled={!textInput.trim() || isTurnInFlightRef.current}
            >
              <Send size={15} />
            </button>
          </form>
        )}

        {/* Call Controls */}
        <div className="phone-controls" style={{ display: 'flex', justifyContent: 'center', gap: '1.25rem' }}>
          {!callActive ? (
            <button
              className="btn-circle btn-call-start"
              onClick={startCall}
              onTouchStart={unlockAudioForMobile}
              title="Start Live Call"
              style={{ width: '64px', height: '64px', borderRadius: '50%' }}
            >
              <Phone size={28} />
            </button>
          ) : (
            <>
              {/* Mic / Push-to-Talk Button */}
              <button
                className={`btn-circle btn-mic-toggle ${isListening ? 'listening' : ''}`}
                onClick={handsFree ? toggleMute : undefined}
                onMouseDown={!handsFree ? handlePushToTalkStart : undefined}
                onMouseUp={!handsFree ? handlePushToTalkEnd : undefined}
                onTouchStart={!handsFree ? handlePushToTalkStart : undefined}
                onTouchEnd={!handsFree ? handlePushToTalkEnd : undefined}
                title={
                  handsFree
                    ? isMicMuted
                      ? 'Unmute Mic'
                      : 'Mute Mic'
                    : 'Hold to Speak, Release to Send'
                }
                style={{
                  width: '56px',
                  height: '56px',
                  borderRadius: '50%',
                  background: isMicMuted
                    ? 'var(--slate-200)'
                    : isListening
                    ? 'var(--emerald-500, #10b981)'
                    : 'var(--sky-500)',
                  color: isMicMuted ? 'var(--slate-600)' : 'white',
                  border: 'none',
                  boxShadow: isListening ? '0 0 16px rgba(16, 185, 129, 0.4)' : 'none',
                  cursor: 'pointer',
                }}
              >
                {isMicMuted ? <MicOff size={22} /> : <Mic size={22} />}
              </button>

              {/* End Call Button */}
              <button
                className="btn-circle btn-call-end"
                onClick={endCall}
                title="Hangup Call"
                style={{
                  width: '56px',
                  height: '56px',
                  borderRadius: '50%',
                  background: 'var(--rose-600)',
                  color: 'white',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                <PhoneOff size={24} />
              </button>
            </>
          )}
        </div>

        {/* Thinking Pause Tolerance & Mode Controls */}
        {callActive && (
          <div
            style={{
              marginTop: '1rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem',
              fontSize: '0.75rem',
              color: 'var(--slate-500)',
              borderTop: '1px solid var(--slate-100)',
              paddingTop: '0.75rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>
                {isMicMuted
                  ? '🔴 Mic Muted'
                  : isListening
                  ? '🟢 Mic Listening'
                  : isSpeaking
                  ? '🔊 Assistant Speaking'
                  : '⚡ Ready'}
              </span>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={handsFree}
                  onChange={(e) => {
                    const val = e.target.checked;
                    setHandsFree(val);
                    handsFreeRef.current = val;
                    if (val && callActiveRef.current && !isSpeakingRef.current) {
                      startSpeechListening();
                    } else if (!val) {
                      stopRecognition();
                    }
                  }}
                  style={{ cursor: 'pointer' }}
                />
                Hands-Free Auto Turn
              </label>
            </div>

            {/* Pause tolerance selector */}
            {handsFree && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  background: 'var(--slate-50)',
                  padding: '4px 8px',
                  borderRadius: '6px',
                  fontSize: '0.72rem',
                }}
              >
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                  <Clock size={12} /> Pause Tolerance:
                </span>
                <div style={{ display: 'flex', gap: '4px' }}>
                  {[
                    { label: '1.5s (Quick)', val: 1500 },
                    { label: '2.5s (Standard)', val: 2500 },
                    { label: '4.0s (Long)', val: 4000 },
                  ].map((p) => (
                    <button
                      key={p.val}
                      type="button"
                      onClick={() => setPauseDuration(p.val)}
                      style={{
                        padding: '2px 6px',
                        borderRadius: '4px',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: '0.7rem',
                        fontWeight: pauseDuration === p.val ? 800 : 500,
                        background: pauseDuration === p.val ? 'var(--sky-500)' : 'transparent',
                        color: pauseDuration === p.val ? 'white' : 'var(--slate-600)',
                      }}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {!handsFree && (
              <div style={{ textAlign: 'center', fontSize: '0.72rem', color: 'var(--sky-700)', fontWeight: 600 }}>
                💡 Push-to-Talk active: Press and hold the green mic to speak, release when finished.
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
