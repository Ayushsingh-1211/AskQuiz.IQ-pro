import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { YouTubePreviewOut, YouTubeSearchResultItem } from '../api/types';

interface DiscoveryPreviewModalProps {
  item: YouTubeSearchResultItem;
  onClose: () => void;
  onImport: (videoId: string, title?: string) => void;
  isImporting: boolean;
  isImported: boolean;
}

export const DiscoveryPreviewModal: React.FC<DiscoveryPreviewModalProps> = ({
  item,
  onClose,
  onImport,
  isImporting,
  isImported,
}) => {
  const [preview, setPreview] = useState<YouTubePreviewOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Close modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Fetch detailed preview from backend GET /api/v1/discovery/preview/{video_id}
  useEffect(() => {
    let active = true;
    const fetchPreview = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getYouTubePreview(item.video_id);
        if (active) {
          setPreview(data);
        }
      } catch (err: any) {
        if (active) {
          setError(err?.message || 'Failed to load video preview details.');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    fetchPreview();
    return () => {
      active = false;
    };
  }, [item.video_id]);

  const displayTitle = preview?.title || item.title;
  const channelTitle = preview?.channel_title || item.channel_title;
  const isEmbeddable = preview ? preview.is_embeddable : item.is_embeddable;
  const hasCaptions = preview ? preview.has_captions : item.has_captions;
  const captionNotice =
    preview?.caption_notice ||
    (hasCaptions
      ? 'Captions metadata found in YouTube (subject to extraction during ingestion).'
      : 'No caption tracks detected in YouTube metadata; audio will be transcribed using Whisper.');

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="preview-modal-title"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        zIndex: 1000,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: 'var(--bg-secondary, #1e293b)',
          borderRadius: 'var(--radius-md, 12px)',
          border: '1px solid var(--border-color, #334155)',
          width: '100%',
          maxWidth: '750px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: 'var(--shadow-lg, 0 10px 25px rgba(0, 0, 0, 0.5))',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '14px 20px',
            borderBottom: '1px solid var(--border-color, #334155)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '1.2rem' }}>📺</span>
            <h2
              id="preview-modal-title"
              style={{
                fontSize: '1.1rem',
                fontWeight: 600,
                color: 'var(--text-primary, #f8fafc)',
              }}
            >
              Video Preview
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close preview modal"
            style={{
              padding: '6px 10px',
              fontSize: '1rem',
              color: 'var(--text-secondary, #94a3b8)',
              background: 'transparent',
              border: 'none',
              borderRadius: 'var(--radius-sm, 6px)',
              cursor: 'pointer',
            }}
          >
            ✕
          </button>
        </div>

        {/* Video Player or Embeddability Guard */}
        <div style={{ background: '#000000', width: '100%', aspectRatio: '16/9', position: 'relative' }}>
          {isEmbeddable ? (
            <iframe
              src={`https://www.youtube-nocookie.com/embed/${item.video_id}?autoplay=1&modestbranding=1&rel=0`}
              title={displayTitle}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              style={{
                width: '100%',
                height: '100%',
                border: 'none',
              }}
            />
          ) : (
            <div
              style={{
                width: '100%',
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '24px',
                textAlign: 'center',
                background: 'rgba(239, 68, 68, 0.08)',
                color: 'var(--text-primary, #f8fafc)',
              }}
            >
              <span style={{ fontSize: '2.5rem', marginBottom: '8px' }}>🚫</span>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--accent-red, #ef4444)' }}>
                Embedding Disabled by Creator
              </h3>
              <p
                style={{
                  fontSize: '0.85rem',
                  color: 'var(--text-secondary, #94a3b8)',
                  maxWidth: '450px',
                  marginTop: '8px',
                }}
              >
                The owner of this video has disabled third-party playback. As a result, this video cannot be previewed
                or studied within AskQuiz.IQ.
              </p>
            </div>
          )}
        </div>

        {/* Content Body */}
        <div
          style={{
            padding: '18px 20px',
            overflowY: 'auto',
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}
        >
          {loading && (
            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary, #94a3b8)' }}>
              Checking embed status and caption metadata...
            </div>
          )}

          {error && (
            <div
              role="alert"
              style={{
                padding: '8px 12px',
                borderRadius: '6px',
                background: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid var(--accent-red, #ef4444)',
                color: '#fca5a5',
                fontSize: '0.85rem',
              }}
            >
              {error}
            </div>
          )}

          <div>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary, #f8fafc)', marginBottom: '4px' }}>
              {displayTitle}
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary, #94a3b8)' }}>
              Channel: <strong style={{ color: 'var(--text-primary, #f8fafc)' }}>{channelTitle}</strong> • Duration:{' '}
              {item.duration_formatted}
            </p>
          </div>

          {/* Caption notice banner */}
          <div
            style={{
              padding: '10px 14px',
              borderRadius: 'var(--radius-sm, 6px)',
              background: 'var(--bg-tertiary, #334155)',
              border: '1px solid var(--border-color, #475569)',
              fontSize: '0.8rem',
              lineHeight: 1.4,
              color: 'var(--text-secondary, #cbd5e1)',
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: '2px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>ℹ️</span> Transcription & Captions Note:
            </div>
            <div>{captionNotice}</div>
          </div>

          {/* Description */}
          {preview?.description && (
            <div>
              <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary, #94a3b8)', marginBottom: '4px' }}>
                Description
              </h4>
              <p
                style={{
                  fontSize: '0.8rem',
                  lineHeight: 1.5,
                  color: 'var(--text-muted, #94a3b8)',
                  whiteSpace: 'pre-line',
                  maxHeight: '120px',
                  overflowY: 'auto',
                  paddingRight: '6px',
                }}
              >
                {preview.description}
              </p>
            </div>
          )}
        </div>

        {/* Modal Footer Actions */}
        <div
          style={{
            padding: '14px 20px',
            borderTop: '1px solid var(--border-color, #334155)',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '12px',
            background: 'var(--bg-secondary, #1e293b)',
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '8px 16px',
              fontSize: '0.85rem',
              fontWeight: 500,
              color: 'var(--text-secondary, #94a3b8)',
              background: 'transparent',
              border: '1px solid var(--border-color, #475569)',
              borderRadius: 'var(--radius-sm, 6px)',
              cursor: 'pointer',
            }}
          >
            Close
          </button>

          <button
            type="button"
            disabled={!isEmbeddable || isImporting}
            onClick={() => onImport(item.video_id, displayTitle)}
            style={{
              padding: '8px 18px',
              fontSize: '0.85rem',
              fontWeight: 600,
              color: '#ffffff',
              background: !isEmbeddable
                ? 'var(--bg-tertiary, #334155)'
                : isImported
                ? 'var(--accent-green, #10b981)'
                : 'var(--accent-primary, #6366f1)',
              borderRadius: 'var(--radius-sm, 6px)',
              border: 'none',
              cursor: !isEmbeddable || isImporting ? 'not-allowed' : 'pointer',
              opacity: !isEmbeddable ? 0.6 : isImporting ? 0.8 : 1,
              transition: 'background 0.15s ease',
            }}
          >
            {isImporting ? '⏳ Importing...' : isImported ? '✓ Already in Library' : '📥 Import & Study'}
          </button>
        </div>
      </div>
    </div>
  );
};
