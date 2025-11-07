import React, { useState, useRef, useEffect } from 'react';
import { Mic, MicOff, Volume2, VolumeX, Pause, Play } from 'lucide-react';

export default function AudioChatbot() {
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Hello! I\'m your audio assistant. Press the microphone to start talking.' }
  ]);
  const [audioLevel, setAudioLevel] = useState(0);
  const audioVisualizerRef = useRef(null);

  // Simulate audio level visualization
  useEffect(() => {
    if (isListening) {
      const interval = setInterval(() => {
        setAudioLevel(Math.random() * 100);
      }, 100);
      return () => clearInterval(interval);
    } else {
      setAudioLevel(0);
    }
  }, [isListening]);

  const toggleListening = () => {
    if (isListening) {
      // Stop listening
      setIsListening(false);
      if (transcript) {
        setMessages(prev => [...prev, 
          { role: 'user', text: transcript },
          { role: 'assistant', text: 'I heard you say: "' + transcript + '". This is a demo interface.' }
        ]);
        setTranscript('');
      }
    } else {
      // Start listening
      setIsListening(true);
      setTranscript('');
    }
  };

  const toggleMute = () => {
    setIsMuted(!isMuted);
  };

  const toggleSpeaking = () => {
    setIsSpeaking(!isSpeaking);
  };

  // Simulate real-time transcript
  useEffect(() => {
    if (isListening) {
      const phrases = ['Hello', 'Hello, how', 'Hello, how are', 'Hello, how are you?'];
      let index = 0;
      const interval = setInterval(() => {
        if (index < phrases.length) {
          setTranscript(phrases[index]);
          index++;
        } else {
          clearInterval(interval);
        }
      }, 500);
      return () => clearInterval(interval);
    }
  }, [isListening]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {/* Main Audio Interface */}
        <div className="bg-white/10 backdrop-blur-xl rounded-3xl p-8 shadow-2xl border border-white/20">
          
          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">Audio Assistant</h1>
            <p className="text-blue-200">Voice-powered conversation</p>
          </div>

          {/* Audio Visualizer */}
          <div className="mb-8 h-24 flex items-end justify-center gap-1">
            {[...Array(30)].map((_, i) => (
              <div
                key={i}
                className="w-2 bg-gradient-to-t from-blue-400 to-purple-400 rounded-full transition-all duration-100"
                style={{
                  height: isListening 
                    ? `${Math.max(10, audioLevel * Math.sin(i * 0.5) + Math.random() * 30)}%`
                    : '10%'
                }}
              />
            ))}
          </div>

          {/* Status Display */}
          <div className="text-center mb-8 min-h-16">
            {isListening ? (
              <div className="space-y-2">
                <p className="text-blue-300 text-sm font-medium">LISTENING...</p>
                <p className="text-white text-lg">{transcript || 'Speak now...'}</p>
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

          {/* Main Control Button */}
          <div className="flex justify-center mb-6">
            <button
              onClick={toggleListening}
              className={`w-24 h-24 rounded-full flex items-center justify-center transition-all transform hover:scale-105 active:scale-95 shadow-2xl ${
                isListening
                  ? 'bg-red-500 hover:bg-red-600 animate-pulse'
                  : 'bg-blue-500 hover:bg-blue-600'
              }`}
            >
              {isListening ? (
                <MicOff className="w-12 h-12 text-white" />
              ) : (
                <Mic className="w-12 h-12 text-white" />
              )}
            </button>
          </div>

          {/* Secondary Controls */}
          <div className="flex justify-center gap-4 mb-8">
            <button
              onClick={toggleMute}
              className="w-14 h-14 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition-all backdrop-blur-sm"
              title={isMuted ? 'Unmute' : 'Mute'}
            >
              {isMuted ? (
                <VolumeX className="w-6 h-6 text-white" />
              ) : (
                <Volume2 className="w-6 h-6 text-white" />
              )}
            </button>
            <button
              onClick={toggleSpeaking}
              className="w-14 h-14 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition-all backdrop-blur-sm"
              title={isSpeaking ? 'Pause' : 'Play'}
            >
              {isSpeaking ? (
                <Pause className="w-6 h-6 text-white" />
              ) : (
                <Play className="w-6 h-6 text-white" />
              )}
            </button>
          </div>

          {/* Conversation History */}
          <div className="bg-black/20 rounded-2xl p-4 max-h-64 overflow-y-auto space-y-3">
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2 ${
                    msg.role === 'user'
                      ? 'bg-blue-500 text-white'
                      : 'bg-white/10 text-white backdrop-blur-sm'
                  }`}
                >
                  <p className="text-sm">{msg.text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Instructions */}
        <div className="mt-6 text-center text-blue-200 text-sm">
          <p>Press and hold the microphone button to speak</p>
          <p className="mt-1">Release to send your message</p>
        </div>
      </div>
    </div>
  );
}