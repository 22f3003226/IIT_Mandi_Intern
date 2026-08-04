import pytest

from app.parsers.router import UnsupportedFormatError, route_and_parse


def test_router_dispatches_txt_by_extension(sample_txt):
    result = route_and_parse(str(sample_txt))
    assert result.metadata.format == "txt"


def test_router_dispatches_pdf_and_passes_hint(sample_pdf):
    result = route_and_parse(str(sample_pdf), doc_nature_hint="Mostly Text")
    assert result.metadata.format == "pdf"


def test_router_rejects_unsupported_extension(tmp_path):
    bad_file = tmp_path / "notes.xyz"
    bad_file.write_text("hello")
    with pytest.raises(UnsupportedFormatError):
        route_and_parse(str(bad_file))
