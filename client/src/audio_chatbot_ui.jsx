import React, { useState, useRef, useEffect } from "react";
import { Mic, MicOff, Volume2, VolumeX, Pause, Play } from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ---- Minimal WAV encoder (client-side) ----
function mergeFloat32(arrays) {
  let length = 0;
  for (const a of arrays) length += a.length;
  const out = new Float32Array(length);
  let offset = 0;
  for (const a of arrays) { out.set(a, offset); offset += a.length; }
  return out;
}
function floatTo16BitPCM(view, offset, input) {
  for (let i = 0; i < input.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
}
function encodeWAV(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  // RIFF chunk descriptor
  const writeString = (v, o, s) => { for (let i=0;i<s.length;i++) v.setUint8(o+i, s.charCodeAt(i)); };
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, "WAVE");
  // fmt subchunk
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);    // PCM
  view.setUint16(20, 1, true);     // PCM format
  view.setUint16(22, 1, true);     // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true);     // block align
  view.setUint16(34, 16, true);    // bits per sample
  // data subchunk
  writeString(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);
  floatTo16BitPCM(view, 44, samples);

  return new Blob([view], { type: "audio/wav" });
}

export default function AudioChatbot() {
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Hello! I'm your audio assistant. Press the microphone to start talking." }
  ]);
  const [audioLevel, setAudioLevel] = useState(0);

  // recorder refs
  const mediaStreamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const sourceRef = useRef(null);
  const processorRef = useRef(null);
  const chunksRef = useRef([]);
  const sampleRateRef = useRef(48000);

  // Fake visualizer just like your mock
  useEffect(() => {
    if (isListening) {
      const t = setInterval(() => setAudioLevel(Math.random() * 100), 100);
      return () => clearInterval(t);
    } else {
      setAudioLevel(0);
    }
  }, [isListening]);

  async function startListening() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const AudioContext = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioContext({ sampleRate: 48000 }); // 48k is fine
      audioCtxRef.current = ctx;
      sampleRateRef.current = ctx.sampleRate;

      const source = ctx.createMediaStreamSource(stream);
      sourceRef.current = source;

      const proc = ctx.createScriptProcessor(4096, 1, 1); // deprecated but widely supported
      processorRef.current = proc;

      chunksRef.current = [];
      proc.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        chunksRef.current.push(new Float32Array(input)); // copy chunk
      };

      source.connect(proc);
      proc.connect(ctx.destination);

      setTranscript("");
      setIsListening(true);
    } catch (err) {
      console.error("Mic error:", err);
      alert("Microphone permission or setup failed.");
    }
  }

  async function stopListening() {
    setIsListening(false);

    try {
      // stop nodes
      try { processorRef.current?.disconnect(); } catch {}
      try { sourceRef.current?.disconnect(); } catch {}
      try { audioCtxRef.current?.close(); } catch {}
      // stop tracks
      mediaStreamRef.current?.getTracks().forEach(t => t.stop());

      const samples = mergeFloat32(chunksRef.current);
      const wavBlob = encodeWAV(samples, sampleRateRef.current);

      // 1) STT
      const fd = new FormData();
      fd.append("file", wavBlob, "input.wav");
      const sttRes = await fetch(`${API_BASE}/stt`, { method: "POST", body: fd });
      if (!sttRes.ok) throw new Error(`STT HTTP ${sttRes.status}`);
      const sttJson = await sttRes.json();
      const text = sttJson.text || "";
      setTranscript(text);

      if (text) {
        setMessages(prev => [...prev, { role: "user", text }]);
      } else {
        setMessages(prev => [...prev, { role: "user", text: "(no speech detected)" }]);
      }

      if (!isMuted) {
        // 2) TTS (echo back the transcript for now)
        const tfd = new FormData();
        tfd.append("text", text || "I didn't catch that.");
        setIsSpeaking(true);
        const ttsRes = await fetch(`${API_BASE}/tts`, { method: "POST", body: tfd });
        setIsSpeaking(false);
        if (!ttsRes.ok) throw new Error(`TTS HTTP ${ttsRes.status}`);
        const reply = await ttsRes.blob();
        new Audio(URL.createObjectURL(reply)).play();
        setMessages(prev => [...prev, { role: "assistant", text: text || "I didn't catch that." }]);
      }
    } catch (err) {
      console.error(err);
      alert("Audio round-trip failed: " + err.message);
    } finally {
      // clear refs
      chunksRef.current = [];
      mediaStreamRef.current = null;
      sourceRef.current = null;
      processorRef.current = null;
      audioCtxRef.current = null;
    }
  }

  const toggleListening = () => {
    if (isListening) stopListening(); else startListening();
  };
  const toggleMute = () => setIsMuted(m => !m);
  const toggleSpeaking = () => setIsSpeaking(s => !s); // demo-only

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        <div className="bg-white/10 backdrop-blur-xl rounded-3xl p-8 shadow-2xl border border-white/20">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">Audio Assistant</h1>
            <p className="text-blue-200">Voice-powered conversation</p>
          </div>

          {/* Visualizer (mocked) */}
          <div className="mb-8 h-24 flex items-end justify-center gap-1">
            {[...Array(30)].map((_, i) => (
              <div
                key={i}
                className="w-2 bg-gradient-to-t from-blue-400 to-purple-400 rounded-full transition-all duration-100"
                style={{
                  height: isListening
                    ? `${Math.max(10, audioLevel * Math.sin(i * 0.5) + Math.random() * 30)}%`
                    : "10%",
                }}
              />
            ))}
          </div>

          {/* Status */}
          <div className="text-center mb-8 min-h-16">
            {isListening ? (
              <div className="space-y-2">
                <p className="text-blue-300 text-sm font-medium">LISTENING...</p>
                <p className="text-white text-lg">{transcript || "Speak now..."}</p>
              </div>
            ) : isSpeaking ? (
              <div className="space-y-2">
                <p className="text-green-300 text-sm font-medium">SPEAKING...</p>
                <p className="text-white text-lg">Playing response</p>
              </div>
            ) : (
              <p className="text-gray-300">Ready to listen</p>
            )}
          </div>

          {/* Main button */}
          <div className="flex justify-center mb-6">
            <button
              onClick={toggleListening}
              className={`w-24 h-24 rounded-full flex items-center justify-center transition-all transform hover:scale-105 active:scale-95 shadow-2xl ${
                isListening ? "bg-red-500 hover:bg-red-600 animate-pulse" : "bg-blue-500 hover:bg-blue-600"
              }`}
            >
              {isListening ? <MicOff className="w-12 h-12 text-white" /> : <Mic className="w-12 h-12 text-white" />}
            </button>
          </div>

          {/* Secondary controls */}
          <div className="flex justify-center gap-4 mb-8">
            <button
              onClick={toggleMute}
              className="w-14 h-14 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition-all backdrop-blur-sm"
              title={isMuted ? "Unmute" : "Mute"}
            >
              {isMuted ? <VolumeX className="w-6 h-6 text-white" /> : <Volume2 className="w-6 h-6 text-white" />}
            </button>
            <button
              onClick={toggleSpeaking}
              className="w-14 h-14 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition-all backdrop-blur-sm"
              title={isSpeaking ? "Pause" : "Play"}
            >
              {isSpeaking ? <Pause className="w-6 h-6 text-white" /> : <Play className="w-6 h-6 text-white" />}
            </button>
          </div>

          {/* Conversation */}
          <div className="bg-black/20 rounded-2xl p-4 max-h-64 overflow-y-auto space-y-3">
            {messages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2 ${
                    msg.role === "user" ? "bg-blue-500 text-white" : "bg-white/10 text-white backdrop-blur-sm"
                  }`}
                >
                  <p className="text-sm">{msg.text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-6 text-center text-blue-200 text-sm">
          <p>Press the microphone to start talking</p>
          <p className="mt-1">Press again to stop and send</p>
        </div>
      </div>
    </div>
  );
}