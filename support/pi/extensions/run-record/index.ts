/**
 * run-record: per-run scratch hygiene and a trajectory a person can check a report against.
 *
 * ./pi-local gives each launch a run folder inside the workspace (LM_BASED_RUN_DIR, with
 * TMPDIR=<run>/tmp; deleted on exit unless --keep-run-files) and a trajectory file outside
 * it (LM_BASED_TRAJECTORY, under the gitignored .runtime/pi/runs/<run-id>/). This extension:
 *
 *   - tells the model where scratch files go (system prompt note)
 *   - blocks write/edit tool calls into shared system temp folders (/tmp, /var/folders)
 *   - appends every user prompt, assistant message, tool call (arguments) and tool result
 *     (text, clipped at 256 KiB with the full length and sha256) to the trajectory as JSONL
 *
 * Inert unless pi-local sets those variables.
 */

import { appendFileSync, chmodSync, mkdirSync } from "node:fs";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { clip, isSystemTemp, runPromptNote, textOf, toolCallsOf } from "./record.ts";

export default function runRecord(pi: ExtensionAPI) {
	const runDir = process.env.LM_BASED_RUN_DIR;
	const trajectory = process.env.LM_BASED_TRAJECTORY;
	const runId = process.env.LM_BASED_RUN_ID;
	const tmp = process.env.TMPDIR;
	if (!runDir && !trajectory) return;

	let ready = false;
	const write = (entry: Record<string, unknown>) => {
		if (!trajectory) return;
		try {
			if (!ready) {
				mkdirSync(path.dirname(trajectory), { recursive: true, mode: 0o700 });
				ready = true;
			}
			appendFileSync(trajectory, `${JSON.stringify({ ts: new Date().toISOString(), ...entry })}\n`, { mode: 0o600 });
			chmodSync(trajectory, 0o600);
		} catch {
			// Recording must never break the session.
		}
	};

	pi.on("session_start", async (event, ctx) => {
		write({ type: "session", reason: event.reason, run_id: runId, cwd: ctx.cwd, run_dir: runDir });
	});

	if (runDir && tmp) {
		pi.on("before_agent_start", async (event) => ({
			systemPrompt: `${event.systemPrompt}\n\n${runPromptNote(runDir, tmp)}`,
		}));

		pi.on("tool_call", async (event, ctx) => {
			if (event.toolName !== "write" && event.toolName !== "edit") return;
			const target = (event.input as { path?: unknown }).path;
			if (typeof target === "string" && isSystemTemp(target, ctx.cwd, tmp)) {
				write({ type: "blocked", id: event.toolCallId, tool: event.toolName, path: target });
				return {
					block: true,
					reason: `Shared temp folders are off limits for this run; write scratch files under ${tmp} ($TMPDIR) instead.`,
				};
			}
		});
	}

	pi.on("tool_call", async (event) => {
		write({ type: "tool_call", id: event.toolCallId, tool: event.toolName, input: event.input });
	});

	pi.on("tool_execution_end", async (event) => {
		write({
			type: "tool_result",
			id: event.toolCallId,
			tool: event.toolName,
			is_error: event.isError,
			...(event.durationMs === undefined ? {} : { duration_ms: event.durationMs }),
			output: clip(textOf(event.result?.content)),
		});
	});

	pi.on("message_end", async (event) => {
		const message: any = event.message;
		if (message?.role === "user") {
			write({ type: "user", text: clip(textOf(message.content)) });
		} else if (message?.role === "assistant") {
			const calls = toolCallsOf(message.content);
			write({
				type: "assistant",
				model: message.model,
				stop: message.stopReason,
				text: clip(textOf(message.content)),
				...(calls.length ? { tool_calls: calls } : {}),
			});
		}
	});

	pi.on("session_shutdown", async (event) => {
		write({ type: "shutdown", reason: event.reason });
	});
}
