#!/usr/bin/env node
// Bridges OMP tool input to Claude Code hook scripts (karanb192/claude-code-hooks).
// omp-hooks already aliases path -> file_path; OMP's hashline `edit` tool instead sends
// `input` with `[PATH#TAG]` sections and `+` body rows, so expand it into one
// Claude-style Edit payload per file. Usage: node adapter.mjs <script.js> [--only <regex>]
import { spawnSync } from "node:child_process";

const [script, flag, only] = process.argv.slice(2);
const filter = flag === "--only" ? new RegExp(only) : null;
let raw = "";
for await (const c of process.stdin) raw += c;
const data = JSON.parse(raw);
const ti = data.tool_input ?? {};

let payloads = [data];
if (data.tool_name === "Edit" && typeof ti.input === "string" && !ti.file_path) {
  const sections = ti.input.split(/^(?=\[[^\]]+\]\s*$)/m);
  payloads = sections.flatMap(sec => {
    const m = sec.match(/^\[([^\]#]+)(?:#[0-9A-Fa-f]+)?\]/);
    if (!m) return [];
    const added = sec.split("\n").filter(l => l.startsWith("+")).map(l => l.slice(1)).join("\n");
    return [{ ...data, tool_input: { file_path: m[1], old_string: "", new_string: added } }];
  });
}
if (filter) payloads = payloads.filter(p => filter.test(p.tool_input?.file_path ?? p.tool_input?.path ?? ""));
if (payloads.length === 0) { console.log("{}"); process.exit(0); }

for (const p of payloads) {
  const r = spawnSync("node", [script], { input: JSON.stringify(p), encoding: "utf8" });
  const blocked = r.status === 2 || /"permissionDecision"\s*:\s*"(deny|ask)"/.test(r.stdout ?? "");
  if (blocked || p === payloads.at(-1)) {
    process.stdout.write(r.stdout ?? "");
    process.stderr.write(r.stderr ?? "");
    process.exit(r.status ?? 1);
  }
}
