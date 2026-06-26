import React from 'react';
import { useNavigate } from 'react-router-dom';

interface PlanFeature {
  text: string;
  included: boolean;
}

interface Plan {
  id: string;
  name: string;
  price: string;
  priceDetail: string;
  description: React.ReactNode;
  color: string;
  borderColor: string;
  badge?: string;
  badgeColor?: string;
  features: PlanFeature[];
}

export const PLANS: Plan[] = [
  {
    id: 'basic-plan',
    name: '기본',
    price: '월 19,900원',
    priceDetail: '프로그램 이용료',
    description: '기본 기능 이용',
    color: '#6b7280',
    borderColor: '#374151',
    features: [
      { text: '글로벌 시장 현황', included: true },
      { text: '차트 (일봉 / 5분봉)', included: true },
      { text: '네이버 뉴스 검색', included: true },
      { text: '매매일지', included: true },
      { text: 'AI 예측 신호', included: false },
      { text: '지표 예측 (today-signals)', included: false },
      { text: '관심종목', included: false },
      { text: '골든보 / 침체구간 신호', included: false },
      { text: '텔레그램 알림', included: false },
    ],
  },
  {
    id: 'ju-model',
    name: 'Basic',
    price: '월 49,900원',
    priceDetail: '프로그램 이용료 포함',
    description: (
      <span>
        <span style={{ color: '#c084fc', fontWeight: 600 }}>ju-model-v2</span>
      </span>
    ),
    color: '#4ade80',
    borderColor: '#166534',
    features: [
      { text: '글로벌 시장 현황', included: true },
      { text: '차트 (일봉 / 5분봉)', included: true },
      { text: '네이버 뉴스 검색', included: true },
      { text: '매매일지', included: true },
      { text: 'AI 예측 신호 (ju-model-v2)', included: true },
      { text: '지표 예측 (today-signals)', included: true },
      { text: '관심종목', included: true },
      { text: '골든보 / 침체구간 신호', included: true },
      { text: '텔레그램 알림', included: false },
    ],
  },
  {
    id: 'seo-model',
    name: 'Pro',
    price: '월 149,900원',
    priceDetail: '프로그램 이용료 포함',
    description: (
      <span>
        <span style={{ color: '#c084fc', fontWeight: 600 }}>ju-model-v2</span>
        {' + '}
        <span style={{ color: '#f472b6', fontWeight: 600 }}>seo-model-v1</span>
      </span>
    ),
    color: '#a5b4fc',
    borderColor: '#3730a3',
    badge: '강력',
    features: [
      { text: '글로벌 시장 현황', included: true },
      { text: '차트 (일봉 / 5분봉)', included: true },
      { text: '네이버 뉴스 검색', included: true },
      { text: '매매일지', included: true },
      { text: 'AI 예측 신호 (ju-model-v2)', included: true },
      { text: 'AI 예측 신호 (seo-model-v1)', included: true },
      { text: '지표 예측 (today-signals)', included: true },
      { text: '관심종목', included: true },
      { text: '골든보 / 침체구간 신호', included: true },
      { text: '텔레그램 알림', included: true },
    ],
  },
  {
    id: 'telegram',
    name: '텔레그램',
    price: '월 79,900원',
    priceDetail: '채널 단독 구독',
    description: '채널 단독 구독',
    color: '#38bdf8',
    borderColor: '#075985',
    badge: '추천',
    badgeColor: '#0ea5e9',
    features: [
      { text: '텔레그램 알림 채널 구독', included: true },
      { text: 'AI 매수/매도 신호 알림', included: true },
      { text: '프로그램 접근', included: false },
      { text: '차트 / 지표 분석', included: false },
      { text: '매매일지', included: false },
    ],
  },
];

export const PlanCard: React.FC<{ plan: Plan; currentPlanId?: string }> = ({ plan, currentPlanId }) => {
  const isCurrent = currentPlanId === plan.id;
  const hasAnyPlan = !!currentPlanId;

  const buttonLabel = (() => {
    if (isCurrent) return '현재 이용 중';
    if (plan.id === 'telegram') return '구독 신청하기';
    if (hasAnyPlan) return '변경하기';
    return '선택하기';
  })();

  const badgeBackground = plan.badgeColor
    ? plan.badgeColor
    : 'linear-gradient(135deg, #7c3aed, #dc2626)';

  return (
    <div
      style={{
        background: '#0f0f1a',
        border: `1px solid ${isCurrent ? plan.color : plan.borderColor}`,
        borderRadius: 12,
        padding: '24px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
        flex: '1 1 180px',
        minWidth: 180,
        maxWidth: 260,
        position: 'relative',
      }}
    >
      {plan.badge && (
        <span
          style={{
            position: 'absolute',
            top: 14,
            right: 14,
            background: badgeBackground,
            color: '#fff',
            fontSize: 9,
            fontWeight: 700,
            padding: '2px 6px',
            borderRadius: 4,
            letterSpacing: '0.05em',
          }}
        >
          {plan.badge}
        </span>
      )}
      {isCurrent && (
        <span
          style={{
            position: 'absolute',
            top: 14,
            left: 14,
            background: plan.color + '22',
            color: plan.color,
            fontSize: 9,
            fontWeight: 700,
            padding: '2px 6px',
            borderRadius: 4,
            border: `1px solid ${plan.color}44`,
          }}
        >
          현재 플랜
        </span>
      )}

      <div style={{ marginTop: isCurrent ? 20 : 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: plan.color, marginBottom: 4 }}>
          {plan.name}
        </div>
        <div style={{ fontSize: 10, color: '#6b7280' }}>{plan.description}</div>
      </div>

      <div>
        <div style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0' }}>{plan.price}</div>
        {plan.priceDetail && (
          <div style={{ fontSize: 9, color: '#4b5563', marginTop: 3 }}>{plan.priceDetail}</div>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {plan.features.map((f, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <span style={{ fontSize: 10, color: f.included ? plan.color : '#374151', flexShrink: 0, width: 12, textAlign: 'center' }}>
              {f.included ? 'v' : 'x'}
            </span>
            <span style={{ fontSize: 10, color: f.included ? '#d1d5db' : '#374151' }}>
              {f.text}
            </span>
          </div>
        ))}
      </div>

      <button
        disabled={isCurrent}
        style={{
          marginTop: 'auto',
          width: '100%',
          padding: '9px 0',
          background: isCurrent
            ? 'transparent'
            : plan.id === 'basic-plan'
              ? 'transparent'
              : `linear-gradient(135deg, ${plan.color}cc, ${plan.color}88)`,
          border: `1px solid ${isCurrent ? '#2d2d3d' : plan.color}`,
          borderRadius: 6,
          color: isCurrent ? '#374151' : plan.id === 'basic-plan' ? plan.color : '#fff',
          fontSize: 11,
          fontWeight: 700,
          cursor: isCurrent ? 'default' : 'pointer',
          letterSpacing: '0.03em',
        }}
      >
        {buttonLabel}
      </button>
    </div>
  );
};

interface PricingContentProps {
  currentPlanId?: string;
}

export const PricingContent: React.FC<PricingContentProps> = ({ currentPlanId }) => (
  <div>
    <div style={{ marginBottom: 10 }}>
      <p style={{ fontSize: 10, color: '#4b5563', margin: 0 }}>
        * 프로그램 기본 사용료는 모든 유료 플랜에 포함됩니다.
      </p>
    </div>

    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 24 }}>
      {PLANS.map((plan) => (
        <PlanCard key={plan.id} plan={plan} currentPlanId={currentPlanId} />
      ))}
    </div>

    <div style={{ background: '#0a0a14', border: '1px solid #1e1e2e', borderRadius: 6, padding: '14px 16px' }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', marginBottom: 12 }}>후원하기</div>
      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
        {[['은행', '-'], ['계좌번호', '-'], ['예금주', '-']].map(([label, value]) => (
          <div key={label}>
            <div style={{ fontSize: 9, color: '#4b5563', marginBottom: 3 }}>{label}</div>
            <div style={{ fontSize: 12, color: '#d1d5db', fontWeight: 600 }}>{value}</div>
          </div>
        ))}
      </div>
      <div style={{ fontSize: 9, color: '#374151', marginTop: 10 }}>
        * 계좌 정보는 추후 업데이트 예정입니다.
      </div>
    </div>
  </div>
);

const PricingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div style={{ background: '#0a0a14', minHeight: '100vh', padding: '40px 24px', fontFamily: 'inherit', boxSizing: 'border-box' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 32 }}>
          <button
            onClick={() => navigate('/')}
            style={{ background: 'none', border: '1px solid #1e1e2e', color: '#6b7280', borderRadius: 4, padding: '4px 10px', fontSize: 11, cursor: 'pointer' }}
          >
            &lt; 돌아가기
          </button>
          <h1 style={{ fontSize: 16, fontWeight: 700, color: '#e2e8f0', margin: 0 }}>
            RichClub AI - 요금제
          </h1>
        </div>
        <PricingContent />
      </div>
    </div>
  );
};

export default PricingPage;
