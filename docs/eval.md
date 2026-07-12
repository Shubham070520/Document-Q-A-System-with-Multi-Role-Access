# Phase-Wise Project Evaluation Criteria

This document details the concrete verification tests, assertion checklists, and evaluation metrics for each of the 7 development phases of the **Document Q&A System with Multi-Role Access**.

---

## Phase 1 Evaluation: Environment Setup & Project Initialization

### 1.1 Development Server Verification
- [ ] **FastAPI Diagnostics**: Execute `uvicorn app.main:app --reload`. The console logs must show no warnings or startup failures, and the Swagger UI should load at `http://127.0.0.1:8000/docs`.
- [ ] **Config Check**: Verify that FastAPI fails to start if crucial variables (e.g., `GROQ_API_KEY`, `SUPABASE_URL`) are missing or blank in the `.env` file.

### 1.2 Service Connections Validation
- [ ] **External API Handshakes**: Create a simple startup diagnostics block in `app/main.py` that executes:
  - A mock connection check to Supabase (`supabase.table('profiles').select('count', count='exact').limit(1).execute()`).
  - A lightweight mock embedding request to Cohere.
  - A lightweight token model check to Groq.
  - A Redis ping test (`redis_client.ping()`).
  Verify all checks return a success signal.

---

## Phase 2 Evaluation: Database Schema & Row Level Security (RLS)

### 2.1 Database Migrations Check
- [ ] **Table Check**: Run a database command to verify that all 6 tables (`profiles`, `documents`, `document_chunks`, `document_shares`, `metrics`, `hallucination_logs`) exist in the `public` schema.
- [ ] **Vector Extension**: Verify that `SELECT extname FROM pg_extension WHERE extname = 'vector';` returns one row.
- [ ] **Index Assertions**: Verify that the HNSW index on `document_chunks(embedding)` exists and is mapped to `vector_cosine_ops`.

### 2.2 Security Definer Helper Assertion
- [ ] **Admin Helper Test**: Execute:
  - `SELECT public.is_admin();` with an Admin user ID set in the session context; verify it returns `true`.
  - `SELECT public.is_admin();` with a standard User user ID set in the session context; verify it returns `false`.

### 2.3 RLS Policy Isolation Testing
- [ ] **Multi-Tenant Read Isolation**: Insert a document row owned by User A. Query the table using User B's Supabase token; verify that `SELECT * FROM public.documents;` returns zero rows.
- [ ] **Multi-Tenant Write Isolation**: Attempt to insert a document row using User B's token but set the `user_id` column to User A's ID; verify that the insert fails or that RLS overrides/blocks the action.
- [ ] **Metric Security**: Query the metrics table using User A's token; verify that no metrics containing User B's ID are visible.

---

## Phase 3 Evaluation: Core Ingestion (Synchronous MVP)

### 3.1 Document Extraction Parsing Test
- [ ] **Layout Preservation**: Parse a test PDF containing multi-column text and headers. Print the parsed result to verify that spacing and structural content are extracted cleanly.
- [ ] **Page Number Verification**: Verify that the parser correctly extracts page markers alongside text blocks.

### 3.2 Splitting & Embeddings Verification
- [ ] **Recursive Separators**: Test character splitting on a text block containing multiple double newlines (`\n\n`), single newlines (`\n`), and spaces. Verify that chunks split on double newlines first.
- [ ] **Chunk Size Validation**: Assert that no individual text chunk exceeds the target 500-character boundary limit (excluding the overlap).
- [ ] **Cohere Integration**: Embed a test chunk; assert that the Cohere response is a vector array containing exactly 1024 float dimensions.

---

## Phase 4 Evaluation: Q&A Retrieval Engine

### 4.1 Vector Query Assertions
- [ ] **Cosine Search Index Performance**: Run `EXPLAIN ANALYZE` on the similarity search SQL block. Verify that pgvector HNSW index is traversed (Index Scan rather than Sequential Scan).
- [ ] **ef_search Validation**: Verify that `SET local hnsw.ef_search = 100;` executes inside the vector retrieval transaction block.
- [ ] **Starvation Verification**: Configure a strict similarity threshold (e.g. `similarity_threshold = 0.8`). Search with a query that has no semantic match; verify it returns an empty list, bypassing the Groq LLM.

### 4.2 Answer Generation grounding
- [ ] **Factual Attribution**: Ask a query that requires context from pages 1 and 3 of the test document. Confirm the API returns the correct answer and identifies both page numbers in the `sources` attribute.
- [ ] **Unrelated Query Guard**: Query: *"What is the capital of France?"* on a corpus containing only financial logs. The engine must refuse to answer or output a standard UNSUPPORTED indicator rather than generating general facts.

---

## Phase 5 Evaluation: Asynchronous Pipeline

### 5.1 Non-Blocking Gateway Verification
- [ ] **Response Time Test**: Measure response latency on the upload API `POST /api/v1/documents/upload` with a 20MB file. Verify that the response returns in `< 1 second` with status code `202 Accepted` and a valid `document_id`.
- [ ] **Database State Progression**: Verify that the document status immediately registers as `pending` in the `documents` table, shifts to `processing` when the Celery task starts, and reaches `completed` on success.

### 5.2 Failure Path Verification
- [ ] **Corrupted Input Recovery**: Upload a text file renamed to `.pdf` but containing garbage bytes. Verify that:
  - The Celery worker does not crash.
  - The document status in the DB updates to `failed`.
  - The local temporary storage file is cleaned up.

---

## Phase 6 Evaluation: Quality Guardrails & Rate Limiting

### 6.1 Redis Rate Limiter Testing
- [ ] **Atomic Limits Boundary**: Fire 12 parallel requests using a single user token. Verify that exactly 10 requests pass and the remaining 2 return `429 Too Many Requests`.
- [ ] **Expiration TTL Verification**: Verify that the Redis key rate limiter TTL counts down to 0 and resets exactly 24 hours after the user's first query.

### 6.2 Hallucination Check Accuracy
- [ ] **Hallucination Detection check**: Inject a fabricated answer that contradicts the retrieved context. Confirm that the hallucination checker identifies this conflict, assigns a low score (below `0.7`), returns the standard fallback message, and logs the query inside the `hallucination_logs` table as `flagged`.

### 6.3 Cost Tracking Accuracy
- [ ] **Token Counter Aggregation**: Run a query and check the resulting `metrics` row. Verify that:
  - Input tokens = `Cohere token count + Groq Call 1 input tokens + Groq Call 2 input tokens`.
  - Output tokens = `Groq Call 1 output tokens + Groq Call 2 output tokens`.
  - The calculated cost matches the pricing model (`$0.10/1M` Cohere, `$0.05/1M` input Groq, `$0.08/1M` output Groq).

---

## Phase 7 Evaluation: Admin Oversight Dashboard

### 7.1 Security Gateway Check
- [ ] **Standard User Block**: Call `GET /api/v1/admin/metrics` using a standard User's authentication token. Verify the API throws a `403 Forbidden` status code.
- [ ] **Admin Allow Check**: Call the same endpoint with an Admin's token. Verify the API returns valid usage aggregates.

### 7.2 System-wide Accuracy suites
- [ ] **Suite Assertion run**: Run the evaluation trigger. Confirm it executes 5 automated queries, checks responses, and logs a percentage correctness rating in the system database.
