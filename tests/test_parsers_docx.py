from app.parsers.docx_parser import parse_docx


def test_parse_docx_extracts_headings_tables_and_equations(sample_docx):
    result = parse_docx(str(sample_docx))
    assert result.metadata.format == "docx"
    headings = [s.heading for s in result.sections]
    assert "Introduction" in headings
    assert "Newtons First Law" in headings
    assert len(result.tables) == 1
    assert result.tables[0].rows[0] == ["Term", "Definition"]
    assert any("F = m * a" in eq.text for eq in result.equations)
