import io

import fitz
import pytesseract
from PIL import Image


def ocr_page_text(doc: fitz.Document, page_index: int) -> str:
    page = doc[page_index]
    pix = page.get_pixmap(dpi=200)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(image)
