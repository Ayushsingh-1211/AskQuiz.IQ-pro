import React from 'react';
import { AskBox } from './AskBox';
import { AnswerMode, AnswerModeToggle } from './AnswerModeToggle';
import { CitationChip } from './CitationChip';
import { Citation } from '../api/types';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  pause_t: number;
  citations?: Citation[];
  refusal?: boolean;
  mode?: 'video' | 'web';
}

interface ChatPanelProps {
  messages: ChatMessage[];
  currentTime: number;
  onPause: () => void;
  onAsk: (query: string, pause_t: number) => void;
  onSeek: (seconds: number) => void;
  isLoading?: boolean;
  mode: AnswerMode;
  onModeChange: (mode: AnswerMode) => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  currentTime,
  onPause,
  onAsk,
  onSeek,
  isLoading = false,
  mode,
  onModeChange,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--bg-secondary)',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border-color)',
        padding: '16px',
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '12px', borderBottom: '1px solid var(--border-color)' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Pause & Ask Assistant</h3>
        {mode === 'video' ? (
          <span style={{ fontSize: '0.75rem', color: 'var(--accent-green)', background: 'rgba(16, 185, 129, 0.15)', padding: '2px 8px', borderRadius: '12px' }}>
            TAC Active (No Spoilers)
          </span>
        ) : (
          <span style={{ fontSize: '0.75rem', color: '#fbbf24', background: 'rgba(245, 158, 11, 0.15)', padding: '2px 8px', borderRadius: '12px' }}>
            Web Research Active
          </span>
        )}
      </div>

      <div style={{ paddingTop: '10px' }}>
        <AnswerModeToggle mode={mode} onChange={onModeChange} disabled={isLoading} />
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 0', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {messages.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', margin: 'auto', padding: '20px' }}>
            <p style={{ fontSize: '1.5rem', marginBottom: '8px' }}>⏸️ 💬</p>
            <p style={{ fontWeight: 500 }}>Pause the video at any point to ask questions.</p>
            <p style={{ fontSize: '0.8rem', marginTop: '6px' }}>
              {mode === 'video'
                ? 'Answers use only what you have seen/heard up to that moment.'
                : 'Web answers search external sources and may reveal forward concepts.'}
            </p>
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '85%',
                background: m.role === 'user' ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
                color: 'var(--text-primary)',
                padding: '10px 14px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.9rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', opacity: 0.8, marginBottom: '4px', gap: '8px' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span>{m.role === 'user' ? 'You' : 'Assistant'}</span>
                  {m.role === 'assistant' && (
                    <span style={{ fontSize: '0.65rem', padding: '1px 5px', borderRadius: '4px', background: m.mode === 'web' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(99, 102, 241, 0.2)', color: m.mode === 'web' ? '#fbbf24' : '#a5b4fc' }}>
                      {m.mode === 'web' ? 'Web' : 'Video'}
                    </span>
                  )}
                </span>
                <span>@{Math.floor(m.pause_t / 60)}:{(Math.floor(m.pause_t % 60)).toString().padStart(2, '0')}</span>
              </div>
              <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.4 }}>{m.content}</p>

              {m.citations && m.citations.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px', paddingTop: '6px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                  {m.citations.map((c, i) => (
                    <CitationChip key={i} citation={c} onSeek={onSeek} />
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <AskBox currentTime={currentTime} onPause={onPause} onSubmit={onAsk} isLoading={isLoading} />
    </div>
  );
};
