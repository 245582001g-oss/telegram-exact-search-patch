"""Exercise the actual Windows PowerShell rule manager on synthetic scratch files."""
from pathlib import Path
import os
import struct
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
shell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
def run(path,kind,action,ok=True):
    result=subprocess.run([str(shell),'-NoProfile','-ExecutionPolicy','Bypass','-File',
        str(root/'tools/Manage-Blacklist.ps1'),'-Kind',kind,'-Action',action,'-Path',str(path)],capture_output=True)
    assert (result.returncode==0)==ok,result.stderr

with tempfile.TemporaryDirectory(prefix='rule-manager-',dir=root/'work') as temporary:
    folder=Path(temporary)
    for kind,name,magic in [('Content','blacklist',b'TGEXBL1\0'),('Channel','channels',b'TGEXCH1\0')]:
        p=folder/f'exact-search-{name}.v1.bin'
        for action in ('Status','Undo','Clear'):run(p,kind,action)
        assert not list(folder.iterdir())
        records=[struct.pack('<IQ24x',8,(2<<48)+i) for i in (1,2)]
        data=magic+struct.pack('<II',1,2)+b''.join(records)
        p.write_bytes(data);run(p,kind,'Status');assert p.read_bytes()==data
        run(p,kind,'Undo');assert p.read_bytes()==magic+struct.pack('<II',1,1)+records[0]
        run(p,kind,'Clear');assert p.read_bytes()==magic+struct.pack('<II',1,0)
        for bad in (b'bad',magic+struct.pack('<II',1,50001)):
            p.write_bytes(bad);run(p,kind,'Undo',False);assert p.read_bytes()==bad
        if kind=='Channel':
            for bad_record in (struct.pack('<IQ24x',8,42),records[0][:-1]+b'\1'):
                bad=magic+struct.pack('<II',1,1)+bad_record
                p.write_bytes(bad);run(p,kind,'Clear',False);assert p.read_bytes()==bad
        p.unlink();p.with_name(p.name+'.lock').unlink()
print('PASS: real PowerShell content/channel Status, Undo, Clear; missing files, malformed IDs/reserved bytes and size validation; no real user rules touched')
