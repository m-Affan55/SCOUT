import React, { useState, useRef } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, CheckCircle2, Loader2, FileText } from 'lucide-react';
import '../styles/Onboarding.css';

export default function Onboarding() {
  const { getToken } = useAuth();
  const navigate = useNavigate();
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [fatherName, setFatherName] = useState('');
  const [dateOfBirth, setDateOfBirth] = useState('');
  const [gender, setGender] = useState('Male');
  const [cnic, setCnic] = useState('');
  const [phone, setPhone] = useState('');
  const [resume, setResume] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setResume(e.target.files[0]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!firstName || !lastName || !phone || !cnic) {
      setError('Please fill in all required fields');
      return;
    }

    setLoading(true);
    setError('');

    const formData = new FormData();
    formData.append('first_name', firstName);
    formData.append('last_name', lastName);
    formData.append('father_name', fatherName);
    formData.append('date_of_birth', dateOfBirth);
    formData.append('gender', gender);
    formData.append('cnic', cnic);
    formData.append('phone', phone);
    if (resume) {
      formData.append('resume', resume);
    }

    try {
      const token = await getToken();
      const response = await fetch(`${import.meta.env.VITE_API_URL}/api/auth/onboarding`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Failed to save profile');
      }

      // Success, redirect to the app
      navigate('/');
    } catch (err) {
      setError(err.message || 'An error occurred during onboarding');
      setLoading(false);
    }
  };

  return (
    <div className="onboarding-container">
      <div className="onboarding-card">
        <div className="onboarding-header">
          <h1>Complete Your Profile</h1>
          <p>Let's set up your profile for automation</p>
        </div>

        <form className="onboarding-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label>First Name</label>
            <input 
              type="text" 
              value={firstName} 
              onChange={(e) => setFirstName(e.target.value)} 
              placeholder="Ali"
              required 
            />
          </div>
          <div className="form-group">
            <label>Last Name</label>
            <input 
              type="text" 
              value={lastName} 
              onChange={(e) => setLastName(e.target.value)} 
              placeholder="Khan"
              required 
            />
          </div>
          <div className="form-group">
            <label>Father's Name</label>
            <input 
              type="text" 
              value={fatherName} 
              onChange={(e) => setFatherName(e.target.value)} 
              placeholder="Muhammad Ali"
            />
          </div>
          <div style={{display: 'flex', gap: '20px'}}>
            <div className="form-group" style={{flex: 1}}>
              <label>Date of Birth</label>
              <input 
                type="date" 
                value={dateOfBirth} 
                onChange={(e) => setDateOfBirth(e.target.value)} 
                style={{
                  backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)', 
                  color: 'var(--text-primary)', padding: '12px 16px', borderRadius: '8px',
                  fontFamily: 'inherit'
                }}
              />
            </div>
            <div className="form-group" style={{flex: 1}}>
              <label>Gender</label>
              <select 
                value={gender} 
                onChange={(e) => setGender(e.target.value)}
                style={{
                  backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)', 
                  color: 'var(--text-primary)', padding: '12px 16px', borderRadius: '8px',
                  fontFamily: 'inherit'
                }}
              >
                <option value="Male">Male</option>
                <option value="Female">Female</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>
          <div className="form-group">
            <label>CNIC</label>
            <input 
              type="text" 
              value={cnic} 
              onChange={(e) => setCnic(e.target.value)} 
              placeholder="35202-1234567-1"
              required 
            />
          </div>
          <div className="form-group">
            <label>Phone Number</label>
            <input 
              type="tel" 
              value={phone} 
              onChange={(e) => setPhone(e.target.value)} 
              placeholder="+92 300 1234567"
              required 
            />
          </div>

          <div 
            className="file-upload-zone" 
            onClick={() => fileInputRef.current?.click()}
          >
            <input 
              type="file" 
              ref={fileInputRef}
              onChange={handleFileChange}
              className="file-input"
              accept=".pdf,.doc,.docx"
            />
            {resume ? (
              <>
                <FileText size={32} className="upload-icon" style={{color: '#3b82f6'}} />
                <span className="file-name">{resume.name}</span>
                <span style={{fontSize: '12px', color: '#888888'}}>Click to change file</span>
              </>
            ) : (
              <>
                <UploadCloud size={32} className="upload-icon" />
                <span style={{color: '#ededed', fontWeight: 500}}>Upload Resume</span>
                <span style={{fontSize: '12px', color: '#888888'}}>PDF, DOCX up to 5MB</span>
              </>
            )}
          </div>

          {error && <div className="error-message">{error}</div>}

          <button type="submit" className="submit-btn" disabled={loading}>
            {loading ? <Loader2 size={18} className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} /> : <CheckCircle2 size={18} />}
            {loading ? 'Saving Profile...' : 'Complete Setup'}
          </button>
        </form>
      </div>
    </div>
  );
}
