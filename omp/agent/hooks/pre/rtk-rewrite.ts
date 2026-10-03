/**
 * RTK Rewrite Hook
 *
 * Routes bash commands through `rtk` so their output reaches the model compact.
 * `rtk rewrite` decides what to rewrite (exit 0 + new command) or leaves the
 * command alone (exit 1), same contract rtk ships for Claude Code / Gemini hooks.
 */
import type { HookAPI } from "@oh-my-pi/pi-coding-agent/extensibility/hooks";

export default function (pi: HookAPI) {
	pi.on("tool_call", async event => {
		if (event.toolName !== "bash") return undefined;
		const command = event.input.command;
		if (typeof command !== "string" || command.trim() === "") return undefined;

		const { stdout, code } = await pi.exec("rtk", ["rewrite", command]);
		const rewritten = stdout.trim();
		if (code !== 0 || rewritten === "" || rewritten === command.trim()) return undefined;

		return { input: { ...event.input, command: rewritten } };
	});
}
