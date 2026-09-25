interface Props { recording: boolean; processing: boolean; disabled: boolean; onClick: () => void; }
export function MicrophoneButton({ recording, processing, disabled, onClick }: Props) {
  const label = processing ? 'Sending voice recording' : recording ? 'Stop recording' : 'Start voice recording';
  return <button className={`mic-button ${recording ? 'is-recording' : ''}`} onClick={onClick} disabled={disabled || processing} aria-label={label} title={label}>
    {processing ? <span className="mini-spinner" /> : <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><path strokeLinecap="round" strokeLinejoin="round" d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm6-4.5a6 6 0 0 1-12 0M12 18v3m-3 0h6" /></svg>}
  </button>;
}
