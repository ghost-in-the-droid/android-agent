"""Static skill Python analysis. Findings are review signals, not a sandbox.

Severity contract (tools/ci/submission.py): ``high`` blocks a PR, ``medium`` adds the
``needs-security-review`` label, ``low`` is informational. Rules:

* network-exfil (high): outbound calls with undeclared or unknown hosts
* aliased-exec (high): aliases/attribute lookup of dangerous builtins, shell or process callables
* soft-injection / typosquat-slug (high): shared instruction and registry namespace checks
* code-execution (high): eval, exec, compile, __import__
* shell-execution (high): os.system, os.popen, subprocess with shell=True, subprocess.getoutput,
  subprocess.getstatusoutput, pty.spawn
* process-execution (medium): subprocess.run/Popen/call/check_call/check_output, os.spawn*, os.exec*,
  os.posix_spawn*
* dynamic-import (high for unresolved import_module names, otherwise medium): importlib.import_module / reload / util.spec_from_file_location /
  util.module_from_spec, runpy.run_path / run_module
* restricted-import / restricted-call (medium): ctypes, socket, requests, urllib, httpx
* external-write (high) / dynamic-write (medium): open() in a write mode, Path.write_text /
  write_bytes / touch / mkdir / unlink / rmdir / symlink_to on any receiver, rename / replace / chmod
  only on a literal Path(...) receiver (they are also str methods), shutil.copy* / move / rmtree,
  os.remove / unlink / rename / replace / makedirs / mkdir / rmdir / symlink / link / chmod: a literal
  destination outside the skill dir and /tmp is high, a destination that cannot be established is medium
* dynamic-attribute (medium): getattr / setattr / delattr with a non-literal attribute name
* getattr-chain (low), encoded-blob (medium), device-shell (low: raw ``device.adb`` / ``device.shell``
  calls, the intended escape hatch, listed so a reviewer reads them), parse-error (high)
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

_SHELL_CALLS = {
    "os.system",
    "os.popen",
    "subprocess.getoutput",
    "subprocess.getstatusoutput",
    "pty.spawn",
    "commands.getoutput",
    "commands.getstatusoutput",
}
_PROCESS_CALLS = {
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "os.posix_spawn",
    "os.posix_spawnp",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
}
_DYNAMIC_IMPORTS = {
    "importlib.import_module",
    "importlib.reload",
    "importlib.util.spec_from_file_location",
    "importlib.util.module_from_spec",
    "importlib.__import__",
    "runpy.run_path",
    "runpy.run_module",
    "imp.load_source",
    "pkgutil.resolve_name",
}
_FS_FUNCS = {
    "shutil.copy",
    "shutil.copy2",
    "shutil.copyfile",
    "shutil.copytree",
    "shutil.move",
    "shutil.rmtree",
    "os.remove",
    "os.unlink",
    "os.rename",
    "os.replace",
    "os.makedirs",
    "os.mkdir",
    "os.rmdir",
    "os.symlink",
    "os.link",
    "os.chmod",
    "os.truncate",
    "os.removedirs",
    "os.renames",
}
_FS_DST_LAST = {
    "shutil.copy",
    "shutil.copy2",
    "shutil.copyfile",
    "shutil.copytree",
    "shutil.move",
    "os.rename",
    "os.replace",
    "os.symlink",
    "os.link",
    "os.renames",
}  # destination is the second positional
_PATH_WRITE_METHODS = {"write_text", "write_bytes", "touch", "mkdir", "unlink", "rmdir", "symlink_to", "hardlink_to"}
_PATH_ONLY_METHODS = {"rename", "replace", "chmod"}  # also str/dict methods: only flagged on a Path(...) receiver
_PATH_CTORS = {"Path", "pathlib.Path", "PosixPath", "pathlib.PosixPath", "PurePath", "pathlib.PurePath"}
_NETWORK_ROOTS = {"requests", "httpx", "urllib", "socket", "aiohttp", "http"}
_CODE_CALLS = {"eval", "exec", "compile", "__import__"}
_ATTR_FUNCS = {"getattr", "setattr", "delattr", "builtins.getattr", "builtins.setattr", "builtins.delattr"}


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    severity: str
    rule: str
    message: str

    def as_dict(self):
        return asdict(self)


def analyze_skill(path: str | Path) -> list[Finding]:
    """Scan helpers, agent instructions and namespace without importing or executing skill code."""
    root = Path(path).resolve()
    if root.is_file():
        root = root.parent
    if not root.is_dir():
        raise FileNotFoundError(f"Skill directory not found: {root}")
    from gitd.skills.engine.content_analysis import content_findings, read_manifest

    raw = read_manifest(root)
    findings = content_findings(root, raw)
    access = raw.get("data_access", {})
    network = access.get("network", []) if isinstance(access, dict) else []
    allowed_hosts = (
        {host.lower().rstrip(".") for host in network if isinstance(host, str)} if isinstance(network, list) else set()
    )
    for source in sorted(root.rglob("*.py")):
        relative = str(source.relative_to(root))

        def flag(node, severity, rule, message):
            findings.append(Finding(relative, getattr(node, "lineno", 1), severity, rule, message))

        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (SyntaxError, UnicodeError) as exc:
            findings.append(Finding(relative, getattr(exc, "lineno", 1) or 1, "high", "parse-error", str(exc)))
            continue
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    aliases[item.asname or item.name.split(".")[0]] = (
                        item.name if item.asname else item.name.split(".")[0]
                    )
                    if item.name.split(".")[0] in {"ctypes", "socket", "requests", "urllib", "httpx"}:
                        flag(node, "medium", "restricted-import", f"Import {item.name}; network should use gitd.http")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for item in node.names:
                    aliases[item.asname or item.name] = f"{module}.{item.name}"
                if module.split(".")[0] in {"ctypes", "socket", "requests", "urllib", "httpx"}:
                    flag(node, "medium", "restricted-import", f"Import {module}; network should use gitd.http")

        def check_write(node, destination, what):
            if isinstance(destination, ast.Constant) and isinstance(destination.value, str):
                candidate = Path(destination.value)
                candidate = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
                if not candidate.is_relative_to(root) and not candidate.is_relative_to(Path("/tmp")):
                    flag(node, "high", "external-write", f"{what} outside skill directory or /tmp: {destination.value}")
            else:
                flag(node, "medium", "dynamic-write", f"{what}: cannot statically establish the destination")

        literals = {}
        stores = Counter(n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store))
        ambiguous_literals = {key for key, count in stores.items() if count > 1}
        ambiguous_literals.update(n.arg for n in ast.walk(tree) if isinstance(n, ast.arg))

        def literal(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value
            if isinstance(node, ast.Name):
                return literals.get(node.id)
            if isinstance(node, ast.JoinedStr):
                parts = [
                    literal(part.value)
                    if isinstance(part, ast.FormattedValue) and part.conversion == -1 and part.format_spec is None
                    else literal(part)
                    for part in node.values
                ]
                return "".join(parts) if all(part is not None for part in parts) else None
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                left, right = literal(node.left), literal(node.right)
                if left is not None and right is not None:
                    return left + right
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "join"
                and len(node.args) == 1
                and isinstance(node.args[0], (ast.Tuple, ast.List))
            ):
                separator = literal(node.func.value)
                parts = [literal(part) for part in node.args[0].elts]
                if separator is not None and all(part is not None for part in parts):
                    return separator.join(parts)
            return None

        def dangerous(target):
            return (
                target.removeprefix("builtins.") in _CODE_CALLS
                or target in _SHELL_CALLS
                or target in _PROCESS_CALLS
                or target.startswith(("os.spawn", "os.exec"))
            )

        def name(node):
            if isinstance(node, ast.Name):
                return aliases.get(node.id, "builtins" if node.id == "__builtins__" else node.id)
            if isinstance(node, ast.Attribute):
                return name(node.value) + "." + node.attr
            if isinstance(node, ast.Call):
                target = name(node.func)
                if target in {"getattr", "builtins.getattr"} and len(node.args) >= 2:
                    attribute = literal(node.args[1])
                    if attribute is not None:
                        return name(node.args[0]) + "." + attribute
                if target in {"__import__", "builtins.__import__", "importlib.import_module"} and node.args:
                    return literal(node.args[0]) or ""
                if target.split(".")[0] in _NETWORK_ROOTS:
                    return target + ".instance"
            return ""

        def bind(target, value):
            if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
                for dst, src in zip(target.elts, value.elts):
                    bind(dst, src)
            elif isinstance(target, ast.Name):
                resolved, string = name(value), literal(value)
                if resolved and (target.id not in aliases or dangerous(resolved)):
                    aliases[target.id] = resolved
                if string is not None and target.id not in ambiguous_literals:
                    literals.setdefault(target.id, string)

        assignments = [n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr))]
        # Resolve chains and tuple unpacking without evaluating Python; bounded fixed point.
        for _ in range(len(assignments) + 1):
            before = (dict(aliases), dict(literals))
            for assignment in assignments:
                for dst in assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]:
                    bind(dst, assignment.value)
            # Collapse alias chains, retaining the original callable name in findings.
            for key, value in list(aliases.items()):
                if value in aliases and aliases[value] != key:
                    aliases[key] = aliases[value]
            if before == (aliases, literals):
                break

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
                value = node.value.decode("ascii", errors="ignore") if isinstance(node.value, bytes) else node.value
                if len(value) > 200 and (
                    re.fullmatch(r"[A-Fa-f0-9]+", value) or re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", value)
                ):
                    flag(node, "medium", "encoded-blob", "Encoded string exceeds 200 characters")
            if not isinstance(node, ast.Call):
                continue
            target = name(node.func)
            if dangerous(target) and ast.unparse(node.func) != target:
                flag(node, "high", "aliased-exec", f"Aliased dangerous callable: {target}")
            is_network = target.split(".")[0] in _NETWORK_ROOTS
            values = [*node.args, *(k.value for k in node.keywords)]
            if is_network:
                # Only endpoint arguments can authorize a network destination; a URL in the body cannot.
                endpoint = next(
                    (k.value for k in node.keywords if k.arg in {"url", "host", "address", "base_url"}), None
                )
                if endpoint is None and node.args:
                    index = 1 if target.endswith(".request") and not target.startswith("http.client.") else 0
                    endpoint = node.args[index] if len(node.args) > index else None
                values = [endpoint]
            urls = [
                literal(value)
                for value in values
                if literal(value) and literal(value).startswith(("http://", "https://"))
            ]
            # Constructors without an endpoint do not send traffic. Their instances remain tracked.
            constructor = target in {
                "requests.Session",
                "requests.session",
                "httpx.Client",
                "httpx.AsyncClient",
                "aiohttp.ClientSession",
                "socket.socket",
            }
            local_utility = target.startswith(("urllib.parse.", "http.cookies.", "http.cookiejar."))
            if urls or (is_network and not constructor and not local_utility):
                hosts = set()
                for url in urls:
                    try:
                        hosts.add((urlsplit(url).hostname or "").lower().rstrip("."))
                    except ValueError:
                        hosts.add("")
                if not hosts and target.startswith(("socket.", "http.client.")) and node.args:
                    endpoint = node.args[0]
                    if isinstance(endpoint, (ast.Tuple, ast.List)) and endpoint.elts:
                        endpoint = endpoint.elts[0]
                    host = literal(endpoint)
                    if host and not host.startswith("/") and "." in host:
                        hosts.add(host.lower().rstrip("."))
                if not hosts or not hosts <= allowed_hosts:
                    flag(
                        node,
                        "high",
                        "network-exfil",
                        f"{target or ast.unparse(node.func)}: undeclared network host(s): {', '.join(sorted(hosts)) or 'dynamic/unknown'}",
                    )
            if target in {
                "eval",
                "exec",
                "__import__",
                "compile",
                "builtins.eval",
                "builtins.exec",
                "builtins.__import__",
                "builtins.compile",
                "os.system",
            }:
                flag(node, "high", "code-execution", target)
            if target.startswith("subprocess.") and any(
                k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords
            ):
                flag(node, "high", "shell-execution", "subprocess with shell=True")
            if target.split(".")[0] in {"ctypes", "socket", "requests", "urllib", "httpx"}:
                flag(node, "medium", "restricted-call", target)
            if target in _ATTR_FUNCS and len(node.args) > 1:
                if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                    if isinstance(node.args[0], ast.Call) and name(node.args[0].func) in {
                        "getattr",
                        "builtins.getattr",
                    }:
                        flag(node, "low", "getattr-chain", "Nested literal getattr chain")
                else:
                    flag(node, "medium", "dynamic-attribute", f"{target} with a non-literal attribute name")
            if target in _SHELL_CALLS:
                flag(node, "high", "shell-execution", target)
            elif target in _PROCESS_CALLS or target.startswith(("os.spawn", "os.exec")):
                flag(node, "medium", "process-execution", target)
            if target in _DYNAMIC_IMPORTS:
                severity = (
                    "high"
                    if target == "importlib.import_module" and (not node.args or literal(node.args[0]) is None)
                    else "medium"
                )
                flag(node, severity, "dynamic-import", target)
            if target in {"open", "builtins.open", "io.open"}:
                mode = (
                    node.args[1]
                    if len(node.args) > 1
                    else next((k.value for k in node.keywords if k.arg == "mode"), ast.Constant("r"))
                )
                if (
                    isinstance(mode, ast.Constant)
                    and isinstance(mode.value, str)
                    and any(c in mode.value for c in "wax+")
                ):
                    destination = (
                        node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "file"), None)
                    )
                    check_write(node, destination, "open")
            if target in _FS_FUNCS:
                if target in _FS_DST_LAST:
                    destination = (
                        node.args[1]
                        if len(node.args) > 1
                        else next((k.value for k in node.keywords if k.arg == "dst"), None)
                    )
                else:
                    destination = node.args[0] if node.args else None
                check_write(node, destination, target)
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _PATH_WRITE_METHODS | _PATH_ONLY_METHODS
                and target not in _FS_FUNCS
            ):
                receiver = node.func.value
                is_path = isinstance(receiver, ast.Call) and name(receiver.func) in _PATH_CTORS
                if node.func.attr in _PATH_WRITE_METHODS or is_path:
                    destination = receiver.args[0] if is_path and receiver.args else None
                    check_write(node, destination, f"Path.{node.func.attr}")
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"adb", "shell"}
                and name(node.func.value).split(".")[-1] in {"device", "dev", "d", "self.device"}
            ):
                flag(node, "low", "device-shell", f"{target}: raw device command, read it")
    return sorted(findings, key=lambda f: (f.file, f.line, f.rule))


# Public short alias for CI callers.
analyze = analyze_skill
