import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import runRecord from "./index.ts";
import { clip, isSystemTemp, textOf, toolCallsOf } from "./record.ts";

test("clip keeps short text and marks long text with its full length and digest", () => {
	assert.deepEqual(Object.keys(clip("abc")).sort(), ["chars", "sha256", "text"]);
	const long = clip("x".repeat(10), 4);
	assert.equal(long.text, "xxxx");
	assert.equal(long.chars, 10);
	assert.equal(long.truncated, true);
	assert.equal(long.sha256, clip("x".repeat(10)).sha256);
});

test("textOf and toolCallsOf read message content", () => {
	assert.equal(textOf("plain"), "plain");
	assert.equal(textOf([{ type: "text", text: "a" }, { type: "thinking", thinking: "t" }, { type: "image" }]), "a\n[image]");
	assert.deepEqual(toolCallsOf([{ type: "toolCall", id: "1", name: "bash", arguments: {} }, { type: "text" }]), [
		{ id: "1", name: "bash" },
	]);
});

test("isSystemTemp flags shared temp folders but not the run's TMPDIR or the workspace", () => {
	assert.ok(isSystemTemp("/tmp/rows.ndjson", "/w"));
	assert.ok(isSystemTemp("/private/var/folders/x/T/a", "/w"));
	assert.ok(isSystemTemp("../../tmp/a", "/w/b"));
	assert.ok(!isSystemTemp("/tmp/run/tmp/a", "/w", "/tmp/run/tmp"));
	assert.ok(!isSystemTemp("out/a.csv", "/w"));
	assert.ok(!isSystemTemp("/tmpfoo/a", "/w"));
});

test("records the trajectory and blocks writes to /tmp", async () => {
	const dir = await mkdtemp(path.join(tmpdir(), "run-record-"));
	const saved = { ...process.env };
	const handlers = new Map<string, ((event: any, ctx: any) => any)[]>();
	try {
		const trajectory = path.join(dir, "records", "trajectory.jsonl");
		Object.assign(process.env, {
			LM_BASED_RUN_DIR: path.join(dir, "run"),
			LM_BASED_TRAJECTORY: trajectory,
			LM_BASED_RUN_ID: "r1",
			TMPDIR: path.join(dir, "run", "tmp"),
		});
		runRecord({ on: (name: string, handler: any) => handlers.set(name, [...(handlers.get(name) ?? []), handler]) } as any);
		const fire = async (name: string, event: any) => {
			const results = [];
			for (const handler of handlers.get(name) ?? []) results.push(await handler(event, { cwd: dir }));
			return results;
		};

		const [prompt] = await fire("before_agent_start", { systemPrompt: "base" });
		assert.match(prompt.systemPrompt, /^base\n\n## Run files/);
		assert.ok(prompt.systemPrompt.includes(path.join(dir, "run", "tmp")));

		const blocked = await fire("tool_call", { toolName: "write", toolCallId: "c1", input: { path: "/tmp/rows.ndjson" } });
		assert.equal(blocked[0].block, true);
		const allowed = await fire("tool_call", { toolName: "write", toolCallId: "c2", input: { path: "notes.md" } });
		assert.equal(allowed[0], undefined);
		await fire("tool_execution_end", {
			toolCallId: "c2",
			toolName: "write",
			isError: false,
			durationMs: 3,
			result: { content: [{ type: "text", text: "wrote 10 bytes" }] },
		});
		await fire("message_end", { message: { role: "assistant", model: "m", stopReason: "stop", content: [{ type: "text", text: "Classified 512 rows." }] } });

		const entries = (await readFile(trajectory, "utf8")).trim().split("\n").map((line) => JSON.parse(line));
		assert.deepEqual(entries.map((e) => e.type), ["blocked", "tool_call", "tool_call", "tool_result", "assistant"]);
		assert.equal(entries[3].output.text, "wrote 10 bytes");
		assert.equal(entries[4].text.text, "Classified 512 rows.");
		assert.equal((await stat(trajectory)).mode & 0o777, 0o600);
	} finally {
		process.env = saved;
		await rm(dir, { recursive: true, force: true });
	}
});

test("inert without pi-local's run variables", () => {
	const saved = { ...process.env };
	try {
		delete process.env.LM_BASED_RUN_DIR;
		delete process.env.LM_BASED_TRAJECTORY;
		const events: string[] = [];
		runRecord({ on: (name: string) => events.push(name) } as any);
		assert.deepEqual(events, []);
	} finally {
		process.env = saved;
	}
});
