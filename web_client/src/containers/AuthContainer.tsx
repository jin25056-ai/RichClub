import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/Button';
import { AuthFormValues } from '../types';
import { login, signup } from '../api';

type AuthMode = 'login' | 'signup';

const parseErrorMessage = (err: any): string => {
  const detail = err?.response?.data?.detail;

  if (!detail) return '요청에 실패했습니다.';

  // FastAPI validation error (배열 형태)
  if (Array.isArray(detail)) {
    const first = detail[0];
    const msg: string = first?.msg ?? '';

    if (msg.includes('email') || msg.includes('@-sign')) return '올바른 이메일 형식을 입력해주세요.';
    if (msg.includes('min_length') || msg.includes('8')) return '비밀번호는 최소 8자 이상이어야 합니다.';
    if (first?.loc?.includes('name')) return '이름을 입력해주세요.';
    return '입력값을 확인해주세요.';
  }

  // 서버 문자열 에러
  if (typeof detail === 'string') {
    if (detail.includes('이메일')) return detail;
    if (detail.includes('비밀번호')) return detail;
    if (detail.includes('이미 사용')) return '이미 가입된 이메일입니다.';
    return detail;
  }

  return '요청에 실패했습니다.';
};

const AuthContainer: React.FC = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState<AuthMode>('login');
  const [form, setForm] = useState<AuthFormValues>({ email: '', password: '', name: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async () => {
    setError(null);

    // 클라이언트 사이드 검증
    if (!form.email.includes('@')) {
      setError('올바른 이메일 형식을 입력해주세요.');
      return;
    }
    if (form.password.length < 8) {
      setError('비밀번호는 최소 8자 이상이어야 합니다.');
      return;
    }
    if (mode === 'signup' && !form.name?.trim()) {
      setError('이름을 입력해주세요.');
      return;
    }

    setLoading(true);
    try {
      const res =
        mode === 'login'
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

  return (
    <main style={styles.container}>
      <div style={styles.card}>
        <div style={styles.tabRow}>
          <button
            style={mode === 'login' ? styles.tabActive : styles.tab}
            onClick={() => { setMode('login'); setError(null); }}
          >
            로그인
          </button>
          <button
            style={mode === 'signup' ? styles.tabActive : styles.tab}
            onClick={() => { setMode('signup'); setError(null); }}
          >
            회원가입
          </button>
        </div>

        <div style={styles.form}>
          {mode === 'signup' && (
            <input
              style={styles.input}
              type="text"
              name="name"
              placeholder="이름"
              value={form.name}
              onChange={handleChange}
            />
          )}
          <input
            style={styles.input}
            type="email"
            name="email"
            placeholder="이메일"
            value={form.email}
            onChange={handleChange}
          />
          <div style={styles.passwordWrapper}>
            <input
              style={styles.passwordInput}
              type={showPassword ? 'text' : 'password'}
              name="password"
              placeholder="비밀번호 (최소 8자)"
              value={form.password}
              onChange={handleChange}
            />
            <button
              style={styles.eyeButton}
              onClick={() => setShowPassword((prev) => !prev)}
              tabIndex={-1}
            >
              {showPassword ? '숨기기' : '보기'}
            </button>
          </div>
          {error && <p style={styles.error}>{error}</p>}
          <Button
            label={loading ? '처리 중...' : mode === 'login' ? '로그인' : '회원가입'}
            onClick={handleSubmit}
          />
        </div>

        <p style={styles.back} onClick={() => navigate('/')}>
          메인으로 돌아가기
        </p>
      </div>
    </main>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: 'calc(100vh - 57px)',
    backgroundColor: '#111111',
  },
  card: {
    width: '360px',
    border: '1px solid #2a2a2a',
    borderRadius: '10px',
    padding: '32px',
    backgroundColor: '#1a1a1a',
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  },
  tabRow: {
    display: 'flex',
    backgroundColor: '#222222',
    borderRadius: '8px',
    padding: '4px',
  },
  tab: {
    flex: 1,
    background: 'none',
    border: 'none',
    fontSize: '14px',
    cursor: 'pointer',
    color: '#666666',
    fontWeight: 500,
    padding: '8px 0',
    borderRadius: '6px',
    transition: 'all 0.15s',
  },
  tabActive: {
    flex: 1,
    border: 'none',
    fontSize: '14px',
    cursor: 'pointer',
    color: '#ffffff',
    fontWeight: 700,
    padding: '8px 0',
    borderRadius: '6px',
    backgroundColor: '#333333',
    transition: 'all 0.15s',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  input: {
    padding: '10px 14px',
    fontSize: '14px',
    border: '1px solid #2a2a2a',
    borderRadius: '6px',
    outline: 'none',
    width: '100%',
    backgroundColor: '#222222',
    color: '#f0f0f0',
  },
  passwordWrapper: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
  },
  passwordInput: {
    padding: '10px 60px 10px 14px',
    fontSize: '14px',
    border: '1px solid #2a2a2a',
    borderRadius: '6px',
    outline: 'none',
    width: '100%',
    backgroundColor: '#222222',
    color: '#f0f0f0',
  },
  eyeButton: {
    position: 'absolute',
    right: '12px',
    background: 'none',
    border: 'none',
    color: '#666666',
    fontSize: '12px',
    cursor: 'pointer',
    padding: '0',
  },
  error: {
    fontSize: '13px',
    color: '#ff4d4d',
  },
  back: {
    fontSize: '13px',
    color: '#555555',
    textAlign: 'center',
    cursor: 'pointer',
  },
};

export default AuthContainer;
