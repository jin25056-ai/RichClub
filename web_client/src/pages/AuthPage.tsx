import React from 'react';
import Header from '../components/Header';
import AuthContainer from '../containers/AuthContainer';

const AuthPage: React.FC = () => {
  return (
    <>
      <Header />
      <AuthContainer />
    </>
  );
};

export default AuthPage;
