import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import speech, { MODELS, VOICES } from "./index.ts";

test("speech selection routes the selected model, saves WAV, and protects existing output", async () => {
	const directory = await mkdtemp(path.join(tmpdir(), "speech-test-"));
	const originalFetch = globalThis.fetch;
	let tool: any, command: any, request: any;
	try {
		speech({ registerTool(t: any) { tool = t; }, registerCommand(name: string, c: any) { if (name === "speech-model") command = c; } } as any);
		globalThis.fetch = async (_url: any, options: any) => {
			request = JSON.parse(options.body);
			return new Response("WAV fixture", { headers: { "content-type": "audio/wav" } });
		};
		const ctx = { cwd: directory, hasUI: false, ui: { notify() {} } };
		await command.handler(MODELS[1], ctx);
		await writeFile(path.join(directory, "ref.wav"), "reference");
		const params = { text: "Hello", ref_audio: "ref.wav", ref_text: "Reference words", play: false, output: "out.wav" };
		await tool.execute("1", params, undefined, undefined, ctx);
		assert.equal(request.model, MODELS[1]);
		assert.equal(request.voice, undefined);
		assert.equal(request.ref_audio, Buffer.from("reference").toString("base64"));
		assert.equal(request.ref_text, "Reference words");
		assert.equal(await readFile(path.join(directory, "out.wav"), "utf8"), "WAV fixture");
		await assert.rejects(tool.execute("2", params, undefined, undefined, ctx), /EEXIST/);
		await assert.rejects(tool.execute("3", { ...params, model: "unknown" }, undefined, undefined, ctx), /Unknown/);
		await assert.rejects(command.handler("unknown", ctx), /Unknown/);
	} finally { globalThis.fetch = originalFetch; await rm(directory, { recursive: true, force: true }); }
});

test("pre-trained voices are enumerated, selectable, and overridable without contaminating clones", async () => {
	const directory = await mkdtemp(path.join(tmpdir(), "speech-voices-test-"));
	const originalFetch = globalThis.fetch;
	let tool: any, request: any;
	const commands: Record<string, any> = {};
	try {
		speech({ registerTool(t: any) { tool = t; }, registerCommand(name: string, c: any) { commands[name] = c; } } as any);
		assert.deepEqual(tool.parameters.properties.voice.enum, [...VOICES]);
		globalThis.fetch = async (_url: any, options: any) => {
			request = JSON.parse(options.body);
			return new Response("WAV fixture", { headers: { "content-type": "audio/wav" } });
		};
		const ctx = { cwd: directory, hasUI: true, ui: {
			notify() {},
			async select(_title: string, choices: string[]) { assert.deepEqual(choices, [...VOICES]); return "aiden"; },
		} };
		let count = 0;
		const execute = (extra = {}) => tool.execute("test", { text: "Hello", play: false, output: `${count++}.wav`, ...extra }, undefined, undefined, ctx);
		await commands["speech-model"].handler(MODELS[1], ctx);
		await commands["speech-voice"].handler("", ctx);
		await execute();
		assert.equal(request.model, MODELS[0]);
		assert.equal(request.voice, "aiden");
		for (const voice of VOICES) {
			await execute({ voice });
			assert.equal(request.voice, voice);
		}
		await execute();
		assert.equal(request.voice, "aiden", "per-call override must not change selection");
		await commands["speech-voice"].handler("Vivian", ctx);
		await execute();
		assert.equal(request.voice, "vivian");
		await commands["speech-model"].handler(MODELS[1], ctx);
		await execute({ ref_text: "Reference" });
		assert.equal(request.voice, undefined);
		await execute({ voice: "ryan" });
		assert.equal(request.model, MODELS[0]);
		await assert.rejects(execute({ model: MODELS[1], voice: "ryan" }), /cannot be combined/);
		await assert.rejects(execute({ voice: "ryan", ref_audio: "reference.wav" }), /cannot be combined/);
		await assert.rejects(execute({ voice: "unknown" }), /Unknown speech voice/);
		await assert.rejects(commands["speech-voice"].handler("unknown", ctx), /Unknown speech voice/);
	} finally { globalThis.fetch = originalFetch; await rm(directory, { recursive: true, force: true }); }
});

test("dropped WAV becomes a persistent selectable clone and speak routes it through Base", async () => {
	const directory = await mkdtemp(path.join(tmpdir(), "speech-clone-test-"));
	const originalFetch = globalThis.fetch, previousDir = process.env.LM_BASED_VOICES_DIR;
	process.env.LM_BASED_VOICES_DIR = path.join(directory, "voices");
	const tools: Record<string, any> = {}, commands: Record<string, any> = {};
	let request: any;
	try {
		const { wav } = await import("./wav-fixture.ts");
		const reference = wav(process.platform === "darwin" ? 2 : 1);
		const source = path.join(directory, "my recording.wav");
		await writeFile(source, reference);
		speech({ registerTool(t: any) { tools[t.name] = t; }, registerCommand(name: string, c: any) { commands[name] = c; } } as any);
		globalThis.fetch = async (_url: any, options: any) => { request = JSON.parse(options.body); return new Response("WAV fixture", { headers: { "content-type": "audio/wav" } }); };
		const ctx = { cwd: directory, hasUI: true, ui: { notify() {}, async select(_title: string, choices: string[]) { assert.ok(choices.includes("clone:my-voice")); return "clone:my-voice"; } } };
		const params = { name: "my-voice", ref_audio: `'${source}'`, ref_text: "The exact reference words." };
		await tools.clone_voice.execute("save", params, undefined, undefined, ctx);
		assert.deepEqual(await readFile(source), reference, "import preserves the original WAV");
		await assert.rejects(tools.clone_voice.execute("save", params, undefined, undefined, ctx), /EEXIST/);
		await assert.rejects(tools.clone_voice.execute("save", { ...params, name: "bad", ref_text: " " }, undefined, undefined, ctx), /transcript/);
		await assert.rejects(tools.clone_voice.execute("save", { ...params, name: "../bad" }, undefined, undefined, ctx), /Voice name/);
		// Recreate the extension to verify profiles survive a Pi restart.
		speech({ registerTool(t: any) { tools[t.name] = t; }, registerCommand(name: string, c: any) { commands[name] = c; } } as any);
		await commands["speech-voice"].handler("", ctx);
		const speak = (extra = {}) => tools.speak.execute("say", { text: "New words", play: false, output: "cloned.wav", ...extra }, undefined, undefined, ctx);
		const result = await speak();
		assert.equal(request.model, MODELS[1]);
		assert.equal(request.voice, undefined);
		assert.equal(request.ref_text, params.ref_text);
		assert.equal(result.details.cloned_voice, "my-voice");
		assert.ok(request.ref_audio);
		await speak({ cloned_voice: "my-voice", output: "override.wav" });
		await assert.rejects(speak({ cloned_voice: "my-voice", voice: "ryan" }), /cannot be combined/);
		await assert.rejects(speak({ cloned_voice: "my-voice", model: MODELS[0] }), /Base/);
		await commands["speech-voice"].handler("aiden", ctx);
		await speak({ output: "preset.wav" });
		assert.equal(request.voice, "aiden");
		assert.equal(request.ref_audio, undefined);
	} finally {
		globalThis.fetch = originalFetch;
		if (previousDir === undefined) delete process.env.LM_BASED_VOICES_DIR; else process.env.LM_BASED_VOICES_DIR = previousDir;
		await rm(directory, { recursive: true, force: true });
	}
});
