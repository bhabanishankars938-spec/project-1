import base64
import io
import logging
from pathlib import Path
from django.conf import settings
from PIL import Image

logger = logging.getLogger(__name__)

# Allowed file extensions and MIME types
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_DOC_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".py", ".js", ".html", ".css", ".sql", ".json"}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB limit


class FileProcessorService:
    """
    Handles secure processing, validation, text extraction, and multimodal preparation
    for uploaded documents and images.
    """

    @classmethod
    def validate_file(cls, uploaded_file) -> tuple[bool, str, str]:
        """
        Validates uploaded file against size and extension whitelist.
        Returns: (is_valid: bool, file_type: 'image' | 'document', error_message: str)
        """
        if uploaded_file.size > MAX_FILE_SIZE:
            return False, "", f"File size exceeds limit of {MAX_FILE_SIZE // (1024*1024)}MB."

        name = uploaded_file.name.lower()
        ext = Path(name).suffix

        if ext in ALLOWED_IMAGE_EXTENSIONS:
            # Verify image integrity with Pillow
            try:
                uploaded_file.seek(0)
                img = Image.open(uploaded_file)
                img.verify()
                uploaded_file.seek(0)
                return True, "image", ""
            except Exception as e:
                return False, "", f"Corrupted or invalid image file: {e}"

        elif ext in ALLOWED_DOC_EXTENSIONS:
            return True, "document", ""

        else:
            return False, "", f"Unsupported file format '{ext}'. Allowed: Images (PNG, JPG, WEBP), Documents (PDF, DOCX, TXT, Code files)."

    @classmethod
    def process_image_attachment(cls, uploaded_file) -> dict:
        """
        Processes an image file: prepares base64 payload for Multimodal LLM inspection.
        Returns dict with mime_type, base64_data, dimensions.
        """
        uploaded_file.seek(0)
        img_bytes = uploaded_file.read()
        uploaded_file.seek(0)

        # Detect dimensions
        width, height = 0, 0
        try:
            img = Image.open(io.BytesIO(img_bytes))
            width, height = img.size
        except Exception:
            pass

        ext = Path(uploaded_file.name).suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        mime_type = mime_map.get(ext, "image/jpeg")

        b64_encoded = base64.b64encode(img_bytes).decode("utf-8")

        return {
            "mime_type": mime_type,
            "base64_data": b64_encoded,
            "width": width,
            "height": height,
            "file_size": len(img_bytes),
        }

    @classmethod
    def extract_document_text(cls, uploaded_file) -> str:
        """
        Extracts raw textual content from PDF, DOCX, TXT, or source code files.
        """
        name = uploaded_file.name.lower()
        ext = Path(name).suffix
        uploaded_file.seek(0)

        if ext == ".pdf":
            return cls._extract_pdf_text(uploaded_file)
        elif ext == ".docx":
            return cls._extract_docx_text(uploaded_file)
        else:
            # Plain text / code
            try:
                content = uploaded_file.read()
                if isinstance(content, bytes):
                    return content.decode("utf-8", errors="replace")
                return str(content)
            except Exception as e:
                logger.error("Error reading text file: %s", e)
                return ""

    @classmethod
    def _extract_pdf_text(cls, file_obj) -> str:
        """Extracts text using PyMuPDF (fitz) or pypdf."""
        text_chunks = []
        try:
            import fitz  # PyMuPDF
            file_obj.seek(0)
            doc = fitz.open(stream=file_obj.read(), filetype="pdf")
            for page_num in range(min(len(doc), 40)):  # Max 40 pages
                page = doc.load_page(page_num)
                page_text = page.get_text()
                if page_text.strip():
                    text_chunks.append(f"--- Page {page_num + 1} ---\n{page_text}")
            doc.close()
            if text_chunks:
                return "\n\n".join(text_chunks)
        except Exception as e:
            logger.debug("PyMuPDF extraction failed, trying pypdf: %s", e)

        # Fallback to pypdf
        try:
            from pypdf import PdfReader
            file_obj.seek(0)
            reader = PdfReader(file_obj)
            for idx, page in enumerate(reader.pages[:40]):
                txt = page.extract_text()
                if txt:
                    text_chunks.append(f"--- Page {idx + 1} ---\n{txt}")
            return "\n\n".join(text_chunks)
        except Exception as e:
            logger.error("All PDF extraction methods failed: %s", e)
            return "Unable to extract text from PDF document."

    @classmethod
    def _extract_docx_text(cls, file_obj) -> str:
        """Extracts text from DOCX files using python-docx."""
        try:
            import docx
            file_obj.seek(0)
            doc = docx.Document(file_obj)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            
            # Also extract tables
            table_data = []
            for table in doc.tables:
                for row in table.rows:
                    row_txt = [c.text.strip() for c in row.cells if c.text.strip()]
                    if row_txt:
                        table_data.append(" | ".join(row_txt))

            full_text = "\n".join(paragraphs)
            if table_data:
                full_text += "\n\n--- Tables in Document ---\n" + "\n".join(table_data)

            return full_text
        except Exception as e:
            logger.error("DOCX extraction error: %s", e)
            return "Unable to extract text from DOCX document."
