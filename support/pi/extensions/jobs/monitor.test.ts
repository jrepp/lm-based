import assert from "node:assert/strict";
import test from "node:test";
import jobs from "./index.ts";
import { progressText, waitForJob } from "./monitor.ts";

test("general tools and lifecycle hooks register", () => {
	const tools: string[] = [], events: string[] = [];
	jobs({ registerTool(t: any) { tools.push(t.name); }, on(e: string) { events.push(e); } } as any);
	assert.deepEqual(tools, ["job_start", "job_status", "jobs"]);
	assert.ok(events.includes("session_shutdown"));
});

test("wait streams queued/running/terminal snapshots and returns failure", async () => {
	const states = ["queued", "running", "failed"];
	const updates: string[] = [];
	const result = await waitForJob("job-test", 5, undefined, job => updates.push(job.state),
		async () => ({ state: states.shift() }));
	assert.deepEqual(updates, ["queued", "running", "failed"]);
	assert.equal(result.state, "failed");
});

test("zero wait returns immediately and abort does not cancel underlying job", async () => {
	let calls = 0;
	const inspect = async (_id: string, cancel: boolean) => { assert.equal(cancel, false); calls++; return { state: "running" }; };
	assert.equal((await waitForJob("job-test", 0, undefined, undefined, inspect)).state, "running");
	const controller = new AbortController();
	controller.abort();
	await assert.rejects(waitForJob("job-test", 60, controller.signal, undefined, inspect), { name: "AbortError" });
	assert.equal(calls, 1);
	await assert.rejects(waitForJob("job-test", 61), /between 0 and 60/);
});

test("progress shows stage counts and stale monitor separately", () => {
	assert.match(progressText({ title: "Build", state: "running", progress: { stage: "compile", completed: 2, total: 3 }, monitor_stale: true }), /Build: running \(compile 2\/3\).*heartbeat stale/);
});
