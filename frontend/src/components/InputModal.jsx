import React, { useEffect, useRef } from 'react';
import { AlertCircle, KeyRound, MessageSquare, ShieldAlert } from 'lucide-react';
import '../styles/InputModal.css';

export default function InputModal({ pauseData, otpInput, setOtpInput, handleResume }) {
  const inputRef = useRef(null);

  useEffect(() => {
    // Auto-focus the input whenever the modal appears
    if (pauseData && inputRef.current) {
      inputRef.current.focus();
    }
  }, [pauseData]);

  if (!pauseData) return null;

  const isOtp = pauseData.input_type === 'otp';
  const isCaptcha = pauseData.field_key === 'captcha_solved';
  const isContinueOnly = pauseData.input_type === 'continue_only' || isCaptcha;
  const isHighStakes = pauseData.field_key === 'high_stakes_confirmation';

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (isContinueOnly || otpInput.trim())) {
      handleResume();
    }
  };

  // Determine the icon
  let icon;
  if (isOtp) {
    icon = <KeyRound size={28} className="modal-icon otp" />;
  } else if (isHighStakes) {
    icon = <ShieldAlert size={28} className="modal-icon warning" />;
  } else {
    icon = <MessageSquare size={28} className="modal-icon info" />;
  }

  // Determine the title
  let title;
  if (isOtp) {
    title = 'OTP Verification';
  } else if (isHighStakes) {
    title = 'Confirmation Required';
  } else if (isCaptcha) {
    title = 'CAPTCHA Detected';
  } else {
    title = 'Information Required';
  }

  // Determine what to show for input
  let inputArea;
  if (isContinueOnly) {
    // No text input needed — just a confirm/resume button
    inputArea = null;
  } else {
    inputArea = (
      <input 
        ref={inputRef}
        type="text" 
        className="modal-input"
        placeholder={isOtp ? 'Enter the OTP code' : 'Enter the requested information'}
        value={otpInput}
        onChange={(e) => setOtpInput(e.target.value)}
        onKeyDown={handleKeyDown}
        autoComplete="off"
      />
    );
  }

  // Determine the button label
  let buttonLabel;
  if (isCaptcha) {
    buttonLabel = 'Resume';
  } else if (isHighStakes) {
    buttonLabel = 'Confirm & Proceed';
  } else {
    buttonLabel = 'Submit & Resume';
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-icon-wrapper">
          {icon}
        </div>

        <h2>{title}</h2>
        <p>{pauseData.message}</p>

        {inputArea}
        <button 
          className="btn-primary btn-full" 
          onClick={handleResume}
          disabled={!isContinueOnly && !otpInput.trim()}
        >
          {buttonLabel}
        </button>
      </div>
    </div>
  );
}
