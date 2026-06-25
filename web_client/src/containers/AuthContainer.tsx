import React, { useState, useEffect, useRef } from 'react';
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

// 글래스모피즘 버튼
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

// 6칸 코드 입력
const CodeInput: React.FC<{ value: string; onChange: (v: string) => void; onComplete: () => void }> = ({ value, onChange, onComplete }) => {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = value.padEnd(6, '').split('').slice(0, 6);

  const handleChange = (i: number, v: string) => {
    const d = v.replace(/\D/g, '').slice(-1);
    const next = digits.map((c, idx) => idx === i ? d : c).join('').replace(/ /g, '');
    onChange(next);
    if (d && i < 5) refs.current[i + 1]?.focus();
    if (next.replace(/ /g, '').length === 6) onComplete();
  };

  const handleKeyDown = (i: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !digits[i] && i > 0) refs.current[i - 1]?.focus();
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    onChange(pasted);
    if (pasted.length === 6) { refs.current[5]?.focus(); onComplete(); }
    e.preventDefault();
  };

  return (
    <div style={{ display: 'flex', gap: 5 }}>
      {Array.from({ length: 6 }).map((_, i) => (
        <input key={i}
          ref={(el) => { refs.current[i] = el; }}
          type="text" inputMode="numeric" maxLength={1}
          value={digits[i] === ' ' ? '' : digits[i]}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          onFocus={(e) => e.target.select()}
          style={{
            width: 36, height: 40,
            textAlign: 'center', fontSize: 15, fontWeight: 700,
            background: 'rgba(255,255,255,0.04)',
            border: digits[i] && digits[i] !== ' '
              ? '1.5px solid rgba(99,102,241,0.7)'
              : '1.5px solid rgba(255,255,255,0.08)',
            borderRadius: 7, color: '#e2e8f0',
            outline: 'none', boxSizing: 'border-box' as const,
            caretColor: 'transparent',
          }}
        />
      ))}
    </div>
  );
};

const AuthContainer: React.FC = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState<AuthMode>('login');
  const [form, setForm] = useState<AuthFormValues>({ email: '', password: '', name: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const [verifyStep, setVerifyStep] = useState<VerifyStep>('input');
  const [verifyCode, setVerifyCode] = useState('');
  const [sendingCode, setSendingCode] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);
  const [expireCountdown, setExpireCountdown] = useState(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const expireRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => () => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (expireRef.current) clearInterval(expireRef.current);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
    if (e.target.name === 'email') {
      setVerifyStep('input'); setVerifyCode(''); setVerifyError(null);
    }
  };

  const startTimers = () => {
    setCountdown(60);
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setCountdown((c) => { if (c <= 1) { clearInterval(timerRef.current!); return 0; } return c - 1; });
    }, 1000);
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
  };

  const handleSendCode = async () => {
    if (!form.email.includes('@')) { setVerifyError('올바른 이메일을 입력해주세요.'); return; }
    setSendingCode(true); setVerifyError(null); setVerifyCode('');
    try {
      await apiClient.post('/api/v1/auth/email/send-code', { email: form.email });
      setVerifyStep('sent');
      // 만료 5분 타이머만
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
      minHeight: '100vh', background: '#0a0a14',
      backgroundImage: 'radial-gradient(ellipse at 20% 50%, rgba(99,102,241,0.08) 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, rgba(79,70,229,0.06) 0%, transparent 50%)',
    }}>
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
            <button key={m} onClick={() => { setMode(m); setError(null); setVerifyStep('input'); setVerifyCode(''); }}
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

        {/* 폼 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {mode === 'signup' && (
            <input style={inputStyle} type="text" name="name" placeholder="이름"
              value={form.name} onChange={handleChange} />
          )}

          {/* 이메일 */}
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
                  background: 'transparent',
                  color: '#6b7280',
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

          {/* 코드 입력 - 일반 인풀 */}
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
                  whiteSpace: 'nowrap', transition: 'all 0.2s',
                }}>
                확인
              </button>
            </div>
          )}

          {verifyError && <p style={{ margin: 0, fontSize: 12, color: '#f87171' }}>{verifyError}</p>}

          {/* 비밀번호 */}
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

          {error && <p style={{ margin: 0, fontSize: 12, color: '#f87171' }}>{error}</p>}

          <GlassButton
            fullWidth
            label={loading ? '처리 중...' : mode === 'login' ? '로그인' : '회원가입'}
            onClick={handleSubmit}
            disabled={loading}
            variant="ghost"
          />
        </div>

        <p onClick={() => navigate('/')}
          style={{ margin: '20px 0 0', fontSize: 12, color: '#374151', textAlign: 'center', cursor: 'pointer' }}>
          메인으로 돌아가기
        </p>
      </div>
    </main>
  );
};

export default AuthContainer;
