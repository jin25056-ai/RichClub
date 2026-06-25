import React from 'react';
import { useNavigate } from 'react-router-dom';
import { logout } from '../api';

const Header: React.FC = () => {
  const navigate = useNavigate();
  const isLoggedIn = !!localStorage.getItem('access_token');

  const handleLogout = () => {
    logout();
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
    borderBottom: '1px solid #1e1e2e',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#0a0a14',
  },
  title: { cursor: 'pointer' },
  nav: { display: 'flex', gap: '24px', alignItems: 'center' },
  navItem: { fontSize: '14px', color: '#6b7280', cursor: 'pointer' },
};

export default Header;
