import importlib.util
from pathlib import Path


def test_source_archive_includes_nested_client_modules():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('verify_archive', root / 'tools/verify_and_archive.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, runtime, source = module.file_sets()
    nested = {p.relative_to(root).as_posix() for p in (root / 'client/ocean').rglob('*') if p.is_file()}
    assert len(nested) >= 6
    assert nested <= source
    assert not nested & runtime
    assert 'client/AmbientOcean.jsx' in source
    assert 'assets/ocean/living/manifest.json' in runtime
