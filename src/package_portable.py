"""Assemble a clean full client from verified upstream files and an explicit allowlist.

Never reads an installed Telegram directory, tdata, local rules or user settings.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parent.parent

def sha(data): return hashlib.sha256(data).hexdigest()

def package(official,patched,full_source,output):
    compatibility=json.loads((ROOT/'compatibility.json').read_text('utf-8'))
    data=Path(patched).read_bytes()
    if sha(data)!=compatibility['verified_output_sha256']:raise ValueError('Patched executable hash mismatch')
    version=compatibility['telegram_version']
    with zipfile.ZipFile(official) as z:
        expected={'Telegram/Telegram.exe','Telegram/modules/x64/d3d/d3dcompiler_47.dll'}
        actual=[i.filename for i in z.infolist() if not i.is_dir()]
        if len(actual)!=len(expected) or set(actual)!=expected:raise ValueError('Unexpected official portable contents')
        if sha(z.read('Telegram/Telegram.exe'))!=compatibility['input_sha256']:raise ValueError('Official executable hash mismatch')
        files={'Telegram/Telegram.exe':data,
               'Telegram/modules/x64/d3d/d3dcompiler_47.dll':z.read('Telegram/modules/x64/d3d/d3dcompiler_47.dll')}
    for name in ('README.md','NOTICE.md','LICENSE','tools/Manage-Blacklist.ps1',
                 'tools/Manage-Keywords.ps1','Manage-Keywords.cmd',
                 'docs/search-guide.md','docs/verification.md','docs/verification.json',
                 'docs/update-persistence.md','docs/abi-7.2.8.json',
                 'licenses/Telegram-LICENSE.txt','licenses/Telegram-LEGAL.txt'):
        files[name]=(ROOT/name).read_bytes()
    # Copy only legal text from the official complete source archive, not any
    # local source directory, and never extract archive-controlled paths.
    prefix=f'tdesktop-{version}-full/'
    with tarfile.open(full_source) as t:
        for member in t:
            path=PurePosixPath(member.name)
            if not member.isfile() or not member.name.startswith(prefix):continue
            if not path.name.upper().startswith(('LICENSE','COPYING','NOTICE','COPYRIGHT','LEGAL')):continue
            relative=member.name[len(prefix):]
            if '..' in path.parts or path.is_absolute() or member.size>2*1024*1024:raise ValueError('Invalid legal text entry')
            files['licenses/upstream/'+relative]=t.extractfile(member).read()
    manifest={'product':'telegram 重庆好人版 '+version+' + 精确搜索','patch_version':compatibility['patch_version'],
              'platform':'windows-x64','upstream_executable_sha256':compatibility['input_sha256'],
              'patched_executable_sha256':compatibility['verified_output_sha256'],
              'upstream_portable_sha256':sha(Path(official).read_bytes()),
              'upstream_full_source_sha256':sha(Path(full_source).read_bytes()),
              'account_data_included':False,'personal_rules_included':False,
              'rule_directory':'KnownFolder Documents/Telegram/blacklists',
              'fresh_profile_auto_update_default':False,
              'files':[{'path':name,'size':len(raw),'sha256':sha(raw)} for name,raw in sorted(files.items())]}
    files['manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(files.items()):
            p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or any(x.lower() in ('tdata','cache','logs') for x in p.parts):raise ValueError('Disallowed artifact path')
            info=zipfile.ZipInfo(name,(2026,9,17,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,raw,compresslevel=9)
    with zipfile.ZipFile(output) as z:
        if set(z.namelist())!=set(files) or z.testzip():raise ValueError('ZIP verification failed')
        for name,raw in files.items():
            if sha(z.read(name))!=sha(raw):raise ValueError('Packed file mismatch')
    return {'file':output.name,'size':output.stat().st_size,'sha256':sha(output.read_bytes()),
            'entries':len(files),'all_entries_verified':True,'manifest':manifest}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('official','patched','full-source','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(package(a.official,a.patched,a.full_source,a.output),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
