-- Migration 004: Add answer mode to messages table for AI conversation history
-- This migration requires manual approval and must not be executed automatically.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS mode VARCHAR(20) DEFAULT 'video';
CREATE INDEX IF NOT EXISTS idx_messages_mode ON messages(mode);
