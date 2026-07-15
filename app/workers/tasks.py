from app.workers.celery_app import celery_app
from app.database import supabase_admin
from app.services.parser import process_file_to_chunks
from app.services.embedding import EmbeddingService
import os
import tempfile

STORAGE_BUCKET = "documents"

@celery_app.task(bind=True, max_retries=3, default_retry_delay=10, name="app.workers.tasks.process_document_task")
def process_document_task(self, document_id: str, storage_path: str, file_ext: str):
    """
    Asynchronously downloads a document from Supabase Storage, parses it, chunks it,
    generates embeddings, and inserts chunks into public.document_chunks.
    Updates the parent document status accordingly. Supports Celery retries.
    """
    print(f"Starting background processing for document: {document_id} (attempt {self.request.retries + 1})")

    if self.request.retries == 0 and supabase_admin is not None:
        try:
            supabase_admin.table("documents").update({"status": "processing"}).eq("id", document_id).execute()
        except Exception as e:
            print(f"Error updating status to processing: {e}")

    local_file_path = None
    try:
        print(f"Downloading from Supabase Storage: {storage_path}")
        file_bytes = supabase_admin.storage.from_(STORAGE_BUCKET).download(storage_path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp:
            tmp.write(file_bytes)
            local_file_path = tmp.name

        print(f"Extracting text and chunking: {local_file_path}")
        chunks = process_file_to_chunks(local_file_path, file_ext)
        if not chunks:
            raise ValueError("No text content could be extracted from this document")

        print(f"Successfully split into {len(chunks)} chunks.")

        print("Generating embeddings via Cohere service...")
        embedding_service = EmbeddingService()
        texts = [c["content"] for c in chunks]
        embeddings = embedding_service.embed_texts(texts, input_type="search_document")

        if supabase_admin is not None:
            print("Writing chunks to database...")
            chunk_records = [
                {
                    "document_id": document_id,
                    "content": chunk["content"],
                    "embedding": embeddings[i],
                    "page_number": chunk["page_number"]
                }
                for i, chunk in enumerate(chunks)
            ]
            if chunk_records:
                supabase_admin.table("document_chunks").delete().eq("document_id", document_id).execute()
                supabase_admin.table("document_chunks").insert(chunk_records).execute()

            supabase_admin.table("documents").update({"status": "completed"}).eq("id", document_id).execute()
            print(f"Document {document_id} ingestion completed successfully.")

        return {
            "status": "success",
            "document_id": document_id,
            "chunks_processed": len(chunks)
        }

    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 10
            print(f"Task failed for document {document_id}. Retrying in {countdown} seconds... Error: {e}")
            raise self.retry(exc=e, countdown=countdown)

        error_msg = f"Task failed for document {document_id} after {self.max_retries} retries: {str(e)}"
        print(error_msg)

        if supabase_admin is not None:
            try:
                supabase_admin.table("documents").update({"status": "failed"}).eq("id", document_id).execute()
            except Exception as e_status:
                print(f"Failed to update document status to failed: {e_status}")

        return {
            "status": "failed",
            "document_id": document_id,
            "error": str(e)
        }
    finally:
        if local_file_path and os.path.exists(local_file_path):
            try:
                os.remove(local_file_path)
                print("Cleaned up local temp file.")
            except Exception as e_cleanup:
                print(f"Failed to remove temporary file {local_file_path}: {e_cleanup}")