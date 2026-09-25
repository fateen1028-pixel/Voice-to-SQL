import { useRef, useState } from 'react';
import { submitVoiceQuery } from '@/api/client';
import type { ApiResponse } from '@/types';
import { MicrophoneButton } from './MicrophoneButton';

interface Props {
  conversationId: string;
  disabled: boolean;
  onSubmit: (message: string) => Promise<void>;
  onVoiceResult: (message: string, response: ApiResponse) => void;
  onError: (message: string) => void;
}

export function InputArea({ conversationId, disabled, onSubmit, onVoiceResult, onError }: Props) {
  const [text, setText] = useState('');
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [lang, setLang] = useState<'en-US' | 'ta-IN'>('en-US');
  const recorder = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<any>(null);
  const latestTranscriptRef = useRef<string>('');
  const chunks = useRef<Blob[]>([]);
  const stream = useRef<MediaStream | null>(null);

  const releaseStream = () => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  };

  const submit = async () => {
    const message = text.trim();
    if (!message || disabled || recording || transcribing) return;
    setText('');
    latestTranscriptRef.current = '';
    await onSubmit(message);
  };

  const toggleVoice = async () => {
    if (recording) {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch (_) {}
        recognitionRef.current = null;
      }
      if (recorder.current && recorder.current.state !== 'inactive') {
        try {
          recorder.current.stop();
        } catch (_) {}
      }
      setRecording(false);
      return;
    }
    if (disabled || transcribing) return;

    // 1. Browser Web Speech API for instant live voice recognition (Chrome, Edge, Safari, Brave, Opera)
    const windowWithSpeech = window as any;
    const SpeechRecognition = windowWithSpeech.SpeechRecognition || windowWithSpeech.webkitSpeechRecognition;

    if (SpeechRecognition) {
      try {
        latestTranscriptRef.current = '';
        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = true;
        recognition.lang = lang;

        recognition.onresult = (event: any) => {
          let transcript = '';
          for (let i = 0; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
          }
          if (transcript) {
            latestTranscriptRef.current = transcript;
            setText(transcript);
          }
        };

        recognition.onerror = (event: any) => {
          console.warn('Speech recognition error:', event.error);
          setRecording(false);
        };

        recognition.onend = async () => {
          setRecording(false);
          recognitionRef.current = null;
          const finalSpokenText = latestTranscriptRef.current.trim();
          if (finalSpokenText) {
            latestTranscriptRef.current = '';
            setText('');
            await onSubmit(finalSpokenText);
          }
        };

        recognitionRef.current = recognition;
        recognition.start();
        setRecording(true);
        return;
      } catch (err) {
        console.warn('Web Speech API failed, falling back to MediaRecorder upload:', err);
      }
    }

    // 2. MediaRecorder audio upload fallback
    try {
      const audio = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = audio;
      chunks.current = [];
      const mediaRecorder = new MediaRecorder(audio);
      recorder.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        setTranscribing(true);
        try {
          const mimeType = mediaRecorder.mimeType || 'audio/webm';
          const audioBlob = new Blob(chunks.current, { type: mimeType });
          const result = await submitVoiceQuery(audioBlob, conversationId);

          if (result.transcript) {
            setText('');
            onVoiceResult(`🎤 ${result.transcript}`, result);
          } else {
            onVoiceResult('🎤 Voice Input', result);
          }
        } catch (error) {
          onError(
            error instanceof Error
              ? error.message
              : 'Voice processing failed. Please type your question.'
          );
        } finally {
          setTranscribing(false);
          releaseStream();
        }
      };

      mediaRecorder.start();
      setRecording(true);
    } catch (error) {
      const name = error instanceof DOMException ? error.name : '';
      onError(
        name === 'NotAllowedError'
          ? 'Microphone access was denied. You can still type your question.'
          : name === 'NotFoundError'
          ? 'No microphone was found. You can still type your question.'
          : 'A microphone could not be started. You can still type your question.'
      );
    }
  };

  const placeholderText = transcribing
    ? 'Transcribing audio...'
    : recording
    ? 'Listening... Click microphone when finished'
    : 'Ask about your data';

  return (
    <div className={`composer ${recording ? 'border-red-400 bg-red-50/10' : ''}`}>
      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
        rows={1}
        placeholder={placeholderText}
        aria-label="Ask about your data"
        disabled={disabled || recording || transcribing}
      />
      <div className="composer-actions">
        <MicrophoneButton
          recording={recording}
          processing={transcribing}
          disabled={disabled}
          onClick={toggleVoice}
        />
        <button
          type="button"
          className="px-2 py-1 text-xs rounded-lg font-medium bg-neutral-800 text-neutral-300 hover:text-white hover:bg-neutral-700 transition-colors"
          onClick={() => setLang((l) => (l === 'en-US' ? 'ta-IN' : 'en-US'))}
          title="Switch Voice Language (English / Tamil)"
        >
          {lang === 'en-US' ? 'EN' : 'தமிழ்'}
        </button>
        <button
          className="send-button"
          onClick={submit}
          disabled={!text.trim() || disabled || recording || transcribing}
          aria-label="Send question"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="m5 12 14-7-4 14-3-5-5-2Z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
