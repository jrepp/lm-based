/**
 * Load every repo extension against the pinned Pi packages with a fake ExtensionAPI.
 *
 * Pi skips an extension that fails to load without failing the command, so a Pi
 * bump that moves an import (e.g. @earendil-works/pi-ai/api/typesafe-system-one)
 * or renames an API would otherwise surface only in a live session. Needs
 * `just pi-install` first:
 *   node --test support/pi/extensions/*.test.ts support/pi/extensions/*\/*.test.ts
 */

import assert from "node:assert/strict";
import { readdirSync, existsSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

interface Registered {
	tools: string[];
	commands: string[];
	providers: string[];
	events: string[];
}

function fakePi(): { pi: any; registered: Registered } {
	const registered: Registered = { tools: [], commands: [], providers: [], events: [] };
	const pi = {
		registerTool: (tool: { name: string }) => registered.tools.push(tool.name),
		registerCommand: (name: string) => registered.commands.push(name),
		registerProvider: (name: string) => registered.providers.push(name),
		on: (event: string) => registered.events.push(event),
		setModel: async () => true,
	};
	return { pi, registered };
}

async function load(name: string, env: Record<string, string> = {}): Promise<Registered> {
	const saved = { ...process.env };
	Object.assign(process.env, env);
	try {
		const module = await import(path.join(here, name, "index.ts"));
		assert.equal(typeof module.default, "function", `${name}: default export must be the extension factory`);
		const { pi, registered } = fakePi();
		await module.default(pi);
		return registered;
	} finally {
		process.env = saved;
	}
}

const extensions = readdirSync(here, { withFileTypes: true })
	.filter((entry) => entry.isDirectory() && existsSync(path.join(here, entry.name, "index.ts")))
	.map((entry) => entry.name);

for (const name of extensions) {
	test(`${name} loads against the pinned Pi packages`, async () => {
		await load(name);
	});
}

test("llama-swap registers /swap and session hooks when routed through llama-swap", async () => {
	const registered = await load("llama-swap", { LM_BASED_SWAP_URL: "http://127.0.0.1:9" });
	assert.deepEqual(registered.commands, ["swap"]);
	for (const event of ["session_start", "session_shutdown", "model_select"]) assert.ok(registered.events.includes(event), event);
});

test("decide registers decide_records and the classifier provider", async () => {
	const classifier = { id: "kev", name: "kev", api: "typesafe-system-one", baseUrl: "http://127.0.0.1:9/v1" };
	const registered = await load("decide", { LM_BASED_CLASSIFIERS: JSON.stringify([classifier]) });
	assert.deepEqual(registered.tools, ["decide_records"]);
	assert.deepEqual(registered.providers, ["lm-based-decision"]);
});
