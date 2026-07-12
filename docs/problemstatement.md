# Document Q&A System with Multi-Role Access: Project Context & Problem Statement

## 1. Executive Summary
This project aims to build a secure, enterprise-grade, multi-role Document Q&A (Question & Answering) system. The system enables Administrators to ingest textual and PDF documents and monitor system-wide operational metrics, while standard Users can search, retrieve, and ask questions only about their authorized documents. A critical aspect of the system is LLM hallucination and garbage detection (identifying when the system produces low-confidence answers) to guarantee data accuracy and build user trust.

---

## 2. Problem Statement & Key Challenges

### 2.1 Information Siloing and Retrieval Inefficiencies
Organizations hold massive amounts of unstructured knowledge in PDFs, manuals, policies, and text files. Traditional search mechanisms are keyword-based and fail to synthesize information or provide direct answers to complex queries. Users spend significant time reading through long documents to find specific answers.

### 2.2 LLM Hallucinations and Factual Accuracy
Generative AI models, while fluent, are prone to "hallucinations"—generating answers that sound plausible but are factually incorrect or unsupported by the source text. In business and legal settings, hallucinated answers are unacceptable. The system must implement robust quality evaluation and confidence scoring mechanisms to identify and flag low-confidence answers (i.e., "garbage/bullshit detection").

### 2.3 Security, Multi-Tenancy, and Isolation
In a multi-user environment, document security is paramount. A user must never be able to query, view, or search documents belonging to another user. Standard user queries must be strictly isolated. Row Level Security (RLS) policies implemented at the database tier are required to guarantee this logical isolation, while also supporting optional document-sharing mechanisms.

### 2.4 Resource Allocation and Cost Management
Large Language Model (LLM) API calls are expensive and subject to strict rate limits. To prevent resource abuse and manage costs, the system must enforce strict usage limits (e.g., query quotas) on a per-user, per-day basis.

### 2.5 Latency and Responsiveness (Asynchronous Processing)
PDF processing, text extraction, chunking, and embedding generation are computationally intensive operations. If processed synchronously during an upload HTTP request, it leads to connection timeouts and a poor user experience. The system must offload document processing to background job queues to keep the ingestion flow non-blocking and highly responsive.

---

## 3. User Roles and Access Control

The system implements two distinct roles with tailored interfaces and permissions, enforced via Supabase Authentication and PostgreSQL Row Level Security (RLS):

### 3.1 Administrator (Admin)
*   **Document Ingestion**: Upload documents (PDFs, TXT) to the system-wide store or assign them to specific users.
*   **Quality & Safety Controls**: Configure minimum confidence thresholds. Answers below this threshold are flagged or suppressed.
*   **Operational Analytics Dashboard**: Monitor token usage, API costs, document count, and general system health.
*   **Hallucination Oversight**: Review instances where the LLM generated low-confidence answers to refine the prompt, chunking strategy, or document corpus.
*   **System Accuracy Evaluation**: View automated evaluation runs (e.g., 5-question test suites run against the database to measure retrieval precision and response accuracy).

### 3.2 End User (User)
*   **Isolated Search**: Search and browse documents. Users can *only* see and search their own uploaded or shared documents.
*   **Q&A Interface**: Query documents and receive synthesized answers using RAG.
*   **Factual Attribution**: Every answer must be accompanied by explicit source attributions (document name, page number, or text snippet) and a calculated confidence score.
*   **Quotas**: See daily remaining query count (e.g., "5/10 queries remaining today") to maintain cost transparency.

---

## 4. System Requirements & Tiered Implementation

### Tier 1: Core Functionality (MVP)
*   **Authentication & Role Setup**: User sign-up and login, with role assignments (Admin vs. User) secured using Supabase and DB-level RLS.
*   **Document Upload Pipeline**: Admin-facing upload endpoint extracting text from PDFs/documents, chunking text, generating vector embeddings, and saving them.
*   **Retrieval-Augmented Generation (RAG)**: User-facing Q&A endpoint. Retrieves matching chunks based on semantic similarity, constructs a prompt for the LLM (using Groq Cloud), and returns the answer alongside source references.
*   **Basic Analytics**: Tracking system-wide total token consumption, estimated API cost, and total document count.

### Tier 2: Multi-Role, Quality, and Asynchronous Upgrades
*   **Per-User Rate Limiting**: Track and enforce a quota of 10 queries per user per day.
*   **Garbage/Hallucination Detection**: Assess answers for confidence (e.g., semantic similarity between prompt/query/context/response, or direct self-evaluation prompt checks). Flag low-confidence outputs.
*   **Automated Accuracy Assessment**: Run periodic checks using 5 pre-defined test questions to measure response consistency and correctness.
*   **Asynchronous Jobs**: Integrate a background task queue (e.g., Celery/Bull) to process document uploads asynchronously.
*   **Admin Quality Dashboard**: Visual charts for overall metrics, token costs, and a log of flagged low-confidence answers.

### Tier 3: Advanced Features
*   **Multi-Tenant Isolation**: Rigorous PostgreSQL RLS policies ensuring users only query their own files.
*   **Document Sharing**: Enable users to securely share specific documents with other users, modifying the RLS evaluation dynamically.
*   **Audit Logging**: Trace all user queries, document uploads, and administrator settings adjustments for compliance and debugging.
*   **Resiliency**: Handlers for API rate limits (exponential backoff), task retries, and clean failover state.

---

## 5. Technology Stack Decisions

The system architecture is designed around modern, scalable technologies:

*   **Backend Framework**:
    *   *Option A*: **Python (FastAPI)** - Ideal for ML/NLP tasks, offering native integration with LangChain, LlamaIndex, and robust async endpoints.
    *   *Option B*: **Node.js (Express/NestJS)** - Fast, event-driven, with strong ecosystems for web development.
*   **Database & Security**: **Supabase** (Postgres) for core transactional data, Authentication, and Row Level Security (RLS).
*   **Vector Database**:
    *   *Option A*: **pgvector** extension inside PostgreSQL (native to Supabase) for integrated relational and vector storage.
    *   *Option B*: **Pinecone** for a dedicated, serverless vector search index.
*   **Large Language Model (LLM)**: **Groq Cloud** API (Mandatory) for lightning-fast, cost-effective inference.
*   **Embedding Generator**: **OpenAI** (`text-embedding-3-small`/`large`) or **Cohere** Embed.
*   **Task Queue & Caching**:
    *   *Python Stack*: **Celery** with **Redis** as a broker.
    *   *Node.js Stack*: **Bull** with **Redis**.