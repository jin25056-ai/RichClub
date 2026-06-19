import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/Button';
import { AuthFormValues } from '../types';
import { login, signup } from '../api';

type AuthMode = 'login' | 'signup';

const AuthContainer: React.FC = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState<AuthMode>('login');
  const [form, setForm] = useState<AuthFormValues>({ email: '', password: '', name: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async () => {
    setError(null);
    setLoading(true);
    try {
      if (mode === 'login') {
        const res = await login({ email: form.email, password: form.password });
        localStorage.setItem('access_token', res.access_token);
      } else {
        const res = await signup(form);
        localStorage.setItem('access_token', res.access_token);
      }
      navigate('/');
    } catch (err: any) {
      setError(err?.response?.data?.message ?? '요청에 실패했습니다.');
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
          <input
            style={styles.input}
            type="password"
            name="password"
            placeholder="비밀번호"
            value={form.password}
            onChange={handleChange}
          />
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
    gap: '0',
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
