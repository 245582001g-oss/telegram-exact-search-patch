"""Build a hash-bound local Telegram PE patch; never deploy or modify the input.

The payload is linked at its final RVAs. The original image keeps every section
RVA and its entry point. An expanded file header creates room for one .exact
section, with raw-file offsets (including debug data pointers) adjusted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import pefile

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE.parent / 'build'
TELEGRAM_VERSION = '7.2.7'
EXPECTED_SHA256 = '16a234e303ecbafde90e0f5ee27e13a40595453f33896fa340d9cb186df60397'
IMAGE_BASE = 0x140000000
ORIGINAL_IMAGE_SIZE = 0xE3F5000
PAYLOAD_RVA = ORIGINAL_IMAGE_SIZE
EXCEPTION = pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']
SECURITY = pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_SECURITY']
RELOC = pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_BASERELOC']
DEBUG = pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DEBUG']
IMPORT = pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']
DELAY_IMPORT = pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']
TLS = pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_TLS']

def align(value: int, alignment: int) -> int:
    assert alignment > 0 and alignment & (alignment-1) == 0
    return (value + alignment - 1) & ~(alignment - 1)

def digest(value: bytes | bytearray) -> str:
    return hashlib.sha256(value).hexdigest()

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def number(value):
    return int(value, 0) if isinstance(value, str) else int(value)

def find_gcc(value: str | None) -> Path:
    """Accept --gcc/GCC, or discover a MinGW-w64 compiler on PATH."""
    candidate = value or os.environ.get('GCC')
    if candidate:
        compiler = shutil.which(candidate) or candidate
    else:
        compiler = shutil.which('x86_64-w64-mingw32-gcc') or shutil.which('gcc')
    require(compiler, 'MinGW-w64 GCC not found; pass --gcc PATH or set GCC/PATH')
    path = Path(compiler).expanduser().resolve()
    require(path.is_file(), f'Compiler missing: {path}')
    completed = subprocess.run([str(path), '-dumpmachine'], capture_output=True, text=True)
    require(completed.returncode == 0 and completed.stdout.strip() == 'x86_64-w64-mingw32',
            'Expected a Windows x64 MinGW-w64 GCC compiler (x86_64-w64-mingw32)')
    return path

def directory(pe, index):
    return pe.OPTIONAL_HEADER.DATA_DIRECTORY[index]

def get_table(pe, index):
    d = directory(pe, index)
    return pe.get_data(d.VirtualAddress, d.Size) if d.VirtualAddress and d.Size else b''

def exceptions(pe):
    data = get_table(pe, EXCEPTION)
    require(len(data) % 12 == 0, 'Malformed exception table size')
    result = [entry for entry in struct.iter_unpack('<III', data) if any(entry)]
    for begin, end, unwind in result:
        require(begin < end and unwind, 'Malformed runtime function entry')
        require(end <= pe.OPTIONAL_HEADER.SizeOfImage, 'Exception function exceeds image')
    return result

def relocations(pe):
    data = get_table(pe, RELOC)
    result = []
    pos = 0
    while pos < len(data):
        require(pos + 8 <= len(data), 'Truncated base relocation block')
        page, size = struct.unpack_from('<II', data, pos)
        if page == 0 and size == 0:
            require(not any(data[pos:]), 'Unexpected data after relocation terminator')
            break
        require(size >= 8 and size % 2 == 0 and pos + size <= len(data), 'Bad relocation size')
        for (entry,) in struct.iter_unpack('<H', data[pos+8:pos+size]):
            kind, offset = entry >> 12, entry & 0xfff
            if kind:
                # AMD64 linker is expected to use only DIR64/HIGHLOW. HIGHADJ
                # consumes an extra word and must not be silently reinterpreted.
                require(kind in (3, 10), f'Unsupported relocation kind {kind}')
                result.append((page+offset, kind))
        pos += size
    return result

def encode_relocations(entries):
    pages = {}
    for rva, kind in sorted(set(entries)):
        pages.setdefault(rva & ~0xfff, []).append((kind << 12) | (rva & 0xfff))
    result = bytearray()
    for page, values in sorted(pages.items()):
        if len(values) & 1:
            values.append(0)
        result += struct.pack('<II', page, 8+2*len(values))
        result += struct.pack('<'+'H'*len(values), *values)
    return result

def compile_payload(gcc: Path, output: Path):
    build = output / 'build'
    build.mkdir(parents=True, exist_ok=True)
    require(gcc.is_file(), f'Compiler missing: {gcc}')
    source_hashes = {}
    for name in ('payload.c', 'hooks.S', 'hooks.json', 'blacklist.h', 'menu.h'):
        require((HERE/name).is_file(), f'Missing {name}')
        source = (HERE/name).read_bytes()
        source_hashes[name] = digest(source)
        # Immutable build inputs avoid mixing concurrently edited sources with
        # a hook manifest from a different revision of the parent's work.
        (build/(name if name.endswith('.h') else 'input-'+name)).write_bytes(source)
    env = os.environ.copy()
    env['PATH'] = str(gcc.parent) + os.pathsep + env.get('PATH', '')
    commands = [
        [str(gcc), '-c', str(build/'input-payload.c'), '-o', str(build/'payload.o'),
         '-std=c11', '-Os', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
         '-fno-ident', '-fasynchronous-unwind-tables', '-Wall', '-Wextra'],
        [str(gcc), '-c', str(build/'input-hooks.S'), '-o', str(build/'hooks.o')],
        [str(gcc), '-shared', '-nostdlib', '-o', str(build/'payload.exe'),
         str(build/'payload.o'), str(build/'hooks.o'),
         f'-Wl,--image-base,{IMAGE_BASE:#x}', f'-Wl,--section-start,.text={IMAGE_BASE+PAYLOAD_RVA:#x}',
         '-Wl,--file-alignment,0x200', '-Wl,--section-alignment,0x1000',
         '-Wl,--entry,PatchMessages', '-Wl,--export-all-symbols',
         '-Wl,--disable-auto-import', '-Wl,--no-insert-timestamp',
         '-Wl,--dynamicbase', '-Wl,--nxcompat', '-Wl,--high-entropy-va'],
    ]
    logs = []
    for args in commands:
        completed = subprocess.run(args, capture_output=True, text=True, env=env)
        logs.append({'argv': args, 'returncode': completed.returncode,
                     'stdout': completed.stdout, 'stderr': completed.stderr})
        (build/'compiler-log.json').write_text(json.dumps(logs, indent=2), encoding='utf-8')
        require(completed.returncode == 0, f'Compiler failed: {completed.stderr}')
    return build/'payload.exe', logs, source_hashes, build/'input-hooks.json'

def build_patch(input_path: Path, output: Path, gcc: Path):
    input_path = input_path.resolve()
    output = output.resolve()
    require(output != input_path.parent and input_path.parent not in output.parents,
            'Output must remain outside the Telegram installation')
    original = input_path.read_bytes()
    require(digest(original) == EXPECTED_SHA256, 'Original EXE hash mismatch; refuse version-unsafe patch')
    output.mkdir(parents=True, exist_ok=True)
    pe = pefile.PE(data=original, fast_load=True)
    require(pe.FILE_HEADER.Machine == 0x8664 and pe.OPTIONAL_HEADER.Magic == 0x20b, 'Expected AMD64 PE32+')
    require(pe.OPTIONAL_HEADER.ImageBase == IMAGE_BASE, 'Unexpected preferred image base')
    require(pe.OPTIONAL_HEADER.SizeOfImage == ORIGINAL_IMAGE_SIZE, 'Unexpected original image size')
    require(PAYLOAD_RVA == align(pe.sections[-1].VirtualAddress +
        max(pe.sections[-1].Misc_VirtualSize, pe.sections[-1].SizeOfRawData),
        pe.OPTIONAL_HEADER.SectionAlignment), 'Windows image section RVAs must be adjacent')
    payload_path, compiler_logs, source_hashes, hooks_path = compile_payload(gcc, output)
    payload_raw = payload_path.read_bytes()
    payload = pefile.PE(data=payload_raw, fast_load=True)
    payload.parse_data_directories(directories=[0, IMPORT, DELAY_IMPORT])
    require(payload.OPTIONAL_HEADER.ImageBase == IMAGE_BASE, 'Payload preferred base mismatch')
    require(not getattr(payload, 'DIRECTORY_ENTRY_IMPORT', []), 'Payload imports are forbidden')
    require(not getattr(payload, 'DIRECTORY_ENTRY_DELAY_IMPORT', []), 'Payload delay imports are forbidden')
    require(not directory(payload, TLS).VirtualAddress, 'Payload TLS initialization is unsupported')
    exports = {e.name.decode('ascii'): e.address for e in payload.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
    sections = [s for s in payload.sections if s.Misc_VirtualSize or s.SizeOfRawData]
    require(sections and min(s.VirtualAddress for s in sections) == PAYLOAD_RVA, 'Unexpected payload first RVA')
    max_end = max(s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData) for s in sections)
    require(max_end-PAYLOAD_RVA < 16*1024*1024, 'Unexpectedly large/non-contiguous payload')
    content = bytearray(max_end-PAYLOAD_RVA)
    payload_sections = []
    for s in sections:
        name = s.Name.rstrip(b'\0').decode('ascii')
        require(s.VirtualAddress >= PAYLOAD_RVA, 'Payload section overlaps original image')
        data = s.get_data()
        offset = s.VirtualAddress-PAYLOAD_RVA
        content[offset:offset+len(data)] = data
        payload_sections.append({'name': name, 'rva': hex(s.VirtualAddress),
            'virtual_size': s.Misc_VirtualSize, 'raw_size': s.SizeOfRawData,
            'characteristics': hex(s.Characteristics)})

    original_functions = exceptions(pe)
    payload_functions = exceptions(payload)
    require(payload_functions, 'Payload requires unwind entries')
    combined_functions = sorted(original_functions + payload_functions)
    require(len({x[0] for x in combined_functions}) == len(combined_functions), 'Duplicate exception function RVA')
    require(all(a[1] <= b[0] for a,b in zip(combined_functions,combined_functions[1:])), 'Overlapping exception function ranges')
    exception_offset = align(len(content), 4)
    content.extend(b'\0' * (exception_offset-len(content)))
    exception_data = b''.join(struct.pack('<III', *e) for e in combined_functions)
    content.extend(exception_data)

    original_relocs = relocations(pe)
    payload_relocs = relocations(payload)
    relocation_rva, relocation_size = directory(pe,RELOC).VirtualAddress, directory(pe,RELOC).Size
    if payload_relocs:
        relocation_offset = align(len(content), 4)
        content.extend(b'\0' * (relocation_offset-len(content)))
        relocated_data = encode_relocations(original_relocs + payload_relocs)
        content.extend(relocated_data)
        relocation_rva, relocation_size = PAYLOAD_RVA+relocation_offset, len(relocated_data)

    old_headers = pe.OPTIONAL_HEADER.SizeOfHeaders
    header_offset = pe.sections[-1].get_file_offset()+40
    file_alignment = pe.OPTIONAL_HEADER.FileAlignment
    section_alignment = pe.OPTIONAL_HEADER.SectionAlignment
    new_headers = align(max(old_headers,header_offset+40),file_alignment)
    shift = new_headers-old_headers
    first_raw = min(s.PointerToRawData for s in pe.sections if s.SizeOfRawData)
    require(first_raw >= old_headers, 'Original raw data overlaps headers')
    require(not any(original[header_offset:old_headers]), 'Occupied header bytes would be overwritten')
    result = bytearray(original[:old_headers] + b'\0'*shift + original[old_headers:])
    changes = []
    def put(offset, fmt, value, reason):
        before = bytes(result[offset:offset+struct.calcsize(fmt)])
        after = struct.pack(fmt,value)
        result[offset:offset+len(after)] = after
        if before != after:
            changes.append({'file_offset':hex(offset),'size':len(after),'before':before.hex(),'after':after.hex(),'reason':reason})
    def map_offset(offset):
        return offset+shift if offset >= old_headers else offset
    def field(obj, key, value, reason, fmt='<I'):
        put(obj.get_field_absolute_offset(key),fmt,value,reason)
    def set_directory(index,rva,size):
        d = directory(pe,index)
        field(d,'VirtualAddress',rva,f'data directory {index} RVA')
        field(d,'Size',size,f'data directory {index} size')

    field(pe.FILE_HEADER,'NumberOfSections',pe.FILE_HEADER.NumberOfSections+1,'add .exact section','<H')
    field(pe.OPTIONAL_HEADER,'SizeOfHeaders',new_headers,'make room for section header')
    for s in pe.sections:
        for key in ('PointerToRawData','PointerToRelocations','PointerToLinenumbers'):
            value = getattr(s,key)
            if value and shift:
                field(s,key,map_offset(value),'header expansion: '+key)
    if pe.FILE_HEADER.PointerToSymbolTable and shift:
        field(pe.FILE_HEADER,'PointerToSymbolTable',map_offset(pe.FILE_HEADER.PointerToSymbolTable),'header expansion: COFF symbols')
    debug_changes = []
    debug_dir = directory(pe,DEBUG)
    require(debug_dir.Size % 28 == 0,'Unexpected debug directory size')
    if debug_dir.VirtualAddress and shift:
        debug_offset = pe.get_offset_from_rva(debug_dir.VirtualAddress)
        for index in range(debug_dir.Size//28):
            entry = debug_offset + index*28
            pointer = struct.unpack_from('<I',original,entry+24)[0]
            if pointer:
                new_pointer = map_offset(pointer)
                put(map_offset(entry)+24,'<I',new_pointer,'header expansion: debug PointerToRawData')
                debug_changes.append({'original_file_offset':entry+24,'old':pointer,'new':new_pointer})

    hooks = json.loads(hooks_path.read_text(encoding='utf-8'))
    require(isinstance(hooks,list) and hooks,'hooks.json must contain a nonempty hook array')
    hook_report = []
    seen_sites = set()
    for hook in hooks:
        site = number(hook['site_rva'])
        covered = set(range(site,site+5))
        require(not seen_sites.intersection(covered),'Overlapping hook sites')
        seen_sites.update(covered)
        offset = pe.get_offset_from_rva(site)
        previous = original[offset:offset+5]
        if hook.get('kind') == 'literal5':
            expected_bytes = bytes.fromhex(hook['expected_bytes'])
            replacement = bytes.fromhex(hook['replacement_bytes'])
            require(len(expected_bytes)==5 and len(replacement)==5,'Literal patch must preserve 5-byte instruction size')
            require(previous==expected_bytes,f'Literal instruction mismatch at {site:#x}')
            mapped = map_offset(offset)
            result[mapped:mapped+5] = replacement
            hook_report.append({'site_rva':hex(site),'kind':'literal5','reason':hook['reason'],
                'original_bytes':previous.hex(),'patched_bytes':replacement.hex(),'file_offset':hex(mapped)})
            continue
        require(hook.get('kind','call')=='call','Unsupported hook kind')
        expected = number(hook['expected_target_rva'])
        name = hook['target_export']
        require(name in exports,f'Missing payload export {name}')
        target = exports[name]
        require(PAYLOAD_RVA <= target < max_end,'Hook target is outside payload sections')
        require(len(previous)==5 and previous[0]==0xe8,f'Expected direct CALL E8 at {site:#x}')
        actual = site+5+struct.unpack_from('<i',previous,1)[0]
        require(actual==expected,f'Hook original target mismatch at {site:#x}: {actual:#x}')
        displacement = target-(site+5)
        require(-(1<<31) <= displacement < (1<<31),'Target exceeds rel32 call range')
        replacement = b'\xe8'+struct.pack('<i',displacement)
        mapped = map_offset(offset)
        result[mapped:mapped+5] = replacement
        hook_report.append({'site_rva':hex(site),'original_target_rva':hex(actual),
            'new_target_rva':hex(target),'target_export':name,'original_bytes':previous.hex(),
            'patched_bytes':replacement.hex(),'file_offset':hex(mapped)})

    raw_offset = align(len(result),file_alignment)
    virtual_size = len(content)
    raw_size = align(virtual_size,file_alignment)
    result.extend(b'\0' * (raw_offset-len(result)))
    result.extend(content)
    result.extend(b'\0' * (raw_size-virtual_size))
    # One combined section hosts text, constants, exports, unwind data and a
    # writable payload section if the linker emitted one. Permission union.
    permissions = 0x60000060
    if any(s.Characteristics & 0x80000000 for s in sections):
        permissions |= 0x80000000
    struct.pack_into('<8sIIIIIIHHI',result,header_offset,b'.exact\0\0',virtual_size,
        PAYLOAD_RVA,raw_size,raw_offset,0,0,0,0,permissions)
    new_image_size = align(PAYLOAD_RVA+virtual_size,section_alignment)
    field(pe.OPTIONAL_HEADER,'SizeOfImage',new_image_size,'extend image for .exact')
    field(pe.OPTIONAL_HEADER,'SizeOfCode',pe.OPTIONAL_HEADER.SizeOfCode+raw_size,'account for added code section')
    field(pe.OPTIONAL_HEADER,'SizeOfInitializedData',pe.OPTIONAL_HEADER.SizeOfInitializedData+raw_size,'account for added initialized section')
    set_directory(EXCEPTION,PAYLOAD_RVA+exception_offset,len(exception_data))
    set_directory(SECURITY,0,0)
    if payload_relocs:
        set_directory(RELOC,relocation_rva,relocation_size)
    field(pe.OPTIONAL_HEADER,'CheckSum',0,'recompute image checksum')
    final_pe = pefile.PE(data=result, fast_load=True)
    checksum = final_pe.generate_checksum()
    field(pe.OPTIONAL_HEADER,'CheckSum',checksum,'image checksum')
    final_pe.close()

    # Prove every original section byte is preserved except explicitly listed
    # callsites and debug file-offset fields. This includes large .data tails.
    for s in pe.sections:
        if not s.SizeOfRawData:
            continue
        expected_section = bytearray(s.get_data())
        for hook in hook_report:
            site = number(hook['site_rva'])
            if s.VirtualAddress <= site < s.VirtualAddress+s.SizeOfRawData:
                off = site-s.VirtualAddress
                expected_section[off:off+5] = bytes.fromhex(hook['patched_bytes'])
        for d in debug_changes:
            off = d['original_file_offset']-s.PointerToRawData
            if 0 <= off < s.SizeOfRawData:
                struct.pack_into('<I',expected_section,off,d['new'])
        start = map_offset(s.PointerToRawData)
        require(result[start:start+s.SizeOfRawData] == expected_section,
                f'Unexpected mutation of original section {s.Name!r}')
    final_pe = pefile.PE(data=result, fast_load=True)
    require(final_pe.OPTIONAL_HEADER.AddressOfEntryPoint == pe.OPTIONAL_HEADER.AddressOfEntryPoint,'Original entry point changed')
    require(final_pe.OPTIONAL_HEADER.DllCharacteristics == pe.OPTIONAL_HEADER.DllCharacteristics,'Original ASLR/NX/etc flags changed')
    require(final_pe.verify_checksum(),'Output checksum invalid')
    require(exceptions(final_pe)==combined_functions,'Exception table verification failed')
    require(set(relocations(final_pe))==set(original_relocs+payload_relocs),'ASLR relocation verification failed')
    require(final_pe.sections[-1].Name.rstrip(b'\0')==b'.exact','New section absent')
    for original_section,new_section in zip(pe.sections,final_pe.sections):
        require(original_section.VirtualAddress==new_section.VirtualAddress,'Original section RVA changed')
    require(digest(input_path.read_bytes()) == EXPECTED_SHA256,'Input changed during build')
    target = output/'Telegram.exact.exe'
    require(target.resolve()!=input_path,'Refuse to overwrite original EXE')
    target.write_bytes(result)
    native_image_validation = {'available':False,'reason':'Windows only'}
    if os.name == 'nt':
        from check_image_load import check
        native_image_validation = check(target)
        require(native_image_validation.get('sec_image_created'),
            f'Windows rejected output SEC_IMAGE: {native_image_validation}')
    report = {
        'telegram_version':TELEGRAM_VERSION,
        'input':str(input_path),'input_sha256':EXPECTED_SHA256,'output':str(target),
        'output_sha256':digest(result),'payload':str(payload_path),'payload_sha256':digest(payload_raw),
        'image_base':hex(IMAGE_BASE),'original_image_size':hex(ORIGINAL_IMAGE_SIZE),
        'image_size':hex(new_image_size),'original_entrypoint_rva':hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint),
        'new_section':{'name':'.exact','rva':hex(PAYLOAD_RVA),'virtual_size':virtual_size,
            'raw_size':raw_size,'raw_offset':hex(raw_offset),'characteristics':hex(permissions)},
        'headers':{'old_size':old_headers,'new_size':new_headers,'raw_file_shift':shift,
            'reason':'Original section table ends exactly at first raw section; expand by one file alignment unit.'},
        'exports':{k:hex(v) for k,v in sorted(exports.items())},'payload_sections':payload_sections,
        'exceptions':{'original_count':len(original_functions),'payload_count':len(payload_functions),
            'merged_count':len(combined_functions),'rva':hex(PAYLOAD_RVA+exception_offset),'size':len(exception_data)},
        'relocations':{'original_nonpadding_count':len(original_relocs),'payload_nonpadding_count':len(payload_relocs),
            'payload_entries':[{'rva':hex(r),'type':t} for r,t in payload_relocs],
            'original_directory_retained':not bool(payload_relocs),'rva':hex(relocation_rva),'size':relocation_size},
        'hooks':hook_report,'header_and_debug_changes':changes,'debug_raw_pointer_updates':debug_changes,
        'checksum':hex(checksum),'security_directory_cleared':True,
        'authenticode':'The derived executable is unsigned; original certificate bytes are inert with a cleared SECURITY directory.',
        'original_file_unchanged':True,'original_section_rvas_unchanged':True,
        'original_section_content_verified_except_hook_and_debug_pointer_changes':True,
        'imports_added':False,'entrypoint_changed':False,'deployed':False,
        'native_image_validation':native_image_validation,
        'compiler_commands':compiler_logs,'source_sha256':source_hashes,
        'validation':'PE structure, exact input/callsite hashes, section preservation, checksum, unwind table, ASLR relocation equality, and Windows SEC_IMAGE acceptance without code execution. App runtime behavior is not validated by this builder.'}
    (output/'build-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True,
                        help=f'Original unmodified Telegram Desktop {TELEGRAM_VERSION} x64 EXE (read-only)')
    parser.add_argument('--output-dir',type=Path,default=DEFAULT_OUTPUT,
                        help='Separate output directory (default: repository/build)')
    parser.add_argument('--gcc',
                        help='MinGW-w64 x64 GCC executable; otherwise GCC environment variable or PATH')
    args=parser.parse_args()
    report=build_patch(args.input,args.output_dir,find_gcc(args.gcc))
    print(json.dumps({k:report[k] for k in ('output','output_sha256','image_size','exports','exceptions','relocations')},indent=2))

if __name__=='__main__':
    main()
