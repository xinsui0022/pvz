"""Apply or restore the version-locked patch using only Python's standard library."""
import argparse
import base64
import hashlib
import json
import os
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PREVIOUS_VERSIONS={
    '2efffb2bad8b29eae2b8dcc1090a2d6239b80b1d93a21b83cd79ab0b4a4a9fd9':'v3.0.1',
    'f2086cb46837c33837287af16fb66d1194849ea39f724a86d8141da46c5f5f68':'v3.0.0',
    'c9ce14bf96c71fe0922c38943c512ffb76e38fbf51ed8a53443d50a732e71513':'v3-failed',
    '0a11af528160c6f79ad75bb27aceed006ff74f5c3e2e0303af945a36ecafe4e5':'v2.0.0',
    '59448d170de8dc92da5300ca6934add241a96b972a404775ab8a314796bf8447':'v6',
    'b4c9028cd6cef84f56e3f6f492e17a6f711aa843f67abb83c7dd6461eb5e97a7':'v1',
    'fbba03d861134204ba82cbf37a8ff8faa689fea41cdce8408b6453cba2469c70':'v2',
    '72cc5c3b9a808a0452c6e87fa853b9d51932b9b9ae84177491ef42f9dffd41ef':'v3',
    '33e35a24d2286a2282eb26b7b32f6f3923bb7134066af5f78d33fc2f54750993':'v4',
    'adab8b74e105e1593df72434574f455a609195406cae00d48d972f542d88eb16':'v5-broken',
}
PARTNER_HASHES={
    'partner.xml':'4e7ff623b419e36feb578eaccb5e80b838290b01c2d2ae282a0648cecbd80290',
    'partner.xml.sig':'ca5b57ce55e4c7dac8086656e7b63c41d56e1cc98a6208391f6fbfa800887537'}

def bundled_partner(directory):
    """Read the matching XML/signature pair already shipped in main.pak."""
    data=bytes(c^0xf7 for c in (directory/'main.pak').read_bytes())
    if struct.unpack_from('<II',data)!=(0xbac04ac0,0):
        raise ValueError('Unrecognized main.pak')
    cursor=8;offset=0;entries={}
    while not data[cursor]&128:
        width=data[cursor+1]
        name=data[cursor+2:cursor+2+width].decode('ascii').lower()
        size=struct.unpack_from('<I',data,cursor+2+width)[0]
        entries[name]=(offset,size)
        offset+=size;cursor+=2+width+12
    result={}
    for name in PARTNER_HASHES:
        start,size=entries['properties\\'+name]
        value=data[cursor+1+start:cursor+1+start+size]
        if len(value)!=size: raise ValueError('Truncated PAK')
        result[name]=value
    if digest(result['partner.xml'])!='afa83947cffe8cefa9fec0850148bf15a7c4ee3fcfb6972bdf29bd65085099d4':
        raise ValueError('Unsupported bundled partner XML')
    if result['partner.xml.sig']!=b'CAB766D7490697636D0D9C3E':
        raise ValueError('Unsupported bundled partner signature')
    return result

def digest(data):
    return hashlib.sha256(data).hexdigest()

def transform(data, package, restore=False):
    source='patched' if restore else 'original'
    dest='original' if restore else 'patched'
    if digest(data)!=package[source+'_sha256']:
        raise ValueError('Executable SHA-256 does not match the supported '+source+' version.')
    out=bytearray(data)
    for change in package['changes']:
        value=base64.b64decode(change['before' if restore else 'after'])
        offset=change['offset']
        if offset+len(value)>len(out): out.extend(b'\0'*(offset+len(value)-len(out)))
        out[offset:offset+len(value)]=value
    out=bytes(out[:package[dest+'_size']])
    if digest(out)!=package[dest+'_sha256']:
        raise ValueError('Patch integrity check failed; executable was not changed.')
    return out

def partner_files(directory, restore=False, check=False):
    """Restore the bundled retail XML/signature pair; retain Steam backups.

    XML reads can use PAK data while signature reads use filesystem data.
    Removing the loose XML alone is therefore insufficient. No signature
    check code, DRM, PAK archive or Steam settings are changed.
    """
    bundled=bundled_partner(directory)
    actions=[]
    for name,expected in PARTNER_HASHES.items():
        active=directory/'properties'/name
        saved=directory/'backups/steam-partner'/name
        if saved.exists() and digest(saved.read_bytes())!=expected:
            raise ValueError('Unexpected partner backup: '+str(saved))
        raw=active.read_bytes() if active.exists() else None
        if raw is not None and digest(raw)!=expected and raw!=bundled[name]:
            raise ValueError('Unexpected active partner file: '+str(active))
        if restore:
            if saved.exists(): actions.append(('restore',active,saved,saved.read_bytes()))
        elif raw!=bundled[name]:
            actions.append(('install',active,saved,bundled[name]))
    if not check:
        for action,active,saved,value in actions:
            if action=='install' and active.exists() and not saved.exists():
                saved.parent.mkdir(parents=True,exist_ok=True)
                saved.write_bytes(active.read_bytes())
            active.parent.mkdir(parents=True,exist_ok=True)
            active.write_bytes(value)
    return len(actions)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,default=ROOT/'PlantsVsZombies.exe')
    parser.add_argument('--restore',action='store_true')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    package=json.loads((ROOT/'patches/izombie-fixes.json').read_text())
    data=args.game.read_bytes()
    partner_files(args.game.parent,args.restore,check=True)
    wanted=package[('original' if args.restore else 'patched')+'_sha256']
    if digest(data)==wanted:
        partner_files(args.game.parent,args.restore,check=args.check)
        print('Already in requested state:',digest(data)); return
    previous=PREVIOUS_VERSIONS.get(digest(data))
    upgrading=not args.restore and previous is not None
    source=(args.game.parent/'backups/PlantsVsZombies.original.exe').read_bytes() if upgrading else data
    result=transform(source,package,args.restore)
    if args.check:
        print('Compatible; output SHA-256:',digest(result)); return
    backup=args.game.parent/'backups'/(f'PlantsVsZombies.{previous}.exe' if upgrading else 'PlantsVsZombies.before-restore.exe' if args.restore else 'PlantsVsZombies.original.exe')
    backup.parent.mkdir(exist_ok=True)
    if backup.exists() and backup.read_bytes()!=data:
        raise ValueError('Existing backup differs. Refusing to overwrite it.')
    if not backup.exists(): backup.write_bytes(data)
    # Atomic replacement fails safely if Windows has the executable open.
    tmp=args.game.with_name(args.game.name+'.patching')
    created=False
    try:
        with tmp.open('xb') as f:
            created=True
            f.write(result); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,args.game)
    finally:
        if created and tmp.exists(): tmp.unlink()
    partner_files(args.game.parent,args.restore)
    print('Restored' if args.restore else 'Installed',digest(result))
    print('Backup:',backup)

if __name__=='__main__': main()
