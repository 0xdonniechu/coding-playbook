**FAIL**

1. **MAJOR** `guard/owner-token-guard.py:55-75` (deny list), `CLAUDE.md:30` (limits). Tracing the gh wrapper prints the owner's token and is not denied or documented. The wrapper on every Ambysto machine does `GH_TOKEN="$(… auth token …)" && export GH_TOKEN` (line 43 of `~/.local/bin/gh`), so `bash -x ~/.local/bin/gh pr list` (or `sh -x`, `SHELLOPTS=xtrace`) echoes `+ GH_TOKEN=gho_…`. `decide()` returns None for it. This is a plausible debugging step ("why does gh pick that account?"), not evasion, and the Open paragraph does not name it. Same class, lower likelihood: gh's own children inherit the injected token, so `gh alias set e '!env' && gh e` passes and prints it.

2. **MINOR** `guard/owner-token-guard.py:41` (`PREFIX`). Quadratic matching on `${…}` runs: a 50 KB command of `${x}` repeats takes 25 s, 100 KB about 100 s, 150 KB over 120 s. Claude Code cancels a hook at 60 s and the call proceeds, so `"${x}"*25000 + "\ngh auth token"` passes the guard, contradicting "any internal error blocks". Benign heredocs (300 KB JSON, 200 KB minified JS, 2 MB text) stay under 2.5 s.

3. **MINOR** deny-list gaps, undocumented: `$(which gh) auth token`, `perl -e 'print $ENV{GH_TOKEN}'`, `env | grep GH_TOKEN` / `set | grep GH_TOKEN` (the variable is named, unlike the documented "bare env"), `cp -r ~/.config/gh/. /tmp/x`, `/proc/self/../self/environ`, `git -c credential.helper='!f(){ cat >>/tmp/c; }; f' fetch` (a helper the agent adds receives the token on `approve`).

4. **MINOR** false positives beyond the documented ones: `npm install keytar`, `cat .netrc.example`, `ls ~/.local/share/keyrings-backup`, `[ -n "$GH_TOKEN" ]`, `echo "${GH_TOKEN:+set}"` denied; `os.environ.get( "AMBYSTO_OWNER", "")` (space after the paren), `environ.pop("AMBYSTO_OWNER", None)`, `print("AMBYSTO_OWNER", 1)` ask. Also any commit message or grep naming `gh auth token` or `oauth_token` is denied, which blocks routine maintenance of this very repo (the reviewed commit's own message contains `gh auth token`).

5. **MINOR** `scripts/install.py:201-211`. The guard is required but can only be installed with `--settings`, which also merges the 33 optional plugin/skill defaults; "defaults stay optional" no longer holds on a machine that wants only the guard.

6. **MINOR** `guard/owner-token-guard.py:130`. A Bash input without a string `command` falls through to checking every string, so the description is read there (contradicts the docstring; harmless).

Commands run:
- `python3 scripts/check.py`: PASS. `guard/owner-token-guard.py --self-test`: PASS, 146 cases.
- Probe of `decide()`: 61 bypass candidates (denied as expected for quoting, `eval`, `sh -c`, `sudo`, D-Bus, `.exe`, case; gaps as in 1-3), 46 ordinary commands (false positives as in 4), 21 owner-switch cases (`read`/`printf -v` with `set -a` and indirect `export $V=1` pass, evasion-class), 22 file/MCP cases as documented.
- Protocol: deny/ask JSON matches the PreToolUse contract, exit 0; `null`, `5`, non-string `tool_name`, empty and invalid UTF-8 stdin exit 2; `LANG=C`, latin1 and `PYTHONIOENCODING=ascii` fine.
- Installer on six temporary HOMEs only: fresh (`--check` 1, `--settings` 0, rerun unchanged, no backup), BOM+CRLF file with other tools' PreToolUse/PostToolUse/Stop hooks (order kept, entry appended last, others byte-equal, one backup), stale entry replaced in place, refusals (two entries, mixed, `hooks` list/null, `PreToolUse` dict, top-level list, bad JSON: exit 2, file unchanged, no backup), `--check --settings` writes nothing, the installed command through `sh` (deny, empty stdin 2, missing script 2, missing python3 127).

Not run: a live Claude Code session with this version installed (needs the real home), the real `settings.json`, Windows hook shell.
