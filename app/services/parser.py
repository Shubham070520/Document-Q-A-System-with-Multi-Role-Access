import pdfplumber
from pypdf import PdfReader
from typing import List, Dict, Any

def extract_pdf_text(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract text content from a PDF file page-by-page.
    Tries pdfplumber first, falls back to pypdf.
    """
    pages_data = []
    
    # Try pdfplumber
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_idx, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text and text.strip():
                    pages_data.append({"text": text, "page_number": page_idx})
    except Exception as e:
        # Fallback to pypdf
        try:
            reader = PdfReader(file_path)
            pages_data = []
            for page_idx, page in enumerate(reader.pages, 1):
                text = page.extract_text()
                if text and text.strip():
                    pages_data.append({"text": text, "page_number": page_idx})
        except Exception as e2:
            raise ValueError(f"Failed to parse PDF file: {e} | {e2}")
            
    return pages_data

def extract_txt_text(file_path: str) -> List[Dict[str, Any]]:
    """Extract text from a plain text file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as f:
            content = f.read()
            
    return [{"text": content, "page_number": 1}]

def split_text_recursive(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
    """
    Splits text recursively using separators: ["\\n\\n", "\\n", " ", ""].
    Ensures chunks satisfy target chunk_size and chunk_overlap constraint.
    """
    if chunk_overlap >= chunk_size:
        raise ValueError("Overlap must be smaller than chunk size")

    separators = ["\n\n", "\n", " ", ""]
    
    def _split(text: str, seps: List[str]) -> List[str]:
        if len(text) <= chunk_size:
            return [text]
        if not seps:
            return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        
        sep = seps[0]
        next_seps = seps[1:]
        
        if sep == "":
            splits = list(text)
        else:
            splits = text.split(sep)
            
        chunks = []
        current_chunk = []
        current_len = 0
        
        for split in splits:
            if len(split) > chunk_size:
                if current_chunk:
                    chunks.append(sep.join(current_chunk))
                    current_chunk = []
                    current_len = 0
                
                sub_splits = _split(split, next_seps)
                chunks.extend(sub_splits)
            else:
                sep_len = len(sep) if current_chunk else 0
                if current_len + sep_len + len(split) > chunk_size:
                    if current_chunk:
                        chunks.append(sep.join(current_chunk))
                    
                    # Backtrack to accumulate overlap
                    overlap_chunk = []
                    overlap_len = 0
                    for prev_split in reversed(current_chunk):
                        prev_sep_len = len(sep) if overlap_chunk else 0
                        if overlap_len + prev_sep_len + len(prev_split) <= chunk_overlap:
                            overlap_chunk.insert(0, prev_split)
                            overlap_len += prev_sep_len + len(prev_split)
                        else:
                            break
                            
                    current_chunk = overlap_chunk
                    current_len = overlap_len
                
                if current_chunk:
                    current_len += len(sep)
                current_chunk.append(split)
                current_len += len(split)
                
        if current_chunk:
            chunks.append(sep.join(current_chunk))
            
        return chunks

    return _split(text, separators)

def process_file_to_chunks(file_path: str, file_type: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[Dict[str, Any]]:
    """
    Extracts text and breaks it into chunks with metadata (page_number).
    """
    if file_type.lower() == "pdf":
        pages = extract_pdf_text(file_path)
    else:
        pages = extract_txt_text(file_path)
        
    all_chunks = []
    for page in pages:
        chunks = split_text_recursive(page["text"], chunk_size, chunk_overlap)
        for chunk in chunks:
            if chunk.strip():
                all_chunks.append({
                    "content": chunk.strip(),
                    "page_number": page["page_number"]
                })
    return all_chunks
