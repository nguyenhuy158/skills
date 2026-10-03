const AGENT_CHROME = "the shared headless agent Chrome at CDP http://127.0.0.1:9223 (profile ~/.chrome-agent, run `agent-chrome` if it is down)";

const HOW_TO =
	"Use the browser-use CLI with your own session name: `BU_NAME=<unique-name> browser-use <<'PY' ... PY`; open your tab with new_tab(url) and finish with close_tab().";

const SUFFIX = " If the agent Chrome is unreachable, stop and report the exact error instead of working around it.";

const BROWSER_USE_META = /^(--doctor|--version|--help|-h|--reload|doctor|skill|recordings|auth)\b/;

const TEXT_RULES: Array<[RegExp, string]> = [
	[
		/\borca\s+(?:--?\S+\s+)*(tab|goto|open|click|dblclick|fill|type|press|hover|select|check|uncheck|scroll|snapshot|screenshot|eval|back|forward|reload|dialog|exec|wait|upload|drag)(?=\s|$)/m,
		`Orca's embedded browser is disabled. ${HOW_TO}`,
	],
	[
		/playwright\s+install|@puppeteer\/browsers|puppeteer\s+browsers\s+install|chrome-headless-shell|Chrome for Testing/i,
		`Chrome for Testing / Playwright / Puppeteer browsers are not used for agent browsing. ${HOW_TO}`,
	],
	[/--remote-debugging-port=(?!9223\b)\d+/, `Do not start Chrome on another debug port. Use ${AGENT_CHROME}.`],
	[
		/--user-data-dir=(?!["']?(~|\$HOME|\/Users\/huyntq)\/\.chrome-agent\b)/,
		`Do not create another Chrome profile. Use ${AGENT_CHROME}.`,
	],
	[
		/BU_CDP_(URL|WS)=(?!["']?http:\/\/127\.0\.0\.1:9223\b)/,
		`Do not point browser-use at another CDP endpoint. Use ${AGENT_CHROME}.`,
	],
];

interface Invocation {
	program: string;
	env: Record<string, string>;
	args: string;
}

const ENV_ASSIGNMENT = /^(\w+)=("[^"]*"|'[^']*'|\S*)\s*/;
const WRAPPER = /^(?:(?:timeout|gtimeout)\s+(?:-\S+\s+)*\S+|env(?:\s+-\S+)*|nice(?:\s+-n\s+\S+)?|time|command|exec|nohup)\s+/;

function parseInvocation(segment: string): Invocation {
	const env: Record<string, string> = {};
	let rest = segment.trim();
	for (;;) {
		const assignment = rest.match(ENV_ASSIGNMENT);
		if (assignment) {
			env[assignment[1]] = assignment[2].replace(/^["']|["']$/g, "");
			rest = rest.slice(assignment[0].length);
			continue;
		}
		const wrapper = rest.match(WRAPPER);
		if (!wrapper) break;
		rest = rest.slice(wrapper[0].length);
	}
	const [program = "", ...args] = rest.split(/\s+/);
	return { program: program.replace(/^.*\//, ""), env, args: args.join(" ") };
}

function stripHeredocBodies(command: string): string {
	const kept: string[] = [];
	let delimiter: string | undefined;
	let dashed = false;
	for (const line of command.split("\n")) {
		if (delimiter !== undefined) {
			if ((dashed ? line.replace(/^\t+/, "") : line) === delimiter) delimiter = undefined;
			continue;
		}
		kept.push(line);
		const open = line.match(/(?<!<)<<(-?)\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\2/);
		if (open) {
			dashed = open[1] === "-";
			delimiter = open[3];
		}
	}
	return kept.join("\n");
}

function checkInvocations(command: string): string | undefined {
	for (const call of stripHeredocBodies(command).split(/\n|;|&&|\|\||\||\$\(|`/).map(parseInvocation)) {
		if (call.program === "agent-browser") return `agent-browser is not used on this machine. ${HOW_TO}`;
		if (call.program !== "browser-use" || BROWSER_USE_META.test(call.args)) continue;
		const name = call.env.BU_NAME;
		if (!name) return `browser-use needs a session name so parallel agents never share a tab. ${HOW_TO}`;
		if (name === "agent" || name === "default") return `BU_NAME=${name} is shared; pick a unique name for your task. ${HOW_TO}`;
	}
	return undefined;
}

interface ToolCallEvent {
	toolName: string;
	input?: { command?: unknown; op?: unknown; application?: unknown; args?: unknown };
}

interface HookApi {
	on(event: "tool_call", handler: (event: ToolCallEvent) => Promise<{ block: true; reason: string } | undefined>): void;
}

function commandOf(event: ToolCallEvent): string | undefined {
	if (event.toolName === "bash") return String(event.input?.command ?? "");
	if (event.toolName !== "hub" || event.input?.op !== "start") return undefined;
	const args = Array.isArray(event.input.args) ? event.input.args.map(String) : [];
	return [String(event.input.application ?? ""), ...args].join(" ");
}

export default function browserGuard(pi: HookApi): void {
	pi.on("tool_call", async event => {
		const command = commandOf(event);
		if (command === undefined) return undefined;
		const reason = TEXT_RULES.find(([pattern]) => pattern.test(command))?.[1] ?? checkInvocations(command);
		return reason ? { block: true, reason: `[browser-guard] ${reason}${SUFFIX}` } : undefined;
	});
}
