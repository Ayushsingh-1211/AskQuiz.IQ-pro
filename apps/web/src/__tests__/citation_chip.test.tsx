import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CitationChip } from '../components/CitationChip';
import { Citation } from '../api/types';

describe('CitationChip Component', () => {
  it('renders video citation with pin icon and triggers onSeek on click', () => {
    const onSeek = vi.fn();
    const videoCitation: Citation = {
      chunk_id: 'c1',
      text: 'Transcript excerpt',
      source_ref: {
        source_type: 'transcript',
        chunk_id: 'c1',
        timestamp_s: 75.5,
        timestamp_formatted: '01:15',
        label: 'Video 01:15-01:35',
      },
    };

    render(<CitationChip citation={videoCitation} onSeek={onSeek} />);

    const btn = screen.getByRole('button');
    expect(btn.textContent).toContain('📌');
    expect(btn.textContent).toContain('Video 01:15-01:35');

    fireEvent.click(btn);
    expect(onSeek).toHaveBeenCalledTimes(1);
    expect(onSeek).toHaveBeenCalledWith(75.5);
  });

  it('renders clickable web citation with globe icon and opens URL safely in a new tab', () => {
    const onSeek = vi.fn();
    const webCitation: Citation = {
      chunk_id: 's1',
      text: 'Attention Is All You Need is a 2017 paper.',
      source_ref: {
        source_type: 'web',
        chunk_id: 's1',
        label: 'Attention Paper - arXiv',
        metadata: {
          url: 'https://arxiv.org/abs/1706.03762',
          title: 'Attention Paper - arXiv',
        },
      },
    };

    render(<CitationChip citation={webCitation} onSeek={onSeek} />);

    const link = screen.getByRole('link');
    expect(link.textContent).toContain('🌐');
    expect(link.textContent).toContain('Attention Paper - arXiv');
    expect(link.getAttribute('href')).toBe('https://arxiv.org/abs/1706.03762');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');

    // Should not call onSeek
    fireEvent.click(link);
    expect(onSeek).not.toHaveBeenCalled();
  });

  it('does not render untrusted HTML tags inside citation text or labels', () => {
    const untrustedCitation: Citation = {
      chunk_id: 's2',
      text: '<script>alert("hack")</script>',
      source_ref: {
        source_type: 'web',
        chunk_id: 's2',
        label: '<b>Malicious Title</b>',
        metadata: {
          url: 'https://safe-domain.org',
          title: '<b>Malicious Title</b>',
        },
      },
    };

    const { container } = render(<CitationChip citation={untrustedCitation} />);
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('b')).toBeNull();
    expect(container.textContent).toContain('<b>Malicious Title</b>');
  });
});
