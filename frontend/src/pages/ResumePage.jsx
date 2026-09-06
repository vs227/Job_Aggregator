import React, { useState, useEffect, useRef } from 'react';
import toast from 'react-hot-toast';
import { 
  MdCloudUpload, 
  MdCheckCircle, 
  MdInfo,
  MdAutorenew,
  MdBookmark,
  MdBookmarkBorder,
  MdDeleteSweep,
  MdAutoAwesome,
  MdChat,
  MdDescription
} from 'react-icons/md';
import { IoIosPaperPlane } from 'react-icons/io';
import './ResumePage.css';
import { uploadResume, chatWithResume, saveJob, unsaveJob, fetchSavedJobs, fetchResumeAnalysis } from '../services/api';

const CHAT_STORAGE_KEY = 'hirepulse_chat_history_v1';

function ResumePage() {
  const [messages, setMessages] = useState(() => {
    try {
      const saved = localStorage.getItem(CHAT_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          return parsed;
        }
      }
    } catch (e) {
      console.error("Failed to load chat history from localStorage", e);
    }
    return [
      {
        id: 1,
        sender: 'ai',
        text: 'Hello! I am HirePulse Pivot AI. Upload your resume on the left, and I will recommend matching jobs and help you optimize your profile.'
      }
    ];
  });
  const [inputVal, setInputVal] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef(null);

  const [file, setFile] = useState(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [showAnalysis, setShowAnalysis] = useState(false);
  const [analysisData, setAnalysisData] = useState(null);
  const [savedJobIds, setSavedJobIds] = useState(new Set());
  const [remainingTokens, setRemainingTokens] = useState(5000);
  const [mobileTab, setMobileTab] = useState('chat'); // 'upload' or 'chat'

  useEffect(() => {
    try {
      const cleanMessages = messages.filter((m) => !m.typing);
      if (cleanMessages.length > 0) {
        localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(cleanMessages));
      }
    } catch (e) {
      console.error("Failed to save chat history to localStorage", e);
    }
  }, [messages]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping, mobileTab]);

  useEffect(() => {
    async function loadInitialData() {
      try {
        const data = await fetchSavedJobs();
        const ids = new Set(data.map(j => j.id));
        setSavedJobIds(ids);
      } catch (err) {
        console.error("Failed to load saved jobs", err);
      }
      try {
        const resumeRes = await fetchResumeAnalysis();
        if (resumeRes && resumeRes.has_resume) {
          setAnalysisData(resumeRes.analysis || null);
          setShowAnalysis(true);
        }
        if (resumeRes && typeof resumeRes.remaining_tokens === 'number') {
          setRemainingTokens(resumeRes.remaining_tokens);
        }
      } catch (err) {
        console.log("No previous resume analysis found for user.");
      } finally {
        setInitialLoading(false);
      }
    }
    loadInitialData();
  }, []);

  async function handleSaveToggle(jobId) {
    const isCurrentlySaved = savedJobIds.has(jobId);
    try {
      if (isCurrentlySaved) {
        await unsaveJob(jobId);
        setSavedJobIds(prev => {
          const next = new Set(prev);
          next.delete(jobId);
          return next;
        });
        toast.success('Job removed from saved list');
      } else {
        await saveJob(jobId);
        setSavedJobIds(prev => new Set(prev).add(jobId));
        toast.success('Job saved!');
      }
    } catch (err) {
      toast.error(err.message || 'Action failed');
    }
  }

  // Fast Typewriter animation for incoming AI response
  function typeTextFast(fullText, msgId, jobs = []) {
    return new Promise((resolve) => {
      let index = 0;
      const length = fullText.length;
      
      const interval = setInterval(() => {
        index += Math.ceil(length / 25);
        if (index >= length) {
          index = length;
          clearInterval(interval);
          setMessages(prev => prev.map(m => {
            if (m.id === msgId) {
              return { ...m, text: fullText, typing: false, jobs };
            }
            return m;
          }));
          resolve();
        } else {
          const currentChunk = fullText.slice(0, index);
          setMessages(prev => prev.map(m => {
            if (m.id === msgId) {
              return { ...m, text: currentChunk, typing: true, jobs: [] };
            }
            return m;
          }));
        }
      }, 20);
    });
  }

  function renderFormattedMessage(text) {
    if (!text) return null;
    const lines = text.split('\n');
    return lines.map((line, lineIdx) => {
      const parts = line.split(/(\*\*.*?\*\*)/g);
      const formattedLine = parts.map((part, partIdx) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={partIdx}>{part.slice(2, -2)}</strong>;
        }
        return part;
      });

      if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
        return (
          <li key={lineIdx} style={{ marginLeft: '16px', marginBottom: '4px' }}>
            {formattedLine.slice(1)}
          </li>
        );
      }
      return (
        <p key={lineIdx} style={{ marginBottom: lineIdx === lines.length - 1 ? 0 : '8px' }}>
          {formattedLine}
        </p>
      );
    });
  }

  async function handleSendMessage(e) {
    e.preventDefault();
    if (!inputVal.trim() || isTyping) return;

    const userMsgVal = inputVal;
    const newMsg = {
      id: Date.now(),
      sender: 'user',
      text: userMsgVal
    };

    const aiMsgId = Date.now() + 1;
    setMessages(prev => [...prev, newMsg]);
    setInputVal('');
    setIsTyping(true);

    const recentHistory = messages
      .filter((m) => !m.typing && m.text)
      .slice(-3)
      .map((m) => ({ sender: m.sender, text: m.text }));

    try {
      const data = await chatWithResume(userMsgVal, recentHistory);
      const fullText = data.response || 'No response.';
      const jobs = data.matches || [];
      if (typeof data.remaining_tokens === 'number') {
        setRemainingTokens(data.remaining_tokens);
      }

      setMessages(prev => [
        ...prev,
        {
          id: aiMsgId,
          sender: 'ai',
          text: '',
          typing: true,
          jobs: []
        }
      ]);

      await typeTextFast(fullText, aiMsgId, jobs);
    } catch (err) {
      toast.error(err.message || 'Rate limit reached. Please try again later.');
      const errorReply = {
        id: aiMsgId,
        sender: 'ai',
        text: `Rate Limit Notice: ${err.message || 'You have reached the query rate limit. Please wait before asking another question.'}`
      };
      setMessages(prev => [...prev, errorReply]);
    } finally {
      setIsTyping(false);
    }
  }

  async function handleFileChange(e) {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      setFile(selectedFile);
      setAnalyzing(true);
      setShowAnalysis(false);

      try {
        const responseData = await uploadResume(selectedFile);
        setAnalysisData(responseData.analysis || null);
        setAnalyzing(false);
        setShowAnalysis(true);
        toast.success('Resume analyzed successfully!');
        // Switch to AI chat tab on mobile after successful analysis
        setMobileTab('chat');
      } catch (err) {
        setAnalyzing(false);
        toast.error(err.message || 'Failed to process resume');
      }
    }
  }

  return (
    <div className="resume-page-wrapper fade-in">
      {/* MOBILE SEGMENTED TAB BAR (< 768px) */}
      <div className="resume-mobile-tab-bar">
        <button 
          className={`resume-tab-btn ${mobileTab === 'upload' ? 'active' : ''}`}
          onClick={() => setMobileTab('upload')}
        >
          <MdDescription /> Resume Upload
        </button>
        <button 
          className={`resume-tab-btn ${mobileTab === 'chat' ? 'active' : ''}`}
          onClick={() => setMobileTab('chat')}
        >
          <MdChat /> AI Assistant
        </button>
      </div>

      <div className="resume-page-layout">

        {/* LEFT COLUMN: RESUME UPLOADER & ANALYSIS */}
        <div className={`resume-upload-section ${mobileTab === 'upload' ? 'show-mobile' : 'hide-mobile'}`}>
          {initialLoading && (
            <div className="resume-loader-container">
              <MdAutorenew className="resume-loader-icon" />
              <span className="resume-loader-text">Restoring profile analysis...</span>
            </div>
          )}

          {!initialLoading && !showAnalysis && !analyzing && (
            <label className="upload-dropzone">
              <MdCloudUpload className="upload-icon" />
              <span className="upload-text-main">
                {file ? file.name : 'Upload your resume'}
              </span>
              <span className="upload-text-sub">
                Supports PDF, DOCX up to 10MB
              </span>
              <input
                type="file"
                accept=".pdf,.doc,.docx"
                onChange={handleFileChange}
                style={{ display: 'none' }}
                disabled={analyzing}
              />
            </label>
          )}

          {!initialLoading && analyzing && (
            <div className="resume-loader-container">
              <MdAutorenew className="resume-loader-icon" />
              <span className="resume-loader-text">Parsing skills & calculating vector embeddings...</span>
            </div>
          )}

          {!initialLoading && showAnalysis && !analyzing && (
            <div className="analysis-results-card">
              <div className="analysis-header">
                <div className="analysis-header-info">
                  <h3>Analysis Complete</h3>
                </div>
                <button 
                  className="reupload-btn" 
                  onClick={() => { 
                    setFile(null); 
                    setShowAnalysis(false); 
                    setAnalysisData(null);
                  }}
                >
                  <MdCloudUpload /> Upload New
                </button>
              </div>

              <div className="analysis-skills-section">
                <span className="skills-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <MdAutoAwesome className="ai-sparkle-icon" /> AI Optimization Recommendation
                </span>
                <div className="analysis-feedback-section">
                  <p className="analysis-feedback-text">
                    {analysisData?.recommendation || "Your resume has been processed. Ask the AI chat for personalized optimization steps."}
                  </p>
                </div>
              </div>

              <div className="analysis-skills-section">
                <span className="skills-title">Your Skills</span>
                <div className="skills-grid">
                  {((analysisData?.extracted_skills || analysisData?.matched_skills) && (analysisData?.extracted_skills || analysisData?.matched_skills).length > 0) ? (
                    (analysisData?.extracted_skills || analysisData?.matched_skills).map((skill, idx) => (
                      <span key={idx} className="skills-badge match">{skill}</span>
                    ))
                  ) : (
                    <span className="skills-badge match" style={{ opacity: 0.6 }}><MdInfo /> No skills extracted</span>
                  )}
                </div>
              </div>

              <button 
                className="mobile-switch-to-chat-btn"
                onClick={() => setMobileTab('chat')}
              >
                <MdChat /> Open AI Chat Assistant
              </button>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: AI CHAT ASSISTANT */}
        <div className={`resume-chat-section ${mobileTab === 'chat' ? 'show-mobile' : 'hide-mobile'}`}>
          <div className="chat-header">
            <div className="chat-header-info">
              <span className="chat-header-title">HirePulse Pivot AI</span>
              <span className="chat-limit-badge" title="Strict Rate Limit: 5,000 Tokens per 30 Minute Window">
                {remainingTokens.toLocaleString()} / 5,000 Tokens (30m Window)
              </span>
            </div>
            <button 
              className="btn-ghost clear-chat-btn" 
              onClick={() => {
                localStorage.removeItem(CHAT_STORAGE_KEY);
                setMessages([{
                  id: Date.now(),
                  sender: 'ai',
                  text: 'Hello! I am HirePulse Pivot AI. Upload your resume on the left, and I will recommend matching jobs and help you optimize your profile.'
                }]);
              }}
            >
              <MdDeleteSweep style={{ fontSize: '1rem' }} /> Clear
            </button>
          </div>

          <div className="chat-history">
            {messages.map((msg) => (
              <div key={msg.id} className={`chat-message ${msg.sender}`}>
                <div className="chat-message-text">
                  {msg.sender === 'ai' ? renderFormattedMessage(msg.text) : msg.text}
                </div>
                {msg.jobs && msg.jobs.length > 0 && (
                  <div className="chat-jobs-container">
                    {msg.jobs.map((job) => (
                      <div key={job.id} className="chat-job-card-inner">
                        <div className="chat-job-card-header">
                          <div className="chat-job-title-container">
                            <h4 className="chat-job-card-title">{job.title}</h4>
                            <span className="chat-job-card-company">{job.company}</span>
                          </div>
                          <button
                            className={`chat-job-card-save-btn ${savedJobIds.has(job.id) ? 'saved' : ''}`}
                            onClick={() => handleSaveToggle(job.id)}
                          >
                            {savedJobIds.has(job.id) ? <MdBookmark /> : <MdBookmarkBorder />}
                          </button>
                        </div>
                        {job.location && (
                          <div className="chat-job-card-meta">
                            <span>{job.location}</span>
                            {job.salary && <span> | INR {Number(job.salary).toLocaleString()}</span>}
                          </div>
                        )}
                        <p className="chat-job-card-reason">{job.match_reason}</p>
                        <div className="chat-job-card-actions">
                          {job.job_url && job.job_url !== "#" && (
                            <a href={job.job_url} target="_blank" rel="noopener noreferrer" className="chat-apply-btn">
                              Apply Now
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {isTyping && !messages.some(m => m.sender === 'ai' && m.typing) && (
              <div className="chat-message ai">
                <div className="chat-typing-indicator">
                  <span></span><span></span><span></span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <form className="chat-input-container" onSubmit={handleSendMessage}>
            <div className="chat-input-wrapper">
              <MdAutoAwesome className="chat-input-ai-icon ai-sparkle-icon" />
              <input
                type="text"
                className="chat-input"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                placeholder="Ask AI for job recommendations..."
              />
            </div>
            <button type="submit" className="chat-send-btn" disabled={isTyping}>
              <IoIosPaperPlane className="plane-icon" />
            </button>
          </form>
        </div>

      </div>
    </div>
  );
}

export default ResumePage;
