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

async function tool(dir: string, classify: (ctx: any) => any) {
	let registered: any;
	decide({ registerTool(t: any) { registered = t; }, registerProvider() {} } as any);
	const requests: any[] = [];
	const ctx = { cwd: dir, modelRegistry: {
		getModelsOfType: () => [{ id: "kev" }],
		classify: async (_model: any, request: any) => { requests.push(request); return classify(request); },
	} };
	return { run: (params: any) => registered.execute("t", params, undefined, undefined, ctx), requests };
}

test("stages run in one call: filter, abstain, examples_from, per-stage summary", async () => {
	const dir = await mkdtemp(path.join(tmpdir(), "decide-stages-"));
	try {
		const rows = ["own transfer", "pharmacy", "mystery"].map((payee, i) => JSON.stringify({ row: `r${i}`, payee }));
		await writeFile(path.join(dir, "rows.ndjson"), rows.join("\n") + "\n");
		await writeFile(path.join(dir, "labeled.ndjson"), [
			JSON.stringify({ payee: "cvs", category: "medical" }),
			JSON.stringify({ payee: "unicef", category: "charity" }),
		].join("\n"));
		const { run, requests } = await tool(dir, (request) => {
			const payee = request.state.record?.payee ?? request.state.payee;
			if (request.questions.tax_relevant) return { stopReason: "stop", answers: { tax_relevant: { type: "bool", probability: payee === "own transfer" ? 0.1 : 0.9 } } };
			const unsure = payee === "mystery";
			return { stopReason: "stop", answers: { category: {
				type: "choice", choice: unsure ? "unsure" : "medical", confidence: 0.4,
				probabilities: unsure ? { medical: 0.3, charity: 0.2, unsure: 0.5 } : { medical: 0.8, charity: 0.1, unsure: 0.1 },
			} } };
		});
		const result = await run({
			path: "rows.ndjson",
			id_field: "row",
			fields: ["payee"],
			stages: [
				{ id: "relevance", questions: { tax_relevant: { type: "bool", instructions: "Tax-relevant household payment?" } } },
				{
					id: "category",
					when: { stage: "relevance", question: "tax_relevant", is: true },
					questions: { category: { type: "choice", instructions: "Which category?", criteria: { medical: "health", charity: "donation" } } },
					abstain: { choice: "unsure" },
					examples_from: { path: "labeled.ndjson", answer_fields: { category: "category" } },
				},
			],
		});
		const details = result.details;
		assert.deepEqual(details.outcomes, { complete: 1, filtered: 1, abstained: 1, error: 0 });
		assert.equal(details.classifier_calls, 5);
		assert.deepEqual(details.examples, { category: 2 });
		const categoryRequest = requests.find((r) => r.questions.category);
		assert.deepEqual(categoryRequest.state.labeled_examples.map((e: any) => e.answers.category), ["medical", "charity"]);
		assert.ok(categoryRequest.questions.category.criteria.unsure);
		const lines = (await readFile(path.join(dir, "rows.ndjson.decisions.ndjson"), "utf8")).trim().split("\n").map((l) => JSON.parse(l));
		assert.deepEqual(lines.map((l) => [l.id, l.outcome, l.stopped_at ?? null]), [
			["r0", "filtered", "category"],
			["r1", "complete", null],
			["r2", "abstained", "category"],
		]);
		assert.equal(lines[1].stages.category.answers.category.margin, 0.7);
		assert.equal(lines[1].stages.category.answers.category.runner_up, "charity");
	} finally { await rm(dir, { recursive: true, force: true }); }
});

test("single-stage abstain keeps the original layout and reports unsure answers", async () => {
	const dir = await mkdtemp(path.join(tmpdir(), "decide-abstain-"));
	try {
		await writeFile(path.join(dir, "in.csv"), "id,text\n1,a\n2,b\n");
		const { run } = await tool(dir, (request) => ({ stopReason: "stop", answers: { topic: {
			type: "choice", choice: request.state.text === "a" ? "bug" : "unsure", confidence: 0.5,
			probabilities: request.state.text === "a" ? { bug: 0.9, feature: 0.05, unsure: 0.05 } : { bug: 0.2, feature: 0.2, unsure: 0.6 },
		} } }));
		const questions = { topic: { type: "choice", instructions: "Topic?", criteria: { bug: "broken", feature: "request" } } };
		const result = await run({ path: "in.csv", id_field: "id", questions, abstain: { choice: "unsure" }, output: "out.csv" });
		assert.equal(result.details.abstained, 1);
		assert.equal(result.details.classified, 2);
		const csv = (await readFile(path.join(dir, "out.csv"), "utf8")).split("\n");
		assert.equal(csv[0], "index,line,id,topic,topic_confidence,error,abstained");
		assert.equal(csv[2], "1,3,2,unsure,0.5,,topic");
		await assert.rejects(run({ path: "in.csv", questions, stages: [{ id: "a", questions }] }), /either `questions` or `stages`/);
		await assert.rejects(run({ path: "in.csv" }), /give `questions`/);
		await assert.rejects(
			run({ path: "in.csv", stages: [{ id: "a", questions }, { id: "b", questions, when: { stage: "c", question: "topic" } }] }),
			/not an earlier stage/,
		);
	} finally { await rm(dir, { recursive: true, force: true }); }
});
