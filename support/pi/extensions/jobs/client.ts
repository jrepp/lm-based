import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../../../", import.meta.url));
export const JOBS = path.join(ROOT, ".runtime", "voice-workbench", "jobs");

export async function serviceRequest(route: string, body?: unknown, signal?: AbortSignal): Promise<any> {
	const base = process.env.LM_JOBS_URL || process.env.LM_VOICE_JOBS_URL || "http://127.0.0.1:8093";
	const tokenPath = process.env.LM_JOBS_TOKEN_FILE || process.env.LM_VOICE_JOBS_TOKEN_FILE || path.join(ROOT, ".runtime", "voice-workbench", "token");
	let token: string;
	try { token = (await readFile(tokenPath, "utf8")).trim(); }
	catch { throw new Error("Job service is not configured. Start it with ./up jobs --add."); }
	let response: Response;
	try {
		response = await fetch(base.replace(/\/+$/, "") + route, {
			method: body === undefined ? "GET" : "POST",
			headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
			body: body === undefined ? undefined : JSON.stringify(body),
			signal: AbortSignal.any([...(signal ? [signal] : []), AbortSignal.timeout(10_000)]),
		});
	} catch (error) {
		signal?.throwIfAborted();
		throw new Error(`Job service unavailable; use ./up jobs --add. ${String(error)}`);
	}
	const result = await response.json();
	if (!response.ok) throw new Error(result.error || `Job service HTTP ${response.status}`);
	return result;
}

export function jobPath(id: string): string {
	if (!/^job-[a-zA-Z0-9_-]+$/.test(id)) throw new Error("Invalid job ID");
	return path.join(JOBS, id);
}

export async function startJob(request: Record<string, unknown>, signal?: AbortSignal) {
	return serviceRequest("/jobs", request, signal);
}

export async function inspectJob(id: string, cancel = false, signal?: AbortSignal) {
	jobPath(id);
	return serviceRequest(`/jobs/${id}${cancel ? "/cancel" : ""}`, cancel ? {} : undefined, signal);
}
