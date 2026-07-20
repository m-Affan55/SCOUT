import React, { useState, useEffect, useRef } from 'react';
import { Terminal, Bot, User, CheckCircle2, Loader2, Play, AlertCircle } from 'lucide-react';
import InputModal from './InputModal';
import '../styles/WorkflowConsole.css';

export default function WorkflowConsole() {
  const [goal, setGoal] = useState('');
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState('idle'); // idle, running, paused
  const [pauseData, setPauseData] = useState(null);
  const [otpInput, setOtpInput] = useState('');
  const ws = useRef(null);
  const feedRef = useRef(null);
  const reconnectTimer = useRef(null);
  const isMounted = useRef(true);

  const connectWebSocket = () => {
    if (!isMounted.current) return;

    const socket = new WebSocket('ws://localhost:8000/ws');

    socket.onopen = () => {
      console.log('[Scout] WebSocket connected');
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'agent_state' || data.type === 'info') {
        setMessages((prev) => [...prev, data]);
      } else if (data.type === 'done') {
        setMessages((prev) => [...prev, { type: 'info', message: data.message }]);
        setStatus('idle');
        // Show a popup to the user to signify the process is fully completed
        window.alert("Process is completed");
      } else if (data.type === 'pause') {
        setStatus('paused');
        setPauseData(data);
        // No need for window.focus() — the backend minimizes the Playwright
        // browser via CDP, so the React app is naturally visible.
      }
    };

    socket.onclose = () => {
      console.log('[Scout] WebSocket closed, reconnecting in 2s...');
      reconnectTimer.current = setTimeout(connectWebSocket, 2000);
    };

    socket.onerror = () => {
      socket.close();
    };

    ws.current = socket;
  };

  useEffect(() => {
    isMounted.current = true;
    connectWebSocket();

    return () => {
      isMounted.current = false;
      clearTimeout(reconnectTimer.current);
      ws.current?.close();
    };
  }, []);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [messages, pauseData]);

  const handleStart = async () => {
    if (!goal.trim()) return;

    setStatus('running');
    setMessages([{ type: 'user', message: goal }]);
    
    try {
      await fetch('http://localhost:8000/api/workflow/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal })
      });
      setGoal('');
    } catch (error) {
      console.error("Failed to start workflow:", error);
      setStatus('idle');
    }
  };

  const handleResume = async () => {
    if (!otpInput.trim()) return;

    try {
      await fetch('http://localhost:8000/api/workflow/resume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input: otpInput })
      });
      setStatus('running');
      setPauseData(null);
      setOtpInput('');
    } catch (error) {
      console.error("Failed to resume workflow:", error);
    }
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1><Terminal size={20} /> Scout</h1>
        <div className={`status-badge ${status}`}>
          {status === 'running' && <Loader2 size={16} className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} />}
          {status === 'paused' && <AlertCircle size={16} />}
          {status === 'idle' && <CheckCircle2 size={16} />}
          {status === 'idle' ? 'Ready' : status === 'paused' ? 'Action Required' : 'Running'}
        </div>
      </header>

      <div className="feed" ref={feedRef}>
        {messages.length === 0 && status === 'idle' && (
          <div className="empty-state">
            <Bot size={24} />
            <p>No workflow started. Enter a goal to begin.</p>
          </div>
        )}
        
        {messages.map((msg, idx) => (
          <div key={idx} className={`message-row ${msg.type === 'user' ? 'user' : 'agent'}`}>
            <div className="message-header">
              {msg.type === 'user' ? <User size={16} /> : <Bot size={16} />}
              <span>{msg.type === 'user' ? 'User' : msg.step || 'System'}</span>
            </div>
            <div className="message-content">{msg.message}</div>
          </div>
        ))}
      </div>

      <div className="input-area">
        <input 
          type="text" 
          className="goal-input" 
          placeholder="What do you want to automate?" 
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleStart()}
          disabled={status !== 'idle'}
        />
        <button 
          className="btn-primary" 
          onClick={handleStart}
          disabled={status !== 'idle' || !goal.trim()}
        >
          <Play size={16} fill="currentColor" />
          Run
        </button>
      </div>

      {status === 'paused' && (
        <InputModal 
          pauseData={pauseData}
          otpInput={otpInput}
          setOtpInput={setOtpInput}
          handleResume={handleResume}
        />
      )}
    </div>
  );
}
