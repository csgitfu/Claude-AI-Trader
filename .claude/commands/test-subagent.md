---
name: test-subagent
description: Manual sanity test for a subagent against a fixture input
allowed-tools: Bash, Agent, Read
---

# Usage

`/test-subagent <subagent-name> <fixture-path>`

Example: `/test-subagent scorer tests/fixtures/subagent_inputs/scorer_input.json`

Valid subagent names: `scorer`, `debater`, `prob-estimator`

# Steps

1. **Read the fixture**:
   Read: `<fixture-path>` — display the fixture content so you can confirm it loaded.

2. **Invoke the named subagent** with the fixture content as the user prompt:
   ```
   Agent(subagent_type=<name>, prompt='Process this input:\n```json\n<fixture-content>\n```')
   ```
   Capture the subagent's full reply text.

3. **Save the reply to a temp file**:
   Bash: Write the reply text to `/tmp/_subagent_reply.txt`
   (Use the Write tool to write the reply, or via Bash heredoc: `cat > /tmp/_subagent_reply.txt <<'REPLY'\n<reply>\nREPLY`)

4. **Validate via parse_subagent_output**:
   Bash: `python -m trader.helpers.parse_subagent_output --schema <name> --input "$(cat /tmp/_subagent_reply.txt)"`

5. **Report the result**:
   - If exit code is 0: print `PASS — validated output:` followed by the stdout (the validated JSON).
   - If exit code is non-zero: print `FAIL — validation error:` followed by the stderr content.

# Notes

- This command is for **Layer 2 manual sanity testing** only. Run it from an interactive Claude Code session, not from a routine.
- Re-run after any edit to a `.claude/agents/*.md` file to confirm the prompt change doesn't break schema compliance.
- If the subagent fails schema validation, the most common fixes are:
  - Tighten the "Output ONLY a fenced JSON block, no preamble" instruction in the agent file.
  - Add a field-range clamping instruction (e.g., `sizing_hint` must be ≤ 0.10).
  - Check that every input ticker is represented in the output (scorer requirement).
