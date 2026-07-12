-- ----------------------------------------------------
-- DATABASE SCHEMA MIGRATION: PHASE 2
-- ----------------------------------------------------

-- Enable pgvector and uuid-ossp extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Profiles Table
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'user')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Documents Table
CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    filename VARCHAR(255) NOT NULL,
    file_url TEXT,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. Document Chunks Table (using Cohere 1024-dimension embeddings)
CREATE TABLE IF NOT EXISTS public.document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES public.documents(id) ON DELETE CASCADE NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1024) NOT NULL,
    page_number INTEGER,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create HNSW Index on pgvector embeddings for fast Cosine distance search
CREATE INDEX IF NOT EXISTS document_chunks_embedding_cosine_hnsw_idx 
ON public.document_chunks USING hnsw (embedding vector_cosine_ops);

-- 4. Document Shares Table (For peer-to-peer sharing)
CREATE TABLE IF NOT EXISTS public.document_shares (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES public.documents(id) ON DELETE CASCADE NOT NULL,
    shared_with_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(document_id, shared_with_user_id)
);

-- 5. Metrics Table
CREATE TABLE IF NOT EXISTS public.metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    metric_type VARCHAR(20) NOT NULL CHECK (metric_type IN ('query', 'upload')),
    tokens_used INTEGER DEFAULT 0,
    cost_usd NUMERIC(10, 6) DEFAULT 0.000000,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 6. Hallucination Logs Table
CREATE TABLE IF NOT EXISTS public.hallucination_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    response TEXT NOT NULL,
    context_retrieved TEXT NOT NULL,
    confidence_score NUMERIC(5, 4) NOT NULL,
    evaluation_status VARCHAR(20) DEFAULT 'approved' CHECK (evaluation_status IN ('flagged', 'approved')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- ----------------------------------------------------
-- ROW LEVEL SECURITY (RLS) & HELPER FUNCTIONS
-- ----------------------------------------------------

-- Security Helper Function (Avoids recursion and caches checks)
CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS BOOLEAN
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = (SELECT auth.uid()) AND role = 'admin'
  );
END;
$$;

-- Enable RLS on all tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_shares ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hallucination_logs ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist to prevent duplication
DROP POLICY IF EXISTS "Allow public read of profiles" ON public.profiles;
DROP POLICY IF EXISTS "Allow system/admins to manage profiles" ON public.profiles;
DROP POLICY IF EXISTS "Read documents policy" ON public.documents;
DROP POLICY IF EXISTS "Insert documents policy" ON public.documents;
DROP POLICY IF EXISTS "Modify documents policy" ON public.documents;
DROP POLICY IF EXISTS "Read document chunks policy" ON public.document_chunks;
DROP POLICY IF EXISTS "Service role write document chunks" ON public.document_chunks;
DROP POLICY IF EXISTS "Read document shares policy" ON public.document_shares;
DROP POLICY IF EXISTS "Insert document shares policy" ON public.document_shares;
DROP POLICY IF EXISTS "Delete document shares policy" ON public.document_shares;
DROP POLICY IF EXISTS "Read own metrics" ON public.metrics;
DROP POLICY IF EXISTS "Insert own metrics" ON public.metrics;
DROP POLICY IF EXISTS "Read own hallucination logs" ON public.hallucination_logs;
DROP POLICY IF EXISTS "Insert own hallucination logs" ON public.hallucination_logs;

-- 1. Profiles Table Policies
CREATE POLICY "Allow public read of profiles"
ON public.profiles FOR SELECT
USING (id = (SELECT auth.uid()) OR public.is_admin());

CREATE POLICY "Allow system/admins to manage profiles"
ON public.profiles FOR ALL
USING (public.is_admin());

-- 2. Documents Table Policies
CREATE POLICY "Read documents policy"
ON public.documents FOR SELECT
USING (
    user_id = (SELECT auth.uid())
    OR public.is_admin()
    OR EXISTS (
        SELECT 1 FROM public.document_shares ds
        WHERE ds.document_id = public.documents.id 
          AND ds.shared_with_user_id = (SELECT auth.uid())
    )
);

CREATE POLICY "Insert documents policy"
ON public.documents FOR INSERT
WITH CHECK (user_id = (SELECT auth.uid()) OR public.is_admin());

CREATE POLICY "Modify documents policy"
ON public.documents FOR ALL
USING (user_id = (SELECT auth.uid()) OR public.is_admin());

-- 3. Document Chunks Table Policies
CREATE POLICY "Read document chunks policy"
ON public.document_chunks FOR SELECT
USING (
  EXISTS (
    SELECT 1 FROM public.documents d
    WHERE d.id = document_chunks.document_id
    AND (
      d.user_id = (SELECT auth.uid())
      OR public.is_admin()
      OR EXISTS (
        SELECT 1 FROM public.document_shares ds 
        WHERE ds.document_id = d.id 
          AND ds.shared_with_user_id = (SELECT auth.uid())
      )
    )
  )
);

CREATE POLICY "Service role write document chunks"
ON public.document_chunks FOR ALL
USING (public.is_admin());

-- 4. Document Shares Table Policies
CREATE POLICY "Read document shares policy"
ON public.document_shares FOR SELECT
USING (
    shared_with_user_id = (SELECT auth.uid())
    OR EXISTS (
        SELECT 1 FROM public.documents d
        WHERE d.id = document_shares.document_id
        AND d.user_id = (SELECT auth.uid())
    )
    OR public.is_admin()
);

CREATE POLICY "Insert document shares policy"
ON public.document_shares FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.documents d
        WHERE d.id = document_shares.document_id
        AND d.user_id = (SELECT auth.uid())
    )
    OR public.is_admin()
);

CREATE POLICY "Delete document shares policy"
ON public.document_shares FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM public.documents d
        WHERE d.id = document_shares.document_id
        AND d.user_id = (SELECT auth.uid())
    )
    OR public.is_admin()
);

-- 5. Metrics Table Policies
CREATE POLICY "Read own metrics"
ON public.metrics FOR SELECT
USING (
    user_id = (SELECT auth.uid())
    OR public.is_admin()
);

CREATE POLICY "Insert own metrics"
ON public.metrics FOR INSERT
WITH CHECK (
    user_id = (SELECT auth.uid())
    OR public.is_admin()
);

-- 6. Hallucination Logs Table Policies
CREATE POLICY "Read own hallucination logs"
ON public.hallucination_logs FOR SELECT
USING (
    user_id = (SELECT auth.uid())
    OR public.is_admin()
);

CREATE POLICY "Insert own hallucination logs"
ON public.hallucination_logs FOR INSERT
WITH CHECK (
    user_id = (SELECT auth.uid())
    OR public.is_admin()
);

-- ----------------------------------------------------
-- VECTOR SIMILARITY SEARCH WITH HNSW OPTIMIZATION (RPC)
-- ----------------------------------------------------

CREATE OR REPLACE FUNCTION public.match_document_chunks(
  query_embedding VECTOR(1024),
  similarity_threshold FLOAT,
  match_count INT
)
RETURNS TABLE (
  id UUID,
  content TEXT,
  page_number INT,
  filename VARCHAR,
  similarity_score FLOAT
)
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
BEGIN
  -- Set local HNSW search parameters within the transaction block
  SET local hnsw.ef_search = 100;
  
  RETURN QUERY
  SELECT 
      c.id,
      c.content,
      c.page_number,
      d.filename,
      (1 - (c.embedding <=> query_embedding))::FLOAT AS similarity_score
  FROM public.document_chunks c
  JOIN public.documents d ON c.document_id = d.id
  WHERE (1 - (c.embedding <=> query_embedding)) > similarity_threshold
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
