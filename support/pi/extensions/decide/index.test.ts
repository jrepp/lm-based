import assert from "node:assert/strict";
import { mkdtemp, writeFile, readFile, rm, symlink, link, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import decide from "./index.ts";

async function fixture(run: (f: any) => Promise<void>) {
	const dir = await mkdtemp(path.join(tmpdir(), "decide-test-"));
	try {
		const input = path.join(dir, "input.jsonl");
		const output = path.join(dir, "results.ndjson");
		const original = '{"text":"keep this source"}\n';
		await writeFile(input, original);
		let tool: any;
		decide({ registerTool(t: any) { tool = t; }, registerProvider() {} } as any);
		const model = { id: "test-classifier" };
		let calls = 0;
		const ctx = { cwd: dir, modelRegistry: {
			getModelsOfType: () => [model],
			classify: async () => {
				calls++;
				return { stopReason: "stop", answers: { ok: { type: "bool", probability: 0.9 } } };
			},
		} };
		const execute = (overrides = {}, signal?: AbortSignal) => tool.execute("test", {
			path: input, output, questions: { ok: { type: "bool", instructions: "Is this okay?" } },
			...overrides,
		}, signal, undefined, ctx);
		await run({ dir, input, output, original, ctx, execute, calls: () => calls });
	} finally { await rm(dir, { recursive: true, force: true }); }
}

for (const alias of ["same", "symlink", "hardlink"]) {
	test(`reject output pointing at source via ${alias}`, () => fixture(async (f) => {
		const output = alias === "same" ? f.input : f.output;
		if (alias === "symlink") await symlink(f.input, output);
		if (alias === "hardlink") await link(f.input, output);
		await assert.rejects(f.execute({ output }), /source|input/i);
		assert.equal(await readFile(f.input, "utf8"), f.original);
		assert.equal(f.calls(), 0);
	}));
}

test("pre-aborted invocation preserves previous output", () => fixture(async (f) => {
	await writeFile(f.output, "previous results\n");
	await assert.rejects(f.execute({}, AbortSignal.abort()), { name: "AbortError" });
	assert.equal(await readFile(f.output, "utf8"), "previous results\n");
	assert.equal(f.calls(), 0);
}));

test("mid-run cancellation never publishes partial results", () => fixture(async (f) => {
	await writeFile(f.output, "previous results\n");
	await writeFile(f.input, f.original.repeat(3));
	const controller = new AbortController();
	f.ctx.modelRegistry.classify = async () => {
		controller.abort();
		return { stopReason: "stop", answers: { ok: { type: "bool", probability: 0.9 } } };
	};
	await assert.rejects(f.execute({ concurrency: 1 }, controller.signal), { name: "AbortError" });
	assert.equal(await readFile(f.output, "utf8"), "previous results\n");
	assert.deepEqual((await readdir(f.dir)).sort(), ["input.jsonl", "results.ndjson"]);
}));

test("successful run replaces output and preserves source", () => fixture(async (f) => {
	await writeFile(f.output, "previous results\n");
	const result = await f.execute();
	assert.equal(result.details.classified, 1);
	assert.equal(JSON.parse(await readFile(f.output, "utf8")).answers.ok.probability, 0.9);
	assert.equal(await readFile(f.input, "utf8"), f.original);
	assert.deepEqual((await readdir(f.dir)).sort(), ["input.jsonl", "results.ndjson"]);
}));
