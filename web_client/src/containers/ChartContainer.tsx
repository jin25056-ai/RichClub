import React from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/Button';

const ChartContainer: React.FC = () => {
  const navigate = useNavigate();

  return (
    <main style={styles.container}>
      <h2 style={styles.heading}>차트</h2>
      <div style={styles.placeholder}>
        <p style={styles.placeholderText}>차트 영역</p>
      </div>
      <Button label="메인으로 돌아가기" onClick={() => navigate('/')} variant="outline" />
    </main>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '48px 32px',
    gap: '24px',
  },
  heading: {
    fontSize: '24px',
    fontWeight: 700,
    letterSpacing: '-0.5px',
  },
  placeholder: {
    width: '100%',
    maxWidth: '800px',
    height: '400px',
    border: '1px dashed #cccccc',
    borderRadius: '10px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholderText: {
    color: '#cccccc',
    fontSize: '14px',
  },
};

export default ChartContainer;
