import { setTimeout as delay } from "node:timers/promises";
import { inspectJob } from "./client.ts";

export const TERMINAL = new Set(["completed", "failed", "cancelled", "interrupted", "expired"]);
export function progressText(job: any): string {
	const p = job.progress || {};
	const count = typeof p.completed === "number" && typeof p.total === "number" ? ` ${p.completed}/${p.total}` : "";
	return `${job.title || job.kind || job.job_id}: ${job.state}${p.stage ? ` (${p.stage}${count})` : ""}${job.monitor_stale ? " [heartbeat stale]" : ""}`;
}

export async function waitForJob(id: string, seconds: number, signal?: AbortSignal,
	onUpdate?: (job: any) => void, inspect = inspectJob) {
	if (!Number.isFinite(seconds) || seconds < 0 || seconds > 60) throw new Error("wait_seconds must be between 0 and 60");
	const deadline = Date.now() + seconds * 1000;
	while (true) {
		signal?.throwIfAborted();
		const job = await inspect(id, false, signal);
		onUpdate?.(job);
		if (TERMINAL.has(job.state) || Date.now() >= deadline) return job;
		await delay(Math.min(1000, deadline - Date.now()), undefined, { signal });
	}
}
