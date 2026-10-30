import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Video, YouTubeQuotaStatusOut, YouTubeSearchResultItem } from '../api/types';
import { DiscoveryCard } from '../components/DiscoveryCard';
import { DiscoveryPreviewModal } from '../components/DiscoveryPreviewModal';

interface DiscoverProps {
  onSelectVideo: (video: Video) => void;
  onGoToUpload?: () => void;
}

const TOPIC_SUGGESTIONS = [
  'Linear Algebra',
  'Machine Learning',
  'Quantum Mechanics',
  'Data Structures',
  'World History',
  'Organic Chemistry',
];

export const Discover: React.FC<DiscoverProps> = ({ onSelectVideo, onGoToUpload }) => {
  const [query, setQuery] = useState('');
  const [lastSearchedQuery, setLastSearchedQuery] = useState('');
  const [results, setResults] = useState<YouTubeSearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Quota tracking
  const [quota, setQuota] = useState<YouTubeQuotaStatusOut | null>(null);
  const [loadingQuota, setLoadingQuota] = useState(false);

  // Preview & Import state
  const [previewItem, setPreviewItem] = useState<YouTubeSearchResultItem | null>(null);
  const [importingId, setImportingId] = useState<string | null>(null);
  const [importedVideos, setImportedVideos] = useState<Record<string, Video>>({});
  const [recentNotification, setRecentNotification] = useState<{
    type: 'success' | 'info' | 'error';
    message: string;
    video?: Video;
  } | null>(null);

  // Fetch quota on mount
  useEffect(() => {
    loadQuota();
  }, []);

  const loadQuota = async () => {
    setLoadingQuota(true);
    try {
      const q = await api.getYouTubeQuota();
      setQuota(q);
    } catch (err) {
      console.warn('Failed to fetch YouTube quota status', err);
    } finally {
      setLoadingQuota(false);
    }
  };

  const handleSearch = async (searchQuery: string) => {
    const trimmed = searchQuery.trim();
    setValidationError(null);
    setError(null);

    if (!trimmed) {
      setValidationError('Please enter a search topic.');
      return;
    }

    if (trimmed.length < 2) {
      setValidationError('Search query must be at least 2 characters long.');
      return;
    }

    if (trimmed.length > 100) {
      setValidationError('Search query cannot exceed 100 characters.');
      return;
    }

    // Avoid duplicate searches for identical query
    if (trimmed.toLowerCase() === lastSearchedQuery.toLowerCase() && results.length > 0) {
      return;
    }

    // Check client-side quota limit
    if (quota && quota.search_calls_remaining <= 0) {
      setError(
        'Daily YouTube search quota (70 searches/day) has been reached. Searches will reset at midnight Pacific Time. You can still import videos directly via URL.'
      );
      return;
    }

    setLoading(true);
    try {
      const res = await api.searchYouTube(trimmed);
      setResults(res.items || []);
      setLastSearchedQuery(trimmed);
      // Refresh quota status after a fresh search
      loadQuota();
    } catch (err: any) {
      if (err?.code === 'RATE_LIMIT_EXCEEDED' || err?.code === 'YOUTUBE_QUOTA_EXCEEDED') {
        setError(
          'Daily search limit reached. Quota resets daily at midnight Pacific Time. You can still paste any YouTube video URL on the Add Video tab.'
        );
      } else if (err?.code === 'DEGRADED_SERVICE') {
        setError('YouTube Discovery is currently disabled or unavailable on this server.');
      } else {
        setError(err?.message || 'Failed to search YouTube educational videos. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch(query);
  };

  const handleImport = async (videoId: string, title?: string) => {
    setImportingId(videoId);
    setRecentNotification(null);

    try {
      const createdVideo = await api.importYouTubeVideo(videoId, title);
      setImportedVideos((prev) => ({ ...prev, [videoId]: createdVideo }));

      const isDeduplicated = createdVideo.status !== 'queued';
      setRecentNotification({
        type: 'success',
        message: isDeduplicated
          ? `Video "${createdVideo.title}" is already in your library!`
          : `Successfully imported "${createdVideo.title}"! Background processing queued.`,
        video: createdVideo,
      });

      // If preview was open for this video, close it
      if (previewItem && previewItem.video_id === videoId) {
        setPreviewItem(null);
      }
    } catch (err: any) {
      setRecentNotification({
        type: 'error',
        message: err?.message || 'Failed to import video into your library.',
      });
    } finally {
      setImportingId(null);
    }
  };

  const isQuotaExhausted = quota !== null && quota.search_calls_remaining <= 0;

  return (
    <div style={{ maxWidth: '1100px', margin: '32px auto', padding: '0 20px' }}>
      {/* Page Header */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: '16px',
          marginBottom: '24px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span style={{ fontSize: '1.6rem' }}>🔍</span>
            <h2 style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--text-primary, #f8fafc)' }}>
              Discover Educational Videos
            </h2>
          </div>
          <p style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.9rem', maxWidth: '640px' }}>
            Search curated YouTube lectures and courses, preview embeddability and caption metadata, and import
            directly into your AskQuiz.IQ study workspace.
          </p>
        </div>

        {/* Quota Status Badge */}
        {quota && (
          <div
            style={{
              background: 'var(--bg-secondary, #1e293b)',
              border: '1px solid var(--border-color, #334155)',
              borderRadius: 'var(--radius-sm, 8px)',
              padding: '8px 14px',
              fontSize: '0.8rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '2px',
              minWidth: '220px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-muted, #64748b)', fontWeight: 500 }}>Daily Search Limit:</span>
              <span
                style={{
                  fontWeight: 700,
                  color: isQuotaExhausted ? 'var(--accent-red, #ef4444)' : 'var(--accent-green, #10b981)',
                }}
              >
                {quota.search_calls_remaining} / {quota.search_calls_limit} left
              </span>
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted, #64748b)' }}>
              Resets midnight Pacific (PT)
            </div>
          </div>
        )}
      </div>

      {/* Notification Banner */}
      {recentNotification && (
        <div
          role="alert"
          style={{
            marginBottom: '20px',
            padding: '12px 18px',
            borderRadius: 'var(--radius-sm, 8px)',
            background:
              recentNotification.type === 'success'
                ? 'rgba(16, 185, 129, 0.15)'
                : recentNotification.type === 'error'
                ? 'rgba(239, 68, 68, 0.15)'
                : 'rgba(99, 102, 241, 0.15)',
            border: `1px solid ${
              recentNotification.type === 'success'
                ? 'rgba(16, 185, 129, 0.4)'
                : recentNotification.type === 'error'
                ? 'rgba(239, 68, 68, 0.4)'
                : 'rgba(99, 102, 241, 0.4)'
            }`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <div style={{ fontSize: '0.88rem', color: '#ffffff' }}>
            <span style={{ marginRight: '6px' }}>
              {recentNotification.type === 'success' ? '✓' : recentNotification.type === 'error' ? '⚠️' : 'ℹ️'}
            </span>
            {recentNotification.message}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {recentNotification.video && (
              <button
                type="button"
                onClick={() => onSelectVideo(recentNotification.video!)}
                style={{
                  padding: '6px 14px',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  background: 'var(--accent-primary, #6366f1)',
                  color: '#ffffff',
                  borderRadius: 'var(--radius-sm, 6px)',
                  border: 'none',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                Study Now ▶️
              </button>
            )}
            <button
              type="button"
              onClick={() => setRecentNotification(null)}
              aria-label="Dismiss message"
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted, #94a3b8)',
                cursor: 'pointer',
                fontSize: '0.85rem',
                padding: '4px',
              }}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Search Input Box */}
      <form onSubmit={handleFormSubmit} style={{ marginBottom: '16px' }}>
        <div style={{ display: 'flex', gap: '10px' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <input
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                if (validationError) setValidationError(null);
              }}
              placeholder="Search educational topics (e.g. Machine Learning, Calculus, World History)..."
              disabled={loading || isQuotaExhausted}
              aria-label="Search educational YouTube videos"
              style={{
                width: '100%',
                padding: '12px 42px 12px 16px',
                background: 'var(--bg-secondary, #1e293b)',
                border: `1px solid ${validationError ? 'var(--accent-red, #ef4444)' : 'var(--border-color, #334155)'}`,
                borderRadius: 'var(--radius-sm, 8px)',
                color: 'var(--text-primary, #f8fafc)',
                fontSize: '0.95rem',
                outline: 'none',
                boxShadow: 'var(--shadow-sm, 0 1px 2px rgba(0, 0, 0, 0.3))',
              }}
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery('')}
                aria-label="Clear search query"
                style={{
                  position: 'absolute',
                  right: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted, #64748b)',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                }}
              >
                ✕
              </button>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || isQuotaExhausted}
            style={{
              padding: '12px 24px',
              fontSize: '0.9rem',
              fontWeight: 600,
              background: isQuotaExhausted ? 'var(--bg-tertiary, #334155)' : 'var(--accent-primary, #6366f1)',
              color: '#ffffff',
              borderRadius: 'var(--radius-sm, 8px)',
              border: 'none',
              cursor: loading || isQuotaExhausted ? 'not-allowed' : 'pointer',
              opacity: loading || isQuotaExhausted ? 0.6 : 1,
              whiteSpace: 'nowrap',
              transition: 'background 0.15s ease',
            }}
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>

        {validationError && (
          <div style={{ color: 'var(--accent-red, #ef4444)', fontSize: '0.8rem', marginTop: '6px', marginLeft: '4px' }}>
            {validationError}
          </div>
        )}
      </form>

      {/* Suggested Search Topics */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '28px' }}>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted, #64748b)', fontWeight: 500 }}>
          Popular topics:
        </span>
        {TOPIC_SUGGESTIONS.map((topic) => (
          <button
            key={topic}
            type="button"
            onClick={() => {
              setQuery(topic);
              handleSearch(topic);
            }}
            disabled={loading || isQuotaExhausted}
            style={{
              padding: '4px 10px',
              fontSize: '0.78rem',
              borderRadius: '16px',
              background: 'var(--bg-secondary, #1e293b)',
              color: 'var(--text-secondary, #94a3b8)',
              border: '1px solid var(--border-color, #334155)',
              cursor: loading || isQuotaExhausted ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            {topic}
          </button>
        ))}
      </div>

      {/* Error State */}
      {error && (
        <div
          role="alert"
          style={{
            padding: '24px',
            background: 'var(--bg-secondary, #1e293b)',
            borderRadius: 'var(--radius-md, 10px)',
            border: '1px solid var(--border-color, #334155)',
            textAlign: 'center',
            marginBottom: '30px',
          }}
        >
          <div style={{ fontSize: '2rem', marginBottom: '10px' }}>⚠️</div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary, #f8fafc)', marginBottom: '8px' }}>
            Search Unavailable
          </h3>
          <p style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.9rem', maxWidth: '500px', margin: '0 auto 16px' }}>
            {error}
          </p>
          {onGoToUpload && (
            <button
              type="button"
              onClick={onGoToUpload}
              style={{
                padding: '8px 16px',
                fontSize: '0.85rem',
                fontWeight: 600,
                color: '#ffffff',
                background: 'var(--accent-primary, #6366f1)',
                borderRadius: 'var(--radius-sm, 6px)',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Add Video via URL Instead
            </button>
          )}
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-secondary, #94a3b8)' }}>
          <div style={{ fontSize: '2.5rem', marginBottom: '16px', animation: 'pulse 1.5s infinite' }}>⏳</div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary, #f8fafc)' }}>
            Searching Educational Videos...
          </h3>
          <p style={{ fontSize: '0.85rem', marginTop: '6px' }}>
            Querying YouTube Data API and filtering for educational lectures and courses.
          </p>
        </div>
      )}

      {/* Empty Initial State (Before searching) */}
      {!loading && !error && results.length === 0 && !lastSearchedQuery && (
        <div
          style={{
            textAlign: 'center',
            padding: '60px 20px',
            background: 'var(--bg-secondary, #1e293b)',
            borderRadius: 'var(--radius-md, 10px)',
            border: '1px solid var(--border-color, #334155)',
          }}
        >
          <div style={{ fontSize: '3rem', marginBottom: '14px' }}>🎓</div>
          <h3 style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--text-primary, #f8fafc)' }}>
            Find Your Next Topic to Master
          </h3>
          <p
            style={{
              color: 'var(--text-secondary, #94a3b8)',
              fontSize: '0.9rem',
              maxWidth: '460px',
              margin: '8px auto 20px',
            }}
          >
            Search topics like "Quantum Mechanics", "Data Structures", or "Linear Algebra" to import high-yield lectures.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '10px' }}>
            <button
              type="button"
              onClick={() => {
                setQuery('Machine Learning');
                handleSearch('Machine Learning');
              }}
              style={{
                padding: '8px 16px',
                fontSize: '0.85rem',
                fontWeight: 600,
                background: 'var(--accent-primary, #6366f1)',
                color: '#ffffff',
                borderRadius: 'var(--radius-sm, 6px)',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Explore Machine Learning
            </button>
          </div>
        </div>
      )}

      {/* Empty Search Results (No videos found for query) */}
      {!loading && !error && results.length === 0 && lastSearchedQuery && (
        <div
          style={{
            textAlign: 'center',
            padding: '50px 20px',
            background: 'var(--bg-secondary, #1e293b)',
            borderRadius: 'var(--radius-md, 10px)',
            border: '1px solid var(--border-color, #334155)',
          }}
        >
          <div style={{ fontSize: '2.5rem', marginBottom: '12px' }}>🔎</div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary, #f8fafc)' }}>
            No Educational Videos Found
          </h3>
          <p
            style={{
              color: 'var(--text-secondary, #94a3b8)',
              fontSize: '0.9rem',
              maxWidth: '420px',
              margin: '6px auto 16px',
            }}
          >
            No educational results found for "{lastSearchedQuery}". Try broader educational keywords.
          </p>
        </div>
      )}

      {/* Results Grid */}
      {!loading && results.length > 0 && (
        <div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '16px',
            }}
          >
            <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary, #94a3b8)' }}>
              Found <strong style={{ color: 'var(--text-primary, #f8fafc)' }}>{results.length}</strong> videos for{' '}
              <em>"{lastSearchedQuery}"</em>
            </span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
              gap: '20px',
            }}
          >
            {results.map((item) => (
              <DiscoveryCard
                key={item.video_id}
                item={item}
                onPreview={(cardItem) => setPreviewItem(cardItem)}
                onImport={(cardItem) => handleImport(cardItem.video_id, cardItem.title)}
                isImporting={importingId === item.video_id}
                isImported={Boolean(importedVideos[item.video_id])}
              />
            ))}
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {previewItem && (
        <DiscoveryPreviewModal
          item={previewItem}
          onClose={() => setPreviewItem(null)}
          onImport={(vid, title) => handleImport(vid, title)}
          isImporting={importingId === previewItem.video_id}
          isImported={Boolean(importedVideos[previewItem.video_id])}
        />
      )}
    </div>
  );
};
