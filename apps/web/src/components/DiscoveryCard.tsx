import React from 'react';
import { YouTubeSearchResultItem } from '../api/types';

interface DiscoveryCardProps {
  item: YouTubeSearchResultItem;
  onPreview: (item: YouTubeSearchResultItem) => void;
  onImport: (item: YouTubeSearchResultItem) => void;
  isImporting: boolean;
  isImported: boolean;
}

export const DiscoveryCard: React.FC<DiscoveryCardProps> = ({
  item,
  onPreview,
  onImport,
  isImporting,
  isImported,
}) => {
  const formattedDate = item.published_at
    ? new Date(item.published_at).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : '';

  return (
    <article
      aria-label={`Video: ${item.title}`}
      style={{
        background: 'var(--bg-secondary, #1e293b)',
        borderRadius: 'var(--radius-md, 10px)',
        border: '1px solid var(--border-color, #334155)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease',
        boxShadow: 'var(--shadow-sm, 0 1px 2px rgba(0, 0, 0, 0.3))',
      }}
    >
      {/* Thumbnail Area */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          aspectRatio: '16/9',
          background: 'var(--bg-tertiary, #334155)',
          overflow: 'hidden',
        }}
      >
        <img
          src={item.thumbnail_url || `https://img.youtube.com/vi/${item.video_id}/hqdefault.jpg`}
          alt={item.title}
          loading="lazy"
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: 'block',
          }}
          onError={(e) => {
            // Fallback placeholder on image load failure
            (e.target as HTMLElement).style.display = 'none';
          }}
        />
        {/* Duration Badge */}
        {item.duration_formatted && (
          <span
            aria-label={`Duration: ${item.duration_formatted}`}
            style={{
              position: 'absolute',
              bottom: '8px',
              right: '8px',
              background: 'rgba(0, 0, 0, 0.8)',
              color: '#ffffff',
              padding: '2px 6px',
              borderRadius: '4px',
              fontSize: '0.75rem',
              fontWeight: 600,
              letterSpacing: '0.5px',
            }}
          >
            {item.duration_formatted}
          </span>
        )}
      </div>

      {/* Details Area */}
      <div
        style={{
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          flex: 1,
        }}
      >
        <h3
          title={item.title}
          style={{
            fontSize: '1rem',
            fontWeight: 600,
            lineHeight: 1.4,
            marginBottom: '6px',
            color: 'var(--text-primary, #f8fafc)',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {item.title}
        </h3>

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '0.8rem',
            color: 'var(--text-secondary, #94a3b8)',
            marginBottom: '12px',
          }}
        >
          <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            📺 {item.channel_title}
          </span>
          {formattedDate && <span style={{ flexShrink: 0, marginLeft: '8px' }}>{formattedDate}</span>}
        </div>

        {/* Badges Row */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px',
            marginBottom: '10px',
          }}
        >
          {/* Embeddability badge */}
          {item.is_embeddable ? (
            <span
              style={{
                fontSize: '0.7rem',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '12px',
                background: 'rgba(16, 185, 129, 0.15)',
                color: 'var(--accent-green, #10b981)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
              }}
            >
              ✓ Embeddable
            </span>
          ) : (
            <span
              style={{
                fontSize: '0.7rem',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '12px',
                background: 'rgba(239, 68, 68, 0.15)',
                color: 'var(--accent-red, #ef4444)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
              }}
            >
              ✕ No Embed
            </span>
          )}

          {/* Caption badge */}
          {item.has_captions ? (
            <span
              title="YouTube metadata indicates caption tracks exist. Extraction will be attempted during ingestion."
              style={{
                fontSize: '0.7rem',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '12px',
                background: 'rgba(99, 102, 241, 0.15)',
                color: 'var(--accent-primary, #6366f1)',
                border: '1px solid rgba(99, 102, 241, 0.3)',
              }}
            >
              CC Captions Available*
            </span>
          ) : (
            <span
              title="No caption track detected in YouTube metadata; audio will be transcribed using Whisper."
              style={{
                fontSize: '0.7rem',
                fontWeight: 500,
                padding: '2px 8px',
                borderRadius: '12px',
                background: 'rgba(100, 116, 139, 0.2)',
                color: 'var(--text-secondary, #94a3b8)',
                border: '1px solid var(--border-color, #334155)',
              }}
            >
              🎙 Audio Transcription
            </span>
          )}
        </div>

        {/* Caption Explanation Note */}
        <p
          style={{
            fontSize: '0.72rem',
            color: 'var(--text-muted, #64748b)',
            lineHeight: 1.35,
            marginBottom: '16px',
            fontStyle: 'italic',
          }}
        >
          *Caption metadata from YouTube does not guarantee successful transcript extraction; automatic Whisper ASR
          runs as a fallback.
        </p>

        {/* Actions Row */}
        <div
          style={{
            marginTop: 'auto',
            display: 'flex',
            gap: '8px',
          }}
        >
          <button
            type="button"
            onClick={() => onPreview(item)}
            aria-label={`Preview video ${item.title}`}
            style={{
              flex: 1,
              padding: '8px 12px',
              fontSize: '0.85rem',
              fontWeight: 600,
              color: 'var(--text-primary, #f8fafc)',
              background: 'var(--bg-tertiary, #334155)',
              borderRadius: 'var(--radius-sm, 6px)',
              border: '1px solid var(--border-color, #475569)',
              transition: 'background 0.15s ease',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '4px',
            }}
          >
            <span>👁</span> Preview
          </button>

          <button
            type="button"
            onClick={() => onImport(item)}
            disabled={isImporting || !item.is_embeddable}
            aria-label={
              !item.is_embeddable
                ? 'Cannot import this video because third-party embedding is disabled'
                : isImported
                ? `Imported: ${item.title}`
                : `Import and study ${item.title}`
            }
            style={{
              flex: 1.4,
              padding: '8px 12px',
              fontSize: '0.85rem',
              fontWeight: 600,
              color: '#ffffff',
              background: !item.is_embeddable
                ? 'var(--bg-tertiary, #334155)'
                : isImported
                ? 'var(--accent-green, #10b981)'
                : 'var(--accent-primary, #6366f1)',
              borderRadius: 'var(--radius-sm, 6px)',
              border: 'none',
              cursor: isImporting || !item.is_embeddable ? 'not-allowed' : 'pointer',
              opacity: !item.is_embeddable ? 0.6 : isImporting ? 0.8 : 1,
              transition: 'background 0.15s ease, opacity 0.15s ease',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '4px',
            }}
          >
            {isImporting ? (
              <span>⏳ Importing...</span>
            ) : isImported ? (
              <span>✓ Imported</span>
            ) : !item.is_embeddable ? (
              <span>✕ Disabled</span>
            ) : (
              <span>📥 Import & Study</span>
            )}
          </button>
        </div>
      </div>
    </article>
  );
};
