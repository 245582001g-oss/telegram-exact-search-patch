"""Create a deterministic hash-bound delta; ordinary users need only PowerShell.

The ZIP contains a JSON recipe and compressed literal bytes. COPY operations read
the user's original EXE, including its unchanged exception table. No executable
or installation path is stored in the package. This tool never installs a patch.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import zipfile

ALGORITHM = 'telegram-exact-copy-data-zero-v1'
MAX_IMAGE = 1024 * 1024 * 1024
MAX_LITERAL = 16 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024
MAX_OPERATIONS = 4096
MANIFEST_KEYS = {'schema', 'algorithm', 'telegram_version', 'patch_revision',
                 'input_sha256', 'output_sha256', 'input_length', 'output_length',
                 'literal_sha256', 'literal_length', 'operations'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def integer(value, minimum, maximum, description):
    require(type(value) is int and minimum <= value <= maximum,
            f'Invalid {description}')
    return value


def validate_manifest(manifest):
    require(isinstance(manifest, dict) and set(manifest) == MANIFEST_KEYS,
            'Unexpected manifest fields')
    require(type(manifest['schema']) is int and manifest['schema'] == 1,
            'Unsupported bundle schema')
    require(manifest['algorithm'] == ALGORITHM, 'Unsupported delta algorithm')
    require(isinstance(manifest['telegram_version'], str) and
            re.fullmatch(r'[0-9]+(?:\.[0-9]+){2,3}', manifest['telegram_version']),
            'Invalid Telegram version')
    require(isinstance(manifest['patch_revision'], str) and
            re.fullmatch(r'r[0-9]+', manifest['patch_revision']), 'Invalid patch revision')
    for key in ('input_sha256', 'output_sha256', 'literal_sha256'):
        require(isinstance(manifest[key], str) and
                re.fullmatch(r'[0-9a-f]{64}', manifest[key]), f'Invalid {key}')
    source_size = integer(manifest['input_length'], 1, MAX_IMAGE, 'input length')
    output_size = integer(manifest['output_length'], 1, MAX_IMAGE, 'output length')
    literal_size = integer(manifest['literal_length'], 0, MAX_LITERAL, 'literal length')
    operations = manifest['operations']
    require(isinstance(operations, list) and 1 <= len(operations) <= MAX_OPERATIONS,
            'Invalid operation count')
    position = 0
    for op in operations:
        require(isinstance(op, dict), 'Operation must be an object')
        kind = op.get('op')
        require(kind in ('copy', 'data', 'zero'), 'Unknown operation')
        require(set(op) == ({'op', 'length'} if kind == 'zero'
                            else {'op', 'offset', 'length'}), 'Unexpected operation fields')
        length = integer(op['length'], 1, MAX_IMAGE, 'operation length')
        if kind != 'zero':
            limit = source_size if kind == 'copy' else literal_size
            offset = integer(op['offset'], 0, limit, 'operation offset')
            require(length <= limit - offset, 'Operation exceeds source bounds')
        require(length <= output_size - position, 'Operation exceeds output bounds')
        position += length
    require(position == output_size, 'Operations do not cover complete output')
    return manifest


def make_manifest(source, output, literal, operations, version, revision):
    result = {'schema': 1, 'algorithm': ALGORITHM, 'telegram_version': version,
              'patch_revision': revision, 'input_sha256': sha256(source),
              'output_sha256': sha256(output), 'input_length': len(source),
              'output_length': len(output), 'literal_sha256': sha256(literal),
              'literal_length': len(literal), 'operations': operations}
    return validate_manifest(result)


def validate_data(manifest, source, literal):
    validate_manifest(manifest)
    require(len(source) == manifest['input_length'] and
            sha256(source) == manifest['input_sha256'], 'Original EXE hash/size mismatch')
    require(len(literal) == manifest['literal_length'] and
            sha256(literal) == manifest['literal_sha256'], 'Literal data hash/size mismatch')


def output_chunks(manifest, source, literal):
    """Bounded chunks, shared by developer verification and reference tests."""
    zero = bytes(1024 * 1024)
    for op in manifest['operations']:
        length = op['length']
        offset = op.get('offset', 0)
        while length:
            count = min(length, len(zero))
            if op['op'] == 'zero':
                yield zero[:count]
            else:
                data = source if op['op'] == 'copy' else literal
                yield data[offset:offset + count]
                offset += count
            length -= count


def reconstruct(manifest, source, literal):
    """Reference application for tests; PowerShell performs end-user application."""
    validate_data(manifest, source, literal)
    result = b''.join(output_chunks(manifest, source, literal))
    require(sha256(result) == manifest['output_sha256'], 'Reconstructed output hash mismatch')
    return result


def encode_bundle(manifest, literal):
    validate_manifest(manifest)
    require(len(literal) == manifest['literal_length'] and
            sha256(literal) == manifest['literal_sha256'], 'Literal data hash/size mismatch')
    raw_manifest = (json.dumps(manifest, ensure_ascii=True, sort_keys=True,
                               separators=(',', ':')) + '\n').encode('utf-8')
    require(len(raw_manifest) <= MAX_MANIFEST, 'Manifest too large')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, allowZip64=False) as archive:
        for name, data in [('manifest.json', raw_manifest), ('literal.bin', literal)]:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0x20
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)
    return buffer.getvalue()


def read_bundle(data):
    """Strict reference parser; reads ZIP entries directly, never extracts files."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        require(len(entries) == 2 and {x.filename for x in entries} ==
                {'manifest.json', 'literal.bin'}, 'Unexpected or duplicate ZIP entries')
        for entry in entries:
            require(entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                    'Unsupported ZIP compression')
            limit = MAX_MANIFEST if entry.filename == 'manifest.json' else MAX_LITERAL
            require(0 <= entry.file_size <= limit, 'ZIP entry exceeds size limit')
        raw = archive.read('manifest.json')
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, 'Duplicate JSON field')
                result[key] = value
            return result
        manifest = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object)
        validate_manifest(manifest)
        literal = archive.read('literal.bin')
        require(len(literal) == manifest['literal_length'] and
                sha256(literal) == manifest['literal_sha256'], 'Literal data hash/size mismatch')
        return manifest, literal


def recipe_from_build(source, patched, report):
    """Use the builder's checked edit list; prove every proposed COPY byte."""
    import pefile
    require(len(source) <= MAX_IMAGE and len(patched) <= MAX_IMAGE, 'Image exceeds size limit')
    require(sha256(source) == report['input_sha256'], 'Build report input hash mismatch')
    require(sha256(patched) == report['output_sha256'], 'Build report output hash mismatch')
    old = pefile.PE(data=source, fast_load=True)
    new = pefile.PE(data=patched, fast_load=True)
    try:
        old_header = old.OPTIONAL_HEADER.SizeOfHeaders
        new_header = new.OPTIONAL_HEADER.SizeOfHeaders
        shift = new_header - old_header
        require(shift >= 0 and shift == report['headers']['raw_file_shift'], 'Header shift mismatch')
        exact = new.sections[-1]
        require(exact.Name.rstrip(b'\0') == b'.exact', 'Missing final exact section')
        require(exact.PointerToRawData == number(report['new_section']['raw_offset']),
                'Exact section offset mismatch')
        old_exception = old.OPTIONAL_HEADER.DATA_DIRECTORY[3]
        new_exception = new.OPTIONAL_HEADER.DATA_DIRECTORY[3]
        old_exception_offset = old.get_offset_from_rva(old_exception.VirtualAddress)
        new_exception_offset = new.get_offset_from_rva(new_exception.VirtualAddress)
        require(old_exception.Size == report['exceptions']['original_count'] * 12,
                'Original exception table size mismatch')
        require(new_exception.Size == report['exceptions']['merged_count'] * 12 and
                new_exception.Size >= old_exception.Size, 'Merged exception table size mismatch')
        require(exact.PointerToRawData <= new_exception_offset and
                new_exception_offset + new_exception.Size <= len(patched),
                'New exception table out of bounds')
        changes = []
        for hook in report['hooks']:
            site = number(hook['site_rva'])
            old_offset = old.get_offset_from_rva(site)
            new_offset = new.get_offset_from_rva(site)
            before, after = bytes.fromhex(hook['original_bytes']), bytes.fromhex(hook['patched_bytes'])
            require(len(before) == len(after) == 5 and new_offset == old_offset + shift,
                    'Hook relocation mismatch')
            require(source[old_offset:old_offset + 5] == before and
                    patched[new_offset:new_offset + 5] == after, 'Hook bytes mismatch')
            changes.append((new_offset, 5))
        for debug in report['debug_raw_pointer_updates']:
            old_offset = debug['original_file_offset']
            new_offset = old_offset + shift
            require(source[old_offset:old_offset + 4] == struct.pack('<I', debug['old']) and
                    patched[new_offset:new_offset + 4] == struct.pack('<I', debug['new']),
                    'Debug pointer bytes mismatch')
            changes.append((new_offset, 4))
        operations, literal = [], bytearray()
        output_position = 0
        def emit(kind, length, offset=0):
            nonlocal output_position
            if not length:
                return
            require(length > 0, 'Overlapping or inverted copy spans')
            if kind == 'copy':
                require(source[offset:offset + length] ==
                        patched[output_position:output_position + length],
                        f'Unreported output mutation at {output_position:#x}')
            elif kind == 'data':
                offset = len(literal)
                literal.extend(patched[output_position:output_position + length])
            else:
                require(not any(patched[output_position:output_position + length]),
                        'Padding contains nonzero data')
            op = {'op': kind, 'length': length}
            if kind != 'zero':
                op['offset'] = offset
            operations.append(op)
            output_position += length
        emit('data', new_header)
        for offset, length in sorted(changes):
            require(offset >= output_position and offset + length <= len(source) + shift,
                    'Mutation outside copied image body')
            emit('copy', offset - output_position, output_position - shift)
            emit('data', length)
        emit('copy', len(source) + shift - output_position, output_position - shift)
        emit('zero', exact.PointerToRawData - output_position)
        emit('data', new_exception_offset - output_position)
        emit('copy', old_exception.Size, old_exception_offset)
        emit('data', len(patched) - output_position)
        require(output_position == len(patched), 'Incomplete generated recipe')
        return operations, bytes(literal)
    finally:
        old.close()
        new.close()


def build_bundle(input_path, patched_path, report_path, output_path, revision='r4'):
    paths = [Path(p).resolve() for p in (input_path, patched_path, report_path, output_path)]
    input_path, patched_path, report_path, output_path = paths
    require(output_path not in paths[:3], 'Output must not overwrite build inputs')
    require(1 <= input_path.stat().st_size <= MAX_IMAGE and
            1 <= patched_path.stat().st_size <= MAX_IMAGE, 'Image exceeds size limit')
    require(report_path.stat().st_size <= MAX_MANIFEST, 'Build report too large')
    source, patched = input_path.read_bytes(), patched_path.read_bytes()
    report = json.loads(report_path.read_text('utf-8'))
    operations, literal = recipe_from_build(source, patched, report)
    manifest = make_manifest(source, patched, literal, operations, report['telegram_version'], revision)
    validate_data(manifest, source, literal)
    digest = hashlib.sha256()
    position = 0
    for chunk in output_chunks(manifest, source, literal):
        require(chunk == patched[position:position + len(chunk)], 'Reconstruction mismatch')
        digest.update(chunk)
        position += len(chunk)
    require(digest.hexdigest() == manifest['output_sha256'], 'Reconstruction hash mismatch')
    bundle = encode_bundle(manifest, literal)
    parsed_manifest, parsed_literal = read_bundle(bundle)
    require(parsed_manifest == manifest and parsed_literal == literal, 'Bundle roundtrip mismatch')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('xb') as destination:
        destination.write(bundle)
    return {'bundle': str(output_path), 'bundle_sha256': sha256(bundle), 'bundle_length': len(bundle),
            'literal_length': len(literal), 'operation_count': len(operations),
            'copied_bytes': sum(op['length'] for op in operations if op['op'] == 'copy'),
            'input_sha256': manifest['input_sha256'], 'output_sha256': manifest['output_sha256'],
            'input_length': len(source), 'output_length': len(patched),
            'telegram_version': manifest['telegram_version'], 'patch_revision': revision,
            'reconstruction_verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Original supported EXE (read-only)')
    parser.add_argument('--patched', type=Path, required=True, help='Verified build output (read-only)')
    parser.add_argument('--build-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New .tgpatch file; refuses overwrite')
    parser.add_argument('--patch-revision', default='r4')
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.input, args.patched, args.build_report,
                                 args.output, args.patch_revision), indent=2))


if __name__ == '__main__':
    main()
