import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { 
  MdOutlineMail, 
  MdOutlineLock, 
  MdOutlinePersonOutline, 
  MdOutlineVisibility, 
  MdOutlineVisibilityOff,
  MdOutlineMarkEmailRead,
  MdOutlineKey,
  MdOutlineArrowBack
} from 'react-icons/md';
import { useAuth } from '../context/AuthContext';
import { sendRegisterOtp, verifyRegisterOtp, resendRegisterOtp } from '../services/api';
import './RegisterPage.css';
import './LoginPage.css';

function RegisterPage() {
  const [step, setStep] = useState('form'); // 'form' or 'otp'
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSendOtp(e) {
    e.preventDefault();
    if (!username || !email || !password) {
      toast.error('All fields are required');
      return;
    }
    setLoading(true);
    try {
      await sendRegisterOtp(username, email, password);
      toast.success(`Verification code sent to ${email}`);
      setStep('otp');
    } catch (err) {
      toast.error(err.message || 'Failed to send verification code');
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOtp(e) {
    e.preventDefault();
    if (!otp.trim()) {
      toast.error('Please enter the 6-digit verification code');
      return;
    }
    setLoading(true);
    try {
      const data = await verifyRegisterOtp(email, otp.trim(), username, password);
      if (data.access_token) {
        login(data.access_token);
        toast.success('Account verified successfully! Welcome to HirePulse.');
        navigate('/dashboard');
      } else {
        toast.success('Account verified successfully! Please sign in.');
        navigate('/login');
      }
    } catch (err) {
      toast.error(err.message || 'Invalid or expired verification code');
    } finally {
      setLoading(false);
    }
  }

  async function handleResendCode() {
    if (resending) return;
    setResending(true);
    try {
      await resendRegisterOtp(email);
      toast.success(`New verification code sent to ${email}`);
    } catch (err) {
      toast.error(err.message || 'Failed to resend verification code');
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="register-page auth-page">
      <div className="auth-card-glow-bg"></div>
      <div className="auth-layout-wrapper fade-in">
        <div className="auth-floating-info">
          <span className="auth-info-tag">START YOUR JOURNEY</span>
          <h2 className="auth-info-title">Discover Opportunities Suited For You</h2>
          <p className="auth-info-subtitle">
            Join HirePulse to track listings, manage application statuses, and automate alerts across the web.
          </p>
          <div className="auth-feature-list">
            <div className="auth-feature-item">
              <span className="feature-dot"></span>
              <span>Real-time email OTP verification</span>
            </div>
            <div className="auth-feature-item">
              <span className="feature-dot"></span>
              <span>Filter by tags, companies, and roles</span>
            </div>
            <div className="auth-feature-item">
              <span className="feature-dot"></span>
              <span>Secure AI career optimization dashboard</span>
            </div>
          </div>
        </div>

        <div className="auth-card">
          {step === 'form' ? (
            <>
              <div className="auth-header">
                <h1 className="auth-title">Create Account</h1>
                <p className="auth-subtitle">Get started with your job search</p>
              </div>
              <form className="auth-form" onSubmit={handleSendOtp}>
                <div className="form-group">
                  <label className="form-label">Username</label>
                  <div className="input-wrapper">
                    <MdOutlinePersonOutline className="input-icon" />
                    <input
                      type="text"
                      className="input-field"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="username"
                      required
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Email Address</label>
                  <div className="input-wrapper">
                    <MdOutlineMail className="input-icon" />
                    <input
                      type="email"
                      className="input-field"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="name@example.com"
                      required
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Password</label>
                  <div className="input-wrapper">
                    <MdOutlineLock className="input-icon" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      className="input-field password-input"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      required
                    />
                    {password && (
                      <button
                        type="button"
                        className="password-toggle-btn"
                        onClick={() => setShowPassword(!showPassword)}
                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                      >
                        {showPassword ? <MdOutlineVisibilityOff /> : <MdOutlineVisibility />}
                      </button>
                    )}
                  </div>
                </div>
                <button type="submit" className="btn-submit" disabled={loading}>
                  {loading ? 'Sending Code...' : 'Register & Verify Email'}
                </button>
              </form>
              <div className="auth-footer">
                Already have an account?
                <Link to="/login" className="auth-link">Sign In</Link>
              </div>
            </>
          ) : (
            <>
              <div className="auth-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <button 
                    type="button" 
                    className="btn-ghost" 
                    style={{ padding: '4px 8px', fontSize: '0.85rem' }} 
                    onClick={() => setStep('form')}
                  >
                    <MdOutlineArrowBack /> Back
                  </button>
                </div>
                <h1 className="auth-title">Verify Your Email</h1>
                <p className="auth-subtitle">
                  Enter the 6-digit code sent to <strong style={{ color: 'var(--text-primary)' }}>{email}</strong>
                </p>
              </div>
              <form className="auth-form" onSubmit={handleVerifyOtp}>
                <div className="form-group">
                  <label className="form-label">6-Digit Verification Code</label>
                  <div className="input-wrapper">
                    <MdOutlineKey className="input-icon" />
                    <input
                      type="text"
                      className="input-field"
                      style={{ letterSpacing: '4px', fontSize: '1.1rem', fontWeight: '700' }}
                      maxLength={6}
                      value={otp}
                      onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                      placeholder="123456"
                      required
                      autoFocus
                    />
                  </div>
                </div>

                <button type="submit" className="btn-submit" disabled={loading}>
                  {loading ? 'Verifying...' : 'Verify & Continue to Dashboard'}
                </button>
              </form>

              <div className="auth-footer" style={{ flexDirection: 'column', gap: '8px', marginTop: '20px' }}>
                <div>
                  Didn't receive code?{' '}
                  <button 
                    type="button" 
                    onClick={handleResendCode} 
                    disabled={resending} 
                    className="auth-link" 
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                  >
                    {resending ? 'Resending...' : 'Resend Code'}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default RegisterPage;
