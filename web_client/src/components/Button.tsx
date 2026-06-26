import React from 'react';

interface ButtonProps {
  label: string;
  onClick: () => void;
  variant?: 'primary' | 'outline';
  disabled?: boolean;
  fullWidth?: boolean;
}

const Button: React.FC<ButtonProps> = ({ label, onClick, variant = 'primary', disabled, fullWidth }) => {
  const style: React.CSSProperties = {
    padding: '11px 24px',
    fontSize: '14px',
    fontWeight: 600,
    borderRadius: '8px',
    cursor: disabled ? 'default' : 'pointer',
    transition: 'opacity 0.15s, background 0.15s',
    width: fullWidth ? '100%' : undefined,
    opacity: disabled ? 0.5 : 1,
    border: 'none',
    ...(variant === 'primary'
      ? { background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)', color: '#fff' }
      : { background: 'transparent', color: '#6b7280', border: '1.5px solid #1e1e2e' }),
  };

  return (
    <button style={style} onClick={disabled ? undefined : onClick}>
      {label}
    </button>
  );
};

export default Button;
