# Phase-Wise Project Implementation Plan

This implementation plan details the step-by-step development roadmap for building the **Document Q&A System with Multi-Role Access**. The plan aligns directly with the specifications in [problemstatement.md](file:///d:/Programming/Assignment/docs/problemstatement.md) and [architecture.md](file:///d:/Programming/Assignment/docs/architecture.md), utilizing **Python FastAPI**, **Supabase (PostgreSQL with pgvector)**, **Cohere Embeddings**, and **Groq Cloud LLM**.

---

## Phase 1: Environment Setup & Project Initialization

### 1.1 Objectives
- Initialize the Python FastAPI project with necessary dependencies.
- Setup environment variables for local development.
- Configure local or cloud connections to Supabase, Redis, Cohere, and Groq.

### 1.2 Tasks
1.  **Project Directory Structure**: Initialize the following directory structure:
    ```text
    assignment/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py
    │   ├── config.py
    │   ├── database.py
    │   ├── api/
    │   │   ├── __init__.py
    │   │   ├── dependencies.py
    │   │   ├── auth.py
    │   │   ├── documents.py
    │   │   └── qa.py
    │   ├── services/
    │   │   ├── __init__.py
    │   │   ├── embedding.py
    │   │   ├── llm.py
    │   │   └── guardrails.py
    │   ├── workers/
    │   │   ├── __init__.py
    │   │   ├── celery_app.py
    │   │   └── tasks.py
    │   └── models/
    │       ├── __init__.py
    │       └── schemas.py
    ├── requirements.txt
    └── .env
    ```
2.  **Dependencies Setup**: Define the packages in `requirements.txt`:
    - `fastapi`, `uvicorn` (FastAPI core)
    - `supabase` (Supabase client client)
    - `psycopg2-binary` or `asyncpg` (Postgres driver)
    - `redis` (Cache & rate limiting client)
    - `celery` (Task queue)
    - `pypdf`, `pdfplumber` (PDF parsing)
    - `cohere` (Cohere SDK)
    - `groq` (Groq SDK)
    - `pydantic-settings` (Environment config)
    - `python-multipart` (File uploads support)
3.  **Environment Variables (`.env`)**:
    ```ini
    SUPABASE_URL=https://your-project-id.supabase.co
    SUPABASE_ANON_KEY=your-supabase-anon-key
    SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-key
    COHERE_API_KEY=your-cohere-api-key
    GROQ_API_KEY=your-groq-api-key
    REDIS_URL=redis://localhost:6379/0
    DATABASE_URL=postgresql://postgres:password@db.your-project-id.supabase.co:5432/postgres
    ```

### 1.3 Verification
- Run a baseline server check: `uvicorn app.main:app --reload` should spin up with `docs` endpoint accessible.
- Verify environmental configurations load properly into `app/config.py`.

---

## Phase 2: Database Schema & Row Level Security (RLS)

### 2.1 Objectives
- Enable pgvector and configure database DDL tables.
- Establish Row Level Security (RLS) policies on Supabase.
- Setup authentication helper functions.

### 2.2 Tasks
1.  **Run Migrations**: Execute the DDL script in Supabase's SQL Editor:
    - Install extensions (`vector`, `uuid-ossp`).
    - Create tables: `profiles`, `documents`, `document_chunks`, `document_shares`, `metrics`, `hallucination_logs`.
    - Create the `public.is_admin()` helper function with `SECURITY DEFINER`.
    - Enable HNSW Index on `document_chunks` embedding column.
2.  **Enable and Configure RLS**:
    - Enable RLS on all 6 tables.
    - Deploy policies defined in [architecture.md (Section 3.1)](file:///d:/Programming/Assignment/docs/architecture.md#L182-L308).
3.  **Supabase Auth Integrations**:
    - Build user token verification middleware in `app/api/dependencies.py` using `supabase-py` client validation.

### 2.3 Verification
- Create two test users (User A, User B) in Supabase.
- Run raw SELECT queries using User A's token; confirm documents owned by User B or public metrics tables return 401/403 or empty sets where appropriate.

---

## Phase 3: Core Document Ingestion (Synchronous MVP)

### 3.1 Objectives
- Set up parsing functions to extract text content from PDF and TXT documents.
- Implement text chunking and metadata extraction.
- Connect the Cohere Embedding API.
- Save chunks and vector embeddings to PostgreSQL.

### 3.2 Tasks
1.  **Document Parser Implementation**:
    - Write text extractor using `pdfplumber` inside `app/services/parser.py`. Extract text layout-safely and capture page numbers.
2.  **Recursive Character Chunking**:
    - Build a text-splitting algorithm inside `app/services/parser.py`. Target chunk size: 500 characters, overlap: 50 characters, appending document name/page metadata to chunks.
3.  **Cohere Vector Embedding Integration**:
    - Implement `app/services/embedding.py` to call Cohere's `embed-english-v3.0` API with `input_type="search_document"`. Retrieve 1024-dimensional float arrays.
4.  **Database Vector Writing**:
    - Implement `POST /api/v1/documents/upload` endpoint in `app/api/documents.py`.
    - Extract text -> Chunk text -> Embed chunks -> Insert into `public.document_chunks` table using pgvector client driver (`psycopg2` or `SQLAlchemy` vector converter).

### 3.3 Verification
- Upload a small 3-page test PDF via FastAPI Swagger UI.
- Verify `public.documents` status changes to `completed`.
- Query `public.document_chunks` table directly to verify that chunk text exists alongside a valid 1024-dimension float array.

---

## Phase 4: Retrieval-Augmented Generation (RAG) & Q&A Engine

### 4.1 Objectives
- Generate vector embeddings for incoming user queries.
- Execute vector similarity searches against `pgvector` inside PostgreSQL.
- Construct the system context prompt and send it to Groq Cloud LLM for rapid answer generation.

### 4.2 Tasks
1.  **Query Embedding**:
    - In `app/services/embedding.py`, call Cohere API for query text with `input_type="search_query"`.
2.  **Semantic Vector Query**:
    - Execute pgvector cosine similarity search (`<=>`) in `app/api/qa.py`.
    - Apply transaction-scoped HNSW optimization: Run `SET local hnsw.ef_search = 100;` before executing vector similarity search.
    - Restrict matches using a similarity threshold (e.g. `similarity_score > 0.6`) and limit context to Top-K (e.g., K = 5).
3.  **Groq Context Prompt Construction**:
    - In `app/services/llm.py`, build prompt:
      ```text
      Context Chunks:
      [1] Source: {filename}, Page: {page} - "{content}"
      ...
      Query: {query}
      Answer the question using only the context chunks. If the answer is not supported, reply with "UNSUPPORTED".
      ```
    - Invoke Groq API (e.g. `llama-3.1-8b-instant`) to generate the response.
4.  **Endpoint Setup**:
    - Expose `POST /api/v1/qa/query` in `app/api/qa.py` returning `{answer, sources: [{filename, page_number}], confidence_score}`.

### 4.3 Verification
- Ask a query that is answered directly in the test PDF. Verify that it returns the exact sentence answer and lists the correct PDF page source.
- Ask a query unrelated to the document. Verify it handles retrieval gracefully (e.g., returns "UNSUPPORTED" or filters out low similarity chunks).

---

## Phase 5: Asynchronous Ingestion Pipeline

### 5.1 Objectives
- Decouple PDF uploading from parsing/embedding generation using background workers.
- Integrate Redis as broker and Celery as worker system.
- Manage document upload status states (`pending`, `processing`, `completed`, `failed`).

### 5.2 Tasks
1.  **Configure Celery & Redis**:
    - Write Celery app definition in `app/workers/celery_app.py` pointing to Redis.
2.  **Refactor Upload Endpoint to Async**:
    - Modify `POST /api/v1/documents/upload` to store files locally or in Supabase bucket, insert a DB row status as `pending`, queue task: `process_document_task.delay(document_id, file_path)`, and immediately return `202 Accepted` with `document_id`.
3.  **Background Parser Task**:
    - Define `process_document_task` in `app/workers/tasks.py`.
    - Wrap execution in a `try/except` block:
      - Set status: `processing`.
      - Extract, chunk, embed, and write to database.
      - On success, set status: `completed`.
      - On failure, set status: `failed` and log trace.

### 5.3 Verification
- Upload a larger PDF (~10MB). Verify the upload request returns in <500ms.
- Monitor the background task logs. Verify status shifts from `pending` -> `processing` -> `completed`.

---

## Phase 6: Quality Guardrails & Rate Limiting

### 6.1 Objectives
- Mitigate hallucinations using a post-generation verification check.
- Track usage token counts and estimated vendor costs.
- Enforce daily request limits.

### 6.2 Tasks
1.  **Redis Atomic Rate Limiting**:
    - Implement the rate check logic in `app/api/qa.py` using Redis `INCR` and `EXPIRE` as detailed in [architecture.md (Section 7.1)](file:///d:/Programming/Assignment/docs/architecture.md#L433-L462).
2.  **Hallucination Check Service**:
    - Implement `app/services/guardrails.py`.
    - Submit a second Groq API request validating if the generated answer is strictly grounded in the retrieved chunks. Return a score.
    - If the score falls below `0.7`, log query/response in `hallucination_logs` with evaluation status `flagged`, and return a default low-confidence template response.
3.  **Token Counting & Billing Logging**:
    - Record tokens spent across all Groq calls (inference + evaluation) and Cohere embedding calls.
    - Write billing calculation metrics to `metrics` table after each query execution.

### 6.3 Verification
- Submit 11 queries using a test User account in a short span. Verify that the 11th call throws a `429 Too Many Requests` status code.
- Force a hallucination (e.g. ask a query and provide a fabricated response template). Confirm that the response is intercepted and marked as low confidence, and that it is logged into the `hallucination_logs` table.

---

## Phase 7: Administrative Oversight & Metrics Dashboard

### 7.1 Objectives
- Provide administrators with a dashboard interface and APIs to monitor tokens, cost metrics, and flagged hallucinated responses.
- Implement an automated system-evaluation suite to check pipeline accuracy.

### 7.2 Tasks
1.  **Admin Metrics Endpoints**:
    - Implement `GET /api/v1/admin/metrics` returning aggregate usage counts, costs, and token history.
    - Implement `GET /api/v1/admin/hallucinations` showing flagged queries from the `hallucination_logs` table.
2.  **Accuracy Evaluation Service**:
    - Implement a test engine that executes 5 pre-defined Q&A assertions against the corpus. Check cosine similarity of outputs against ground truth responses to record system accuracy.
3.  **Security Validation**:
    - Enforce that the admin metrics endpoints verify `public.is_admin()` equals true, returning a `403 Forbidden` for standard users.

### 7.3 Verification
- Call `/api/v1/admin/metrics` using a standard User's token. Confirm a `403 Forbidden` is returned.
- Call the same endpoint with an Admin's token. Verify a JSON object is returned containing token costs and document volumes.
- Execute accuracy test suites, verifying accuracy metrics are updated.
