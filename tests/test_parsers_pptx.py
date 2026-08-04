from app.parsers.pptx_parser import parse_pptx


def test_parse_pptx_extracts_slide_sections_and_equations(sample_pptx):
    result = parse_pptx(str(sample_pptx))
    assert result.metadata.format == "pptx"
    assert result.metadata.page_count == 1
    assert result.sections[0].heading == "Newtons Laws"
    assert any("F = m * a" in eq.text for eq in result.equations)
