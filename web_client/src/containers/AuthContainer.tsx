import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/Button';
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

const AuthContainer: React.FC = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState<AuthMode>('login');
  const [form, setForm] = useState<AuthFormValues>({ email: '', password: '', name: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  // 이메일 인증 상태
  const [verifyStep, setVerifyStep] = useState<VerifyStep>('input');
  const [verifyCode, setVerifyCode] = useState('');
  const [sendingCode, setSendingCode] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
    // 이메일 변경 시 인증 초기화
    if (e.target.name === 'email') {
      setVerifyStep('input');
      setVerifyCode('');
      setVerifyError(null);
    }
  };

  const handleSendCode = async () => {
    if (!form.email.includes('@')) { setVerifyError('올바른 이메일을 입력해주세요.'); return; }
    setSendingCode(true);
    setVerifyError(null);
    try {
      await apiClient.post('/api/v1/auth/email/send-code', { email: form.email });
      setVerifyStep('sent');
      // 60초 카운트다운
      setCountdown(60);
      const timer = setInterval(() => {
        setCountdown((c) => {
          if (c <= 1) { clearInterval(timer); return 0; }
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
    if (verifyCode.length !== 6) { setVerifyError('6자리 코드를 입력해주세요.'); return; }
    setVerifyError(null);
    try {
      await apiClient.post('/api/v1/auth/email/verify-code', { email: form.email, code: verifyCode });
      setVerifyStep('verified');
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
      navigate('/');
      window.location.reload();
    } catch (err: any) {
      setError(parseErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSubmit();
  };

  return (
    <main style={styles.container}>
      <div style={styles.card}>
        <div style={styles.tabRow}>
          <button style={mode === 'login' ? styles.tabActive : styles.tab}
            onClick={() => { setMode('login'); setError(null); setVerifyStep('input'); }}>로그인</button>
          <button style={mode === 'signup' ? styles.tabActive : styles.tab}
            onClick={() => { setMode('signup'); setError(null); }}>회원가입</button>
        </div>

        <div style={styles.form}>
          {mode === 'signup' && (
            <input style={styles.input} type="text" name="name" placeholder="이름"
              value={form.name} onChange={handleChange} onKeyDown={handleKeyDown} />
          )}

          {/* 이메일 + 인증코드 발송 버튼 */}
          <div style={{ display: 'flex', gap: 6 }}>
            <input style={{ ...styles.input, flex: 1 }} type="email" name="email" placeholder="이메일"
              value={form.email} onChange={handleChange} onKeyDown={handleKeyDown}
              disabled={verifyStep === 'verified'} />
            {mode === 'signup' && verifyStep !== 'verified' && (
              <button onClick={handleSendCode} disabled={sendingCode || countdown > 0}
                style={{
                  flexShrink: 0, padding: '0 12px', fontSize: 12, borderRadius: 6,
                  border: '1px solid #3730a3', background: 'transparent',
                  color: countdown > 0 ? '#555' : '#a5b4fc',
                  cursor: countdown > 0 ? 'default' : 'pointer', whiteSpace: 'nowrap',
                }}>
                {sendingCode ? '발송 중...' : countdown > 0 ? `${countdown}초` : verifyStep === 'sent' ? '재발송' : '인증코드 발송'}
              </button>
            )}
            {mode === 'signup' && verifyStep === 'verified' && (
              <span style={{ flexShrink: 0, fontSize: 12, color: '#4ade80', display: 'flex', alignItems: 'center' }}>인증완료</span>
            )}
          </div>

          {/* 인증코드 입력 */}
          {mode === 'signup' && verifyStep === 'sent' && (
            <div style={{ display: 'flex', gap: 6 }}>
              <input
                style={{ ...styles.input, flex: 1, letterSpacing: 6, textAlign: 'center', fontSize: 16 }}
                type="text" maxLength={6} placeholder="인증코드 6자리"
                value={verifyCode}
                onChange={(e) => { setVerifyCode(e.target.value.replace(/\D/g, '')); setVerifyError(null); }}
                onKeyDown={(e) => { if (e.key === 'Enter') handleVerifyCode(); }}
              />
              <button onClick={handleVerifyCode}
                style={{
                  flexShrink: 0, padding: '0 12px', fontSize: 12, borderRadius: 6,
                  border: 'none', background: '#6366f1', color: '#fff', cursor: 'pointer',
                }}>
                확인
              </button>
            </div>
          )}

          {verifyError && <p style={styles.error}>{verifyError}</p>}

          <div style={styles.passwordWrapper}>
            <input style={styles.passwordInput}
              type={showPassword ? 'text' : 'password'} name="password"
              placeholder="비밀번호 (최소 8자)" value={form.password}
              onChange={handleChange} onKeyDown={handleKeyDown} />
            <button style={styles.eyeButton} onClick={() => setShowPassword((p) => !p)} tabIndex={-1}>
              {showPassword ? '숨기기' : '보기'}
            </button>
          </div>

          {error && <p style={styles.error}>{error}</p>}
          <Button label={loading ? '처리 중...' : mode === 'login' ? '로그인' : '회원가입'} onClick={handleSubmit} />
        </div>

        <p style={styles.back} onClick={() => navigate('/')}>메인으로 돌아가기</p>
      </div>
    </main>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: { display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', backgroundColor: '#111111' },
  card: { width: '380px', border: '1px solid #2a2a2a', borderRadius: '10px', padding: '32px', backgroundColor: '#1a1a1a', display: 'flex', flexDirection: 'column', gap: '20px' },
  tabRow: { display: 'flex', backgroundColor: '#222222', borderRadius: '8px', padding: '4px' },
  tab: { flex: 1, background: 'none', border: 'none', fontSize: '14px', cursor: 'pointer', color: '#666666', fontWeight: 500, padding: '8px 0', borderRadius: '6px', transition: 'all 0.15s' },
  tabActive: { flex: 1, border: 'none', fontSize: '14px', cursor: 'pointer', color: '#ffffff', fontWeight: 700, padding: '8px 0', borderRadius: '6px', backgroundColor: '#333333', transition: 'all 0.15s' },
  form: { display: 'flex', flexDirection: 'column', gap: '12px' },
  input: { padding: '10px 14px', fontSize: '14px', border: '1px solid #2a2a2a', borderRadius: '6px', outline: 'none', width: '100%', backgroundColor: '#222222', color: '#f0f0f0', boxSizing: 'border-box' },
  passwordWrapper: { position: 'relative', display: 'flex', alignItems: 'center' },
  passwordInput: { padding: '10px 60px 10px 14px', fontSize: '14px', border: '1px solid #2a2a2a', borderRadius: '6px', outline: 'none', width: '100%', backgroundColor: '#222222', color: '#f0f0f0' },
  eyeButton: { position: 'absolute', right: '12px', background: 'none', border: 'none', color: '#666666', fontSize: '12px', cursor: 'pointer', padding: '0' },
  error: { fontSize: '13px', color: '#ff4d4d', margin: 0 },
  back: { fontSize: '13px', color: '#555555', textAlign: 'center', cursor: 'pointer' },
};

export default AuthContainer;
