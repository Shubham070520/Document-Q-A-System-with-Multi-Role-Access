from app.workers.celery_app import celery_app
from app.database import supabase_admin
from app.services.parser import process_file_to_chunks
from app.services.embedding import EmbeddingService
import os

@celery_app.task(bind=True, max_retries=3, default_retry_delay=10, name="app.workers.tasks.process_document_task")
def process_document_task(self, document_id: str, file_path: str, file_ext: str):
    """
    Asynchronously parses a document file, chunks it, generates embeddings,
    and inserts chunks into public.document_chunks.
    Updates the parent document status accordingly. Supports Celery retries.
    """
    print(f"Starting background processing for document: {document_id} (attempt {self.request.retries + 1})")
    
    # 1. Update status to processing (on the first attempt)
    if self.request.retries == 0 and supabase_admin is not None:
        try:
            supabase_admin.table("documents").update({"status": "processing"}).eq("id", document_id).execute()
        except Exception as e:
            print(f"Error updating status to processing: {e}")
            
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at: {file_path}")

        # 2. Extract and split text recursively
        print(f"Extracting text and chunking: {file_path}")
        chunks = process_file_to_chunks(file_path, file_ext)
        if not chunks:
            raise ValueError("No text content could be extracted from this document")
            
        print(f"Successfully split into {len(chunks)} chunks.")

        # 3. Generate vector embeddings using Cohere
        print("Generating embeddings via Cohere service...")
        embedding_service = EmbeddingService()
        texts = [c["content"] for c in chunks]
        embeddings = embedding_service.embed_texts(texts, input_type="search_document")

        # 4. Insert chunks bulk to db using admin client (bypasses RLS write restrictions)
        if supabase_admin is not None:
            print("Writing chunks to database...")
            chunk_records = []
            for i, chunk in enumerate(chunks):
                chunk_records.append({
                    "document_id": document_id,
                    "content": chunk["content"],
                    "embedding": embeddings[i],
                    "page_number": chunk["page_number"]
                })
            if chunk_records:
                # Clear any chunks from previous failed runs first to avoid duplication
                supabase_admin.table("document_chunks").delete().eq("document_id", document_id).execute()
                supabase_admin.table("document_chunks").insert(chunk_records).execute()
                
            # 5. Update status to completed
            supabase_admin.table("documents").update({"status": "completed"}).eq("id", document_id).execute()
            print(f"Document {document_id} ingestion completed successfully.")
        else:
            print("Supabase admin client unconfigured. Running in dry-run mock mode.")

        # 6. Cleanup local temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
            print("Cleaned up temporary upload file.")

        return {
            "status": "success",
            "document_id": document_id,
            "chunks_processed": len(chunks)
        }

    except Exception as e:
        # Check if we should retry
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 10
            print(f"Task failed for document {document_id}. Retrying in {countdown} seconds... Error: {e}")
            raise self.retry(exc=e, countdown=countdown)

        error_msg = f"Task failed for document {document_id} after {self.max_retries} retries: {str(e)}"
        print(error_msg)
        
        # 6. Cleanup local temporary file on final failure
        if os.path.exists(file_path):
            os.remove(file_path)
            print("Cleaned up temporary upload file on error.")
            
        # 7. Update status to failed
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
