import React, { useState } from 'react';
import { useAuth } from './hooks/useAuth';
import { Discover } from './pages/Discover';
import { Library } from './pages/Library';
import { Login } from './pages/Login';
import { Upload } from './pages/Upload';
import { Watch } from './pages/Watch';
import { Video } from './api/types';

export const App: React.FC = () => {
  const { user, login, logout, isAuthenticated } = useAuth();
  const [currentView, setCurrentView] = useState<'library' | 'discover' | 'upload' | 'watch'>('library');
  const [selectedVideo, setSelectedVideo] = useState<Video | null>(null);

  if (!isAuthenticated) {
    return <Login onLogin={login} />;
  }

  const handleSelectVideo = (v: Video) => {
    setSelectedVideo(v);
    setCurrentView('watch');
  };

  const handleVideoCreated = (v: Video) => {
    setSelectedVideo(v);
    setCurrentView('watch');
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Global Navbar */}
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
          padding: '12px 24px',
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border-color)',
        }}
      >
        {/* Brand & Main Navigation */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '24px', flexWrap: 'wrap' }}>
          <div
            onClick={() => setCurrentView('library')}
            style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}
          >
            <span style={{ fontSize: '1.4rem' }}>🎓</span>
            <h1 style={{ fontSize: '1.2rem', fontWeight: 700, letterSpacing: '-0.5px' }}>
              AskQuiz<span style={{ color: 'var(--accent-primary)' }}>.IQ</span>
            </h1>
          </div>

          <nav
            role="navigation"
            aria-label="Main Navigation"
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <button
              type="button"
              onClick={() => setCurrentView('library')}
              aria-current={currentView === 'library' ? 'page' : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 14px',
                fontSize: '0.85rem',
                fontWeight: 600,
                borderRadius: 'var(--radius-sm, 6px)',
                background: currentView === 'library' ? 'var(--bg-tertiary, #334155)' : 'transparent',
                color: currentView === 'library' ? '#ffffff' : 'var(--text-secondary, #94a3b8)',
                border: currentView === 'library' ? '1px solid var(--border-color, #475569)' : '1px solid transparent',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <span>📚</span> My Library
            </button>

            <button
              type="button"
              onClick={() => setCurrentView('discover')}
              aria-current={currentView === 'discover' ? 'page' : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 14px',
                fontSize: '0.85rem',
                fontWeight: 600,
                borderRadius: 'var(--radius-sm, 6px)',
                background: currentView === 'discover' ? 'var(--bg-tertiary, #334155)' : 'transparent',
                color: currentView === 'discover' ? '#ffffff' : 'var(--text-secondary, #94a3b8)',
                border: currentView === 'discover' ? '1px solid var(--border-color, #475569)' : '1px solid transparent',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <span>🔍</span> Discover
            </button>

            <button
              type="button"
              onClick={() => setCurrentView('upload')}
              aria-current={currentView === 'upload' ? 'page' : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 14px',
                fontSize: '0.85rem',
                fontWeight: 600,
                borderRadius: 'var(--radius-sm, 6px)',
                background: currentView === 'upload' ? 'var(--bg-tertiary, #334155)' : 'transparent',
                color: currentView === 'upload' ? '#ffffff' : 'var(--text-secondary, #94a3b8)',
                border: currentView === 'upload' ? '1px solid var(--border-color, #475569)' : '1px solid transparent',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <span>➕</span> Add Video
            </button>
          </nav>
        </div>

        {/* User Status & Sign Out */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            {user?.email}
          </span>
          <button
            onClick={logout}
            style={{
              padding: '6px 12px',
              fontSize: '0.8rem',
              color: 'var(--text-muted)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
            }}
          >
            Sign Out
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main style={{ flex: 1 }}>
        {currentView === 'library' && (
          <Library
            onSelectVideo={handleSelectVideo}
            onNewUpload={() => setCurrentView('upload')}
            onDiscover={() => setCurrentView('discover')}
          />
        )}
        {currentView === 'discover' && (
          <Discover
            onSelectVideo={handleSelectVideo}
            onGoToUpload={() => setCurrentView('upload')}
          />
        )}
        {currentView === 'upload' && (
          <Upload
            onVideoCreated={handleVideoCreated}
            onCancel={() => setCurrentView('library')}
          />
        )}
        {currentView === 'watch' && selectedVideo && (
          <Watch
            video={selectedVideo}
            onBack={() => setCurrentView('library')}
          />
        )}
      </main>
    </div>
  );
};

export default App;
