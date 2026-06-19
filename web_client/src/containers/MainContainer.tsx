import React from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/Button';

const MainContainer: React.FC = () => {
  const navigate = useNavigate();

  return (
    <main style={styles.container}>
      <h1 style={styles.heading}>RichClub</h1>
      <p style={styles.sub}>자산 관리를 시작하세요</p>
      <div style={styles.actions}>
        <Button label="로그인 / 회원가입" onClick={() => navigate('/auth')} />
        <Button label="차트 보기" onClick={() => navigate('/chart')} variant="outline" />
      </div>
    </main>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: 'calc(100vh - 57px)',
    gap: '16px',
  },
  heading: {
    fontSize: '40px',
    fontWeight: 700,
    letterSpacing: '-1px',
  },
  sub: {
    fontSize: '15px',
    color: '#666666',
    marginBottom: '8px',
  },
  actions: {
    display: 'flex',
    gap: '12px',
  },
};

export default MainContainer;
