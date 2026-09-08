"""Delta protocol and builder checks, including corruption and partial input."""
from pathlib import Path
import copy
import io
import json
import struct
import sys
import tempfile
import unittest
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import build_bundle as bundle


def synthetic_build():
    """Small PE32+ pair with one hook, one debug edit and duplicated .pdata."""
    def headers(count, exception_rva, exception_size, image_size):
        raw = bytearray(512)
        raw[:2] = b'MZ'
        struct.pack_into('<I', raw, 0x3c, 0x40)
        raw[0x40:0x44] = b'PE\0\0'
        struct.pack_into('<HHIIIHH', raw, 0x44, 0x8664, count, 0, 0, 0, 240, 0x22)
        optional = 0x58
        struct.pack_into('<H', raw, optional, 0x20b)
        struct.pack_into('<Q', raw, optional + 24, 0x140000000)
        struct.pack_into('<II', raw, optional + 32, 0x1000, 512)
        struct.pack_into('<II', raw, optional + 56, image_size, 512)
        struct.pack_into('<I', raw, optional + 108, 16)
        struct.pack_into('<II', raw, optional + 112 + 24, exception_rva, exception_size)
        sections = [(b'.text', 0x1000, 512, 512), (b'.pdata', 0x2000, 1024, 12)]
        if count == 3:
            sections.append((b'.exact', 0x3000, 1536, 512))
        for index, (name, rva, offset, length) in enumerate(sections):
            struct.pack_into('<8sIIIIIIHHI', raw, optional + 240 + index * 40,
                             name, length, rva, 512, offset, 0, 0, 0, 0, 0x60000040)
        return raw
    old_table = struct.pack('<III', 0x1000, 0x1010, 0x1100)
    source = headers(2, 0x2000, 12, 0x3000) + bytearray(1024)
    source[512:1024] = bytes(range(256)) * 2
    source[600:605] = bytes.fromhex('e801020304')
    struct.pack_into('<I', source, 620, 0x1234)
    source[1024:1036] = old_table
    output = headers(3, 0x3040, 24, 0x4000) + source[512:] + bytearray(512)
    output[600:605] = bytes.fromhex('e805060708')
    struct.pack_into('<I', output, 620, 0x5678)
    output[1536:1600] = b'PAYLOAD!' * 8
    output[1600:1612] = old_table
    output[1612:1624] = struct.pack('<III', 0x3000, 0x3010, 0x3030)
    report = {'input_sha256': bundle.sha256(source), 'output_sha256': bundle.sha256(output),
              'telegram_version': '7.2.7', 'headers': {'raw_file_shift': 0},
              'new_section': {'raw_offset': '0x600'},
              'exceptions': {'original_count': 1, 'merged_count': 2},
              'hooks': [{'site_rva': '0x1058', 'original_bytes': 'e801020304',
                         'patched_bytes': 'e805060708'}],
              'debug_raw_pointer_updates': [{'original_file_offset': 620,
                                             'old': 0x1234, 'new': 0x5678}]}
    return bytes(source), bytes(output), report


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.source = bytes(range(256)) * 4
        self.literal = b'new\0payload\xe8'
        self.output = self.source[8:40] + self.literal + bytes(64) + self.source[100:220]
        self.ops = [{'op': 'copy', 'offset': 8, 'length': 32},
                    {'op': 'data', 'offset': 0, 'length': len(self.literal)},
                    {'op': 'zero', 'length': 64},
                    {'op': 'copy', 'offset': 100, 'length': 120}]
        self.manifest = bundle.make_manifest(self.source, self.output, self.literal,
                                             self.ops, '7.2.7', 'r4')

    def test_deterministic_zip_and_exact_reconstruction(self):
        first = bundle.encode_bundle(self.manifest, self.literal)
        self.assertEqual(first, bundle.encode_bundle(self.manifest, self.literal))
        manifest, literal = bundle.read_bundle(first)
        self.assertEqual(bundle.reconstruct(manifest, self.source, literal), self.output)
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            self.assertEqual(archive.namelist(), ['manifest.json', 'literal.bin'])
            self.assertTrue(all(x.date_time == (1980, 1, 1, 0, 0, 0) for x in archive.infolist()))

    def test_refuse_partial_or_wrong_source(self):
        for source in (self.source[:-1], bytes(len(self.source))):
            with self.subTest(length=len(source)), self.assertRaisesRegex(ValueError, 'Original EXE'):
                bundle.reconstruct(self.manifest, source, self.literal)

    def test_refuse_corrupt_or_partial_literals(self):
        for literal in (self.literal[:-1], bytes(len(self.literal))):
            with self.subTest(length=len(literal)), self.assertRaisesRegex(ValueError, 'Literal'):
                bundle.reconstruct(self.manifest, self.source, literal)

    def test_refuse_changed_recipe_with_valid_literal_hash(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['operations'][0]['offset'] += 1
        with self.assertRaisesRegex(ValueError, 'output hash'):
            bundle.reconstruct(manifest, self.source, self.literal)

    def test_validate_unused_literal_bytes_too(self):
        manifest = bundle.make_manifest(self.source, self.source[:8], self.literal,
                                        [{'op': 'copy', 'offset': 0, 'length': 8}], '7.2.7', 'r4')
        with self.assertRaisesRegex(ValueError, 'Literal'):
            bundle.reconstruct(manifest, self.source, bytes(len(self.literal)))

    def test_reject_unknown_schema_algorithm_and_extra_manifest_fields(self):
        for key, value in [('schema', 2), ('schema', True), ('algorithm', 'shell'),
                           ('command', 'never-execute'), ('output_sha256', 'x' * 64)]:
            manifest = copy.deepcopy(self.manifest)
            manifest[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                bundle.validate_manifest(manifest)

    def test_bounds_and_integer_checks(self):
        changes = [('offset', -1), ('offset', len(self.source)), ('offset', 1.5),
                   ('offset', True), ('length', 0), ('length', -1),
                   ('length', bundle.MAX_IMAGE + 1)]
        for key, value in changes:
            manifest = copy.deepcopy(self.manifest)
            manifest['operations'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                bundle.validate_manifest(manifest)
        for key, value in [('input_length', bundle.MAX_IMAGE + 1),
                           ('output_length', len(self.output) - 1),
                           ('output_length', len(self.output) + 1),
                           ('literal_length', bundle.MAX_LITERAL + 1)]:
            manifest = copy.deepcopy(self.manifest)
            manifest[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                bundle.validate_manifest(manifest)

    def test_operation_shape_limits(self):
        for operation in ({'op': 'run', 'length': 1},
                          {'op': 'zero', 'length': 1, 'offset': 0},
                          {'op': 'copy', 'length': 1, 'offset': 0, 'path': '../x'},
                          {'op': 'data', 'length': 1, 'offset': len(self.literal)}):
            manifest = copy.deepcopy(self.manifest)
            manifest['operations'][0] = operation
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                bundle.validate_manifest(manifest)
        manifest = copy.deepcopy(self.manifest)
        manifest['operations'] = [{'op': 'zero', 'length': 1}] * (bundle.MAX_OPERATIONS + 1)
        with self.assertRaisesRegex(ValueError, 'operation count'):
            bundle.validate_manifest(manifest)

    def make_zip(self, entries):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                for name, data in entries:
                    archive.writestr(name, data)
        return output.getvalue()

    def test_reject_extra_duplicate_and_path_entries(self):
        original = [('manifest.json', json.dumps(self.manifest)), ('literal.bin', self.literal)]
        for extra in [('literal.bin', b'x'), ('../escape.exe', b'x'), ('script.ps1', b'x')]:
            with self.subTest(extra=extra[0]), self.assertRaises(ValueError):
                bundle.read_bundle(self.make_zip(original + [extra]))

    def test_reject_zip_size_limit_before_reading(self):
        entries = [('manifest.json', b' ' * (bundle.MAX_MANIFEST + 1)), ('literal.bin', b'')]
        with self.assertRaisesRegex(ValueError, 'size limit'):
            bundle.read_bundle(self.make_zip(entries))

    def test_reject_duplicate_json_and_partial_zip(self):
        raw = json.dumps(self.manifest)
        raw = '{"schema":1,' + raw[1:]
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            bundle.read_bundle(self.make_zip([('manifest.json', raw), ('literal.bin', self.literal)]))
        zipped = bundle.encode_bundle(self.manifest, self.literal)
        with self.assertRaises(zipfile.BadZipFile):
            bundle.read_bundle(zipped[:-20])

    def test_recipe_copies_original_exception_table(self):
        source, output, report = synthetic_build()
        operations, literal = bundle.recipe_from_build(source, output, report)
        self.assertIn({'op': 'copy', 'offset': 1024, 'length': 12}, operations)
        manifest = bundle.make_manifest(source, output, literal, operations, '7.2.7', 'r4')
        self.assertEqual(bundle.reconstruct(manifest, source, literal), output)

    def test_recipe_rejects_unreported_mutation_and_wrong_build_report(self):
        source, output, report = synthetic_build()
        altered = bytearray(output)
        altered[800] ^= 1
        report['output_sha256'] = bundle.sha256(altered)
        with self.assertRaisesRegex(ValueError, 'Unreported output mutation'):
            bundle.recipe_from_build(source, altered, report)
        report['input_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'input hash'):
            bundle.recipe_from_build(source, altered, report)

    def test_builder_never_overwrites_inputs_or_existing_bundle(self):
        source, output, report = synthetic_build()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a, b, r, result = [root / name for name in ('source.exe', 'patched.exe', 'report.json', 'delta.tgpatch')]
            a.write_bytes(source)
            b.write_bytes(output)
            r.write_text(json.dumps(report), 'utf-8')
            record = bundle.build_bundle(a, b, r, result)
            self.assertTrue(record['reconstruction_verified'])
            first = result.read_bytes()
            with self.assertRaises(FileExistsError):
                bundle.build_bundle(a, b, r, result)
            with self.assertRaisesRegex(ValueError, 'overwrite build inputs'):
                bundle.build_bundle(a, b, r, a)
            self.assertEqual(result.read_bytes(), first)
            self.assertEqual(a.read_bytes(), source)
            self.assertEqual(b.read_bytes(), output)
            self.assertNotIn(str(root).encode(), zipfile.ZipFile(io.BytesIO(first)).read('manifest.json'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
