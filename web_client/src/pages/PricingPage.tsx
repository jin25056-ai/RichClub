import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { subscribePlan } from '../api/auth';

interface PlanFeature {
  text: string;
  included: boolean;
}

interface Plan {
  id: string;
  name: string;
  monthlyPrice: number; // 월 정가 (원)
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
    name: 'Demo',
    monthlyPrice: 19900,
    priceDetail: '프로그램 이용료',
    description: '기본 기능 이용',
    color: '#6b7280',
    borderColor: '#374151',
    features: [
      { text: '글로벌 시장 현황', included: true },
      { text: '차트 (일봉 / 5분봉)', included: true },
      { text: '네이버 뉴스 검색', included: true },
      { text: '매매일지', included: true },
      { text: '관심종목', included: true },
      { text: '골든보 / 침체구간 신호', included: true },
      { text: 'AI 예측 신호', included: false },
      { text: '지표 예측 (today-signals)', included: false },
      { text: '텔레그램 알림', included: false },
    ],
  },
  {
    id: 'ju-model',
    name: 'Basic',
    monthlyPrice: 49900,
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
    monthlyPrice: 149900,
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
    id: 'auto-trade',
    name: 'Max (자동매매)',
    monthlyPrice: 249000,
    priceDetail: '프로그램 이용료 포함',
    description: (
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span>
          <span style={{ color: '#c084fc', fontWeight: 600 }}>ju-model-v2</span>
          {' + '}
          <span style={{ color: '#f472b6', fontWeight: 600 }}>seo-model-v1</span>
        </span>
        <span style={{ color: '#6b7280' }}>키움 / 한국투자 API 연동</span>
      </span>
    ),
    color: '#fb923c',
    borderColor: '#7c2d12',
    badge: 'NEW',
    badgeColor: '#ea580c',
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
      { text: '키움증권 / 한국투자증권 자동매매', included: true },
      { text: '신규 모델 즉시 체험', included: true },
    ],
  },
  {
    id: 'telegram',
    name: '텔레그램',
    monthlyPrice: 79900,
    priceDetail: '채널 단독 구독',
    description: '채널 단독 구독',
    color: '#38bdf8',
    borderColor: '#075985',
    badge: '추천',
    badgeColor: '#0ea5e9',
    features: [
      { text: '텔레그램 알림 채널 구독', included: true },
      { text: 'AI 매수/매도 신호 알림', included: true },
      { text: '프로그램 접근', included: true },
      { text: '차트 / 지표 분석', included: false },
      { text: '매매일지', included: false },
    ],
  },
];

const ANNUAL_DISCOUNT = 0.2; // 20% 할인

const fmtPrice = (n: number) => n.toLocaleString('ko-KR');

const CheckIcon = ({ color }: { color: string }) => (
  <svg width="11" height="11" viewBox="0 0 12 12" fill="none" style={{ flexShrink: 0 }}>
    <path d="M2 6.5l3 3 5-6" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const CrossIcon = () => (
  <svg width="11" height="11" viewBox="0 0 12 12" fill="none" style={{ flexShrink: 0 }}>
    <circle cx="6" cy="6" r="6" fill="#374151" fillOpacity="0.3" />
    <path d="M4 4l4 4M8 4l-4 4" stroke="#4b5563" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

interface PlanCardProps {
  plan: Plan;
  currentPlanId?: string;
  isAnnual: boolean;
  onSubscribe?: (planId: string, planName: string, price: string) => void;
}

export const PlanCard: React.FC<PlanCardProps> = ({ plan, currentPlanId, isAnnual, onSubscribe }) => {
  const isCurrent = currentPlanId === plan.id;
  const hasAnyPlan = !!currentPlanId;

  const displayMonthly = isAnnual
    ? Math.floor(plan.monthlyPrice * (1 - ANNUAL_DISCOUNT))
    : plan.monthlyPrice;
  const annualTotal = Math.floor(plan.monthlyPrice * (1 - ANNUAL_DISCOUNT)) * 12;
  const originalAnnual = plan.monthlyPrice * 12;
  const savedAmount = originalAnnual - annualTotal;

  const priceStr = `월 ${fmtPrice(displayMonthly)}원`;

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
        flex: '1 1 160px',
        minWidth: 160,
        maxWidth: 220,
        position: 'relative',
      }}
    >
      {plan.badge && (
        <span style={{ position: 'absolute', top: 14, right: 14, background: badgeBackground, color: '#fff', fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 4, letterSpacing: '0.05em' }}>
          {plan.badge}
        </span>
      )}

      <div>
        <div style={{ fontSize: 13, fontWeight: 700, color: plan.color, marginBottom: 4 }}>{plan.name}</div>
        <div style={{ fontSize: 10, color: '#6b7280', minHeight: 32 }}>{plan.description}</div>
      </div>

      <div>
        {isAnnual && (
          <div style={{ fontSize: 9, color: '#4b5563', textDecoration: 'line-through', marginBottom: 2 }}>
            월 {fmtPrice(plan.monthlyPrice)}원
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0' }}>{priceStr}</div>
          {isAnnual && (
            <span style={{ fontSize: 9, color: '#4ade80', fontWeight: 700 }}>-20%</span>
          )}
        </div>
        {!isAnnual && (
          <div style={{ fontSize: 9, color: '#4b5563', marginTop: 3 }}>{plan.priceDetail}</div>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {plan.features.map((f, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            {f.included ? <CheckIcon color={plan.color} /> : <CrossIcon />}
            <span style={{ fontSize: 10, color: f.included ? '#d1d5db' : '#374151' }}>{f.text}</span>
          </div>
        ))}
      </div>

      <button
        disabled={isCurrent}
        onClick={() => !isCurrent && onSubscribe?.(plan.id, plan.name, priceStr)}
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

// 결제 확인 모달
interface ConfirmModalProps {
  planName: string;
  price: string;
  isAnnual: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}

const ConfirmModal: React.FC<ConfirmModalProps> = ({ planName, price, isAnnual, onConfirm, onCancel, loading }) => (
  <div
    onClick={onCancel}
    style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 3000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
  >
    <div
      onClick={(e) => e.stopPropagation()}
      style={{ background: '#0f0f1a', border: '1px solid #1e1e2e', borderRadius: 10, padding: '28px 28px', width: 360, maxWidth: '90vw' }}
    >
      <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', marginBottom: 8 }}>플랜 변경 확인</div>
      <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 20, lineHeight: 1.7 }}>
        <span style={{ color: '#d1d5db', fontWeight: 600 }}>{planName}</span> 플랜으로 변경합니다.<br />
        요금: <span style={{ color: '#d1d5db', fontWeight: 600 }}>{price}</span>
        {isAnnual && <span style={{ color: '#4ade80', marginLeft: 4, fontSize: 10 }}>(연간 결제 · 20% 할인)</span>}
      </div>
      <div style={{ background: '#0a0a14', border: '1px solid #1e1e2e', borderRadius: 6, padding: '10px 12px', marginBottom: 20 }}>
        <div style={{ fontSize: 9, color: '#4b5563', lineHeight: 1.7 }}>
          본 서비스는 투자 권유가 아니며, 모든 투자 결과는 이용자 본인에게 귀속됩니다. 원금 보장이 되지 않으며, 서비스 제공자는 투자 손실에 대한 법적 책임을 지지 않습니다.
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={onCancel} style={{ flex: 1, padding: '9px 0', background: 'transparent', border: '1px solid #2d2d3d', borderRadius: 6, color: '#6b7280', fontSize: 11, cursor: 'pointer' }}>
          취소
        </button>
        <button onClick={onConfirm} disabled={loading}
          style={{ flex: 1, padding: '9px 0', background: '#6366f1', border: 'none', borderRadius: 6, color: '#fff', fontSize: 11, fontWeight: 700, cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.7 : 1 }}>
          {loading ? '처리 중...' : '확인'}
        </button>
      </div>
    </div>
  </div>
);

interface PricingContentProps {
  currentPlanId?: string;
  onPlanChanged?: (newPlanId: string) => void;
}

export const PricingContent: React.FC<PricingContentProps> = ({ currentPlanId, onPlanChanged }) => {
  const [isAnnual, setIsAnnual] = useState(false);
  const [confirm, setConfirm] = useState<{ planId: string; planName: string; price: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleSubscribe = (planId: string, planName: string, price: string) => {
    setSuccessMsg(null);
    setConfirm({ planId, planName, price });
  };

  const handleConfirm = async () => {
    if (!confirm) return;
    setLoading(true);
    try {
      await subscribePlan(confirm.planId);
      setSuccessMsg(`${confirm.planName} 플랜으로 변경되었습니다.`);
      onPlanChanged?.(confirm.planId);
    } catch (e: any) {
      setSuccessMsg(e?.response?.data?.detail ?? '오류가 발생했습니다. 다시 시도해주세요.');
    } finally {
      setLoading(false);
      setConfirm(null);
    }
  };

  return (
    <div>
      {/* 월간 / 연간 토글 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <div style={{ display: 'inline-flex', background: '#0d0d1a', border: '1px solid #1e1e2e', borderRadius: 8, padding: 3 }}>
          <button
            onClick={() => setIsAnnual(false)}
            style={{
              padding: '6px 18px', fontSize: 11, fontWeight: isAnnual ? 400 : 700,
              borderRadius: 6, border: 'none', cursor: 'pointer',
              background: !isAnnual ? '#1e1e35' : 'transparent',
              color: !isAnnual ? '#a5b4fc' : '#4b5563',
              boxShadow: !isAnnual ? '0 0 0 1px #3730a344' : 'none',
            }}
          >
            월간
          </button>
          <button
            onClick={() => setIsAnnual(true)}
            style={{
              padding: '6px 18px', fontSize: 11, fontWeight: isAnnual ? 700 : 400,
              borderRadius: 6, border: 'none', cursor: 'pointer',
              background: isAnnual ? '#1e1e35' : 'transparent',
              color: isAnnual ? '#a5b4fc' : '#4b5563',
              boxShadow: isAnnual ? '0 0 0 1px #3730a344' : 'none',
            }}
          >
            연간
          </button>
        </div>
        {isAnnual && (
          <span style={{ fontSize: 10, color: '#4ade80', fontWeight: 700, background: '#14532d', border: '1px solid #166534', padding: '3px 8px', borderRadius: 4 }}>
            20% 절약
          </span>
        )}
        <p style={{ fontSize: 10, color: '#4b5563', margin: 0 }}>
          * 프로그램 기본 사용료는 모든 유료 플랜에 포함됩니다.
        </p>
      </div>

      {successMsg && (
        <div style={{ background: '#14532d', border: '1px solid #166534', borderRadius: 6, padding: '10px 14px', marginBottom: 14, fontSize: 11, color: '#4ade80' }}>
          {successMsg}
        </div>
      )}

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
        {PLANS.map((plan) => (
          <PlanCard key={plan.id} plan={plan} currentPlanId={currentPlanId} isAnnual={isAnnual} onSubscribe={handleSubscribe} />
        ))}
      </div>

      <div style={{ background: '#0a0a14', border: '1px solid #1e1e2e', borderRadius: 6, padding: '12px 16px' }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: '#4b5563', marginBottom: 6 }}>투자 위험 고지</div>
        <div style={{ fontSize: 9, color: '#374151', lineHeight: 1.8 }}>
          본 서비스는 투자 참고용 정보 제공 서비스이며, 투자 권유 또는 금융 자문이 아닙니다.
          AI 예측 신호 및 자동매매 기능은 시장 상황에 따라 손실이 발생할 수 있으며, 원금 보장이 되지 않습니다.
          모든 투자 결정과 그에 따른 손익은 전적으로 이용자 본인에게 귀속되며, 본 서비스 제공자는 투자 결과에 대한 법적 책임을 지지 않습니다.
          자동매매 기능 이용 시 증권사 API 연동 과정에서 발생하는 오류, 네트워크 장애, 시스템 점검 등으로 인한 손실에 대해서도 책임지지 않습니다.
        </div>
      </div>

      {confirm && (
        <ConfirmModal
          planName={confirm.planName}
          price={confirm.price}
          isAnnual={isAnnual}
          onConfirm={handleConfirm}
          onCancel={() => setConfirm(null)}
          loading={loading}
        />
      )}
    </div>
  );
};

const PricingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div style={{ background: '#0a0a14', minHeight: '100vh', padding: '40px 24px', fontFamily: 'inherit', boxSizing: 'border-box' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 32 }}>
          <button onClick={() => navigate('/')}
            style={{ background: 'none', border: '1px solid #1e1e2e', color: '#6b7280', borderRadius: 4, padding: '4px 10px', fontSize: 11, cursor: 'pointer' }}>
            &lt; 돌아가기
          </button>
          <h1 style={{ fontSize: 16, fontWeight: 700, color: '#e2e8f0', margin: 0 }}>RichClub AI - 요금제</h1>
        </div>
        <PricingContent />
      </div>
    </div>
  );
};

export default PricingPage;
