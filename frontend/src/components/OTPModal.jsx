import React from 'react';
import { AlertCircle } from 'lucide-react';
import '../styles/OTPModal.css';

export default function OTPModal({ pauseData, otpInput, setOtpInput, handleResume }) {
  if (!pauseData) return null;

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <h2><AlertCircle size={20} color="#f59e0b" /> Required Action</h2>
        <p>{pauseData.message}</p>
        <input 
          type="text" 
          className="otp-input"
          placeholder="e.g. 123456"
          value={otpInput}
          onChange={(e) => setOtpInput(e.target.value)}
          autoFocus
        />
        <button className="btn-primary btn-full" onClick={handleResume}>
          Submit & Resume
        </button>
      </div>
    </div>
  );
}
