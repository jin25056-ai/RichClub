import React from 'react';
import { useNavigate } from 'react-router-dom';

const Header: React.FC = () => {
  const navigate = useNavigate();
  const isLoggedIn = !!localStorage.getItem('access_token');

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    navigate('/');
    window.location.reload();
  };

  return (
    <header style={styles.header}>
      <span style={styles.title} onClick={() => navigate('/')}>
        RichClub
      </span>
      <nav style={styles.nav}>
        <span style={styles.navItem} onClick={() => navigate('/')}>홈</span>
        <span style={styles.navItem} onClick={() => navigate('/chart')}>차트</span>
        {isLoggedIn ? (
          <span style={styles.navItem} onClick={handleLogout}>로그아웃</span>
        ) : (
          <span style={styles.navItem} onClick={() => navigate('/auth')}>로그인</span>
        )}
      </nav>
    </header>
  );
};

const styles: Record<string, React.CSSProperties> = {
  header: {
    padding: '16px 32px',
    borderBottom: '1px solid #2a2a2a',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#111111',
  },
  title: {
    fontSize: '20px',
    fontWeight: 700,
    cursor: 'pointer',
    letterSpacing: '-0.5px',
    color: '#ffffff',
  },
  nav: {
    display: 'flex',
    gap: '24px',
    alignItems: 'center',
  },
  navItem: {
    fontSize: '14px',
    color: '#888888',
    cursor: 'pointer',
  },
};

export default Header;
