/**
 * Pure helpers for the run-record extension (no Pi imports; `node --test` friendly).
 */

import { createHash } from "node:crypto";
import path from "node:path";

/** Per-entry cap: a trajectory must stay readable, and the digest still proves what was cut. */
export const MAX_ENTRY_CHARS = 256 * 1024;

const SYSTEM_TEMP_ROOTS = ["/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp", "/var/folders", "/private/var/folders"];

export interface Clipped {
	text: string;
	chars: number;
	sha256: string;
	truncated?: true;
}

export function clip(text: string, limit = MAX_ENTRY_CHARS): Clipped {
	const sha256 = createHash("sha256").update(text).digest("hex");
	if (text.length <= limit) return { text, chars: text.length, sha256 };
	return { text: text.slice(0, limit), chars: text.length, sha256, truncated: true };
}

/** Text parts of a message or tool result content (string or content-part array). */
export function textOf(content: unknown): string {
	if (typeof content === "string") return content;
	if (!Array.isArray(content)) return "";
	return content
		.map((part: any) => {
			if (part?.type === "text") return String(part.text ?? "");
			if (part?.type === "image") return "[image]";
			return "";
		})
		.filter(Boolean)
		.join("\n");
}

/** Tool calls an assistant message made, as {id, name} (arguments are logged at tool_call). */
export function toolCallsOf(content: unknown): { id: string; name: string }[] {
	if (!Array.isArray(content)) return [];
	return content
		.filter((part: any) => part?.type === "toolCall")
		.map((part: any) => ({ id: String(part.id ?? ""), name: String(part.name ?? "") }));
}

/**
 * True when `file` (resolved against cwd) is under a shared system temp folder. The run's own
 * TMPDIR and the workspace itself (which may live in a temp folder) are never flagged.
 */
export function isSystemTemp(file: string, cwd: string, runTmp?: string): boolean {
	const resolved = path.resolve(cwd, file);
	const under = (root: string) => resolved === root || resolved.startsWith(root + path.sep);
	if ((runTmp && under(runTmp)) || under(path.resolve(cwd))) return false;
	return SYSTEM_TEMP_ROOTS.some(under);
}

export function runPromptNote(runDir: string, tmp: string): string {
	return [
		"## Run files",
		`This run has a private scratch folder: ${tmp} (also $TMPDIR). Put every intermediate file there:`,
		"downloads, NDJSON/CSV exports, decision results, drafts. It is deleted when the session ends.",
		"Do not write scratch files to /tmp or into the project tree, and do not write notes or work logs",
		"into the project unless the person asks for a file there; report results in your reply instead.",
		"Every tool call and its output is recorded, so report only numbers and ids that tool output shows.",
		`(run folder: ${runDir})`,
	].join("\n");
}
