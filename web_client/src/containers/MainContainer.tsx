import React from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/Button';

// 비로그인 메인
const GuestMain: React.FC = () => {
  const navigate = useNavigate();
  return (
    <main style={styles.guestContainer}>
      <h1 style={styles.heading}>RichClub</h1>
      <p style={styles.sub}>자산 관리를 시작하세요</p>
      <div style={styles.actions}>
        <Button label="로그인 / 회원가입" onClick={() => navigate('/auth')} />
        <Button label="차트 보기" onClick={() => navigate('/chart')} variant="outline" />
      </div>
    </main>
  );
};

// 로그인 메인
const AuthedMain: React.FC = () => {
  const navigate = useNavigate();
  return (
    <main style={styles.authedContainer}>
      {/* 상단: 메인 콘텐츠 + 사이드 */}
      <div style={styles.topSection}>
        {/* 왼쪽: AI 예측 리스트 or 미니차트 */}
        <div style={styles.mainPanel}>
          <p style={styles.panelLabel}>AI 예측 리스트 / 미니차트</p>
        </div>

        {/* 오른쪽: 종목 검색 + 리스트 탭 */}
        <div style={styles.sidePanel}>
          <div style={styles.searchBox}>
            <p style={styles.panelLabel}>종목 검색</p>
            <Button label="차트로 이동" onClick={() => navigate('/chart')} variant="outline" />
          </div>
          <div style={styles.listTabBox}>
            <p style={styles.panelLabelSmall}>시장지표 리스트 / AI 예측 리스트 탭</p>
          </div>
        </div>
      </div>

      {/* 중단: 시장지표 + 공시 리스트 */}
      <div style={styles.midSection}>
        <div style={styles.midPanel}>
          <p style={styles.panelLabel}>시장지표 리스트</p>
          <p style={styles.panelSub}>전체 종목 공공 API 활용</p>
        </div>
        <div style={styles.midPanel}>
          <p style={styles.panelLabel}>공시 리스트</p>
          <p style={styles.panelSub}>전체 종목 공공 API 활용</p>
        </div>
      </div>

      {/* 하단: 리포트 or 실적발표 일정 */}
      <div style={styles.bottomSection}>
        <p style={styles.panelLabel}>리포트 / 실적발표 일정 리스트</p>
        <p style={styles.panelSub}>API 활용</p>
      </div>
    </main>
  );
};

const MainContainer: React.FC = () => {
  const isLoggedIn = !!localStorage.getItem('access_token');
  return isLoggedIn ? <AuthedMain /> : <GuestMain />;
};

const styles: Record<string, React.CSSProperties> = {
  // 비로그인
  guestContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: 'calc(100vh - 57px)',
    backgroundColor: '#111111',
    gap: '16px',
  },
  heading: {
    fontSize: '40px',
    fontWeight: 700,
    letterSpacing: '-1px',
    color: '#ffffff',
  },
  sub: {
    fontSize: '15px',
    color: '#888888',
    marginBottom: '8px',
  },
  actions: {
    display: 'flex',
    gap: '12px',
  },

  // 로그인
  authedContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    padding: '16px',
    backgroundColor: '#111111',
    minHeight: 'calc(100vh - 57px)',
  },
  topSection: {
    display: 'flex',
    gap: '12px',
    height: '320px',
  },
  mainPanel: {
    flex: 2,
    border: '1px solid #2a2a2a',
    borderRadius: '8px',
    backgroundColor: '#1a1a1a',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sidePanel: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  searchBox: {
    flex: 1,
    border: '1px solid #2a2a2a',
    borderRadius: '8px',
    backgroundColor: '#1a1a1a',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '12px',
  },
  listTabBox: {
    flex: 1,
    border: '1px solid #2a2a2a',
    borderRadius: '8px',
    backgroundColor: '#1a1a1a',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '12px',
  },
  midSection: {
    display: 'flex',
    gap: '12px',
    height: '160px',
  },
  midPanel: {
    flex: 1,
    border: '1px solid #2a2a2a',
    borderRadius: '8px',
    backgroundColor: '#1a1a1a',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
  },
  bottomSection: {
    border: '1px solid #2a2a2a',
    borderRadius: '8px',
    backgroundColor: '#1a1a1a',
    height: '80px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '4px',
  },
  panelLabel: {
    fontSize: '14px',
    color: '#888888',
  },
  panelLabelSmall: {
    fontSize: '12px',
    color: '#666666',
    textAlign: 'center',
  },
  panelSub: {
    fontSize: '12px',
    color: '#555555',
  },
};

export default MainContainer;
