import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { MdSearch, MdOutlineSecurity, MdOutlineDns, MdOutlineHub, MdOutlineTrendingUp, MdOutlineSpeed } from 'react-icons/md';
import { useAuth } from '../context/AuthContext';
import './LandingPage.css';

const PREVIEW_JOBS = [
  { title: 'Frontend Lead', company: 'DevPulse', source: 'Internshala', loc: 'Bengaluru', type: 'Full-time', match: '98%', salary: '₹12 - 18 LPA' },
  { title: 'Senior React Dev', company: 'Himalayas LLC', source: 'Remotive', loc: 'Remote', type: 'Contract', match: '95%', salary: '$90k - 120k' },
  { title: 'ML Researcher', company: 'MindFlow AI', source: 'Himalayas', loc: 'Remote', type: 'Full-time', match: '97%', salary: '$110k - 140k' },
  { title: 'Backend Developer', company: 'Alpha Corp', source: 'TimesJobs', loc: 'Mumbai', type: 'Full-time', match: '92%', salary: '₹10 - 15 LPA' },
  { title: 'Fullstack Dev', company: 'Bengaluru Tech', source: 'Internshala', loc: 'Bengaluru', type: 'Part-time', match: '91%', salary: '₹8 - 12 LPA' }
];

function LandingPage() {
  const { isAuthenticated } = useAuth();
  const [filter, setFilter] = useState('All');
  const [typingText, setTypingText] = useState('');
  const [isTyping, setIsTyping] = useState(true);

  // Simulated Typing effect in mock console search bar
  useEffect(() => {
    let index = 0;
    const query = filter === 'All' ? 'Software Engineer' : `${filter} Developer`;
    setTypingText('');
    setIsTyping(true);

    const interval = setInterval(() => {
      if (index < query.length) {
        setTypingText((prev) => prev + query.charAt(index));
        index++;
      } else {
        setIsTyping(false);
        clearInterval(interval);
      }
    }, 80);

    return () => clearInterval(interval);
  }, [filter]);

  const filteredJobs = PREVIEW_JOBS.filter(job => {
    if (filter === 'All') return true;
    if (filter === 'Remote') return job.loc === 'Remote';
    if (filter === 'Bengaluru') return job.loc === 'Bengaluru';
    return job.loc === filter;
  });

  return (
    <div className="landing-page">
      {/* 1. HERO & INTERACTIVE CONSOLE GRID */}
      <section className="hero-grid-section container">
        <div className="hero-left">
          <div className="landing-badge">
            <span className="badge-pulse"></span>
            <span>Live Aggregator Online</span>
          </div>
          <h1 className="hero-main-title">
            The Smart Way <br />
            To Hunt <span>Careers</span>
          </h1>
          <p className="hero-description">
            HumRes continuously aggregates, deduplicates, and filters active roles from multiple primary job platforms. Stop browsing ten tabs. Find your next role in one.
          </p>

          <div className="filter-shortcuts">
            <span className="shortcuts-label">Simulate Filter:</span>
            <button 
              className={`shortcut-btn ${filter === 'All' ? 'active' : ''}`}
              onClick={() => setFilter('All')}
            >
              All Jobs
            </button>
            <button 
              className={`shortcut-btn ${filter === 'Remote' ? 'active' : ''}`}
              onClick={() => setFilter('Remote')}
            >
              Remote Only
            </button>
            <button 
              className={`shortcut-btn ${filter === 'Bengaluru' ? 'active' : ''}`}
              onClick={() => setFilter('Bengaluru')}
            >
              Bengaluru
            </button>
          </div>

          <div className="hero-cta-buttons">
            {isAuthenticated ? (
              <Link to="/dashboard" className="btn-primary-glow">
                Go to Dashboard
              </Link>
            ) : (
              <>
                <Link to="/register" className="btn-primary-glow">
                  Get Started Free
                </Link>
                <Link to="/login" className="btn-secondary-outline">
                  Sign In
                </Link>
              </>
            )}
          </div>
        </div>

        <div className="hero-right">
          {/* Simulated Aggregator Dashboard Window */}
          <div className="mock-console glass">
            <div className="console-titlebar">
              <div className="console-dots">
                <span className="dot red"></span>
                <span className="dot yellow"></span>
                <span className="dot green"></span>
              </div>
              <div className="console-title">aggregator-stream-v1.log</div>
              <div className="console-engine-status">
                <span className="engine-status-dot"></span>
                <span>Active Scanner</span>
              </div>
            </div>

            <div className="console-search-bar">
              <MdSearch className="search-icon" />
              <div className="typing-container">
                <span>{typingText}</span>
                {isTyping && <span className="cursor-blink">|</span>}
              </div>
            </div>

            <div className="console-results">
              {filteredJobs.map((job, idx) => (
                <div key={idx} className="console-job-row glass slide-in-bottom" style={{ animationDelay: `${idx * 0.1}s` }}>
                  <div className="job-row-left">
                    <div className="row-title-block">
                      <h4 className="row-job-title">{job.title}</h4>
                      <span className="row-match-badge">{job.match} Match</span>
                    </div>
                    <p className="row-job-meta">
                      {job.company} • <strong>{job.loc}</strong> • <span className="row-salary">{job.salary}</span>
                    </p>
                  </div>
                  <div className="job-row-right">
                    <span className="source-pill" data-source={job.source.toLowerCase()}>
                      {job.source}
                    </span>
                    <span className="job-type-pill">{job.type}</span>
                  </div>
                </div>
              ))}
            </div>

            <div className="console-footer">
              <span>Found {filteredJobs.length} matches for current scanner</span>
              <span>Sorted by matching score</span>
            </div>
          </div>
        </div>
      </section>

      {/* 2. INFINITE TICKER MARQUEE */}
      <section className="marquee-section">
        <div className="marquee-wrapper">
          <div className="marquee-content">
            <span>AGGREGATING LIVE FROM:</span>
            <span>INTERNSHALA</span>
            <span className="marquee-dot">•</span>
            <span>TIMESJOBS</span>
            <span className="marquee-dot">•</span>
            <span>REMOTIVE</span>
            <span className="marquee-dot">•</span>
            <span>HIMALAYAS</span>
            <span className="marquee-dot">•</span>
            <span>DEDUPLICATED ON THE FLY</span>
            <span className="marquee-dot">•</span>
            <span>SECURE PROFILES</span>
            <span className="marquee-dot">•</span>
          </div>
          {/* Duplicate for infinite loop */}
          <div className="marquee-content" aria-hidden="true">
            <span>AGGREGATING LIVE FROM:</span>
            <span>INTERNSHALA</span>
            <span className="marquee-dot">•</span>
            <span>TIMESJOBS</span>
            <span className="marquee-dot">•</span>
            <span>REMOTIVE</span>
            <span className="marquee-dot">•</span>
            <span>HIMALAYAS</span>
            <span className="marquee-dot">•</span>
            <span>DEDUPLICATED ON THE FLY</span>
            <span className="marquee-dot">•</span>
            <span>SECURE PROFILES</span>
            <span className="marquee-dot">•</span>
          </div>
        </div>
      </section>

      {/* 3. DYNAMIC PROCESS TIMELINE */}
      <section className="workflow-section container">
        <div className="section-header-left">
          <span className="subtitle-tag">HOW HUMRES WORKS</span>
          <h2 className="section-main-title">Continuous Aggregation Pipeline</h2>
          <p className="section-desc-para">We automate the repetitive, tedious parts of job hunting, giving you clean data without duplicates.</p>
        </div>

        <div className="workflow-steps-layout">
          <div className="workflow-step-card glass">
            <div className="step-num-badge">01</div>
            <div className="step-icon-box">
              <MdOutlineDns />
            </div>
            <h3 className="step-title">Automated Scrapes</h3>
            <p className="step-text">Our backend executes cron-job scrapers targeting Internshala, TimesJobs, Himalayas, and Remotive every few hours.</p>
          </div>

          <div className="workflow-step-card glass">
            <div className="step-num-badge">02</div>
            <div className="step-icon-box">
              <MdOutlineHub />
            </div>
            <h3 className="step-title">Deduplication</h3>
            <p className="step-text">Smart hash algorithms analyze titles, descriptions, and locations to filter duplicate entries across platforms.</p>
          </div>

          <div className="workflow-step-card glass">
            <div className="step-num-badge">03</div>
            <div className="step-icon-box">
              <MdOutlineSecurity />
            </div>
            <h3 className="step-title">Match Alerts</h3>
            <p className="step-text">Specify keywords or filters; our notification engine monitors feeds and notifies you when a perfect match lands.</p>
          </div>
        </div>
      </section>

      {/* 4. PREMIUM CTA SECTION */}
      <section className="creative-cta-section container">
        <div className="cta-gradient-container glass">
          <div className="cta-left">
            <h2 className="cta-head-title">Ready To Level Up Your Hunt?</h2>
            <p className="cta-sub-text">Join thousands of engineers who track, filter, and alert job listings dynamically.</p>
          </div>
          <div className="cta-right">
            {isAuthenticated ? (
              <Link to="/dashboard" className="btn-cta-glow">
                Go to Dashboard
              </Link>
            ) : (
              <Link to="/register" className="btn-cta-glow">
                Create Free Account
              </Link>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

export default LandingPage;
