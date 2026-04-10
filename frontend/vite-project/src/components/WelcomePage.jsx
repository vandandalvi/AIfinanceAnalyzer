import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import API_BASE_URL from '../config/api';
import './WelcomePage.css';

const WelcomePage = () => {
  const navigate = useNavigate();
  const [backendStatus, setBackendStatus] = useState('checking'); // 'checking', 'waking', 'ready'

  // Wake up the backend when component mounts
  useEffect(() => {
    const wakeUpBackend = async () => {
      try {
        console.log('Pinging backend to wake up Render free tier...');
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout
        
        const response = await fetch(API_BASE_URL, {
          signal: controller.signal,
          headers: { 'Content-Type': 'application/json' }
        });
        
        clearTimeout(timeoutId);
        
        if (response.ok) {
          console.log('Backend is awake and ready!');
          setBackendStatus('ready');
        } else {
          console.log('Backend responding but with error');
          setBackendStatus('waking');
        }
      } catch (error) {
        if (error.name === 'AbortError') {
          console.log('Backend is waking up (this can take 30-60 seconds on free tier)');
          setBackendStatus('waking');
        } else {
          console.log('Backend ping error:', error);
          setBackendStatus('waking');
        }
      }
    };

    wakeUpBackend();
  }, []);

  const handleGetStarted = () => {
    navigate('/upload');
  };

  const handleTryDemo = async () => {
    try {
      // Fetch the demo PDF file
      const response = await fetch('/mysampleacc.pdf');
      const blob = await response.blob();
      
      // Create a file object
      const file = new File([blob], 'mysampleacc.pdf', { type: 'application/pdf' });

      // Navigate to upload page with demo file
      navigate('/upload', { state: { demoFile: file, bankType: 'kotak' } });
    } catch (error) {
      console.error('Error loading demo file:', error);
      alert('Failed to load demo file. Please try manual upload.');
      navigate('/upload');
    }
  };

  const statusInfo = useMemo(() => {
    if (backendStatus === 'ready') {
      return {
        text: 'Server is live and ready',
        helper: 'You can upload instantly.',
        className: 'ready'
      };
    }

    if (backendStatus === 'waking') {
      return {
        text: 'Server is waking up',
        helper: 'First request can take ~30-60 seconds on free tier.',
        className: 'waking'
      };
    }

    return {
      text: 'Connecting to server',
      helper: 'Checking backend health now...',
      className: 'checking'
    };
  }, [backendStatus]);

  return (
    <div className="welcome-container">
      <header className="top-bar">
        <img src="/kotak_logo.svg" alt="Kotak Mahindra Bank Logo" className="top-logo" />
        <div className={`server-pill ${statusInfo.className}`}>
          <span className="server-dot" />
          <span>{statusInfo.text}</span>
        </div>
      </header>

      <main className="hero-layout simple-layout">
        <section className="hero-content-left">
          <span className="hero-badge">Kotak-Only Statement Analyzer</span>
          <h1 className="hero-title">
            Kotak Finance <br />
            <span className="gradient-text">Analyzer</span>
          </h1>
          <p className="hero-subtitle">
            Upload your Kotak statement and instantly view a clean dashboard with trends,
            categories, and actionable insights.
          </p>

          <div className="server-panel">
            <div className="server-panel-header">
              <span className={`status-dot-large ${statusInfo.className}`} />
              <strong>{statusInfo.text}</strong>
            </div>
            <p>{statusInfo.helper}</p>
          </div>

          <div className="hero-actions">
            <button className="btn-primary" onClick={handleGetStarted}>
              Get Started
            </button>
            <button className="btn-secondary" onClick={handleTryDemo}>
              Try Demo
            </button>
            <a href="/mysampleacc.pdf" download="demo_kotak_statement.pdf" className="btn-secondary link-btn">
              Download Sample
            </a>
          </div>
          <div className="quick-points">
            <span>✓ Kotak only</span>
            <span>✓ Live status</span>
            <span>✓ Simple flow</span>
          </div>
        </section>
        
        <section className="hero-visual-right">
          <div className="visual-composition">
            <div className="floating-card card-1">
              <div className="card-icon trend-icon">📈</div>
              <div className="card-text">
                <h4>Smart Trends</h4>
                <p>Visualize spending habits over time</p>
              </div>
            </div>
            <div className="floating-card card-2">
              <div className="card-icon categorize-icon">🗂️</div>
              <div className="card-text">
                <h4>Auto-Categorization</h4>
                <p>AI groups your transactions instantly</p>
              </div>
            </div>
            <div className="floating-card card-3">
              <div className="card-icon security-icon">🔒</div>
              <div className="card-text">
                <h4>100% Secure</h4>
                <p>No data stored on our servers</p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <section className="flow-section">
        <h2>Steps to access system</h2>
        <div className="flow-chart">
          <article className="flow-step">
            <span className="flow-number">1</span>
            <h3>Check Server</h3>
            <p>Confirm status from the live indicator.</p>
          </article>
          <span className="flow-arrow">→</span>
          <article className="flow-step">
            <span className="flow-number">2</span>
            <h3>Upload Statement</h3>
            <p>Use your Kotak PDF/CSV file.</p>
          </article>
          <span className="flow-arrow">→</span>
          <article className="flow-step">
            <span className="flow-number">3</span>
            <h3>Analyze</h3>
            <p>Process transactions securely.</p>
          </article>
          <span className="flow-arrow">→</span>
          <article className="flow-step">
            <span className="flow-number">4</span>
            <h3>View Dashboard</h3>
            <p>See charts, insights, and trends.</p>
          </article>
        </div>
      </section>
    </div>
  );
};

export default WelcomePage;
