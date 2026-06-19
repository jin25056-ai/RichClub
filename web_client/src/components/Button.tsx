import React from 'react';

interface ButtonProps {
  label: string;
  onClick: () => void;
  variant?: 'primary' | 'outline';
}

const Button: React.FC<ButtonProps> = ({ label, onClick, variant = 'primary' }) => {
  const baseStyle: React.CSSProperties = {
    padding: '10px 24px',
    fontSize: '14px',
    fontWeight: 600,
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'opacity 0.15s',
  };

  const variantStyle: React.CSSProperties =
    variant === 'primary'
      ? { backgroundColor: '#ffffff', color: '#111111', border: '1px solid #ffffff' }
      : { backgroundColor: 'transparent', color: '#888888', border: '1px solid #2a2a2a' };

  return (
    <button style={{ ...baseStyle, ...variantStyle }} onClick={onClick}>
      {label}
    </button>
  );
};

export default Button;
