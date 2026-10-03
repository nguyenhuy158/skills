// Sync the omp session name to the Orca terminal tab title.
// Why polling: omp exposes no title_change event to extensions, and /rename
// runs as a command without a turn. Comparing a string every few seconds is
// free; `orca` is spawned only when the name actually changes.
// Why local types: Pi and OMP publish the extension API under different
// package names (same reason as orca-agent-status.ts).
const ORCA_BIN = "/Applications/Orca.app/Contents/Resources/bin/orca"
const POLL_MS = 3000

type Ctx = {
  sessionManager?: { getSessionName?: () => unknown }
  setInterval?: (fn: () => void, ms: number) => unknown
}
type Api = {
  on: (event: string, handler: (event: unknown, ctx: Ctx) => void) => void
}

export default function (pi: Api) {
  const handle = process.env.ORCA_TERMINAL_HANDLE
  if (!handle) return

  let lastTitle: string | undefined

  const sync = (ctx: Ctx) => {
    const name = ctx.sessionManager?.getSessionName?.()
    const title = typeof name === "string" ? name.trim() : ""
    if (title === lastTitle) return
    lastTitle = title
    try {
      Bun.spawn([ORCA_BIN, "terminal", "rename", "--terminal", handle, "--title", title], {
        stdout: "ignore",
        stderr: "ignore",
      })
    } catch {}
  }

  // Why: task subagents load a fresh copy of every extension in the same process and
  // inherit ORCA_TERMINAL_HANDLE, so without an owner they rename the tab to the
  // subagent's (empty) session name. The first live instance owns the tab.
  const owner = Symbol.for("orca.title-sync.owner")
  const self = {}
  const g = globalThis as Record<symbol, unknown>

  pi.on("session_start", (_e, ctx) => {
    g[owner] ??= self
    if (g[owner] !== self) return
    sync(ctx)
    ctx.setInterval?.(() => g[owner] === self && sync(ctx), POLL_MS)
  })
  pi.on("session_switch", (_e, ctx) => g[owner] === self && sync(ctx))
  pi.on("agent_end", (_e, ctx) => g[owner] === self && sync(ctx))
  pi.on("session_shutdown", () => {
    if (g[owner] === self) delete g[owner]
  })
}
