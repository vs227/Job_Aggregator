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
  MdAutoAwesome
} from 'react-icons/md';
import { IoIosPaperPlane } from 'react-icons/io';
import './ResumePage.css';
import { uploadResume, chatWithResume, saveJob, unsaveJob, fetchSavedJobs, fetchResumeAnalysis } from '../services/api';

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
  const [initialLoading, setInitialLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [showAnalysis, setShowAnalysis] = useState(false);
  const [analysisData, setAnalysisData] = useState(null);
  const [savedJobIds, setSavedJobIds] = useState(new Set());
  const [remainingQueries, setRemainingQueries] = useState(30);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

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
        if (resumeRes && typeof resumeRes.remaining_daily === 'number') {
          setRemainingQueries(resumeRes.remaining_daily);
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

  // Beacon High-Speed Live Typewriter Animation
  const typeTextFast = async (fullText, messageId, jobs = []) => {
    if (!fullText) return;
    let idx = 0;
    const totalLen = fullText.length;
    const chunkSize = Math.max(16, Math.ceil(totalLen / 15));

    while (idx < totalLen) {
      idx = Math.min(totalLen, idx + chunkSize);
      const currentText = fullText.slice(0, idx);

      setMessages(prev =>
        prev.map(m =>
          m.id === messageId
            ? { ...m, text: currentText, typing: idx < totalLen, jobs: idx >= totalLen ? jobs : [] }
            : m
        )
      );
      await new Promise(res => setTimeout(res, 6));
    }

    setMessages(prev =>
      prev.map(m =>
        m.id === messageId ? { ...m, text: fullText, typing: false, jobs } : m
      )
    );
  };

  // Formatter for AI output: renders bold headers and styled bullet points (Beacon RAG standard)
  function renderFormattedMessage(text) {
    if (!text) return null;

    const lines = text.split('\n');
    return lines.map((line, idx) => {
      const cleanLine = line.trim();
      if (!cleanLine) return <div key={idx} style={{ height: '4px' }} />;

      const bulletMatch = cleanLine.match(/^[*\-]\s+(.*)/);
      const isBullet = Boolean(bulletMatch);
      const lineContent = isBullet ? bulletMatch[1] : cleanLine;

      const parts = lineContent.split(/(\*\*.*?\*\*)/g);
      const formattedContent = parts.map((part, pIdx) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return (
            <strong key={pIdx} style={{ color: 'var(--text-primary)', fontWeight: 700 }}>
              {part.slice(2, -2)}
            </strong>
          );
        }
        return part;
      });

      if (isBullet) {
        return (
          <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', margin: '4px 0 4px 4px' }}>
            <span style={{ opacity: 0.6, fontSize: '0.85rem', lineHeight: '1.4' }}>-</span>
            <span style={{ flex: 1, lineHeight: '1.45' }}>{formattedContent}</span>
          </div>
        );
      }

      return (
        <div key={idx} style={{ margin: '3px 0', lineHeight: '1.45' }}>
          {formattedContent}
        </div>
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

    try {
      const data = await chatWithResume(userMsgVal);
      const fullText = data.response || 'No response.';
      const jobs = data.matches || [];
      if (typeof data.remaining_daily === 'number') {
        setRemainingQueries(data.remaining_daily);
      }

      // Add typing placeholder message
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

      // Trigger high-speed typewriter output animation
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
      } catch (err) {
        setAnalyzing(false);
        toast.error(err.message || 'Failed to process resume');
      }
    }
  }

  return (
    <div className="resume-page-layout fade-in">

        <div className="resume-upload-section">
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
              <div className="analysis-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div className="analysis-header-info">
                  <h3>Analysis Complete</h3>
                </div>
                <button 
                  className="reupload-btn" 
                  style={{ marginTop: 0 }}
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
            </div>
          )}

        </div>

        <div className="animated-divider"></div>

        <div className="resume-chat-section">
          <div className="chat-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span className="chat-header-title">HirePulse Pivot AI</span>
              <span className="chat-limit-badge" title="Daily AI Chat Query Quota">
                {remainingQueries}/30 Queries Left Today
              </span>
            </div>
            <button 
              className="btn-ghost" 
              style={{ padding: '6px 12px', fontSize: '0.8rem', gap: '6px', borderRadius: '8px' }}
              onClick={() => setMessages([{
                id: Date.now(),
                sender: 'ai',
                text: 'Hello! I am HirePulse Pivot AI. Upload your resume on the left, and I will recommend matching jobs and help you optimize your profile.'
              }])}
            >
              <MdDeleteSweep style={{ fontSize: '1rem' }} /> Clear Chat
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
