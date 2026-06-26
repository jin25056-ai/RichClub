import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { AuthFormValues } from '../types';
import { login, signup } from '../api';
import apiClient from '../api/client';

type AuthMode = 'login' | 'signup';
type VerifyStep = 'input' | 'sent' | 'verified';

const parseErrorMessage = (err: any): string => {
  const detail = err?.response?.data?.detail;
  if (!detail) return '요청에 실패했습니다.';
  if (Array.isArray(detail)) {
    const first = detail[0];
    const msg: string = first?.msg ?? '';
    if (msg.includes('email') || msg.includes('@-sign')) return '올바른 이메일 형식을 입력해주세요.';
    if (msg.includes('min_length') || msg.includes('8')) return '비밀번호는 최소 8자 이상이어야 합니다.';
    if (first?.loc?.includes('name')) return '이름을 입력해주세요.';
    return '입력값을 확인해주세요.';
  }
  if (typeof detail === 'string') return detail;
  return '요청에 실패했습니다.';
};

const GlassButton: React.FC<{
  label: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'ghost' | 'danger';
  fullWidth?: boolean;
  small?: boolean;
}> = ({ label, onClick, disabled, variant = 'primary', fullWidth, small }) => {
  const [hover, setHover] = useState(false);
  const base: React.CSSProperties = {
    position: 'relative',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: fullWidth ? '100%' : undefined,
    padding: small ? '6px 14px' : '11px 20px',
    fontSize: small ? 12 : 14,
    fontWeight: 600,
    borderRadius: small ? 6 : 10,
    cursor: disabled ? 'default' : 'pointer',
    border: 'none',
    outline: 'none',
    transition: 'all 0.2s',
    letterSpacing: '0.01em',
    opacity: disabled ? 0.45 : 1,
    whiteSpace: 'nowrap' as const,
  };
  const variants: Record<string, React.CSSProperties> = {
    primary: {
      background: hover && !disabled ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.03)',
      boxShadow: '0 0 0 1px rgba(255,255,255,0.1)',
      color: '#e2e8f0',
    },
    ghost: {
      background: hover && !disabled ? 'rgba(255,255,255,0.05)' : 'transparent',
      boxShadow: '0 0 0 1px rgba(255,255,255,0.08)',
      color: '#6b7280',
    },
    danger: {
      background: hover && !disabled ? 'rgba(239,68,68,0.15)' : 'rgba(239,68,68,0.06)',
      boxShadow: '0 0 0 1px rgba(239,68,68,0.2)',
      color: '#f87171',
    },
  };
  return (
    <button
      style={{ ...base, ...variants[variant] }}
      onClick={disabled ? undefined : onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {label}
    </button>
  );
};

// 이용약관 모달
const TermsModal: React.FC<{ onClose: () => void }> = ({ onClose }) => (
  <div
    onClick={onClose}
    style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
  >
    <div
      onClick={(e) => e.stopPropagation()}
      style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 12, padding: '24px', width: 480, maxWidth: '90vw', maxHeight: '75vh', display: 'flex', flexDirection: 'column' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: '#e2e8f0' }}>이용약관</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#6b7280', fontSize: 16, cursor: 'pointer' }}>&#x2715;</button>
      </div>
      <div style={{ overflowY: 'auto', flex: 1, fontSize: 11, color: '#4b5563', lineHeight: 1.9 }}>
        <div style={{ fontWeight: 600, color: '#6b7280', marginBottom: 8 }}>제1조 (목적)</div>
        <p>본 약관은 RichClub (이하 "서비스")이 제공하는 AI 기반 주식 분석 서비스의 이용 조건 및 절차에 관한 사항을 규정함을 목적으로 합니다.</p>

        <div style={{ fontWeight: 600, color: '#6b7280', marginBottom: 8, marginTop: 16 }}>제2조 (투자 위험 고지)</div>
        <p>서비스에서 제공하는 AI 예측, 매매 신호, 자동매매 기능은 투자 참고 목적의 정보 제공 서비스입니다. 이는 투자 권유 또는 금융 자문이 아니며, 어떠한 경우에도 원금 보장을 하지 않습니다. 모든 투자 결정과 그에 따른 손익은 전적으로 이용자 본인에게 귀속됩니다.</p>

        <div style={{ fontWeight: 600, color: '#6b7280', marginBottom: 8, marginTop: 16 }}>제3조 (서비스 제공자의 면책)</div>
        <p>서비스 제공자는 다음 각 호의 사유로 발생한 손해에 대하여 책임을 지지 않습니다.</p>
        <p>1. AI 예측 신호의 오류 또는 부정확성으로 인한 투자 손실<br />
        2. 자동매매 기능 이용 시 증권사 API 오류, 네트워크 장애, 시스템 점검 등으로 인한 손실<br />
        3. 시장 급변동, 거래 정지 등 불가항력적 상황으로 인한 손실<br />
        4. 이용자의 판단에 의한 투자 결과</p>

        <div style={{ fontWeight: 600, color: '#6b7280', marginBottom: 8, marginTop: 16 }}>제4조 (요금 및 결제)</div>
        <p>서비스 이용 요금은 선불 월정액 방식으로 운영됩니다. 결제 완료 후 환불은 서비스 미이용 시에 한하여 개별 협의합니다. 자동매매 기능 연동을 위한 증권사 API 이용에 따른 별도 비용은 이용자 부담입니다.</p>

        <div style={{ fontWeight: 600, color: '#6b7280', marginBottom: 8, marginTop: 16 }}>제5조 (개인정보 보호)</div>
        <p>서비스는 이용자의 이메일, 이름, 플랜 정보를 수집합니다. 수집된 정보는 서비스 제공 목적에만 사용되며 제3자에게 제공하지 않습니다.</p>

        <div style={{ fontWeight: 600, color: '#6b7280', marginBottom: 8, marginTop: 16 }}>제6조 (서비스 변경 및 중단)</div>
        <p>서비스 제공자는 운영상 필요에 따라 서비스 내용을 변경하거나 중단할 수 있습니다. 이 경우 사전 공지를 원칙으로 하며, 불가피한 상황에서는 사후 공지할 수 있습니다.</p>
      </div>
      <button
        onClick={onClose}
        style={{ marginTop: 16, padding: '10px 0', background: '#1e1e2e', border: '1px solid #2d2d3d', borderRadius: 8, color: '#9ca3af', fontSize: 12, cursor: 'pointer', fontWeight: 600 }}
      >
        닫기
      </button>
    </div>
  </div>
);

const AuthContainer: React.FC = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState<AuthMode>('login');
  const [form, setForm] = useState<AuthFormValues>({ email: '', password: '', name: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [showTermsModal, setShowTermsModal] = useState(false);

  const [verifyStep, setVerifyStep] = useState<VerifyStep>('input');
  const [verifyCode, setVerifyCode] = useState('');
  const [sendingCode, setSendingCode] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [expireCountdown, setExpireCountdown] = useState(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const expireRef = useRef<NodeJS.Timeout | null>(null);

  const [resetStep, setResetStep] = useState<'email' | 'code' | 'password'>('email');
  const [resetEmail, setResetEmail] = useState('');
  const [resetCode, setResetCode] = useState('');
  const [resetNewPw, setResetNewPw] = useState('');
  const [resetError, setResetError] = useState<string | null>(null);
  const [resetSending, setResetSending] = useState(false);
  const [resetExpire, setResetExpire] = useState(0);
  const resetExpireRef = useRef<NodeJS.Timeout | null>(null);
  const [showNewPw, setShowNewPw] = useState(false);
  const [showReset, setShowReset] = useState(false);

  useEffect(() => () => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (expireRef.current) clearInterval(expireRef.current);
  }, []);

  const handleReset = () => {
    setShowReset(false); setError(null);
    setResetStep('email'); setResetEmail(''); setResetCode('');
    setResetNewPw(''); setResetError(null);
    if (resetExpireRef.current) clearInterval(resetExpireRef.current);
  };

  const handleResetSendCode = async () => {
    if (!resetEmail.includes('@')) { setResetError('올바른 이메일을 입력해주세요.'); return; }
    setResetSending(true); setResetError(null);
    try {
      await apiClient.post('/api/v1/auth/email/send-code', { email: resetEmail });
      setResetStep('code');
      setResetExpire(300);
      if (resetExpireRef.current) clearInterval(resetExpireRef.current);
      resetExpireRef.current = setInterval(() => {
        setResetExpire((c) => {
          if (c <= 1) { clearInterval(resetExpireRef.current!); setResetStep('email'); setResetError('인증 시간이 만료되었습니다.'); return 0; }
          return c - 1;
        });
      }, 1000);
    } catch (err: any) {
      setResetError(err?.response?.data?.detail ?? '발송에 실패했습니다.');
    } finally { setResetSending(false); }
  };

  const handleResetVerify = async () => {
    if (resetCode.length !== 6) { setResetError('6자리 코드를 입력해주세요.'); return; }
    setResetError(null);
    try {
      await apiClient.post('/api/v1/auth/email/verify-code', { email: resetEmail, code: resetCode });
      setResetStep('password');
      if (resetExpireRef.current) clearInterval(resetExpireRef.current);
    } catch (err: any) {
      setResetError(err?.response?.data?.detail ?? '인증에 실패했습니다.');
    }
  };

  const handleResetPassword = async () => {
    if (resetNewPw.length < 8) { setResetError('비밀번호는 최소 8자 이상이어야 합니다.'); return; }
    setResetError(null);
    try {
      await apiClient.post('/api/v1/auth/password/reset', { email: resetEmail, code: resetCode, new_password: resetNewPw });
      handleReset();
      setError('비밀번호가 변경되었습니다.');
    } catch (err: any) {
      setResetError(err?.response?.data?.detail ?? '변경에 실패했습니다.');
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
    if (e.target.name === 'email') {
      setVerifyStep('input'); setVerifyCode(''); setVerifyError(null);
    }
  };

  const handleSendCode = async () => {
    if (!form.email.includes('@')) { setVerifyError('올바른 이메일을 입력해주세요.'); return; }
    setSendingCode(true); setVerifyError(null); setVerifyCode('');
    try {
      await apiClient.post('/api/v1/auth/email/send-code', { email: form.email });
      setVerifyStep('sent');
      setExpireCountdown(300);
      if (expireRef.current) clearInterval(expireRef.current);
      expireRef.current = setInterval(() => {
        setExpireCountdown((c) => {
          if (c <= 1) {
            clearInterval(expireRef.current!);
            setVerifyStep('input');
            setVerifyError('인증 시간이 만료되었습니다. 다시 발송해주세요.');
            return 0;
          }
          return c - 1;
        });
      }, 1000);
    } catch (err: any) {
      setVerifyError(err?.response?.data?.detail ?? '발송에 실패했습니다.');
    } finally {
      setSendingCode(false);
    }
  };

  const handleVerifyCode = async () => {
    if (verifyCode.length !== 6) { setVerifyError('6자리 코드를 모두 입력해주세요.'); return; }
    setVerifyError(null);
    try {
      await apiClient.post('/api/v1/auth/email/verify-code', { email: form.email, code: verifyCode });
      setVerifyStep('verified');
      if (expireRef.current) clearInterval(expireRef.current);
    } catch (err: any) {
      setVerifyError(err?.response?.data?.detail ?? '인증에 실패했습니다.');
    }
  };

  const handleSubmit = async () => {
    setError(null);
    if (!form.email.includes('@')) { setError('올바른 이메일 형식을 입력해주세요.'); return; }
    if (form.password.length < 8) { setError('비밀번호는 최소 8자 이상이어야 합니다.'); return; }
    if (mode === 'signup') {
      if (!form.name?.trim()) { setError('이름을 입력해주세요.'); return; }
      if (verifyStep !== 'verified') { setError('이메일 인증을 완료해주세요.'); return; }
      if (!agreedToTerms) { setError('이용약관에 동의해주세요.'); return; }
    }
    setLoading(true);
    try {
      const res = mode === 'login'
        ? await login({ email: form.email, password: form.password })
        : await signup(form);
      localStorage.setItem('access_token', res.access_token);
      localStorage.setItem('refresh_token', res.refresh_token);
      navigate('/'); window.location.reload();
    } catch (err: any) {
      setError(parseErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '11px 14px', fontSize: 14,
    background: 'rgba(255,255,255,0.04)',
    border: '1.5px solid rgba(255,255,255,0.08)',
    borderRadius: 10, outline: 'none', color: '#e2e8f0',
    boxSizing: 'border-box',
    backdropFilter: 'blur(8px)',
    transition: 'border-color 0.15s',
  };

  return (
    <main style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: 'calc(100vh - 60px)', background: '#0a0a14',
    }}>
      {showTermsModal && <TermsModal onClose={() => setShowTermsModal(false)} />}

      <div style={{
        width: 400, padding: '36px 32px',
        background: 'rgba(255,255,255,0.03)',
        backdropFilter: 'blur(24px)',
        WebkitBackdropFilter: 'blur(24px)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: 20,
        boxShadow: '0 24px 64px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06)',
      }}>
        {/* 탭 */}
        <div style={{
          display: 'flex', background: 'rgba(255,255,255,0.04)',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: 10, padding: 3, marginBottom: 24,
        }}>
          {(['login', 'signup'] as AuthMode[]).map((m) => (
            <button key={m} onClick={() => { setMode(m); setError(null); setVerifyStep('input'); setVerifyCode(''); setAgreedToTerms(false); }}
              style={{
                flex: 1, padding: '8px 0', fontSize: 13, fontWeight: mode === m ? 700 : 500,
                borderRadius: 8, border: 'none', cursor: 'pointer',
                background: mode === m ? 'rgba(99,102,241,0.25)' : 'transparent',
                color: mode === m ? '#a5b4fc' : '#4b5563',
                boxShadow: mode === m ? '0 0 0 1px rgba(99,102,241,0.3)' : 'none',
                transition: 'all 0.2s',
              }}>
              {m === 'login' ? '로그인' : '회원가입'}
            </button>
          ))}
        </div>

        {!showReset && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {mode === 'signup' && (
              <input style={inputStyle} type="text" name="name" placeholder="이름"
                value={form.name} onChange={handleChange} />
            )}

            <div style={{ display: 'flex', gap: 8 }}>
              <input
                style={{ ...inputStyle, flex: 1 }}
                type="email" name="email" placeholder="이메일"
                value={form.email} onChange={handleChange}
                disabled={verifyStep === 'verified'}
              />
              {mode === 'signup' && verifyStep !== 'verified' && (
                <button
                  onClick={handleSendCode}
                  disabled={sendingCode}
                  style={{
                    flexShrink: 0, padding: '0 14px', fontSize: 12, fontWeight: 600,
                    borderRadius: 10, border: '1px solid rgba(255,255,255,0.1)',
                    background: 'transparent', color: '#6b7280',
                    cursor: sendingCode ? 'default' : 'pointer',
                    whiteSpace: 'nowrap', transition: 'all 0.2s',
                  }}>
                  {sendingCode ? '발송중' : verifyStep === 'sent' ? '재발송' : '인증'}
                </button>
              )}
              {mode === 'signup' && verifyStep === 'verified' && (
                <span style={{ flexShrink: 0, display: 'flex', alignItems: 'center', fontSize: 12, color: '#818cf8', fontWeight: 600 }}>✓ 인증됨</span>
              )}
            </div>

            {mode === 'signup' && verifyStep === 'sent' && (
              <div style={{ display: 'flex', gap: 8 }}>
                <div style={{ position: 'relative', flex: 1 }}>
                  <input
                    style={{ ...inputStyle, width: '100%', letterSpacing: 2 }}
                    type="text" inputMode="numeric" maxLength={6}
                    placeholder="인증코드 6자리"
                    value={verifyCode}
                    onChange={(e) => { setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6)); setVerifyError(null); }}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleVerifyCode(); }}
                  />
                  <span style={{
                    position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                    fontSize: 10, color: expireCountdown < 60 ? '#f87171' : '#374151', fontWeight: 500,
                  }}>{fmtTime(expireCountdown)}</span>
                </div>
                <button
                  onClick={handleVerifyCode}
                  disabled={verifyCode.length !== 6}
                  style={{
                    flexShrink: 0, padding: '0 14px', fontSize: 12, fontWeight: 600,
                    borderRadius: 10, border: '1px solid rgba(255,255,255,0.1)',
                    background: 'transparent',
                    color: verifyCode.length === 6 ? '#9ca3af' : '#374151',
                    cursor: verifyCode.length === 6 ? 'pointer' : 'default',
                    whiteSpace: 'nowrap',
                  }}>
                  확인
                </button>
              </div>
            )}

            {verifyError && <p style={{ margin: 0, fontSize: 12, color: '#f87171' }}>{verifyError}</p>}

            <div style={{ position: 'relative' }}>
              <input
                style={{ ...inputStyle, paddingRight: 60 }}
                type={showPassword ? 'text' : 'password'} name="password"
                placeholder="비밀번호 (최소 8자)" value={form.password}
                onChange={handleChange}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit(); }}
              />
              <button
                onClick={() => setShowPassword((p) => !p)} tabIndex={-1}
                style={{
                  position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none', color: '#4b5563', fontSize: 11,
                  cursor: 'pointer', padding: 0, fontWeight: 500,
                }}>
                {showPassword ? '숨기기' : '보기'}
              </button>
            </div>

            {/* 이용약관 동의 - 회원가입 시만 표시 */}
            {mode === 'signup' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
                <input
                  type="checkbox"
                  id="terms-agree"
                  checked={agreedToTerms}
                  onChange={(e) => setAgreedToTerms(e.target.checked)}
                  style={{ cursor: 'pointer', accentColor: '#6366f1', width: 14, height: 14, flexShrink: 0 }}
                />
                <label htmlFor="terms-agree" style={{ fontSize: 12, color: '#4b5563', cursor: 'pointer', userSelect: 'none' }}>
                  <span
                    onClick={(e) => { e.preventDefault(); setShowTermsModal(true); }}
                    style={{ color: '#6366f1', textDecoration: 'underline', cursor: 'pointer' }}
                  >
                    이용약관
                  </span>
                  {' '}및 투자 위험 고지에 동의합니다
                </label>
              </div>
            )}

            {error && <p style={{ margin: 0, fontSize: 12, color: '#f87171' }}>{error}</p>}

            <GlassButton
              fullWidth
              label={loading ? '처리 중...' : mode === 'login' ? '로그인' : '회원가입'}
              onClick={handleSubmit}
              disabled={loading}
              variant="ghost"
            />
            {mode === 'login' && (
              <p onClick={() => { setShowReset(true); setResetStep('email'); setResetEmail(''); setResetCode(''); setResetNewPw(''); setResetError(null); }}
                style={{ margin: '2px 0 0', fontSize: 12, color: '#374151', textAlign: 'center', cursor: 'pointer' }}>
                비밀번호를 잊으셨나요?
              </p>
            )}
          </div>
        )}

        {showReset && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <button onClick={handleReset}
                style={{ background: 'none', border: 'none', color: '#4b5563', cursor: 'pointer', fontSize: 16, padding: 0, lineHeight: 1 }}>
                ←
              </button>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#9ca3af' }}>비밀번호 재설정</span>
            </div>
            {resetStep === 'email' && (
              <>
                <input style={inputStyle} type="email" placeholder="가입한 이메일"
                  value={resetEmail} onChange={(e) => setResetEmail(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleResetSendCode(); }} />
                {resetError && <p style={{ margin: 0, fontSize: 12, color: '#f87171' }}>{resetError}</p>}
                <GlassButton fullWidth label={resetSending ? '발송중...' : '인증코드 발송'} onClick={handleResetSendCode} disabled={resetSending} variant="ghost" />
              </>
            )}
            {resetStep === 'code' && (
              <>
                <div style={{ fontSize: 12, color: '#6b7280' }}>{resetEmail}로 보낸 코드를 입력하세요</div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <div style={{ position: 'relative', flex: 1 }}>
                    <input style={{ ...inputStyle, width: '100%', letterSpacing: 2 }}
                      type="text" inputMode="numeric" maxLength={6} placeholder="인증코드 6자리"
                      value={resetCode}
                      onChange={(e) => { setResetCode(e.target.value.replace(/\D/g, '').slice(0, 6)); setResetError(null); }}
                      onKeyDown={(e) => { if (e.key === 'Enter') handleResetVerify(); }} />
                    <span style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', fontSize: 10, color: resetExpire < 60 ? '#f87171' : '#374151', fontWeight: 500 }}>{fmtTime(resetExpire)}</span>
                  </div>
                  <button onClick={handleResetVerify} disabled={resetCode.length !== 6}
                    style={{ flexShrink: 0, padding: '0 14px', fontSize: 12, fontWeight: 600, borderRadius: 10, border: '1px solid rgba(255,255,255,0.1)', background: 'transparent', color: resetCode.length === 6 ? '#9ca3af' : '#374151', cursor: resetCode.length === 6 ? 'pointer' : 'default', whiteSpace: 'nowrap' }}>
                    확인
                  </button>
                </div>
                {resetError && <p style={{ margin: 0, fontSize: 12, color: '#f87171' }}>{resetError}</p>}
              </>
            )}
            {resetStep === 'password' && (
              <>
                <div style={{ position: 'relative' }}>
                  <input style={{ ...inputStyle, paddingRight: 60 }}
                    type={showNewPw ? 'text' : 'password'} placeholder="새 비밀번호 (최소 8자)"
                    value={resetNewPw} onChange={(e) => setResetNewPw(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleResetPassword(); }} />
                  <button onClick={() => setShowNewPw(p => !p)} tabIndex={-1}
                    style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#4b5563', fontSize: 11, cursor: 'pointer', padding: 0 }}>
                    {showNewPw ? '숨기기' : '보기'}
                  </button>
                </div>
                {resetError && <p style={{ margin: 0, fontSize: 12, color: '#f87171' }}>{resetError}</p>}
                <GlassButton fullWidth label="비밀번호 변경" onClick={handleResetPassword} variant="ghost" />
              </>
            )}
          </div>
        )}

        <p onClick={() => navigate('/')}
          style={{ margin: '20px 0 0', fontSize: 12, color: '#374151', textAlign: 'center', cursor: 'pointer' }}>
          메인으로 돌아가기
        </p>
      </div>
    </main>
  );
};

export default AuthContainer;
