export interface User {
  id: string;
  email: string;
  full_name?: string;
  is_active: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Video {
  id: string;
  user_id: string;
  title: string;
  url?: string;
  file_path?: string;
  duration_s?: number;
  status: string;
  content_hash?: string;
  metadata?: Record<string, any>;
  created_at: string;
  visual_unavailable?: boolean;
  stream_url?: string;
  is_ready_text?: boolean;
  is_ready_full?: boolean;
}

export interface VideoList {
  items: Video[];
  total: number;
}

export interface SourceRef {
  source_type: string;
  chunk_id?: string;
  timestamp_s?: number;
  timestamp_formatted?: string;
  page_number?: number;
  slide_number?: number;
  label?: string;
  metadata?: Record<string, any>;
}

export interface Citation {
  chunk_id: string;
  text?: string;
  source_ref?: SourceRef;
}

export interface AskRequest {
  query: string;
  pause_t: number;
  session_id?: string;
  mode?: 'video' | 'web';
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  used_pause_frame: boolean;
  confidence: string;
  refusal: boolean;
  notes?: string;
  session_id: string;
  pause_t: number;
  mode?: 'video' | 'web';
}

export interface ApiError {
  code: string;
  message: string;
  hint?: string;
  request_id?: string;
}
