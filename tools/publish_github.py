"""Publish source to a new GitHub branch using the user's local Git credentials.
Never touches main. Does not copy config, statistics, templates, caches or build outputs.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
REPO='https://github.com/9akarena8-bit/easy-rewards.git'
VERSION = (BASE / 'VERSION').read_text(encoding='utf-8').strip()
BRANCH = f'feature/easyrewards-v{VERSION}'
SKIP_DIRS={'.git','.venv','.buildenv','.pytest_cache','__pycache__','dist','build','release',
           'legacy','_backup','.idea','.vscode'}
SKIP_FILES={'config.json','tracker.json','treasure.json','rewards.json','crash.log',
            'installed_files.json','EasyRewards.spec','pytest_cache'}


def run(*args, cwd=None):
    print('>', ' '.join(args), flush=True)
    subprocess.run(list(args),cwd=cwd,check=True)


def publish():
    with tempfile.TemporaryDirectory(prefix='easyrewards_publish_') as temp:
        checkout=Path(temp)/'repo'
        run('git','clone','--branch','main',REPO,str(checkout))
        run('git','checkout','-b',BRANCH,cwd=checkout)
        # Existing repository layout contains extra copies of old sources. Preserve history.
        # Replace only corresponding source paths; don't delete unrelated files from main.
        copied=0
        for source in BASE.rglob('*'):
            if not source.is_file(): continue
            rel=source.relative_to(BASE)
            if any(piece in SKIP_DIRS for piece in rel.parts): continue
            if source.name in SKIP_FILES or source.suffix in {'.pyc','.bak'}: continue
            if rel.parts[0]=='templates' and source.suffix.lower()=='.png': continue
            target=checkout/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
            copied+=1
        print(f'Copied {copied} source files')
        run('git','add','-A',cwd=checkout)
        status=subprocess.run(['git','status','--porcelain'],cwd=checkout,capture_output=True,text=True,check=True)
        if not status.stdout.strip():
            print('No changes; all code is already in GitHub.');return
        run('git','commit','-m',f'Prepare Easy Rewards {VERSION}: randomized movement and replay templates',cwd=checkout)
        run('git','push','-u','origin',BRANCH,cwd=checkout)
        print('\nUpload successful! Open a pull request:')
        print(f'https://github.com/9akarena8-bit/easy-rewards/compare/main...{BRANCH}?expand=1')
        print(f'Merge after reviewing. Then publish tag v{VERSION} to build the installer release.')

if __name__=='__main__':
    try:publish()
    except subprocess.CalledProcessError as e:
        print('Git operation failed:',e)
        print('Check Git for Windows and sign in to GitHub in your browser.')
        raise SystemExit(1)
