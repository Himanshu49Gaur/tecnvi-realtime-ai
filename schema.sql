-- Supabase PostgreSQL Database Schema
-- Assignment: Realtime AI Backend (WebSockets + Supabase)

-- Enable UUID Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Primary Table: Sessions Metadata
CREATE TABLE IF NOT EXISTS public.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'anonymous',
    start_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time TIMESTAMPTZ,
    duration_seconds DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'active',
    summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast session lookup by session_id & user_id
CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON public.sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON public.sessions(user_id);

-- 2. Secondary Table: Detailed Event Log
CREATE TABLE IF NOT EXISTS public.session_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES public.sessions(session_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    sender TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for chronological timeline retrieval per session
CREATE INDEX IF NOT EXISTS idx_session_events_session_id_timestamp 
ON public.session_events(session_id, timestamp ASC);

-- Row Level Security (RLS) Policies (Optional/Recommended for Supabase)
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.session_events ENABLE ROW LEVEL SECURITY;

-- Allow public access for demonstration / API service role
CREATE POLICY "Allow public read/write to sessions" ON public.sessions FOR ALL USING (true);
CREATE POLICY "Allow public read/write to session_events" ON public.session_events FOR ALL USING (true);
