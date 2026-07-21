import React, { useEffect, useRef } from 'react';
import { AlertCircle, KeyRound, MessageSquare } from 'lucide-react';
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

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (isCaptcha || otpInput.trim())) {
      handleResume();
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-icon-wrapper">
          {isOtp
            ? <KeyRound size={28} className="modal-icon otp" />
            : <MessageSquare size={28} className="modal-icon info" />
          }
        </div>

        <h2>{isOtp ? 'OTP Verification' : 'Information Required'}</h2>
        <p>{pauseData.message}</p>

        {isCaptcha ? (
          <p className="captcha-instruction">Please interact with the browser directly to solve the CAPTCHA, then click Resume.</p>
        ) : (
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
        )}
        <button 
          className="btn-primary btn-full" 
          onClick={handleResume}
          disabled={!isCaptcha && !otpInput.trim()}
        >
          {isCaptcha ? 'Resume' : 'Submit & Resume'}
        </button>
      </div>
    </div>
  );
}
