import React from 'react';

export type AnswerMode = 'video' | 'web';

interface AnswerModeToggleProps {
  mode: AnswerMode;
  onChange: (mode: AnswerMode) => void;
  disabled?: boolean;
}

export const AnswerModeToggle: React.FC<AnswerModeToggleProps> = ({
  mode,
  onChange,
  disabled = false,
}) => {
  return (
    <div style={{ marginBottom: '10px' }}>
      <div
        role="group"
        aria-label="Answer Mode Selection"
        style={{
          display: 'flex',
          background: 'var(--bg-tertiary, #1f2937)',
          padding: '3px',
          borderRadius: '8px',
          border: '1px solid var(--border-color, rgba(255, 255, 255, 0.1))',
          gap: '4px',
        }}
      >
        <button
          type="button"
          aria-pressed={mode === 'video'}
          disabled={disabled}
          onClick={() => onChange('video')}
          style={{
            flex: 1,
            padding: '6px 12px',
            fontSize: '0.8rem',
            fontWeight: 600,
            borderRadius: '6px',
            border: 'none',
            cursor: disabled ? 'not-allowed' : 'pointer',
            transition: 'all 0.15s ease',
            background: mode === 'video' ? 'var(--accent-primary, #6366f1)' : 'transparent',
            color: mode === 'video' ? '#ffffff' : 'var(--text-secondary, #9ca3af)',
          }}
        >
          🎬 Video Only
        </button>

        <button
          type="button"
          aria-pressed={mode === 'web'}
          disabled={disabled}
          onClick={() => onChange('web')}
          style={{
            flex: 1,
            padding: '6px 12px',
            fontSize: '0.8rem',
            fontWeight: 600,
            borderRadius: '6px',
            border: 'none',
            cursor: disabled ? 'not-allowed' : 'pointer',
            transition: 'all 0.15s ease',
            background: mode === 'web' ? '#f59e0b' : 'transparent',
            color: mode === 'web' ? '#ffffff' : 'var(--text-secondary, #9ca3af)',
          }}
        >
          🌐 Web Research
        </button>
      </div>

      {mode === 'web' && (
        <div
          role="alert"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginTop: '8px',
            padding: '8px 12px',
            background: 'rgba(245, 158, 11, 0.12)',
            border: '1px solid rgba(245, 158, 11, 0.35)',
            borderRadius: '6px',
            color: '#fbbf24',
            fontSize: '0.78rem',
            lineHeight: 1.35,
          }}
        >
          <span style={{ fontSize: '1rem' }}>⚠️</span>
          <span>Web answers may reveal later parts of the video.</span>
        </div>
      )}
    </div>
  );
};
