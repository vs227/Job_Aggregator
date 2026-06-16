import React, { useState, useEffect, useRef } from 'react';
import toast from 'react-hot-toast';
import { 
  MdCloudUpload, 
  MdContactPage, 
  MdCheckCircle, 
  MdCancel, 
  MdInfo,
  MdAutorenew,
  MdBookmark,
  MdBookmarkBorder
} from 'react-icons/md';
import { IoIosPaperPlane } from 'react-icons/io';
import './ResumePage.css';
import { uploadResume, chatWithResume, saveJob, unsaveJob, fetchSavedJobs } from '../services/api';

function ResumePage() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'ai',
      text: 'Hello! I am HirePulse Pivot AI. Upload your resume on the right, and I will recommend matching jobs and help you optimize your profile.'
    }
  ]);
  const [inputVal, setInputVal] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef(null);

  const [file, setFile] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [showAnalysis, setShowAnalysis] = useState(false);
  const [fillHeight, setFillHeight] = useState('0%');
  const [analysisData, setAnalysisData] = useState(null);
  const [savedJobIds, setSavedJobIds] = useState(new Set());

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  useEffect(() => {
    if (showAnalysis) {
      const timer = setTimeout(() => {
        setFillHeight(`${analysisData?.match_score || 87}%`);
      }, 100);
      return () => clearTimeout(timer);
    } else {
      setFillHeight('0%');
    }
  }, [showAnalysis, analysisData]);

  useEffect(() => {
    async function loadSavedJobs() {
      try {
        const data = await fetchSavedJobs();
        const ids = new Set(data.map(j => j.id));
        setSavedJobIds(ids);
      } catch (err) {
        console.error("Failed to load saved jobs", err);
      }
    }
    loadSavedJobs();
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
        toast.success('Job removed from bookmarks!');
      } else {
        await saveJob(jobId);
        setSavedJobIds(prev => {
          const next = new Set(prev);
          next.add(jobId);
          return next;
        });
        toast.success('Job bookmarked successfully!');
      }
    } catch (err) {
      toast.error(err.message || 'Failed to update bookmark');
    }
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

    setMessages(prev => [...prev, newMsg]);
    setInputVal('');
    setIsTyping(true);

    try {
      const data = await chatWithResume(userMsgVal);
      const aiReply = {
        id: Date.now() + 1,
        sender: 'ai',
        text: data.response,
        jobs: data.matches || []
      };
      setMessages(prev => [...prev, aiReply]);
    } catch (err) {
      const errorReply = {
        id: Date.now() + 1,
        sender: 'ai',
        text: `Error: ${err.message || 'Failed to communicate with AI'}`
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
      } catch (err) {
        setAnalyzing(false);
        toast.error(err.message || 'Failed to process resume');
      }
    }
  }

  return (
    <div className="resume-page-layout fade-in">

        <div className="resume-upload-section">
          <h2 className="section-title">Resume Analyzer & Matcher</h2>

          {!showAnalysis && !analyzing && (
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

          {analyzing && (
            <div className="resume-loader-container">
              <MdAutorenew className="resume-loader-icon" />
              <span className="resume-loader-text">Parsing skills & calculating match score...</span>
            </div>
          )}

          {showAnalysis && !analyzing && (
            <div className="analysis-results-card">
              <div className="analysis-header">
                <div className="analysis-header-info">
                  <h3>Analysis Complete</h3>
                  <p>Matches evaluated against 125 active job listings</p>
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

                <div className="water-container">
                  <div 
                    className="water-fill" 
                    style={{ height: fillHeight }}
                  />
                </div>
              </div>

              <div className="analysis-skills-section">
                <span className="skills-title">Matched Skills</span>
                <div className="skills-grid">
                  {analysisData?.matched_skills && analysisData.matched_skills.length > 0 ? (
                    analysisData.matched_skills.map((skill, idx) => (
                      <span key={idx} className="skills-badge match"><MdCheckCircle /> {skill}</span>
                    ))
                  ) : (
                    <span className="skills-badge match" style={{ opacity: 0.6 }}><MdInfo /> No matched skills found</span>
                  )}
                </div>
              </div>

              <div className="analysis-skills-section">
                <span className="skills-title">Missing / Demanded Skills</span>
                <div className="skills-grid">
                  {analysisData?.missing_skills && analysisData.missing_skills.length > 0 ? (
                    analysisData.missing_skills.map((skill, idx) => (
                      <span key={idx} className="skills-badge missing"><MdCancel /> {skill}</span>
                    ))
                  ) : (
                    <span className="skills-badge missing" style={{ opacity: 0.6 }}><MdInfo /> None identified</span>
                  )}
                </div>
              </div>

              <div className="analysis-skills-section">
                <span className="skills-title">AI Optimization Recommendation</span>
                <div className="analysis-feedback-section">
                  <p className="analysis-feedback-text">
                    {analysisData?.recommendation || "Your resume has been processed. Ask the AI chat for personalized optimization steps."}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="animated-divider"></div>

        <div className="resume-chat-section">
          <div className="chat-header">
            <span className="chat-header-title">HirePulse Pivot AI</span>
          </div>

          <div className="chat-history">
            {messages.map((msg) => (
              <div key={msg.id} className={`chat-message ${msg.sender}`}>
                <div className="chat-message-text">
                  {msg.text.split('\n').map((line, idx) => (
                    <React.Fragment key={idx}>
                      {line}
                      <br />
                    </React.Fragment>
                  ))}
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
                            {job.salary && <span> • ₹{Number(job.salary).toLocaleString()}</span>}
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
            {isTyping && (
              <div className="chat-message ai">
                <div className="chat-typing-indicator">
                  <span></span><span></span><span></span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <form className="chat-input-container" onSubmit={handleSendMessage}>
            <input
              type="text"
              className="chat-input"
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              placeholder="Ask AI for job recommendations..."
            />
            <button type="submit" className="chat-send-btn" disabled={isTyping}>
              <IoIosPaperPlane className="plane-icon" />
            </button>
          </form>
        </div>

      </div>
  );
}

export default ResumePage;
