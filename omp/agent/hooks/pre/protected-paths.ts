/**
 * Protected Paths Hook
 *
 * Blocks write and edit operations to protected paths.
 * Useful for preventing accidental modifications to sensitive files.
 */
import type { HookAPI } from "@oh-my-pi/pi-coding-agent/extensibility/hooks";

export default function (pi: HookAPI) {
	const protectedPaths = [".env", ".git/", "node_modules/"];

	pi.on("tool_call", async (event, ctx) => {
		if (event.toolName !== "write" && event.toolName !== "edit") {
			return undefined;
		}

		const paths =
			typeof event.input.path === "string"
				? [event.input.path]
				: [...String(event.input.input ?? "").matchAll(/^\[([^\]#]+)(?:#[0-9A-Fa-f]+)?\]/gm)].map(m => m[1]);
		const path = paths.find(p => protectedPaths.some(pp => p.includes(pp)));
		const isProtected = path !== undefined;

		if (isProtected) {
			if (ctx.hasUI) {
				ctx.ui.notify(`Blocked write to protected path: ${path}`, "warning");
			}
			return { block: true, reason: `Path "${path}" is protected` };
		}

		return undefined;
	});
}
