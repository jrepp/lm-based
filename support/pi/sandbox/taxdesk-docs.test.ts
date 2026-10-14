import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { checkFilePath, EXIT, main, prepareArgs } from "./taxdesk-docs.ts";

test("prepareArgs resolves --out against the cwd and turns --body into --stdin", () => {
	assert.deepEqual(prepareArgs(["table", "batch", "7", "--out", "rows.ndjson"], "/sandbox/ws"), {
		argv: ["table", "batch", "7", "--out", "/sandbox/ws/rows.ndjson"],
		outputs: [{ flag: "out", path: "/sandbox/ws/rows.ndjson" }],
		bodyFile: undefined,
		readStdin: false,
	});
	const body = prepareArgs(["propose", "12", "--model=qwen", "--body=p.json"], "/w");
	assert.deepEqual(body.argv, ["propose", "12", "--model=qwen", "--stdin"]);
	assert.equal(body.bodyFile, "/w/p.json");
	assert.throws(() => prepareArgs(["propose", "1", "--stdin", "--body", "x"], "/w"), /either --stdin or --body/);
	assert.throws(() => prepareArgs(["get", "1", "--out"], "/w"), /needs a value/);
});

test("checkFilePath only accepts requested outputs", () => {
	const outputs = [{ flag: "out", path: "/w/files" }];
	assert.ok(checkFilePath("/w/files", outputs));
	assert.ok(checkFilePath("/w/files/12.pdf", outputs));
	assert.ok(!checkFilePath("/w/files-other/12.pdf", outputs));
	assert.ok(!checkFilePath("/w/files/../escape", outputs));
	assert.ok(!checkFilePath("relative", outputs));
});

async function withBroker(
	handler: (request: any, auth: string | undefined) => { status?: number; body: any },
	run: (dir: string, configPath: string) => Promise<void>,
) {
	const dir = await mkdtemp(path.join(tmpdir(), "taxdesk-shim-"));
	const server = createServer(async (req, res) => {
		const chunks: Buffer[] = [];
		for await (const chunk of req) chunks.push(chunk as Buffer);
		const { status = 200, body } = handler(JSON.parse(Buffer.concat(chunks).toString() || "{}"), req.headers.authorization);
		res.writeHead(status, { "Content-Type": "application/json" });
		res.end(JSON.stringify(body));
	});
	await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
	const port = (server.address() as any).port;
	const configPath = path.join(dir, "broker.json");
	await writeFile(configPath, JSON.stringify({ url: `http://127.0.0.1:${port}`, token: "t0ken" }));
	try {
		await run(dir, configPath);
	} finally {
		server.close();
		await rm(dir, { recursive: true, force: true });
	}
}

test("main forwards argv, sends --body as stdin, and writes returned files mode 600", async () => {
	let seen: any;
	await withBroker(
		(request, auth) => {
			seen = { request, auth };
			if (!request.argv.includes("--out")) return { body: { exit: 0, stdout: "{}\n", files: [] } };
			const out = request.argv[request.argv.indexOf("--out") + 1];
			return {
				body: {
					exit: 0,
					stdout: JSON.stringify({ path: `${out}/12.pdf` }),
					stderr: "",
					files: [{ path: `${out}/12.pdf`, data: Buffer.from("%PDF").toString("base64") }],
				},
			};
		},
		async (dir, configPath) => {
			const code = await main(["get", "12", "--out", "files"], { TAXDESK_BROKER_CONFIG: configPath }, dir);
			assert.equal(code, 0);
			assert.equal(seen.auth, "Bearer t0ken");
			assert.deepEqual(seen.request.argv, ["get", "12", "--out", path.join(dir, "files")]);
			const written = path.join(dir, "files", "12.pdf");
			assert.equal(await readFile(written, "utf8"), "%PDF");
			assert.equal((await stat(written)).mode & 0o777, 0o600);

			await writeFile(path.join(dir, "p.json"), '{"kind":"receipt"}');
			assert.equal(await main(["propose", "12", "--model", "m", "--body", "p.json"], { TAXDESK_BROKER_CONFIG: configPath }, dir), 0);
			assert.deepEqual(seen.request.argv, ["propose", "12", "--model", "m", "--stdin"]);
			assert.equal(Buffer.from(seen.request.stdin, "base64").toString(), '{"kind":"receipt"}');
		},
	);
});

test("main refuses files outside the requested output and relays broker errors", async () => {
	let reply: { status?: number; body: any } = {
		body: { exit: 0, stdout: "", files: [{ path: "/etc/passwd", data: "" }] },
	};
	await withBroker(
		() => reply,
		async (dir, configPath) => {
			const env = { TAXDESK_BROKER_CONFIG: configPath };
			assert.equal(await main(["table", "batch", "1", "--out", "x.ndjson"], env, dir), EXIT.other);
			reply = { status: 400, body: { error: "unknown or disallowed command", exit: 2 } };
			assert.equal(await main(["login"], env, dir), EXIT.usage);
		},
	);
});

test("main reports an unavailable broker without a config", async () => {
	assert.equal(await main(["whoami"], {}, "/"), EXIT.unavailable);
});
