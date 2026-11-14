import pytest
import json
import shutil
from pathlib import Path

from gitd.skills.engine import cli
from gitd.skills.engine.analyze import analyze_skill


def test_analyze_rules(tmp_path, capsys):
    shutil.copytree(Path(__file__).resolve().parents[1] / 'skillhub/ghost/tiktok', tmp_path / 'skill')
    skill = tmp_path / 'skill'
    (skill / 'suspicious.py').write_text('''import os as operating
from subprocess import run as execute
import requests
import ctypes
import socket
import urllib.request
import httpx
operating.system('true')
execute('true', shell=True)
eval('1')
exec('pass')
__import__('os')
compile('pass', '', 'exec')
open('/etc/outside', 'w')
open('/tmp/allowed', 'w')
open('allowed', 'w')
getattr(getattr(obj, 'a'), 'b')
''' + 'blob = ' + repr('a' * 201) + '\n')
    findings = analyze_skill(skill)
    rules = {f.rule for f in findings if f.file == 'suspicious.py'}
    assert {'code-execution', 'shell-execution', 'restricted-import', 'external-write', 'getattr-chain', 'encoded-blob'} <= rules
    assert len([f for f in findings if f.rule == 'external-write']) == 1
    assert cli.main(['analyze', str(skill), '--json']) == 2
    assert any(f['severity'] == 'high' for f in json.loads(capsys.readouterr().out))
    assert cli.main(['submit', str(skill), '--dry-run']) == 2
    assert cli.main(['lint', str(skill)]) == 1


def test_analyze_fixture_and_parse_failure(tmp_path, capsys):
    shutil.copytree(Path(__file__).resolve().parents[1] / 'skillhub/ghost/tiktok', tmp_path / 'skill')
    skill = tmp_path / 'skill'
    assert cli.main(['analyze', str(skill)]) == 0
    assert 'SEVERITY' in capsys.readouterr().out
    (skill / 'broken.py').write_text('def broken(')
    assert any(f.rule == 'parse-error' for f in analyze_skill(skill))


@pytest.mark.parametrize('snippet, rule, severity', [
    ('import subprocess\nsubprocess.run(["id"])', 'process-execution', 'medium'),
    ('import subprocess as sp\nsp.Popen(["id"])', 'process-execution', 'medium'),
    ('from subprocess import check_output\ncheck_output(["id"])', 'process-execution', 'medium'),
    ('import os\nos.execvp("id", ["id"])', 'process-execution', 'medium'),
    ('import os\nos.spawnlp(os.P_WAIT, "id", "id")', 'process-execution', 'medium'),
    ('import os\nos.popen("id")', 'shell-execution', 'high'),
    ('import subprocess\nsubprocess.getoutput("id")', 'shell-execution', 'high'),
    ('import importlib\nimportlib.import_module("os")', 'dynamic-import', 'medium'),
    ('import importlib.util\nimportlib.util.spec_from_file_location("m", "/x.py")', 'dynamic-import', 'medium'),
    ('import runpy\nrunpy.run_path("/x.py")', 'dynamic-import', 'medium'),
    ('from pathlib import Path\nPath("/etc/evil").write_text("x")', 'external-write', 'high'),
    ('from pathlib import Path\nPath("/tmp/ok").write_bytes(b"x")', None, None),
    ('from pathlib import Path\nPath("inside.txt").write_text("x")', None, None),
    ('from pathlib import Path\nPath(p).write_text("x")', 'dynamic-write', 'medium'),
    ('target.write_bytes(b"x")', 'dynamic-write', 'medium'),
    ('import shutil\nshutil.copy("a", "/etc/b")', 'external-write', 'high'),
    ('import shutil\nshutil.copy("a", dst)', 'dynamic-write', 'medium'),
    ('import shutil\nshutil.copy("/etc/passwd", "copy.txt")', None, None),
    ('s = "a-b".replace("-", "_")', None, None),
    ('from pathlib import Path\nPath("/etc/x").replace("/etc/y")', 'external-write', 'high'),
    ('import shutil\nshutil.rmtree("/etc/b")', 'external-write', 'high'),
    ('import os\nos.remove("/etc/passwd")', 'external-write', 'high'),
    ('import os\nos.remove(path)', 'dynamic-write', 'medium'),
    ('import os\ngetattr(os, "sys" + "tem")("id")', 'dynamic-attribute', 'medium'),
    ('import os\nsetattr(obj, name, 1)', 'dynamic-attribute', 'medium'),
    ('device.adb("shell", "rm", "-rf", "/sdcard")', 'device-shell', 'low'),
    ('device.shell("id")', 'device-shell', 'low'),
    ('print("hello")', None, None),
])
def test_analyzer_bypass_corpus(tmp_path, snippet, rule, severity):
    """Each known analyzer bypass from the 2026-10-20 review is now a finding; benign code stays clean."""
    skill = tmp_path / 'skill'
    skill.mkdir()
    (skill / 'skill.yaml').write_text('name: x\n')
    (skill / 'helpers.py').write_text(snippet + '\n')
    findings = analyze_skill(skill)
    if rule is None:
        assert findings == [], findings
    else:
        assert (rule, severity) in {(f.rule, f.severity) for f in findings}, findings


def test_official_skills_have_no_high_findings():
    hub = Path(__file__).resolve().parents[1] / 'skillhub'
    highs = [(d.parent.name, f.rule, f.file) for d in hub.glob('*/*/skill.yaml') for f in analyze_skill(d.parent) if f.severity == 'high']
    assert highs == []
