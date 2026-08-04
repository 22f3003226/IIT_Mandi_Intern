# tests/test_parsers_txt.py
from app.parsers.txt_parser import parse_txt


def test_parse_txt_extracts_headings_and_equations(sample_txt):
    result = parse_txt(str(sample_txt))
    assert result.metadata.format == "txt"
    headings = [s.heading for s in result.sections]
    assert "Introduction" in headings
    assert "Newtons First Law" in headings
    assert any("F = m * a" in eq.text for eq in result.equations)
