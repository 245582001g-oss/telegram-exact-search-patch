"""Unknown-version rejection must happen before compilation or output creation."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'src'))
import build_patch

manifest = json.loads((REPO / 'compatibility.json').read_text('utf-8'))
assert manifest['input_sha256'] == build_patch.EXPECTED_SHA256
assert manifest['telegram_version'] == build_patch.TELEGRAM_VERSION

work = REPO / 'work'
work.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='reject-', dir=work) as temporary:
    root = Path(temporary)
    original = root / 'input' / 'Telegram.exe'
    original.parent.mkdir()
    original.write_bytes(b'MZ synthetic unsupported Telegram build')
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    output = root / 'output'
    with patch.object(build_patch, 'compile_payload') as compile_payload:
        try:
            build_patch.build_patch(original, output, root / 'unused-gcc.exe')
        except RuntimeError as error:
            assert 'hash mismatch' in str(error), error
        else:
            raise AssertionError('Unsupported input was accepted')
        compile_payload.assert_not_called()
    assert not output.exists(), 'Unknown input created output files'
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
print('PASS: manifest/build agreement; unknown input rejected before compilation or writes')
