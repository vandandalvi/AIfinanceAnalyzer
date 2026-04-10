import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { API_ENDPOINTS } from '../config/api';
import './UploadPage.css';

function UploadPage() {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [selectedBank, setSelectedBank] = useState('');
  const [detectedBank, setDetectedBank] = useState(null);
  const [fileStructure, setFileStructure] = useState(null);
  const [uploadTimer, setUploadTimer] = useState(0);
  const navigate = useNavigate();
  const location = useLocation();

  // Countdown timer for long requests (waking up server)
  useEffect(() => {
    let timer;
    if (uploading) {
      timer = setInterval(() => {
        setUploadTimer(prev => prev + 1);
      }, 1000);
    } else {
      setUploadTimer(0);
    }
    return () => clearInterval(timer);
  }, [uploading]);

  // Handle demo file from welcome page
  useEffect(() => {
    if (location.state?.demoFile) {
      handleFileSelect(location.state.demoFile);
      if (location.state.bankType) {
        setSelectedBank(location.state.bankType);
      }
    }
  }, [location.state]);

  // Detect bank from CSV structure
  const detectBankFromCSV = async (file) => {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target.result;
        const firstLine = text.split('\n')[0].toLowerCase();
        
        // Check for specific column patterns
        if (firstLine.includes('txn date') && 
            firstLine.includes('value date') && 
            firstLine.includes('ref no./cheque no.')) {
          resolve({ bank: 'sbi', headers: firstLine });
        } else if (firstLine.includes('tran date') && 
                   firstLine.includes('chq/ref number') && 
                   firstLine.includes('withdrawal amt') && 
                   firstLine.includes('deposit amt')) {
          resolve({ bank: 'axis', headers: firstLine });
        } else if (firstLine.includes('date') && 
                   firstLine.includes('particulars') && 
                   !firstLine.includes('tran date') && 
                   !firstLine.includes('txn date')) {
          resolve({ bank: 'kotak', headers: firstLine });
        } else {
          resolve({ bank: null, headers: firstLine });
        }
      };
      reader.readAsText(file);
    });
  };

  const handleFileSelect = async (selectedFile) => {
    if (!selectedFile) return;

    // Validate file type
    const isCsv = selectedFile.type === 'text/csv' || selectedFile.name.toLowerCase().endsWith('.csv');
    const isPdf = selectedFile.type === 'application/pdf' || selectedFile.name.toLowerCase().endsWith('.pdf');   

    if (!isCsv && !isPdf) {
      alert("Please upload a valid .csv or .pdf file.");
      return;
    }

    setFile(selectedFile);
    setSelectedBank('kotak');
    setDetectedBank('kotak');
  };

  const validateBankSelection = () => {
    if (!file) {
      return { valid: false, message: 'Please select a file.' };  
    }
    return { valid: true };
  };

  const handleUpload = async () => {
    const validation = validateBankSelection();
    
    if (!validation.valid) {
      if (validation.critical) {
        // Critical error - don't allow to proceed
        alert(validation.message);
        return;
      } else if (validation.warning) {
        // Show confirmation dialog for warning
        const confirmed = window.confirm(validation.message);
        if (!confirmed) {
          return;
        }
      } else {
        alert(validation.message);
        return;
      }
    }
    
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('bank', selectedBank);

    try {
      const response = await axios.post(API_ENDPOINTS.upload, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      console.log('Upload success:', response.data);
      // Clear all cached insights/dashboard snapshots so latest upload is always reflected
      [
        'aiInsights',
        'aiInsightsV2',
        'aiInsightsV3',
        'dashboardDataV2',
        'dashboardDataV3'
      ].forEach((k) => sessionStorage.removeItem(k));
      // Add a small delay to ensure backend has processed the file
      setTimeout(() => {
        navigate('/dashboard', { state: { forceRefresh: true, uploadedAt: Date.now() } });
      }, 500);
    } catch (error) {
      console.error('Upload error:', error);
      console.error('Error response:', error.response?.data);
      console.error('Error status:', error.response?.status);
      
      let errorMessage = 'Upload failed. ';
      if (error.response?.status === 404) {
        errorMessage += 'Backend not found. Please check if the backend is running.';
      } else if (error.response?.status === 500) {
        errorMessage += 'Server error: ' + (error.response?.data?.error || 'Internal server error');
      } else if (error.code === 'ERR_NETWORK') {
        errorMessage += 'Cannot connect to backend. Please check your internet connection.';
      } else {
        errorMessage += error.response?.data?.error || error.message || 'Please try again.';
      }
      
      alert(errorMessage);
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && (droppedFile.type === 'text/csv' || droppedFile.type === 'application/pdf' || droppedFile.name.endsWith('.pdf'))) {
      handleFileSelect(droppedFile);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  return (
    <div className="upload-page">
      <div className="upload-container">
        <div className="upload-content">
        <div style={{ textAlign: 'center', marginBottom: '30px' }}>
          <img src="/kotak_logo.svg" alt="Kotak Mahindra Bank Logo" style={{ maxWidth: '220px' }} />
        </div>
        <div className="upload-header">
          <button onClick={() => navigate('/')} className="back-button">
            ← Back
          </button>
          <h1 className="upload-title">Upload Your Bank Statement</h1>
          <p className="upload-subtitle">Get started by uploading your bank statement file.</p>
        </div>

        {/* Step Indicator */}
        <div className="steps-indicator">
          <div className={`step-item ${file ? 'completed' : 'active'}`}>
            <div className="step-circle">1</div>
            <span>Upload File</span>
          </div>
          <div className="step-line"></div>
          <div className={`step-item ${selectedBank ? 'completed' : file ? 'active' : ''}`}>
            <div className="step-circle">2</div>
            <span>Select Bank</span>
          </div>
          <div className={`step-item ${file && selectedBank ? 'active' : ''}`}>
            <div className="step-circle">3</div>
            <span>Analyze</span>
          </div>
        </div>

        <div className="upload-box">
          <div
            className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            <svg width="80" height="80" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            
            {file ? (
              <div>
                <p className="file-selected">✓ File Selected</p>
                <p style={{color: '#666', marginTop: '10px'}}>{file.name}</p>
              </div>
            ) : (
              <div>
                <p style={{color: '#666', marginBottom: '20px', fontSize: '1.1rem'}}>
                  Drag and drop your file (.csv or .pdf) here, or
                </p>
                <div style={{ position: 'relative', display: 'inline-block' }}>
                  <button className="browse-button" style={{ pointerEvents: 'none' }}>
                    Browse Files
                  </button>
                  <input
                    type="file"
                    accept="*/*"
                    onChange={(e) => handleFileSelect(e.target.files[0])}
                    title="Browse Files"
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: '100%',
                      opacity: 0,
                      cursor: 'pointer'
                    }}
                  />
                </div>
                <div style={{ marginTop: '30px', borderTop: '1px solid #e2e8f0', paddingTop: '20px', position: 'relative', zIndex: 10 }}>
                  <p style={{ color: '#64748b', fontSize: '0.95rem', marginBottom: '10px' }}>Don't have a statement handy?</p>
                  <a href="/mysampleacc.pdf" download="demo_kotak_statement.pdf" style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', color: '#ED1C24', textDecoration: 'none', fontWeight: '600', fontSize: '0.95rem', padding: '10px 20px', backgroundColor: '#fff1f2', borderRadius: '8px', border: '1px solid #fecdd3' }}>
                    <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Download Sample PDF
                  </a>
                </div>
              </div>
            )}
          </div>

          <div className="bank-selection" style={{ display: 'none' }}>
            <h3>Select Your Bank</h3>
            <div className="bank-grid">
              {[
                { id: 'kotak', name: 'Kotak Mahindra Bank', logo: '🏦', format: 'Kotak CSV Format' }
              ].map((bank) => (
                <button
                  key={bank.id}
                  onClick={() => setSelectedBank(bank.id)}
                  className={`bank-button ${selectedBank === bank.id ? 'selected' : ''}`}
                >
                  <div className="bank-icon">{bank.logo}</div>
                  <div className="bank-name">{bank.name}</div>
                  <div className="bank-format">{bank.format}</div>
                </button>
              ))}
            </div>
          </div>

          {file && selectedBank && (
            <div style={{ width: '100%' }}>
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="upload-button"
              >
                {uploading ? (
                  <span style={{display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                    <span className="spinner"></span>
                    Uploading...
                  </span>
                ) : (
                  'Analyze My Finances'
                )}
              </button>

              {uploading && uploadTimer > 3 && (
                <div style={{ marginTop: '20px', color: '#047857', fontSize: '0.95rem', textAlign: 'center', padding: '15px', backgroundColor: '#ecfdf5', borderRadius: '10px', border: '1px solid #34d399', boxShadow: '0 4px 10px rgba(0, 0, 0, 0.05)' }}>
                  <p style={{ margin: '0 0 8px', fontWeight: '700', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                    <span className="spinner" style={{ width: '16px', height: '16px', borderWidth: '2px', borderTopColor: '#047857' }}></span>
                    Waking up secure server...
                  </p>
                  <p style={{ margin: 0, fontSize: '0.9rem', color: '#065f46' }}>
                    Free servers take a moment to start. <br/> Estimated wait time: <strong style={{color: '#dc2626', fontSize: '1.05rem'}}>{Math.max(0, 50 - uploadTimer)}s</strong>
                  </p>
                </div>
              )}
            </div>
          )}

          <div className="features">
            <div className="feature-item">Upload your Kotak bank statement</div>
            <div className="feature-item">Secure and private analysis</div>
            <div className="feature-item">Get AI-powered financial insights</div>
          </div>
        </div>
      </div>
    </div>
    </div>
  );
}

export default UploadPage;