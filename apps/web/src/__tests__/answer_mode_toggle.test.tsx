import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AnswerModeToggle } from '../components/AnswerModeToggle';

describe('AnswerModeToggle Component', () => {
  it('renders Video Only as active and hides spoiler warning', () => {
    const onChange = vi.fn();
    render(<AnswerModeToggle mode="video" onChange={onChange} />);

    const videoBtn = screen.getByRole('button', { name: /video only/i });
    const webBtn = screen.getByRole('button', { name: /web research/i });

    expect(videoBtn.getAttribute('aria-pressed')).toBe('true');
    expect(webBtn.getAttribute('aria-pressed')).toBe('false');

    // Warning should NOT be present in video mode
    expect(screen.queryByText(/Web answers may reveal later parts of the video/i)).toBeNull();
  });

  it('triggers onChange with "web" when clicking Web Research', () => {
    const onChange = vi.fn();
    render(<AnswerModeToggle mode="video" onChange={onChange} />);

    const webBtn = screen.getByRole('button', { name: /web research/i });
    fireEvent.click(webBtn);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('web');
  });

  it('displays the required spoiler warning when Web Research mode is active', () => {
    const onChange = vi.fn();
    render(<AnswerModeToggle mode="web" onChange={onChange} />);

    const webBtn = screen.getByRole('button', { name: /web research/i });
    expect(webBtn.getAttribute('aria-pressed')).toBe('true');

    // Exactly matches required warning text: "Web answers may reveal later parts of the video."
    const warning = screen.getByRole('alert');
    expect(warning).toBeTruthy();
    expect(warning.textContent).toContain('Web answers may reveal later parts of the video.');
  });
});
