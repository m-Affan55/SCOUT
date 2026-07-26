import React from 'react';
import { ClerkProvider, SignedIn, SignedOut, RedirectToSignIn, SignIn, SignUp } from '@clerk/clerk-react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import WorkflowConsole from './components/WorkflowConsole';
import Onboarding from './components/Onboarding';
import './styles/Global.css';
import './styles/Auth.css';

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!clerkPubKey) {
  throw new Error("Missing Publishable Key");
}

// Clerk's baseTheme object supports custom colors to match our dark mode
const clerkAppearance = {
  variables: {
    colorBackground: '#111111',
    colorPrimary: '#3b82f6',
    colorText: '#ededed',
    colorInputBackground: '#0a0a0a',
    colorInputText: '#ededed',
    colorDanger: '#ef4444',
  },
  elements: {
    card: {
      border: '1px solid #1f1f1f',
      boxShadow: 'none',
      borderRadius: '12px'
    },
    headerTitle: {
      color: '#ededed'
    },
    headerSubtitle: {
      color: '#888888'
    },
    dividerLine: {
      background: '#1f1f1f'
    },
    dividerText: {
      color: '#888888'
    },
    socialButtonsBlockButton: {
      border: '1px solid #1f1f1f',
      color: '#ededed',
      background: '#0a0a0a'
    },
    formButtonPrimary: {
      textTransform: 'none',
      fontWeight: '500'
    },
    formFieldInput: {
      border: '1px solid #1f1f1f',
      borderRadius: '8px'
    },
    formFieldLabel: {
      color: '#888888'
    },
    footerActionText: {
      color: '#888888'
    },
    footerActionLink: {
      color: '#3b82f6'
    }
  }
};

function App() {
  return (
    <ClerkProvider publishableKey={clerkPubKey} appearance={clerkAppearance}>
      <BrowserRouter>
        <Routes>
          {/* Main App Route */}
          <Route path="/" element={
            <>
              <SignedIn>
                <WorkflowConsole />
              </SignedIn>
              <SignedOut>
                <RedirectToSignIn />
              </SignedOut>
            </>
          } />
          
          {/* Auth Routes */}
          <Route path="/sign-in/*" element={
            <div className="auth-container">
              <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" forceRedirectUrl="/onboarding" />
            </div>
          } />
          
          <Route path="/sign-up/*" element={
            <div className="auth-container">
              <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" forceRedirectUrl="/onboarding" />
            </div>
          } />

          {/* Custom Onboarding Route */}
          <Route path="/onboarding" element={
            <>
              <SignedIn>
                <Onboarding />
              </SignedIn>
              <SignedOut>
                <RedirectToSignIn />
              </SignedOut>
            </>
          } />
        </Routes>
      </BrowserRouter>
    </ClerkProvider>
  );
}

export default App;
