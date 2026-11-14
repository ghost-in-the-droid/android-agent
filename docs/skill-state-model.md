# Skill state and runtime secrets (v1.6)

**auto-login runner: beta.** A state is a named fact about the current device,
not a stored credential or a promise that an account is authenticated. The runner
probes immediately before an action. State badges add no scoring points and are
not evidence of a successful login.

Actions optionally declare `requires_state`, `provides_state`, and `clears_state`
as lists of unique snake_case names. Each referenced state needs a skill-level
`state_probes` entry. An action cannot both provide and clear the same state.
`idempotent: true` explicitly permits a provider to run when the probe is unknown;
the default is false. Author this assertion only when repeating the action is safe.

```yaml
state_probes:
  logged_in:
    kind: element_present
    id: com.example.app:id/inbox

actions:
  - name: read_inbox
    ref_prompt: Read my inbox
    requires_state: [logged_in]
    steps:
      - action: tap_element
        id: com.example.app:id/inbox
    end_state_validator:
      kind: element_present
      id: com.example.app:id/inbox

  - name: login
    ref_prompt: Log in with credentials supplied by the caller
    provides_state: [logged_in]
    idempotent: false
    params:
      - {name: username, type: str, required: true, secret: true}
      - {name: passphrase, type: str, required: true, secret: true}
    steps:
      - action: tap_element
        id: com.example.app:id/username
      - action: type_text
        text: '{username}'
      - action: tap_element
        id: com.example.app:id/password
      - action: type_text
        text: '{passphrase}'
      - action: tap_element
        id: com.example.app:id/login
      - checkpoint:
          reason: login
          prompt: "HUMAN: complete any captcha or verification on the device"
          success: {kind: element_present, id: 'com.example.app:id/inbox'}
          timeout_s: 600
    end_state_validator:
      kind: element_present
      id: com.example.app:id/inbox

  - name: logout
    ref_prompt: Log out of this account
    clears_state: [logged_in]
    steps:
      - action: tap_element
        id: com.example.app:id/logout
    end_state_validator:
      not: {kind: element_present, id: 'com.example.app:id/inbox'}
```

The example selectors must be replaced with selectors from the intended app.
Login and logout use ordinary actions, params, and the existing human checkpoint;
there is no special credential database or captcha-solving path.

A probe accepts only `kind: element_present` with exactly one literal `id`, `text`,
or `desc`, optionally wrapped in `not:` to test absence. It compares exact visible
accessibility node attributes. Helpers, XPath, interpolation, OCR, screenshots,
and model calls are not probe kinds. An unavailable device, malformed/empty UI
tree, or undeclared state returns `unknown`, never a false assertion of absence.

```sh
ghost skill probe author/skill logged_in --device "$GHOST_DEVICE"
# Prints exactly true, false, or unknown.
```

For each prerequisite, a true probe allows the action to proceed. False selects
exactly one same-skill provider; zero or multiple candidates stop. Unknown also
requires the provider's explicit `idempotent: true`. The runner checks the
provider's runtime parameters before executing it, runs at most one transition
per state per invocation, and probes again afterward. A provider failure, missing
secret, dependency cycle, or an unestablished state returns a structured result:

```json
{"success": false, "status": "needs_state", "needs_state": "logged_in",
 "error": {"kind": "needs_state", "state": "logged_in", "reason": "missing_secret",
           "provider": "login", "message": "Required state unavailable"}}
```

All prerequisites are checked again after the last provider, so a provider that
clears another required state stops the target. Declarations never populate a
trusted state cache. Dry runs skip probes and transitions, and do not prove state.
An explicit caller retry is a new invocation. A durable continuation retains its
transition-attempt set. If a provider pauses for a parent-agent answer, the
`needs_state` result includes its resume token; finish that provider explicitly,
then retry the originally requested action. No input is silently prompted.

Supply provider parameters by **action name**, separately from the target action:

```python
result = run_action(skill, 'read_inbox', device_serial=serial,
                    state_params={'login': {'username': runtime_username,
                                            'passphrase': runtime_passphrase}})
```

MCP `run_skill` accepts the equivalent JSON object in its `state_params` argument
and returns the structured status unchanged. For the CLI, bind secrets from a
local environment populated by your secret store; the binding names, not values,
appear in the command line:

```sh
ghost skill run author/skill read_inbox --device "$GHOST_DEVICE" \
  --state-secret-env login.username=APP_USERNAME \
  --state-secret-env login.passphrase=APP_PASSPHRASE
# Direct login uses --secret-env username=APP_USERNAME --secret-env passphrase=APP_PASSPHRASE.
```

`--state-param login.name=value` is available for nonsecret provider inputs.
`--secret-env` and `--state-secret-env` require parameters declared `secret: true`.
Secrets must be nonempty runtime strings. They cannot have `default`, `values`,
`demo_params`, or test-case parameter values in the skill. Never put credentials
in manifests, helper source, sample prompts, command histories, or fixtures.

The beta engine applies a secret boundary to the whole invocation of a skill
with secret parameters, including providers and the action after login. It
redacts trace/callback/result text and durable continuation data, withholds log
diagnostics and ask attachments, and omits secret params from continuation files.
Resume must resupply exactly those secret params via `--secret-env` (MCP:
`run_skill_resume(..., secrets=...)`). Secrets are kept only in runtime memory.
Signed evidence contains run/step outcomes, not credentials. The bound applies
to engine-managed outputs; the app necessarily receives the entered credentials.

Secret-bearing invocations support declarative UI steps and human checkpoints.
Secret interpolation filters and numeric UI-text conversion are refused to keep
transformed credentials out of outputs. Python helpers, nested skill escape hatches, shell/custom steps, screenshot and
XML-file capture, screenshot validators, sub-agent asks, and automatic demo
recording are refused. Android UI reads require the in-memory Portal reader;
the engine will not fall back to an on-device XML file. This boundary is not a
sandbox for arbitrary Python. Do not run a separate screen recorder or device
stream while entering credentials. A supervised recording should record the
public setup and human pause markers, with credential entry excluded.

CI exercises state transitions with mocked probes and devices.
