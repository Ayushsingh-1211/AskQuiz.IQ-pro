import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Video } from '../api/types';

interface LibraryProps {
  onSelectVideo: (video: Video) => void;
  onNewUpload: () => void;
  onDiscover?: () => void;
}

export const Library: React.FC<LibraryProps> = ({ onSelectVideo, onNewUpload, onDiscover }) => {
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadVideos();
  }, []);

  const loadVideos = async () => {
    setLoading(true);
    try {
      const res = await api.listVideos();
      setVideos(res.items);
    } catch (err) {
      console.error('Failed to load videos', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '40px auto', padding: '0 20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '1.6rem', fontWeight: 700 }}>Your Video Library</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Choose a lecture to watch and ask questions</p>
        </div>
        <button
          onClick={onNewUpload}
          style={{ padding: '10px 18px', background: 'var(--accent-primary)', color: '#fff', borderRadius: 'var(--radius-sm)', fontWeight: 600 }}
        >
          + Add New Video
        </button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>Loading lectures...</div>
      ) : videos.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
          <p style={{ fontSize: '2rem', marginBottom: '12px' }}>🎬</p>
          <h3>No videos yet</h3>
          <p style={{ color: 'var(--text-secondary)', margin: '8px 0 16px' }}>Upload an MP4 or enter a YouTube URL to get started.</p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <button
              onClick={onNewUpload}
              style={{ padding: '10px 20px', background: 'var(--accent-primary)', color: '#fff', borderRadius: 'var(--radius-sm)' }}
            >
              Upload your first video
            </button>
            {onDiscover && (
              <button
                onClick={onDiscover}
                style={{
                  padding: '10px 20px',
                  background: 'var(--bg-tertiary, #334155)',
                  color: '#fff',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-color, #475569)',
                }}
              >
                🔍 Discover on YouTube
              </button>
            )}
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '20px' }}>
          {videos.map((v) => (
            <div
              key={v.id}
              onClick={() => onSelectVideo(v)}
              style={{
                background: 'var(--bg-secondary)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border-color)',
                padding: '16px',
                cursor: 'pointer',
                transition: 'transform 0.15s ease, border-color 0.15s ease',
              }}
            >
              <div style={{ width: '100%', aspectRatio: '16/9', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2rem', marginBottom: '12px' }}>
                ▶️
              </div>
              <h4 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {v.title}
              </h4>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                <span>Status: <strong style={{ color: v.is_ready_text ? 'var(--accent-green)' : 'var(--accent-amber)' }}>{v.status}</strong></span>
                <span>{v.duration_s ? `${Math.floor(v.duration_s / 60)}m` : ''}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
