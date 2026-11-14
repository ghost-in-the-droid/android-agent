import json
import shlex
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from gitd.skills.engine import cli, demo, load_skill, run_action

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def skill(tmp_path):
    import shutil
    target = tmp_path/'tiktok'
    shutil.copytree(ROOT/'skillhub/ghost/tiktok', target)
    return load_skill(target)


def arguments(skill, **changes):
    action = skill.actions[0]
    values = dict(ref=str(skill.skill_dir), action=action.name, param=[], device='emulator-5554',
                  out=None, prompt=None, record_size=None, layout='split', agent='claude',
                  dry=True, no_ocr=False, i_know=False, render_host='render-host',
                  render_root='~/ghost-in-the-droid', render_python='python3')
    return SimpleNamespace(**(values | changes))


def test_template_plan_default_claude_and_exact_dry_commands(skill, monkeypatch, capsys):
    monkeypatch.setenv('ADB_SERVER_SOCKET','tcp:127.0.0.1:5038')
    plan = demo.build_plan(skill, arguments(skill), {})
    assert plan['out'] == str(skill.skill_dir/'demos'/f'{skill.actions[0].name}.webm')
    assert plan['spec']['demo'] == f'skill-{skill.name}-{skill.actions[0].name}'
    assert plan['spec']['record_size'] is None
    assert plan['spec']['_phone_only'] is False
    mcp = plan['mcp_config']['mcpServers']['android-agent']
    assert mcp['env']['ANDROID_SERIAL'] == 'emulator-5554'
    assert mcp['env']['ADB_SERVER_SOCKET'] == 'tcp:render-host:5037'
    assert '--record' in plan['engine_command']
    command = demo.capture_command(plan,'/tmp/demo')
    assert 'claude_tui_driver.py' in command[1]
    assert command[command.index('--prompt')+1] == plan['agent_prompt']
    assert command[command.index('--mcp-config')+1] == '/tmp/demo/mcp.json'
    # Dry planning cannot execute a process, including ffmpeg/agg/adb.
    monkeypatch.setattr('subprocess.run', lambda *a, **k: pytest.fail('dry executed a process'))
    demo.print_plan(plan)
    printed = json.loads(capsys.readouterr().out)
    commands = printed['commands']
    assert commands['compose_remote'][0] == 'ssh'
    assert 'record_skill_demo.py' in commands['compose_remote'][-1]
    assert '--external-cast' in commands['compose_remote'][-1]
    assert 'claude_tui_driver.py' in commands['local_cast'][1]



@pytest.mark.parametrize('agent',['cli','engine'])
def test_secondary_agent_modes(skill, agent):
    plan = demo.build_plan(skill, arguments(skill,agent=agent), {})
    command = demo.capture_command(plan,'/tmp/demo')
    assert command[:2] == ['asciinema','rec']
    inner = shlex.split(command[command.index('-c')+1])
    if agent == 'cli':
        assert inner == ['ghost',plan['agent_prompt']]
    else:
        assert '--live-trace' in inner and '--record' in inner


def test_prompt_interpolation_params_and_override(skill):
    from gitd.skills.engine.loader import Param
    action = skill.actions[0]
    action.params = [Param(name='query', required=True)]
    action.ref_prompt = 'Search {query}'
    plan = demo.build_plan(skill, arguments(skill), {'query': "a'; echo unsafe"})
    assert "Search a'; echo unsafe" in plan['prompt']
    override = demo.build_plan(skill, arguments(skill,prompt='Find {query}'), {'query':'cats'})
    assert override['prompt'].startswith('Find cats')
    with pytest.raises(Exception):
        demo.build_plan(skill, arguments(skill), {'unknown':'cats'})


@pytest.mark.parametrize('changes',[{'out':'demo.mp4'},{'device':'ios:123'},{'device':'fake:test'},{'record_size':'bad'}])
def test_bad_arguments_rejected(skill, changes):
    with pytest.raises(ValueError):
        demo.build_plan(skill, arguments(skill,**changes), {})


def test_limits_and_tool_hints(skill, tmp_path, monkeypatch, capsys):
    plan = demo.build_plan(skill,arguments(skill),{})
    monkeypatch.setattr('shutil.which',lambda tool: None)
    hints = dict(demo.tool_check(plan))
    assert {'adb','asciinema','ssh','scp','claude'} == set(hints)
    assert all('Linux' in text and 'Windows' in text for text in hints.values())
    plan['ocr'] = False
    assert 'tesseract' not in dict(demo.tool_check(plan))
    output = tmp_path/'demo.webm'
    output.write_bytes(b'x'*1_500_001)
    demo.check_size(output)
    assert '1.5 MB' in capsys.readouterr().out
    output.write_bytes(b'x'*3_000_001)
    with pytest.raises(ValueError,match='3 MB'):
        demo.check_size(output)
    command = demo.transcode_command('in.webm','out.webm')
    assert command[command.index('-t')+1] == '30'
    assert command[command.index('-c:v')+1] == 'libvpx-vp9'
    assert '-an' in command and '720' in command[command.index('-vf')+1]


def test_physical_account_guard_fail_closed():
    dev = Mock()
    dev.adb.return_value = '0'
    dev.adb_soft.return_value = SimpleNamespace(returncode=0,stdout='Accounts: 1')
    with pytest.raises(RuntimeError,match='--i-know'):
        demo.require_clean_device(dev,False)
    demo.require_clean_device(dev,True)
    dev.adb_soft.return_value.stdout = 'Accounts: 0'
    demo.require_clean_device(dev,False)
    dev.adb_soft.return_value.stdout = ''
    with pytest.raises(RuntimeError):
        demo.require_clean_device(dev,False)
    dev.adb.return_value = '1'
    demo.require_clean_device(dev,False)


def test_live_trace_callback_arrives_before_next_step(skill, monkeypatch):
    import gitd.skills.engine.runner as runner
    action = skill.actions[0]
    action.params = []
    action.pre_hooks = []
    action.steps = [{'action':'sleep','duration_s':0}, {'action':'sleep','duration_s':0}]
    action.end_state_validator = {}
    events = []
    # The real skill requires a visible signed-in profile before trace dispatch.
    device = SimpleNamespace(dump_xml=lambda: '<hierarchy><node content-desc="Profile menu"/></hierarchy>')
    monkeypatch.setattr(runner,'_get_device',lambda serial: device)
    monkeypatch.setattr(runner,'dispatch',lambda step,*args: events.append('dispatch'))
    result = run_action(skill,action.name,device_serial='fake',progress_callback=lambda entry: events.append(entry.step_index))
    assert result.success
    assert events == ['dispatch',0,'dispatch',1]
    assert len(result.trace) == 2


def test_demo_cli_dry_and_invalid_params(skill,monkeypatch,capsys):
    monkeypatch.setattr(cli,'load_skill',lambda ref:skill)
    monkeypatch.setattr('shutil.which',lambda tool:None)
    monkeypatch.setattr('subprocess.run',lambda *a,**k:pytest.fail('process called'))
    assert cli.main(['demo','ref',skill.actions[0].name,'--device','emulator-5554','--dry']) == 0
    assert 'claude_tui_driver.py' in capsys.readouterr().out
    assert cli.main(['demo','ref',skill.actions[0].name,'--device','serial','--param','invalid','--dry']) == 1


@pytest.mark.parametrize('violations',[False,True])
def test_split_record_only_encodes_remotely_and_publishes_after_gate(skill,tmp_path,monkeypatch,violations):
    import subprocess
    recorder=demo.load_recorder()
    output=tmp_path/'result.webm'
    plan=demo.build_plan(skill,arguments(skill,out=str(output)),{})
    monkeypatch.setattr(recorder,'scan_text',lambda *args:[])
    calls=[]
    def run(command,**kwargs):
        calls.append(command)
        stdout=''
        if command[0] == 'ssh':
            remote=command[-1]
            if '--check-tools' in remote:
                stdout=json.dumps({'missing':[]})
            elif '--phone-start' in remote:
                stdout=json.dumps({'started_at':100})
            elif '--compose-plan' in remote and violations:
                raise subprocess.CalledProcessError(1,command,stderr='OCR privacy gate failed')
        elif command[0] == 'scp':
            if command[-2].startswith('render-host:'):
                destination=Path(command[-1])
                if command[-2].endswith('demo.webm'):
                    destination.write_bytes(b'webm')
                else:
                    destination.write_text(json.dumps(dict(codec='vp9',width=720,height=406,audio=False,duration_s=24,size_bytes=4)))
        else:
            assert 'claude_tui_driver.py' in command[1]
            cast=Path(command[command.index('--cast')+1])
            cast.write_text('{}\n')
            artifacts=Path(plan['artifact_dir'])
            artifacts.mkdir(exist_ok=True)
            (artifacts/'test.json').write_text(json.dumps({'signature':{'value':'mock'},'actions':[{'name':plan['action']}]}))
        return SimpleNamespace(returncode=0,stdout=stdout)
    monkeypatch.setattr('subprocess.run',run)
    if violations:
        with pytest.raises(RuntimeError,match='no clip published'):
            demo.record(plan,recorder)
        assert not output.exists()
    else:
        assert demo.record(plan,recorder) == 0
        assert output.read_bytes() == b'webm'
        import yaml
        saved=yaml.safe_load(Path(plan['spec_out']).read_text())
        assert saved['skill_demo']['render_host'] == 'render-host'
        assert Path(plan['legacy_out']).read_bytes() == b'webm'
    assert any('--cleanup' in command[-1] for command in calls if command[0]=='ssh')
    assert all(command[0] not in ('agg','ffmpeg','ffprobe') for command in calls)
    start=next(i for i,cmd in enumerate(calls) if cmd[0]=='ssh' and '--phone-start' in cmd[-1])
    local=next(i for i,cmd in enumerate(calls) if cmd[0] not in ('ssh','scp'))
    stop=next(i for i,cmd in enumerate(calls) if cmd[0]=='ssh' and '--phone-stop' in cmd[-1])
    assert start < local < stop


def test_live_cli_printer_and_failure_callback(skill,monkeypatch,capsys):
    import gitd.skills.engine.runner as runner
    action = skill.actions[0]
    action.params=[]
    action.pre_hooks=[]
    action.steps=[{'action':'sleep','duration_s':0}]
    action.end_state_validator={}
    monkeypatch.setattr(cli,'load_skill',lambda ref:skill)
    device = SimpleNamespace(dump_xml=lambda: '<hierarchy><node content-desc="Profile menu"/></hierarchy>')
    monkeypatch.setattr(runner,'_get_device',lambda serial:device)
    monkeypatch.setattr(runner,'dispatch',lambda *args:None)
    assert cli.cmd_run(['ref',action.name,'--device','mock','--live-trace']) == 0
    text=capsys.readouterr().out
    assert 'Prompt:' in text and '0: sleep' in text and 'ms ✓' in text
    assert 'End-state validator: passed' in text
    assert run_action(skill,action.name,device_serial='mock',progress_callback=lambda entry:1/0).success


def test_missing_tools_prevent_real_recording(skill,monkeypatch):
    monkeypatch.setattr(cli,'load_skill',lambda ref:skill)
    monkeypatch.setattr('shutil.which',lambda tool:None)
    monkeypatch.setattr(demo,'record',lambda *args:pytest.fail('recording started'))
    assert cli.main(['demo','ref',skill.actions[0].name,'--device','emulator-5554']) == 1


@pytest.mark.parametrize('options',[[],['--device','serial','--agent','bad'],['--device','serial','--layout','bad']])
def test_parser_rejects_missing_device_and_unknown_choices(options):
    with pytest.raises(SystemExit) as exc:
        demo.parser().parse_args(['ref','action']+options)
    assert exc.value.code == 2


def test_phone_layout_uses_existing_frame_without_terminal(skill):
    plan=demo.build_plan(skill,arguments(skill,layout='phone'),{})
    command=demo.render_commands(plan)[-1]
    filters=command[command.index('-filter_complex')+1]
    assert plan['spec']['layout'] == 'phone_only'
    assert '[term]' not in filters and not any(str(v).endswith('terminal.mp4') for v in command)
    assert 'overlay=0:0:format=auto' in filters


def test_all_actions_have_individual_plans_and_fresh_state(skill):
    skill.actions = skill.actions[:2]
    for action in skill.actions:
        action.params=[]
    args = demo.parser().parse_args(['ref','--device','emulator-5554','--dry'])
    plans=demo.build_plans(skill,args,{})
    assert [plan['action'] for plan in plans] == skill.action_names()
    for action,plan in zip(skill.actions,plans):
        assert plan['out'] == str(skill.skill_dir/'demos'/f'{action.name}.webm')
        assert plan['spec_out'] == str(skill.skill_dir/'demos'/f'{action.name}.spec.yaml')
        setup=plan['spec']['setup']
        assert setup[-2]['args']['cmd'].startswith('am force-stop ')
        assert setup[-1]['step'] == 'launch_app'
        assert plan['spec']['timeline'][0]['caption'] == plan['prompt']
        assert plan['spec']['timeline'][1]['caption'].startswith('Step 1:')
        assert plan['spec']['outro']['cta_line'] == f'ghost skill install {skill.author}/{skill.name}'
    assert plans[0]['legacy_out'] == str(skill.skill_dir/'demo.webm')
    assert plans[1]['legacy_out'] is None


def test_action_flag_and_parameter_routing(skill):
    from gitd.skills.engine.loader import Param
    skill.actions=skill.actions[:2]
    skill.actions[0].params=[Param(name='first',default='one')]
    skill.actions[1].params=[Param(name='second',default='two')]
    args=demo.parser().parse_args(['ref','--device','serial','--dry'])
    plans=demo.build_plans(skill,args,{'second':'custom'})
    assert 'custom' not in plans[0]['prompt']
    assert 'custom' in plans[1]['prompt']
    args=demo.parser().parse_args(['ref','--device','serial','--action',skill.actions[1].name,'--dry'])
    assert [plan['action'] for plan in demo.build_plans(skill,args,{})] == [skill.actions[1].name]
    with pytest.raises(ValueError,match='Unknown'):
        demo.build_plans(skill,args,{'first':'wrong-action'})
    args=demo.parser().parse_args(['ref','--device','serial','--out','out.webm'])
    with pytest.raises(ValueError,match='--out'):
        demo.build_plans(skill,args,{})
    args=demo.parser().parse_args(['ref',skill.actions[0].name,'--device','serial','--action',skill.actions[1].name])
    with pytest.raises(ValueError,match='legacy'):
        demo.build_plans(skill,args,{})


def test_cli_records_every_action_sequentially(skill,monkeypatch):
    skill.actions=skill.actions[:2]
    for action in skill.actions:
        action.params=[]
    monkeypatch.setattr(cli,'load_skill',lambda ref:skill)
    monkeypatch.setattr(demo,'tool_check',lambda plan:[])
    monkeypatch.setattr(demo,'select_agent',lambda args:None)
    recorded=[]
    monkeypatch.setattr(demo,'record',lambda plan,recorder:recorded.append(plan['action']) or 0)
    assert cli.cmd_demo(['ref','--device','serial','--render-host','render-host']) == 0
    assert recorded == skill.action_names()


def test_folder_limit_is_soft_warning(tmp_path,capsys):
    output=tmp_path/'demos'
    output.mkdir()
    with (output/'one.webm').open('wb') as file:
        file.truncate(10_000_001)
    demo.warn_folder_size(output)
    assert '10 MB' in capsys.readouterr().out


@pytest.mark.parametrize('logged_in,expected',[(True,'claude'),(False,'engine')])
def test_claude_auth_fallback_is_deterministic(monkeypatch,logged_in,expected):
    args=SimpleNamespace(agent='claude',dry=False)
    monkeypatch.setattr('shutil.which',lambda tool:'/mock/'+tool)
    calls=[]
    def auth(command,**kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0,stdout=json.dumps({'loggedIn':logged_in}))
    monkeypatch.setattr('subprocess.run',auth)
    demo.select_agent(args)
    assert args.agent == expected
    assert calls == [['claude','auth','status']]


def test_dry_never_checks_auth_and_missing_claude_uses_engine(monkeypatch):
    monkeypatch.setattr('subprocess.run',lambda *args,**kwargs:pytest.fail('auth process invoked'))
    args=SimpleNamespace(agent='claude',dry=True)
    demo.select_agent(args)
    assert args.agent == 'claude'
    args.dry=False
    monkeypatch.setattr('shutil.which',lambda tool:None)
    demo.select_agent(args)
    assert args.agent == 'engine'


def test_columns_device_hidden_and_phone_compensation(skill):
    plan=demo.build_plan(skill,arguments(skill,agent='engine'),{})
    command=demo.capture_command(plan,'/tmp/demo')
    assert command[command.index('--cols')+1] == '60'
    assert '--device' not in plan['engine_command']
    assert plan['serial'] not in plan['engine_command']
    assert plan['spec']['env']['GHOST_DEVICE'] == plan['serial']
    composite=demo.render_commands(plan)[-1]
    graph=composite[composite.index('-filter_complex')+1]
    assert 'tpad=start_mode=clone:start_duration=3' in graph
    assert any(f"intro-{plan['spec']['demo']}.png" in value for value in composite)


def test_external_cast_helper_never_wraps_asciinema(tmp_path,monkeypatch):
    recorder=demo.load_recorder()
    cast=tmp_path/'terminal.cast'
    command=['python3','claude_tui_driver.py','--cast',str(cast)]
    calls=[]
    def capture(argv,**kwargs):
        calls.append(argv)
        cast.write_text('cast')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('subprocess.run',capture)
    assert recorder.capture_external_cast(command,cast) == cast
    assert calls == [command]
    cast.unlink()
    monkeypatch.setattr('subprocess.run',lambda *a,**kw:SimpleNamespace(returncode=0))
    with pytest.raises(RuntimeError,match='did not produce'):
        recorder.capture_external_cast(command,cast)


def test_seed_wrapper_generates_intro_without_rendering_in_test(skill,tmp_path,monkeypatch):
    import importlib.util
    recorder=demo.load_recorder()
    wrapper=demo.load_skill_recorder()
    original=tmp_path/'brand'
    original.mkdir()
    (original/'frame.png').write_text('fixture')
    recorder.BRAND_DIR=original
    plan=demo.build_plan(skill,arguments(skill),{})
    import sys
    sys.path.insert(0, str(ROOT / 'scripts/showcase'))
    import skill_cards
    def build(demo_id, spec):
        for name in (f'intro-{demo_id}.png', f'outro-{demo_id}.png', f'bg-{demo_id}.png'):
            (skill_cards.BRAND_DIR / name).write_text('mock card')
    monkeypatch.setattr(skill_cards, 'build', build)
    working=tmp_path/'work'
    working.mkdir()
    spec=wrapper.prepare_showcase(plan,recorder,working)
    assert spec['demo'] == plan['spec']['demo']
    assert spec['timeline'][0]['caption'] == f'{skill.author}/{skill.name}: {plan["action"]}'
    assert spec['title'] == "TikTok: Open my profile"
    assert (recorder.BRAND_DIR/f"intro-{spec['demo']}.png").read_text() == 'mock card'
    assert recorder.TERM_COLS == 60
    assert (recorder.SHOWCASE_DIR/'copy.yaml').exists()


def test_actions_subset_and_render_host_environment(skill,monkeypatch):
    monkeypatch.setenv('GHOST_DEMO_RENDER_HOST','render-host')
    skill.actions=skill.actions[:2]
    for action in skill.actions:
        action.params=[]
    names=','.join(reversed(skill.action_names()))
    args=demo.parser().parse_args(['ref','--actions',names,'--device','emulator-5554','--dry'])
    plans=demo.build_plans(skill,args,{})
    assert [plan['action'] for plan in plans] == list(reversed(skill.action_names()))
    assert all(plan['render_host']=='render-host' for plan in plans)
    assert all(plan['spec']['env']['ADB_SERVER_SOCKET']=='tcp:render-host:5037' for plan in plans)
    args.actions=skill.actions[0].name+','+skill.actions[0].name
    with pytest.raises(ValueError,match='unique'):
        demo.build_plans(skill,args,{})
    args.actions=skill.actions[0].name
    args.action=skill.actions[0].name
    with pytest.raises(ValueError,match='cannot be combined'):
        demo.build_plans(skill,args,{})


def test_split_refuses_local_encoding_without_host(skill,monkeypatch):
    plan=demo.build_plan(skill,arguments(skill,render_host=None),{})
    monkeypatch.setattr('subprocess.run',lambda *args,**kwargs:pytest.fail('process called'))
    with pytest.raises(ValueError,match='local encoding is disabled'):
        demo.record(plan,demo.load_recorder())


def test_remote_commands_quote_root_and_reject_host_injection(skill):
    from gitd.skills.engine.split_demo import remote_command
    plan=demo.build_plan(skill,arguments(skill,render_root="/tmp/repo with spaces;echo nope"),{})
    command=remote_command(plan,'--check-tools')
    assert command[0]=='ssh'
    assert command[command.index('render-host')+1].startswith("cd '/tmp/repo with spaces;echo nope' &&")
    with pytest.raises(ValueError,match='hostname'):
        demo.build_plan(skill,arguments(skill,render_host='render-host;echo nope'),{})


@pytest.mark.parametrize('trim_idle', [False, True])
def test_remote_compose_uses_existing_files_and_checks_ocr(skill,tmp_path,monkeypatch,trim_idle):
    wrapper=demo.load_skill_recorder()
    recorder=demo.load_recorder()
    plan=demo.build_plan(skill,arguments(skill),{})
    plan['capture_offset_s']=-3
    plan['capture_duration_s']=20
    plan['trim_idle']=trim_idle
    monkeypatch.setattr(wrapper,'load_helpers',lambda:(demo,recorder))
    monkeypatch.setattr(wrapper,'prepare_showcase',lambda plan,recorder,workdir:dict(plan['spec']))
    monkeypatch.setattr(recorder,'scrub_cast',lambda source,dest,**kwargs:dest.write_text('clean'))
    monkeypatch.setattr(recorder,'scan_text',lambda *args:[])
    render=Mock()
    composite=Mock()
    gate=Mock(return_value=[])
    monkeypatch.setattr(recorder,'render_terminal',render)
    monkeypatch.setattr(recorder,'composite',composite)
    monkeypatch.setattr(recorder,'ocr_gate',gate)
    render_commands = []
    def render_command(command, *a, **kw):
        render_commands.append(command)
        Path(command[-1]).write_bytes(b'webm')
    monkeypatch.setattr(recorder,'run',render_command)
    def probe(command,**kwargs):
        assert command[0]=='ffprobe'
        return SimpleNamespace(returncode=0,stdout=json.dumps({'streams':[{'codec_type':'video','codec_name':'vp9','width':720,'height':406}], 'format':{'duration':'24'}}))
    monkeypatch.setattr('subprocess.run',probe)
    output=tmp_path/'demo.webm'
    wrapper.compose_existing(plan,tmp_path/'cast',tmp_path/'phone.mp4',output,tmp_path)
    render.assert_called_once()
    composite.assert_called_once()
    if trim_idle:
        trim = render_commands[0]
        assert trim[trim.index('-i') + 1] == str(tmp_path / 'composite.webm')
        assert 'mpdecimate' in trim[trim.index('-filter_complex') + 1]
        assert '[intro][body][outro]concat' in trim[trim.index('-filter_complex') + 1]
        assert render_commands[1][render_commands[1].index('-i') + 1] == str(tmp_path / 'trimmed.webm')
    else:
        assert len(render_commands) == 1
    assert composite.call_args.args[4]==-3
    gate.assert_called_once()
    assert json.loads((tmp_path/'metrics.json').read_text())['duration_s']==24
    gate.return_value=['private']
    with pytest.raises(RuntimeError,match='OCR privacy'):
        wrapper.compose_existing(plan,tmp_path/'cast',tmp_path/'phone.mp4',output,tmp_path)
    assert not output.exists()


def test_ocr_failure_fails_closed(tmp_path,monkeypatch):
    recorder=demo.load_recorder()
    monkeypatch.setattr('subprocess.run',lambda *a,**kw:SimpleNamespace(returncode=1,stdout=''))
    with pytest.raises(RuntimeError,match='OCR command failed'):
        recorder.ocr_png(tmp_path/'screenshot.png')


def test_remote_phone_start_stop_detaches_and_restores(skill,tmp_path,monkeypatch):
    import os
    wrapper=demo.load_skill_recorder()
    recorder=demo.load_recorder()
    plan=demo.build_plan(skill,arguments(skill),{})
    plan['privacy_patterns']='personal fixture identifier'
    monkeypatch.setenv('ADB_SERVER_SOCKET','tcp:client:5037')
    monkeypatch.setattr(wrapper,'load_helpers',lambda:(demo,recorder))
    device=Mock(serial=plan['serial'])
    def adb(*args, **kwargs):
        if args[-1] == '-s':
            return ''
        if args[-1] == '-3':
            return 'package:' + plan['spec']['demo_app']
        if args[1:3] == ('pm', 'clear'):
            return 'Success'
        return '1'
    device.adb.side_effect = adb
    monkeypatch.setattr(recorder,'get_device',lambda serial:device)
    prep=Mock(return_value={'zen_mode':'0'})
    restore=Mock()
    monkeypatch.setattr(recorder,'phone_privacy_prep',prep)
    monkeypatch.setattr(recorder,'phone_privacy_restore',restore)
    monkeypatch.setattr(recorder,'run_setup',Mock())
    process=Mock(pid=1234)
    process.poll.return_value=None
    started=[]
    def popen(command,**kwargs):
        started.append((command,kwargs))
        return process
    monkeypatch.setattr('subprocess.Popen',popen)
    monkeypatch.setattr('time.sleep',lambda seconds:None)
    pulled=[]
    monkeypatch.setattr('subprocess.run',lambda command,**kwargs:pulled.append(command) or SimpleNamespace(returncode=0))
    wrapper.remote_phone_start(plan,tmp_path)
    assert os.environ['ADB_SERVER_SOCKET']=='tcp:127.0.0.1:5037'
    assert started[0][0][:4] == ['adb','-s',plan['serial'],'shell']
    assert started[0][1]['start_new_session'] is True
    assert (tmp_path/'phone-state.json').exists()
    assert 'personal fixture identifier' in (tmp_path/'capture-forbidden.txt').read_text()
    wrapper.remote_phone_stop(plan,tmp_path)
    assert not (tmp_path/'phone-state.json').exists()
    assert pulled[0][:4] == ['adb','-s',plan['serial'],'pull']
    restore.assert_called_once_with(device,{'zen_mode':'0'})


def test_remote_cleanup_rejects_non_generated_paths():
    wrapper=demo.load_skill_recorder()
    with pytest.raises(ValueError,match='Refusing cleanup'):
        wrapper.remote_main(['--cleanup','/tmp'])
    with pytest.raises(ValueError,match='Refusing cleanup'):
        wrapper.remote_main(['--cleanup','/home/ghost'])


def test_demo_params_loader_and_all_actions_mode(tmp_path):
    import shutil
    from types import SimpleNamespace

    import pytest
    import yaml

    from gitd.skills.engine import demo
    from gitd.skills.engine.errors import SchemaError
    from gitd.skills.engine.loader import load_skill

    repo = Path(__file__).resolve().parents[1]
    skill_dir = tmp_path / 'calculator'
    shutil.copytree(repo / 'skillhub/ghost/calculator', skill_dir, ignore=shutil.ignore_patterns('runs'))
    skill = load_skill(skill_dir)
    assert skill.action('convert_units').demo_params['from_unit'] == 'Fahrenheit'
    assert skill.action('read_result').demo_params == {}
    args = SimpleNamespace(action=None, legacy_action=None, actions=None, out=None, device='emulator-5554',
                           prompt=None, record_size=None, layout='split', agent='engine', dry=True,
                           no_ocr=False, i_know=False, render_host='render-host', render_root='~/r',
                           render_python='python3', phone_offset=3.0, long_side=1080, crf=33)
    plans = {p['action']: p for p in demo.build_plans(skill, args, {})}
    assert plans['convert_units']['params']['value'] == '100'
    assert 'from_unit=Fahrenheit' in plans['convert_units']['engine_command']
    assert plans['calculate']['params'] == {'expression': '1234*5'}
    assert plans['calculate']['limits']['long_side_px'] == 1080 and plans['calculate']['limits']['crf'] == 33
    assert '1080' in ' '.join(demo.transcode_command('a', 'b', 1080, 33)) and '33' in demo.transcode_command('a', 'b', 1080, 33)
    explicit = {p['action']: p for p in demo.build_plans(skill, args, {'expression': '2+2'})}
    assert explicit['calculate']['params'] == {'expression': '2+2'}   # --param wins over demo_params
    raw = yaml.safe_load((skill_dir / 'skill.yaml').read_text())
    raw['actions'][0]['demo_params'] = {'nope': 1}
    (skill_dir / 'skill.yaml').write_text(yaml.safe_dump(raw, sort_keys=False))
    with pytest.raises(SchemaError, match='undeclared'):
        load_skill(skill_dir)


def test_long_agent_capture_is_stretched_then_sped_up_not_trimmed():
    import importlib.util
    repo = Path(__file__).resolve().parents[1]
    spec_obj = importlib.util.spec_from_file_location('rsd_fit', repo / 'scripts/showcase/record_skill_demo.py')
    module = importlib.util.module_from_spec(spec_obj)
    spec_obj.loader.exec_module(module)
    recorder = demo.load_recorder()
    spec = {'timeline': [{'t': 0, 'action': 'terminal_type', 'args': {'cmd': 'x'}},
                         {'t': 12, 'action': 'sleep', 'args': {'seconds': 0}},
                         {'t': 24, 'action': 'wait_for_phone', 'args': {'seconds': 2}}]}
    assert recorder.timeline_end(spec) == 28.0
    fitted = module.fit_timeline(spec, recorder, 56.0)
    assert recorder.timeline_end(fitted) == 56.0 and fitted['timeline'][1]['t'] == 26.0
    assert module.fit_timeline(spec, recorder, 20.0) is spec          # short captures untouched
    fast = ' '.join(demo.transcode_command('a.webm', 'b.webm', 1080, 33, 2.0))
    assert 'setpts=PTS/2.0000,' in fast and "1080" in fast and '-crf 33' in fast
    assert 'setpts' not in ' '.join(demo.transcode_command('a.webm', 'b.webm'))


def test_skill_demo_intro_card_fields_are_in_the_spec():
    skill = load_skill(Path(__file__).resolve().parents[1] / 'skillhub/ghost/calculator')
    intro = demo.intro_fields(skill, skill.action('convert_units'))
    assert intro == {'kicker': 'SKILL DEMO', 'byline': '@ghost', 'title': 'Fossify Calculator: Convert units'}
    args = SimpleNamespace(action='convert_units', legacy_action=None, actions=None, out=None, device='emulator-5554',
                           prompt=None, record_size=None, layout='split', agent='engine', dry=True, no_ocr=False,
                           i_know=False, render_host='render-host', render_root='~/r', render_python='python3',
                           phone_offset=3.0, long_side=720, crf=41)
    spec = demo.build_plans(skill, args, {})[0]['spec']
    assert spec['intro'] == intro and spec['title'] == intro['title']


def test_saved_demo_spec_has_no_local_paths():
    from gitd.skills.engine.split_demo import portable_demo_meta
    plan = {'agent': 'claude', 'params': {}, 'render_host': 'h', 'render_root': '~/r', 'phone_offset_s': 3.0,
            'capture_offset_s': -1.0, 'limits': {'long_side_px': 1080},
            'mcp_config': {'mcpServers': {'android-agent': {'command': '/usr/bin/python3', 'args': ['-m', 'gitd.mcp_server'],
                                                            'env': {'PYTHONPATH': str(demo.REPO_ROOT), 'GHOST_DEVICE': 'e'}}}}}
    meta = portable_demo_meta(plan)
    server = meta['mcp_config']['mcpServers']['android-agent']
    assert server['command'] == 'python3' and server['env']['PYTHONPATH'] == '<repo>'
    assert str(demo.REPO_ROOT) not in json.dumps(meta) and meta['limits'] == {'long_side_px': 1080}
    assert plan['mcp_config']['mcpServers']['android-agent']['command'] == '/usr/bin/python3'   # plan untouched


def test_card_overrides_from_spec_and_cli(skill, tmp_path):
    spec = tmp_path / 'spec.yaml'
    spec.write_text('cards:\n  title: From spec\n  header: DEMO HEADER\n  outro_url: https://example.org/\n')
    args = demo.parser().parse_args(['ref', skill.actions[0].name, '--device', 'mock-device',
                                     '--spec', str(spec), '--title', 'CLI wins', '--mode', 'hard', '--dry'])
    plan = demo.build_plans(skill, args, {})[0]
    import sys
    sys.path.insert(0, str(ROOT / 'scripts/showcase'))
    import skill_cards
    cards = skill_cards.resolve(plan['spec'])
    assert cards['title'] == 'CLI wins'
    assert cards['header'] == 'DEMO HEADER'
    assert cards['eyebrow'] == 'SKILL SHOWCASE'
    assert cards['outro_url'] == 'https://example.org/'
    assert cards['outro_cmd'] == f'ghost skill install {skill.author}/{skill.name}'
    command = demo.capture_command(plan, tmp_path)
    assert command[0] == 'asciinema'
    assert 'skill run' in command[command.index('-c') + 1]


def test_soft_mode_is_real_notes_driven_and_has_no_auth_fallback(skill, monkeypatch):
    args = demo.parser().parse_args(['ref', skill.actions[0].name, '--device', 'mock-device', '--mode', 'soft', '--dry'])
    plan = demo.build_plans(skill, args, {})[0]
    assert 'get_skill_notes' in plan['agent_prompt']
    assert plan['mcp_config']['mcpServers']['android-agent']['env']['GHOST_MCP_PROFILE'] == 'soft-only'
    assert 'Run this action exactly once' not in plan['agent_prompt']
    command = demo.capture_command(plan, '/tmp/mock')
    assert 'claude_tui_driver.py' in command[1]
    assert command[command.index('--model') + 1] == 'haiku'
    assert '--notes-only' in command
    assert command[command.index('--max-tokens') + 1] == '12000'
    monkeypatch.setattr('shutil.which', lambda tool: None)
    args.dry = False
    with pytest.raises(ValueError, match='no replay fallback'):
        demo.select_agent(args)


@pytest.mark.parametrize('system,installed', [(True, True), (False, False)])
def test_clean_reset_never_clears_system_or_missing_apps(system, installed):
    wrapper = demo.load_skill_recorder()
    dev = Mock()
    dev.adb.side_effect = ['package:org.example.demo' if system else '',
                           'package:org.example.demo' if installed else '']
    with pytest.raises(ValueError, match='non-system'):
        wrapper.clean_reset(dev, {'demo_app': 'org.example.demo'})
    assert not any('clear' in call.args for call in dev.adb.call_args_list)


def test_clean_reset_orders_clear_seed_home_and_fails_closed():
    wrapper = demo.load_skill_recorder()
    dev = Mock()
    dev.adb.side_effect = ['', 'package:org.example.demo', '', 'Success', '', '']
    wrapper.clean_reset(dev, {'demo_app': 'org.example.demo', 'seed': [
        {'action': 'org.example.demo.SEED', 'extras': {'fixture': 'sample data'}}]})
    calls = [call.args for call in dev.adb.call_args_list]
    assert calls[2] == ('shell', 'am', 'force-stop', 'org.example.demo')
    assert calls[3] == ('shell', 'pm', 'clear', 'org.example.demo')
    assert shlex.split(calls[4][1]) == ['am', 'broadcast', '-p', 'org.example.demo', '-a',
                                       'org.example.demo.SEED', '--es', 'fixture', 'sample data']
    assert calls[5][-1] == 'KEYCODE_HOME'
    dev.adb.reset_mock(side_effect=True)
    dev.adb.side_effect = ['', 'package:org.example.demo', '', 'Failure']
    with pytest.raises(RuntimeError, match='reset failed'):
        wrapper.clean_reset(dev, {'demo_app': 'org.example.demo'})


def test_live_token_counter_deduplicates_streamed_messages(tmp_path):
    import importlib.util
    module_spec = importlib.util.spec_from_file_location('demo_driver', ROOT / 'scripts/showcase/claude_tui_driver.py')
    driver = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(driver)
    transcript = tmp_path / 'session.jsonl'
    entries = [{'type': 'assistant', 'message': {'id': 'one', 'usage': {'input_tokens': 20, 'output_tokens': n,
                'cache_read_input_tokens': 5}}} for n in (1, 10)]
    entries += [{'type': 'assistant', 'message': {'id': 'two', 'usage': {'input_tokens': 30, 'output_tokens': 4}}}]
    transcript.write_text('\n'.join(json.dumps(entry) for entry in entries) + '\n{')
    assert driver.session_tokens(transcript) == 69
