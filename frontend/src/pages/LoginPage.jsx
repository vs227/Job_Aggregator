import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { 
  MdOutlineMail, 
  MdOutlineLock, 
  MdOutlineVisibility, 
  MdOutlineVisibilityOff,
  MdOutlineKey,
  MdOutlineArrowBack
} from 'react-icons/md';
import { useAuth } from '../context/AuthContext';
import { loginUser, sendForgotPasswordOtp, resetPasswordWithOtp } from '../services/api';
import './LoginPage.css';

function LoginPage() {
  const [mode, setMode] = useState('login'); // 'login', 'forgot_email', 'forgot_otp'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleLogin(e) {
    e.preventDefault();
    if (!email || !password) {
      toast.error('All fields are required');
      return;
    }
    setLoading(true);
    try {
      const data = await loginUser(email, password);
      login(data.access_token);
      toast.success('Login successful');
      navigate('/dashboard');
    } catch (err) {
      toast.error(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleSendForgotOtp(e) {
    e.preventDefault();
    if (!email.trim()) {
      toast.error('Please enter your email address');
      return;
    }
    setLoading(true);
    try {
      await sendForgotPasswordOtp(email.trim());
      toast.success(`Reset code sent to ${email}`);
      setMode('forgot_otp');
    } catch (err) {
      toast.error(err.message || 'Failed to send reset code');
    } finally {
      setLoading(false);
    }
  }

  async function handleResetPassword(e) {
    e.preventDefault();
    if (!otp.trim() || !newPassword) {
      toast.error('Verification code and new password are required');
      return;
    }
    setLoading(true);
    try {
      const data = await resetPasswordWithOtp(email.trim(), otp.trim(), newPassword);
      if (data.access_token) {
        login(data.access_token);
        toast.success('Password reset successfully! Welcome back.');
        navigate('/dashboard');
      } else {
        toast.success('Password reset successfully! Please sign in.');
        setMode('login');
      }
    } catch (err) {
      toast.error(err.message || 'Invalid or expired verification code');
    } finally {
      setLoading(false);
    }
  }

  async function handleResendResetCode() {
    if (resending) return;
    setResending(true);
    try {
      await sendForgotPasswordOtp(email.trim());
      toast.success(`New reset code sent to ${email}`);
    } catch (err) {
      toast.error(err.message || 'Failed to resend code');
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card-glow-bg"></div>
      <div className="auth-layout-wrapper fade-in">
        <div className="auth-floating-info">
          <span className="auth-info-tag">AGGREGATED JOB INSIGHTS</span>
          <h2 className="auth-info-title">Your Next Career Move Starts Here</h2>
          <p className="auth-info-subtitle">
            We track thousands of job listings across major platforms so you can find the perfect opportunity in real-time.
          </p>
          <div className="auth-feature-list">
            <div className="auth-feature-item">
              <span className="feature-dot"></span>
              <span>Secure password reset via Email OTP</span>
            </div>
            <div className="auth-feature-item">
              <span className="feature-dot"></span>
              <span>Filter by tags, companies, and roles</span>
            </div>
            <div className="auth-feature-item">
              <span className="feature-dot"></span>
              <span>Secure job application tracking dashboard</span>
            </div>
          </div>
        </div>

        <div className="auth-card">
          {mode === 'login' && (
            <>
              <div className="auth-header">
                <h1 className="auth-title">Welcome Back</h1>
                <p className="auth-subtitle">Sign in to search and track jobs</p>
              </div>
              <form className="auth-form" onSubmit={handleLogin}>
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

                <div style={{ textAlign: 'right', marginTop: '-6px', marginBottom: '16px' }}>
                  <button
                    type="button"
                    onClick={() => setMode('forgot_email')}
                    className="auth-link"
                    style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.85rem', padding: 0 }}
                  >
                    Forgot Password?
                  </button>
                </div>

                <button type="submit" className="btn-submit" disabled={loading}>
                  {loading ? 'Signing in...' : 'Sign In'}
                </button>
              </form>
              <div className="auth-footer">
                Don't have an account?
                <Link to="/register" className="auth-link">Register</Link>
              </div>
            </>
          )}

          {mode === 'forgot_email' && (
            <>
              <div className="auth-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <button 
                    type="button" 
                    className="btn-ghost" 
                    style={{ padding: '4px 8px', fontSize: '0.85rem' }} 
                    onClick={() => setMode('login')}
                  >
                    <MdOutlineArrowBack /> Back to Sign In
                  </button>
                </div>
                <h1 className="auth-title">Reset Password</h1>
                <p className="auth-subtitle">Enter your registered email to receive a 6-digit verification code</p>
              </div>
              <form className="auth-form" onSubmit={handleSendForgotOtp}>
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
                      autoFocus
                    />
                  </div>
                </div>
                <button type="submit" className="btn-submit" disabled={loading}>
                  {loading ? 'Sending Code...' : 'Send Verification OTP'}
                </button>
              </form>
            </>
          )}

          {mode === 'forgot_otp' && (
            <>
              <div className="auth-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <button 
                    type="button" 
                    className="btn-ghost" 
                    style={{ padding: '4px 8px', fontSize: '0.85rem' }} 
                    onClick={() => setMode('forgot_email')}
                  >
                    <MdOutlineArrowBack /> Change Email
                  </button>
                </div>
                <h1 className="auth-title">Set New Password</h1>
                <p className="auth-subtitle">
                  Enter the 6-digit code sent to <strong style={{ color: 'var(--text-primary)' }}>{email}</strong>
                </p>
              </div>
              <form className="auth-form" onSubmit={handleResetPassword}>
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

                <div className="form-group">
                  <label className="form-label">New Password</label>
                  <div className="input-wrapper">
                    <MdOutlineLock className="input-icon" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      className="input-field password-input"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="Enter new password"
                      required
                    />
                    {newPassword && (
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
                  {loading ? 'Resetting...' : 'Reset Password & Continue'}
                </button>
              </form>

              <div className="auth-footer" style={{ flexDirection: 'column', gap: '8px', marginTop: '20px' }}>
                <div>
                  Didn't receive code?{' '}
                  <button 
                    type="button" 
                    onClick={handleResendResetCode} 
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

export default LoginPage;
