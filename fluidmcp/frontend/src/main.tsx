import React from 'react'
import ReactDOM from "react-dom/client";
import { BrowserRouter } from 'react-router-dom';
import './index.css'
import './styles/globals.css'
import App from './App.tsx'
import { ThemeProvider } from './components/theme-provider.tsx'
import { AuthProvider } from './contexts/AuthContext'

// Entry point of the React application.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
        <div className="min-h-screen bg-background font-sans antialiased" style={{ fontFamily: 'Inter, sans-serif' }}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </div>
      </ThemeProvider>
    </AuthProvider>
  </React.StrictMode>,
)