---
name: platform-testing
description: Required for any test that runs the FluidGPT app — verifying a branch, PR or change with real HTTP calls. Starts the server from the current checkout (config from Azure Key Vault), logs in with the Key Vault test account, makes curl calls that are recorded as evidence, records checks on the outputs, and produces a report that verify_run.py proves against the server's own log. Use for "test this PR", "run the app and curl it", "verify end to end".
---

# Platform Testing

> Two identical copies: `skills/platform-testing/` and `.claude/skills/platform-testing/`.
> Edit both — `tests/test_platform_testing_skill_copies.py` fails if they differ.
> `/run-test` (`.claude/commands/run-test.md`) runs this skill.

Run the app from the current checkout, call it with curl, check what comes back, and leave evidence that anyone can verify afterwards.

## Rules — a result without evidence is not a result

1. **Every API call goes through `api_call.sh`.** A bare `curl` to the server is not evidence.
2. **Every claim about an output goes through `check.sh`.** A 200 only shows the request didn't fail — check the content (right file, right text, right user's data).
3. **The report is the output of `verify_run.py`, pasted verbatim, plus the `RUN_DIR` path.** Never write a pass/fail table by hand.
4. **If anything can't run — server won't start, login fails, a step errors — stop and report that, with the error.** Never substitute unit tests, mocks or reasoning and call it a pass. Never edit files in the run directory.

## Steps

```bash
S=.claude/skills/platform-testing/scripts

bash $S/start_local_server.sh     # ~1 min. Prints branch@commit, BASE_URL, RUN_DIR
bash $S/get_token.sh              # fresh JWT for the Key Vault test account; prints role/tenant only
RUN_DIR=$(cat "${TMPDIR:-/tmp}/fluidgpt-local-server-8010/current_run")

# Calls — label, method, path, then any curl args
bash $S/api_call.sh convert-pptx POST "/api/fileOperations/convert/?dest_type=pdf" -F "file=@/path/to/Report.pptx"
NO_AUTH=1 bash $S/api_call.sh convert-no-auth POST "/api/fileOperations/convert/?dest_type=pdf" -F "file=@/path/to/Report.pptx"

# Checks — label, expected, a command that prints the actual value
bash $S/check.sh "pptx converted" "completed" \
  'python3 -c "import json,glob; print(json.load(open(sorted(glob.glob(\"$RUN_DIR/calls/*convert-pptx.body\"))[-1]))[\"status\"])"'

bash $S/stop_local_server.sh      # always, even after a failure; deletes the token, keeps RUN_DIR
python3 $S/verify_run.py "$RUN_DIR"   # the report — paste its output verbatim
```

Each call's response body is saved as `$RUN_DIR/calls/<time>-<random>-<label>.body`; `api_call.sh` prints the path.

## What `verify_run.py` proves

| Claim | Checked against (not written by the agent) |
|---|---|
| The server from this checkout ran | uvicorn's own log line `Started server process [<pid>]` matches the pid recorded at start; listening on the recorded port; startup completed |
| Each call reached that server | every call (from curl's own output) matches a server access-log line on **client port + method + path + status** |
| Evidence wasn't edited afterwards | response bodies and uploaded inputs re-hashed against values recorded at call time |
| Outputs were checked | at least one check; PASS recomputed from recorded expected vs actual |
| Which code was tested | branch, commit and "uncommitted changes" recorded at start; warns if the checkout has moved since |

It prints `VERIFIED: ...` and exits 0 only when all of these hold; otherwise `NOT VERIFIED:` with each reason.

**For the human reviewer:** run `python3 .claude/skills/platform-testing/scripts/verify_run.py <RUN_DIR>` yourself, from a machine where that directory exists — don't rely on pasted output. Then open one `calls/*.body` file and one check's `command` in `checks.jsonl` to see they test what was claimed. For endpoints that persist data (e.g. conversions), the records also appear in the app (`/api/fileOperations/convert/history`) at the run's timestamps.

## Concurrency and user-isolation tests

Run calls in parallel with `&`, then check every response — not just one:

```bash
for round in 1 2 3 4 5; do for who in a b; do
  bash $S/api_call.sh "same-name-$who$round" POST "/api/fileOperations/convert/?dest_type=pdf" -F "file=@$who/Report.pptx" &
done; done; wait

for who in a b; do for body in "$RUN_DIR"/calls/*same-name-$who*.body; do
  bash $S/check.sh "$(basename "$body" .body) got own file" "USER-${who^^} deck" \
    "curl -s -o '$body.pdf' \"\$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[\"converted_file_url\"])' '$body')\" && pdftotext '$body.pdf' - | head -1"
done; done
```

To test a concurrency cap, record the peak number of real worker processes as a check:

```bash
( peak=0; for _ in $(seq 1 600); do n=$(ps -C soffice.bin --no-headers | wc -l); [ "$n" -gt "$peak" ] && peak=$n; echo $peak > "$RUN_DIR/peak"; sleep 0.05; done ) &
# ... fire the parallel calls, wait ...
bash $S/check.sh "never more than 2 LibreOffice at once" "2" "cat '$RUN_DIR/peak'"
```

Use `ps -C <name>`, not `pgrep -f "<pattern>"`: `pgrep -f` also matches the sampler's own shell and overcounts.

## How the scripts work, and the pitfalls they avoid

| Step | How | Pitfall avoided |
|---|---|---|
| Config | Server loads ~100 variables from Azure Key Vault at startup (`services/environment_variables.py`); only `AZURE_KEY_VAULT_*` must be in the shell | The repo `.env` has no MongoDB/S3 values |
| Python | If `pyproject.toml` or `poetry.lock` differ from `BASE_REF` (default `origin/pre-development`, committed or not): `poetry install`, then the server runs with `poetry run`. Otherwise reuses an existing complete project virtualenv. Override with `PYTHON=`. `verify_run.py` prints which was used | Changed dependencies are tested with the branch's own packages; for unchanged ones it skips a long install (`poetry run` in a git worktree would otherwise create a new **empty** virtualenv). `python -m uvicorn` is used because some envs have no `uvicorn` script |
| Port | `8010` by default (`PORT=` to change); refuses if the port answers | `8000` is usually another checkout's server — it answers, with the wrong code |
| Health | `POST /apps/health-check/is-alive` (same as the e2e `init.sh`) | `/is-alive` at the root is not the app's health check |
| Token | `POST /auth/get_token` with `TEST_DEV_EMAIL` / `TEST_DEV_PASSWORD` from Key Vault; saved mode 600, never printed | `BEARER_TOKEN` in the shell is a long-expired JWT → `401 Token validation error` |
| Evidence | `${TMPDIR:-/tmp}/fluidgpt-local-server-<port>/runs/<UTC time>-<commit>/` — `run.json`, `server.log`, `calls.jsonl`, `calls/`, `checks.jsonl` | Kept out of the repo |
| Stop | Kills only the recorded server; a `<defunct>` zombie counts as stopped once the port is free | |

## Side effects — state them in the report

The Key Vault config points at the shared dev tenant (`demo-dev`): calls write real MongoDB records and real S3 objects there. Use small, obviously fake test files.
