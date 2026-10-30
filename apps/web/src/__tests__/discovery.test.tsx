import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { App } from '../App';
import { Discover } from '../pages/Discover';
import { DiscoveryCard } from '../components/DiscoveryCard';
import { DiscoveryPreviewModal } from '../components/DiscoveryPreviewModal';
import { api } from '../api/client';
import {
  YouTubePreviewOut,
  YouTubeQuotaStatusOut,
  YouTubeSearchResultItem,
  Video,
} from '../api/types';

// Mock mock items
const MOCK_ITEM_EMBEDDABLE: YouTubeSearchResultItem = {
  video_id: 'test_vid101',
  title: 'Quantum Physics 101: Introduction',
  channel_title: 'MIT OpenCourseWare',
  description: 'Full introductory lecture on quantum mechanics and wavefunctions.',
  thumbnail_url: 'https://img.youtube.com/vi/test_vid101/hqdefault.jpg',
  published_at: '2024-03-01T12:00:00Z',
  duration_s: 3600,
  duration_formatted: '1:00:00',
  is_embeddable: true,
  has_captions: true,
  url: 'https://www.youtube.com/watch?v=test_vid101',
};

const MOCK_ITEM_NON_EMBEDDABLE: YouTubeSearchResultItem = {
  video_id: 'test_vid102',
  title: 'Protected Lecture: Embedding Disabled',
  channel_title: 'Restricted Channel',
  description: 'This video creator has disabled embedding.',
  thumbnail_url: 'https://img.youtube.com/vi/test_vid102/hqdefault.jpg',
  published_at: '2024-02-15T12:00:00Z',
  duration_s: 1800,
  duration_formatted: '30:00',
  is_embeddable: false,
  has_captions: false,
  url: 'https://www.youtube.com/watch?v=test_vid102',
};

const MOCK_PREVIEW: YouTubePreviewOut = {
  ...MOCK_ITEM_EMBEDDABLE,
  importable: true,
  import_notice: null,
  caption_notice: 'Captions metadata found in YouTube (subject to extraction during ingestion).',
};

const MOCK_QUOTA_NORMAL: YouTubeQuotaStatusOut = {
  date_pacific: '2026-10-30',
  timezone: 'America/Los_Angeles',
  next_reset_pt: '2026-10-31 00:00:00 PDT',
  next_reset_utc: '2026-10-31T07:00:00Z',
  seconds_until_reset: 14400,
  search_calls_used: 5,
  search_calls_limit: 70,
  search_calls_remaining: 65,
  videos_units_used: 12,
  videos_units_budget: 7000,
  videos_units_remaining: 6988,
};

const MOCK_QUOTA_EXHAUSTED: YouTubeQuotaStatusOut = {
  ...MOCK_QUOTA_NORMAL,
  search_calls_used: 70,
  search_calls_remaining: 0,
};

const MOCK_IMPORTED_VIDEO: Video = {
  id: 'video-uuid-1234',
  user_id: 'user-uuid-1',
  title: 'Quantum Physics 101: Introduction',
  url: 'https://www.youtube.com/watch?v=test_vid101',
  duration_s: 3600,
  status: 'queued',
  created_at: '2026-10-30T12:00:00Z',
};

describe('YouTube Discovery UI & Navigation Tests', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  // --------------------------------------------------------------------------
  // 1. Discover Navigation
  // --------------------------------------------------------------------------
  it('renders Discover navigation tab in navbar and switches views', async () => {
    // Authenticate user in localStorage
    localStorage.setItem('askquiz_token', 'valid-mock-token');

    vi.spyOn(api, 'listVideos').mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(api, 'getYouTubeQuota').mockResolvedValue(MOCK_QUOTA_NORMAL);

    render(<App />);

    // Initially on Library
    const libraryBtn = screen.getByRole('button', { name: /my library/i });
    expect(libraryBtn.getAttribute('aria-current')).toBe('page');

    // Find Discover tab
    const discoverBtn = screen.getByRole('button', { name: /discover/i });
    expect(discoverBtn).toBeTruthy();

    // Click Discover tab
    fireEvent.click(discoverBtn);

    // Active tab updates to discover
    expect(discoverBtn.getAttribute('aria-current')).toBe('page');
    expect(libraryBtn.getAttribute('aria-current')).toBeNull();

    // Discover page header is rendered
    expect(await screen.findByRole('heading', { name: /discover educational videos/i })).toBeTruthy();
  });

  // --------------------------------------------------------------------------
  // 2. Successful Search
  // --------------------------------------------------------------------------
  it('performs educational search and renders video result cards', async () => {
    vi.spyOn(api, 'getYouTubeQuota').mockResolvedValue(MOCK_QUOTA_NORMAL);
    const searchSpy = vi.spyOn(api, 'searchYouTube').mockResolvedValue({
      query: 'Quantum Physics',
      items: [MOCK_ITEM_EMBEDDABLE],
      total: 1,
    });

    const onSelectVideo = vi.fn();
    render(<Discover onSelectVideo={onSelectVideo} />);

    // Enter query
    const input = screen.getByPlaceholderText(/search educational topics/i);
    fireEvent.change(input, { target: { value: 'Quantum Physics' } });

    // Submit search
    const searchBtn = screen.getByRole('button', { name: /^search$/i });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(searchSpy).toHaveBeenCalledWith('Quantum Physics');
    });

    // Card should be rendered
    expect(await screen.findByText('Quantum Physics 101: Introduction')).toBeTruthy();
    expect(screen.getByText(/MIT OpenCourseWare/i)).toBeTruthy();
    expect(screen.getByText('1:00:00')).toBeTruthy();
  });

  // --------------------------------------------------------------------------
  // 3. Empty Search Results
  // --------------------------------------------------------------------------
  it('displays empty state when no educational videos are found for query', async () => {
    vi.spyOn(api, 'getYouTubeQuota').mockResolvedValue(MOCK_QUOTA_NORMAL);
    vi.spyOn(api, 'searchYouTube').mockResolvedValue({
      query: 'UnusualTopicName999',
      items: [],
      total: 0,
    });

    render(<Discover onSelectVideo={vi.fn()} />);

    const input = screen.getByPlaceholderText(/search educational topics/i);
    fireEvent.change(input, { target: { value: 'UnusualTopicName999' } });
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }));

    expect(await screen.findByRole('heading', { name: /no educational videos found/i })).toBeTruthy();
    expect(screen.getByText(/no educational results found for "UnusualTopicName999"/i)).toBeTruthy();
  });

  // --------------------------------------------------------------------------
  // 4. Search API Errors
  // --------------------------------------------------------------------------
  it('displays understandable error message on API failure', async () => {
    vi.spyOn(api, 'getYouTubeQuota').mockResolvedValue(MOCK_QUOTA_NORMAL);
    vi.spyOn(api, 'searchYouTube').mockRejectedValue({
      code: 'YOUTUBE_API_ERROR',
      message: 'YouTube API is currently unreachable. Please try again.',
    });

    render(<Discover onSelectVideo={vi.fn()} />);

    const input = screen.getByPlaceholderText(/search educational topics/i);
    fireEvent.change(input, { target: { value: 'Linear Algebra' } });
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }));

    const errorAlert = await screen.findByRole('alert');
    expect(errorAlert.textContent).toContain('YouTube API is currently unreachable');
  });

  // --------------------------------------------------------------------------
  // 5. Video Card Rendering (Badges, Thumbnail, Captions Disclaimer)
  // --------------------------------------------------------------------------
  it('renders embeddability badge, caption badge and disclaimer footnote on card', () => {
    render(
      <DiscoveryCard
        item={MOCK_ITEM_EMBEDDABLE}
        onPreview={vi.fn()}
        onImport={vi.fn()}
        isImporting={false}
        isImported={false}
      />
    );

    // Embeddable badge
    expect(screen.getByText('✓ Embeddable')).toBeTruthy();

    // Caption badge
    expect(screen.getByText('CC Captions Available*')).toBeTruthy();

    // Disclaimer footnote
    expect(
      screen.getByText(
        /\*Caption metadata from YouTube does not guarantee successful transcript extraction/i
      )
    ).toBeTruthy();

    // Duration badge
    expect(screen.getByText('1:00:00')).toBeTruthy();
  });

  // --------------------------------------------------------------------------
  // 6. Video Preview Behavior
  // --------------------------------------------------------------------------
  it('opens preview modal, displays iframe embed, and closes on Escape', async () => {
    const previewSpy = vi.spyOn(api, 'getYouTubePreview').mockResolvedValue(MOCK_PREVIEW);

    const onClose = vi.fn();
    const onImport = vi.fn();

    render(
      <DiscoveryPreviewModal
        item={MOCK_ITEM_EMBEDDABLE}
        onClose={onClose}
        onImport={onImport}
        isImporting={false}
        isImported={false}
      />
    );

    // Calls backend preview endpoint
    expect(previewSpy).toHaveBeenCalledWith('test_vid101');

    // Title and channel rendered
    expect(await screen.findByRole('heading', { name: /video preview/i })).toBeTruthy();
    expect(screen.getByText('Quantum Physics 101: Introduction')).toBeTruthy();

    // Verify permitted iframe player is present
    const iframe = screen.getByTitle('Quantum Physics 101: Introduction');
    expect(iframe).toBeTruthy();
    expect(iframe.getAttribute('src')).toContain('youtube-nocookie.com/embed/test_vid101');

    // Close on Escape key
    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('displays warning when preview video embedding is disabled by creator', async () => {
    vi.spyOn(api, 'getYouTubePreview').mockResolvedValue({
      ...MOCK_PREVIEW,
      is_embeddable: false,
      importable: false,
      import_notice: 'The owner of this video has disabled third-party embedding.',
    });

    render(
      <DiscoveryPreviewModal
        item={MOCK_ITEM_NON_EMBEDDABLE}
        onClose={vi.fn()}
        onImport={vi.fn()}
        isImporting={false}
        isImported={false}
      />
    );

    expect(await screen.findByText(/embedding disabled by creator/i)).toBeTruthy();
  });

  // --------------------------------------------------------------------------
  // 7. Successful Import
  // --------------------------------------------------------------------------
  it('imports video, shows success notification, and navigates to player on Study Now', async () => {
    vi.spyOn(api, 'getYouTubeQuota').mockResolvedValue(MOCK_QUOTA_NORMAL);
    vi.spyOn(api, 'searchYouTube').mockResolvedValue({
      query: 'Quantum Physics',
      items: [MOCK_ITEM_EMBEDDABLE],
      total: 1,
    });
    const importSpy = vi.spyOn(api, 'importYouTubeVideo').mockResolvedValue(MOCK_IMPORTED_VIDEO);

    const onSelectVideo = vi.fn();
    render(<Discover onSelectVideo={onSelectVideo} />);

    // Perform search
    const input = screen.getByPlaceholderText(/search educational topics/i);
    fireEvent.change(input, { target: { value: 'Quantum Physics' } });
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }));

    // Click Import & Study on the card
    const importBtn = await screen.findByRole('button', { name: /import and study/i });
    fireEvent.click(importBtn);

    await waitFor(() => {
      expect(importSpy).toHaveBeenCalledWith('test_vid101', 'Quantum Physics 101: Introduction');
    });

    // Success notification banner
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Successfully imported');

    // Click "Study Now ▶️"
    const studyNowBtn = screen.getByRole('button', { name: /study now/i });
    fireEvent.click(studyNowBtn);
    expect(onSelectVideo).toHaveBeenCalledWith(MOCK_IMPORTED_VIDEO);
  });

  // --------------------------------------------------------------------------
  // 8. Duplicate Import
  // --------------------------------------------------------------------------
  it('handles duplicate video import gracefully and indicates already in library', async () => {
    vi.spyOn(api, 'getYouTubeQuota').mockResolvedValue(MOCK_QUOTA_NORMAL);
    vi.spyOn(api, 'searchYouTube').mockResolvedValue({
      query: 'Quantum Physics',
      items: [MOCK_ITEM_EMBEDDABLE],
      total: 1,
    });
    // Duplicate import returns existing video with status 'ready_text'
    const duplicateVideo: Video = {
      ...MOCK_IMPORTED_VIDEO,
      status: 'ready_text',
    };
    vi.spyOn(api, 'importYouTubeVideo').mockResolvedValue(duplicateVideo);

    render(<Discover onSelectVideo={vi.fn()} />);

    const input = screen.getByPlaceholderText(/search educational topics/i);
    fireEvent.change(input, { target: { value: 'Quantum Physics' } });
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }));

    const importBtn = await screen.findByRole('button', { name: /import and study/i });
    fireEvent.click(importBtn);

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('already in your library');
  });

  // --------------------------------------------------------------------------
  // 9. Quota-Exceeded Behavior
  // --------------------------------------------------------------------------
  it('displays quota status and disables search when daily quota is exhausted', async () => {
    vi.spyOn(api, 'getYouTubeQuota').mockResolvedValue(MOCK_QUOTA_EXHAUSTED);

    render(<Discover onSelectVideo={vi.fn()} />);

    // Quota display shows 0 / 70 left
    expect(await screen.findByText('0 / 70 left')).toBeTruthy();

    // Search button is disabled
    const searchBtn = screen.getByRole('button', { name: /^search$/i });
    expect(searchBtn.getAttribute('disabled')).toBeDefined();

    // Search input is disabled
    const input = screen.getByPlaceholderText(/search educational topics/i);
    expect(input.getAttribute('disabled')).toBeDefined();
  });

  it('handles 429 RATE_LIMIT_EXCEEDED error with clear Pacific reset message', async () => {
    vi.spyOn(api, 'getYouTubeQuota').mockResolvedValue(MOCK_QUOTA_NORMAL);
    vi.spyOn(api, 'searchYouTube').mockRejectedValue({
      code: 'RATE_LIMIT_EXCEEDED',
      message: 'Daily YouTube search limit reached. Limit resets at Pacific midnight.',
    });

    render(<Discover onSelectVideo={vi.fn()} />);

    const input = screen.getByPlaceholderText(/search educational topics/i);
    fireEvent.change(input, { target: { value: 'Machine Learning' } });
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Daily search limit reached');
    expect(alert.textContent).toContain('Pacific Time');
  });

  // --------------------------------------------------------------------------
  // 10. Authentication / Session Handling
  // --------------------------------------------------------------------------
  it('redirects to Login screen when unauthenticated', () => {
    // No token in localStorage
    localStorage.removeItem('askquiz_token');

    render(<App />);

    // Shows login form, not main navbar or Discover
    expect(screen.getByRole('heading', { name: /askquiz\.iq/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /discover/i })).toBeNull();
  });
});
