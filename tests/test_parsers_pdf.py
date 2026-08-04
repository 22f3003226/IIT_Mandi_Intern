from unittest.mock import patch

from app.parsers.pdf_parser import parse_pdf


def test_parse_pdf_extracts_headings_and_equations(sample_pdf):
    result = parse_pdf(str(sample_pdf))
    assert result.metadata.format == "pdf"
    headings = [s.heading for s in result.sections]
    assert "Introduction" in headings
    assert any("F = m * a" in eq.text for eq in result.equations)


def test_parse_pdf_triggers_ocr_for_scanned_pdf(blank_scanned_pdf):
    with patch("app.parsers.pdf_parser.ocr_page_text", return_value="OCR extracted text") as mock_ocr:
        result = parse_pdf(str(blank_scanned_pdf), doc_nature_hint="Scanned PDF")
    mock_ocr.assert_called()
    assert result.metadata.page_count == 1
