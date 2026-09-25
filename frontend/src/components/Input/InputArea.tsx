import { useRef, useState } from 'react';
import { submitVoiceQuery } from '@/api/client';
import type { ApiResponse } from '@/types';
import { MicrophoneButton } from './MicrophoneButton';

interface Props { conversationId: string; disabled: boolean; onSubmit: (message: string) => Promise<void>; onVoiceResult: (message: string, response: ApiResponse) => void; onError: (message: string) => void; }

export function InputArea({ disabled, onSubmit, onVoiceResult, onError }: Props) {
  const [text, setText] = useState('');
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const stream = useRef<MediaStream | null>(null);

  const releaseStream = () => { stream.current?.getTracks().forEach((track) => track.stop()); stream.current = null; };
  const submit = async () => { const message = text.trim(); if (!message || disabled) return; setText(''); await onSubmit(message); };

  const toggleVoice = async () => {
    if (recording) { recorder.current?.stop(); setRecording(false); return; }
    if (disabled || transcribing) return;
    try {
      const audio = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = audio; chunks.current = [];
      const mediaRecorder = new MediaRecorder(audio);
      recorder.current = mediaRecorder;
      mediaRecorder.ondataavailable = (event) => { if (event.data.size) chunks.current.push(event.data); };
      mediaRecorder.onstop = async () => {
        setTranscribing(true);
        try {
          const result = await submitVoiceQuery(new Blob(chunks.current, { type: mediaRecorder.mimeType || 'audio/webm' }));
          onVoiceResult(result.message || 'Voice query', result);
        } catch (error) { onError(error instanceof Error ? error.message : 'Voice processing failed. Please type your question.'); }
        finally { setTranscribing(false); releaseStream(); }
      };
      mediaRecorder.start(); setRecording(true);
    } catch (error) {
      const name = error instanceof DOMException ? error.name : '';
      onError(name === 'NotAllowedError' ? 'Microphone access was not allowed. You can still type your question.' : 'A microphone could not be started. You can still type your question.');
    }
  };

  return <div className="composer">
    <textarea value={text} onChange={(event) => setText(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(); } }} rows={1} placeholder="Ask about your data" aria-label="Ask about your data" disabled={disabled || recording || transcribing} />
    <div className="composer-actions">
      <MicrophoneButton recording={recording} processing={transcribing} disabled={disabled} onClick={toggleVoice} />
      <button className="send-button" onClick={submit} disabled={!text.trim() || disabled || recording || transcribing} aria-label="Send question"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="m5 12 14-7-4 14-3-5-5-2Z" /></svg></button>
    </div>
  </div>;
}
