# Document Q&A System with Multi-Role Access

An API-only Retrieval-Augmented Generation (RAG) system with role-based document isolation, asynchronous file ingestion, peer-to-peer sharing, rate limiting, and cost/hallucination tracking.

---

## 🚀 Key Features

*   **Asynchronous Document Ingestion**: Document uploads are queued in Redis and processed in the background (text extraction, splitting, Cohere embedding generation) without blocking client requests.
*   **Multi-Role Document Isolation**: Utilizes PostgreSQL Row Level Security (RLS) to ensure standard users only search their own documents or those explicitly shared with them.
*   **P2P Document Sharing**: Allows document owners to grant secure query permissions to standard users.
*   **Confidence Scoring & Hallucination Checks**: Evaluates LLM responses for context-faithfulness and flags hallucinated responses.
*   **Metrics & Cost Auditing**: Computes API token costs (Cohere + Groq) and logs complete usage metrics.
*   **Daily Rate Limiting**: Enforces a strict quota of 10 requests per user per day, with automatic database fallback if Redis goes offline.

---

## 🛠️ Technology Stack

*   **Framework**: FastAPI (Python 3.10+)
*   **Database**: Supabase (PostgreSQL with `pgvector` extension)
*   **Message Broker**: Redis
*   **Task Queue**: Celery
*   **Embeddings**: Cohere API (`embed-english-v3.0` - 1024-dimension)
*   **LLM Provider**: Groq Cloud API (`llama-3.1-8b-instant` / `llama3-70b-8192`)

---

## ⚙️ Project Setup & Installation

### 1. Clone the repository and navigate to the project directory:
```bash
git clone https://github.com/Shubham070520/Document-Q-A-System-with-Multi-Role-Access.git
cd Document-Q-A-System-with-Multi-Role-Access
```

### 2. Configure the Environment:
Copy the `.env.example` template to create your `.env` file:
```bash
cp .env.example .env
```
Fill in the configuration parameters in `.env`:
*   `SUPABASE_URL`: Your Supabase project URL.
*   `SUPABASE_ANON_KEY`: Your Supabase anonymous key.
*   `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase service role key (required for admin operations).
*   `DATABASE_URL`: Connection string to your Postgres database.
*   `COHERE_API_KEY`: Cohere developer key.
*   `GROQ_API_KEY`: Groq developer key.

### 3. Initialize Database Schemas & RLS:
Open the **Supabase SQL Editor** and execute the contents of [docs/schema_migration.sql](file:///d:/Programming/Assignment/docs/schema_migration.sql). This will set up the target tables, indexes, and custom Row Level Security policies.

### 4. Create Virtual Environment & Install Dependencies:
```bash
python -m venv venv
# On Windows
.\venv\Scripts\activate
# On Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
```

---

## 🏃 Running the Application

### 1. Start the FastAPI Web Server:
```bash
.\venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) in your browser to access the interactive Swagger API documentation.

### 2. Start the Celery Worker (In a separate terminal):
```bash
# On Windows (solo pool)
.\venv\Scripts\celery -A app.workers.tasks.celery_app worker --loglevel=info -P solo

# On Linux/macOS
celery -A app.workers.tasks.celery_app worker --loglevel=info
```
*(If Redis is offline, the web server will automatically fall back to native asynchronous threads without crashing).*

---

## 🔑 Authentication Guide: Mock vs. Real Tokens

Accessing protected endpoints requires passing a Bearer Token in the `Authorization` header. You can authorize testing using either **Mock Development Tokens** or **Real Supabase JWT Tokens**:

### 1. Mock Development Tokens (Offline Mode)
To simplify testing during development without registering actual users, the backend supports these quick header tokens:
*   **Admin Access**: In the Swagger Authorize dialog, type `dummy-admin-token`.
    *   *Resolves to*: User UUID `00000000-0000-0000-0000-000000000002` with **Admin** permissions.
*   **User Access**: In the Swagger Authorize dialog, type `dummy-token`.
    *   *Resolves to*: User UUID `00000000-0000-0000-0000-000000000001` with **User** permissions.

### 2. Real Production Tokens (Supabase Mode)
For testing real user isolation and RLS checks in production:
1.  **Register Users & Assign Roles**: Create user accounts in your Supabase Auth dashboard, then map their UUIDs to `'admin'` or `'user'` roles by running SQL inserts in the `public.profiles` table:
    ```sql
    INSERT INTO public.profiles (id, role) VALUES ('<user-uuid>', 'admin');
    INSERT INTO public.profiles (id, role) VALUES ('<user-uuid>', 'user');
    ```
2.  **Generate a JWT Access Token**: Log in using your favorite API Client (like Postman) by sending a request directly to Supabase Auth:
    *   **POST** `https://<your-supabase-url>/auth/v1/token?grant_type=password`
    *   **Headers**: `apikey: <your-supabase-anon-key>`
    *   **Body**: `{ "email": "user@example.com", "password": "password123" }`
3.  **Use Token**: Copy the returned `"access_token"` string, click **Authorize** in Swagger, and paste it.

---

## 🔗 Peer-to-Peer (P2P) Document Sharing

The sharing pipeline allows both Admins and Standard Users to share access. However, security checks differ based on roles:

1.  **Admin Sharing**:
    *   Administrators have permission to share **any** document in the database with any user.
2.  **Standard User Sharing**:
    *   Standard users can **only** share documents they own.
    *   When a standard user calls `POST /api/v1/documents/share`, the database Row Level Security evaluates `public.is_document_owner(document_id)`.
    *   If they are the owner, the share is written to `document_shares` and access is granted. Otherwise, it is rejected.

---

## 📖 Step-by-Step Pipeline Walkthrough

Follow these steps in **Swagger UI** to test the complete lifecycle:

### Step 1: Upload a Document (Admin)
1.  Authorize using `dummy-admin-token` *(or your real Admin JWT Access Token)*.
2.  Go to `POST /api/v1/documents/upload` and select a `.txt` or `.pdf` file. 
3.  *(Optional)* Assign ownership to a standard user:
    *   **Mock Token**: Set `target_user_id` to `00000000-0000-0000-0000-000000000001` (User 2).
    *   **Real Token**: Set `target_user_id` to your standard user's UUID (e.g. `5281c32e-46e0-40de-8f20-9b3b2db32a3c`).
    *   *Note: Leave it empty if you want the Admin to own the file.*
4.  Execute. The API will immediately return `202 Accepted` with a `document_id`.

### Step 2: Check Processing Status
1.  Go to `GET /api/v1/documents` and click Execute.
2.  Confirm that your document status is `completed` (this takes 3-10 seconds depending on size).

### Step 3: Query the Document (Admin)
1.  Go to `POST /api/v1/qa/query` and query about your document contents.
2.  Verify you receive the answer, confidence score, and document sources.

### Step 4: Share Document Access
1.  Go to `POST /api/v1/documents/share`.
2.  Set `document_id` to your uploaded document.
3.  Set `target_email` to the recipient:
    *   **Mock Token**: Set `target_email` to `00000000-0000-0000-0000-000000000001`.
    *   **Real Token**: Set `target_email` to the user's email address (e.g., `user@example.com`) or their raw user UUID directly.
4.  Execute.

### Step 5: Query as the Standard User
1.  Click **Authorize** at the top right of Swagger, click **Logout**, then log back in:
    *   **Mock Token**: Authorize using `dummy-token`.
    *   **Real Token**: Authorize using your standard user's real JWT Access Token.
2.  Go to `POST /api/v1/qa/query` and ask the same question.
3.  Verify the standard user can now search and retrieve answers from the shared document, proving that Row Level Security (RLS) is working correctly!

---

## 🗺️ API Reference

| Endpoint | Method | Role | Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/documents/upload` | **POST** | Admin | Uploads a document (PDF/TXT) and queues it for chunking/embedding. |
| `/api/v1/documents` | **GET** | All | Lists status of all documents owned by or shared with the authenticated user. |
| `/api/v1/documents/{document_id}` | **DELETE** | Admin/Owner | Deletes a document and its parsed chunks from the vector database. |
| `/api/v1/documents/share` | **POST** | Admin/Owner | Shares a document with another standard user using their email or UUID. |
| `/api/v1/qa/query` | **POST** | All | Processes user queries, retrieves matches using pgvector, and returns LLM answers. |
| `/api/v1/admin/metrics` | **GET** | Admin | Displays system-wide aggregated metrics, total API token costs, and usage list. |
| `/api/v1/admin/hallucinations` | **GET** | Admin | Retrieves logs of all low-confidence generations flagged by the system. |
| `/api/v1/admin/evaluate` | **POST** | Admin | Runs an accuracy evaluation suite by querying 5 static test checks. |
| `/health` | **GET** | All | Quick diagnostic endpoint reporting API settings configuration status. |
