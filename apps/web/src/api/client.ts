import {
  ApiError,
  AskRequest,
  AskResponse,
  LoginResponse,
  Video,
  VideoList,
  YouTubePreviewOut,
  YouTubeQuotaStatusOut,
  YouTubeSearchResponse,
} from './types';

const API_BASE = import.meta.env.VITE_API_URL || '';

function getToken(): string | null {
  return localStorage.getItem('askquiz_token');
}

export function setToken(token: string) {
  localStorage.setItem('askquiz_token', token);
}

export function clearToken() {
  localStorage.removeItem('askquiz_token');
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = `${API_BASE}${endpoint}`;
  const resp = await fetch(url, { ...options, headers });

  if (!resp.ok) {
    let errData: ApiError;
    try {
      errData = await resp.json();
    } catch {
      errData = {
        code: `HTTP_${resp.status}`,
        message: resp.statusText || 'An unexpected error occurred',
      };
    }
    throw errData;
  }

  return resp.json();
}

export const api = {
  login: async (email: string, password: string): Promise<LoginResponse> => {
    const res = await request<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    setToken(res.access_token);
    return res;
  },

  listVideos: async (): Promise<VideoList> => {
    return request<VideoList>('/api/v1/videos');
  },

  getVideo: async (id: string): Promise<Video> => {
    return request<Video>(`/api/v1/videos/${id}`);
  },

  createVideoFromUrl: async (url: string, title?: string): Promise<Video> => {
    return request<Video>('/api/v1/videos', {
      method: 'POST',
      body: JSON.stringify({ url, title }),
    });
  },

  uploadVideo: async (file: File, title?: string): Promise<Video> => {
    const token = getToken();
    const formData = new FormData();
    formData.append('file', file);
    if (title) formData.append('title', title);

    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const resp = await fetch(`${API_BASE}/api/v1/videos/upload`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!resp.ok) {
      const err = await resp.json();
      throw err;
    }
    return resp.json();
  },

  ask: async (videoId: string, req: AskRequest): Promise<AskResponse> => {
    return request<AskResponse>(`/api/v1/videos/${videoId}/ask`, {
      method: 'POST',
      body: JSON.stringify(req),
    });
  },

  searchYouTube: async (query: string): Promise<YouTubeSearchResponse> => {
    return request<YouTubeSearchResponse>(`/api/v1/discovery/search?q=${encodeURIComponent(query)}`);
  },

  getYouTubePreview: async (videoId: string): Promise<YouTubePreviewOut> => {
    return request<YouTubePreviewOut>(`/api/v1/discovery/preview/${encodeURIComponent(videoId)}`);
  },

  importYouTubeVideo: async (videoId: string, title?: string): Promise<Video> => {
    return request<Video>('/api/v1/discovery/import', {
      method: 'POST',
      body: JSON.stringify({ video_id: videoId, title }),
    });
  },

  getYouTubeQuota: async (): Promise<YouTubeQuotaStatusOut> => {
    return request<YouTubeQuotaStatusOut>('/api/v1/discovery/quota');
  },
};
