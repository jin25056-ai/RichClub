import React from 'react';
import { useNavigate } from 'react-router-dom';

const Header: React.FC = () => {
  const navigate = useNavigate();

  return (
    <header style={styles.header}>
      <span style={styles.title} onClick={() => navigate('/')}>
        RichClub
      </span>
    </header>
  );
};

const styles: Record<string, React.CSSProperties> = {
  header: {
    padding: '16px 32px',
    borderBottom: '1px solid #2a2a2a',
    display: 'flex',
    alignItems: 'center',
    backgroundColor: '#111111',
  },
  title: {
    fontSize: '20px',
    fontWeight: 700,
    cursor: 'pointer',
    letterSpacing: '-0.5px',
    color: '#ffffff',
  },
};

export default Header;
