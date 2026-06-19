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
    border: '1px solid #111111',
    transition: 'opacity 0.15s',
  };

  const variantStyle: React.CSSProperties =
    variant === 'primary'
      ? { backgroundColor: '#111111', color: '#ffffff' }
      : { backgroundColor: '#ffffff', color: '#111111' };

  return (
    <button style={{ ...baseStyle, ...variantStyle }} onClick={onClick}>
      {label}
    </button>
  );
};

export default Button;
