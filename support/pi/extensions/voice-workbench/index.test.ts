import assert from "node:assert/strict";
import test from "node:test";
import workbench from "./index.ts";
import { jobPath, startJob, inspectJob, serviceRequest } from "./jobs.ts";

test("reasoning agent receives managed voice tools and orchestration instructions", async () => {
	const tools: any[] = [];
	let hook: any;
	workbench({ registerTool(t: any) { tools.push(t); }, on(_event: string, handler: any) { hook = handler; } } as any);
	assert.deepEqual(tools.map(tool => tool.name), ["media_download", "media_extract", "voice_analyze", "voice_dataset", "voice_train", "voice_render", "voice_evaluate", "voice_job", "audio_stitch", "voice_library"]);
	const response = await hook({ systemPrompt: "Original instructions" });
	assert.ok(response.systemPrompt.startsWith("Original instructions"));
	assert.match(response.systemPrompt, /untrusted source content/);
	assert.match(response.systemPrompt, /never stop other model services/);
	assert.throws(() => jobPath("../../other"), /Invalid/);
});

test("jobs use authenticated service submission, status and cancellation", async () => {
	const { mkdtemp, writeFile, rm } = await import("node:fs/promises");
	const { tmpdir } = await import("node:os");
	const { join } = await import("node:path");
	const directory = await mkdtemp(join(tmpdir(), "voice-client-test-"));
	const token = join(directory, "token");
	await writeFile(token, "test-secret");
	const priorToken = process.env.LM_VOICE_JOBS_TOKEN_FILE;
	const priorFetch = globalThis.fetch;
	process.env.LM_VOICE_JOBS_TOKEN_FILE = token;
	const calls: any[] = [];
	globalThis.fetch = async (url, options) => {
		calls.push({ url: String(url), ...options });
		return new Response(JSON.stringify({ job_id: "job-test", state: "queued" }), { status: 202 });
	};
	try {
		assert.equal((await startJob({ kind: "render", voice: "one", text: "Hello" })).state, "queued");
		await inspectJob("job-test");
		await inspectJob("job-test", true);
		assert.equal(calls[0].headers.Authorization, "Bearer test-secret");
		assert.equal(calls[0].method, "POST");
		assert.match(calls[1].url, /\/jobs\/job-test$/);
		assert.match(calls[2].url, /\/cancel$/);
		globalThis.fetch = async () => new Response(JSON.stringify({ error: "queue full" }), { status: 400 });
		await assert.rejects(serviceRequest("/jobs", {}), /queue full/);
	} finally {
		globalThis.fetch = priorFetch;
		if (priorToken === undefined) delete process.env.LM_VOICE_JOBS_TOKEN_FILE;
		else process.env.LM_VOICE_JOBS_TOKEN_FILE = priorToken;
		await rm(directory, { recursive: true, force: true });
	}
});
