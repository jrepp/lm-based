/**
 * taxdesk-docs inside the OpenShell sandbox: forwards each call to the host broker.
 *
 * The real CLI is a macOS binary that needs the login Keychain and HTTPS to the Tax
 * Desk host, so it cannot run in the Linux microVM. `pi-local --sandbox` starts a broker
 * on the host (lm_launcher/taxdesk_broker.py) reachable only at the sandbox gateway,
 * and puts this shim on PATH as `taxdesk-docs`. The agent's calls look local:
 *
 *   - arguments go to the broker, which validates them against its allowlist
 *   - `--out <path>` is resolved here; the broker streams the bytes back and they are
 *     written here, inside the sandbox, with mode 600
 *   - `--body <file>` is read here and sent as stdin with `--stdin`
 *   - stdout, stderr and the exit code are the CLI's own
 *
 * The broker config (URL + per-launch token, never the Tax Desk credential) comes from
 * $TAXDESK_BROKER_CONFIG.
 */

import { mkdir, readFile, writeFile, chmod } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const EXIT = { ok: 0, other: 1, usage: 2, auth: 3, notFound: 4, refused: 5, unavailable: 6 } as const;
const REQUEST_TIMEOUT_MS = 11 * 60 * 1000; // a little over the broker's own call timeout

export interface Output {
	flag: string;
	path: string; // absolute sandbox path
}

export interface Prepared {
	argv: string[];
	outputs: Output[];
	bodyFile?: string; // --body <file>, read and sent as stdin
	readStdin: boolean;
}

export class ShimError extends Error {
	exit: number;
	hint?: string;
	constructor(message: string, exit: number, hint?: string) {
		super(message);
		this.exit = exit;
		this.hint = hint;
	}
}

/** Rewrite the agent's argv for the broker: absolute --out paths, --body -> --stdin. */
export function prepareArgs(argv: string[], cwd: string): Prepared {
	const out: string[] = [];
	const outputs: Output[] = [];
	let bodyFile: string | undefined;
	let readStdin = false;
	for (let i = 0; i < argv.length; i++) {
		const arg = argv[i];
		if (!arg.startsWith("--")) {
			out.push(arg);
			continue;
		}
		const eq = arg.indexOf("=");
		const name = eq >= 0 ? arg.slice(2, eq) : arg.slice(2);
		const takesValue = name === "out" || name === "body";
		if (!takesValue) {
			if (name === "stdin") readStdin = true;
			out.push(arg);
			continue;
		}
		let value: string | undefined;
		if (eq >= 0) value = arg.slice(eq + 1);
		else if (i + 1 < argv.length && !argv[i + 1].startsWith("--")) value = argv[++i];
		if (!value) throw new ShimError(`--${name} needs a value`, EXIT.usage);
		if (name === "body") {
			if (bodyFile !== undefined) throw new ShimError("--body given twice", EXIT.usage);
			bodyFile = path.resolve(cwd, value);
			continue;
		}
		const resolved = path.resolve(cwd, value);
		outputs.push({ flag: name, path: resolved });
		out.push("--out", resolved);
	}
	if (bodyFile !== undefined) {
		if (readStdin) throw new ShimError("give either --stdin or --body, not both", EXIT.usage);
		out.push("--stdin");
	}
	return { argv: out, outputs, bodyFile, readStdin };
}

/** A returned file must be one of the requested outputs (or inside a requested --out folder). */
export function checkFilePath(file: string, outputs: Output[]): boolean {
	const normalized = path.normalize(file);
	if (normalized !== file || !path.isAbsolute(file)) return false;
	return outputs.some((output) => file === output.path || file.startsWith(output.path + path.sep));
}

async function readAll(stream: NodeJS.ReadableStream): Promise<Buffer> {
	const chunks: Buffer[] = [];
	for await (const chunk of stream) chunks.push(Buffer.from(chunk as Buffer));
	return Buffer.concat(chunks);
}

function fail(error: ShimError): number {
	process.stdout.write(
		`${JSON.stringify({ error: error.message, ...(error.hint ? { hint: error.hint } : {}), exit: error.exit }, null, 2)}\n`,
	);
	return error.exit;
}

export async function main(argv: string[], env: NodeJS.ProcessEnv = process.env, cwd = process.cwd()): Promise<number> {
	try {
		const configPath = env.TAXDESK_BROKER_CONFIG;
		let config: { url: string; token: string };
		try {
			if (!configPath) throw new Error("unset");
			config = JSON.parse(await readFile(configPath, "utf8"));
		} catch {
			throw new ShimError(
				"taxdesk-docs is not available in this sandbox.",
				EXIT.unavailable,
				"Ask the person to start pi-local --sandbox where the host taxdesk-docs is installed (TAXDESK_DOCS_BIN).",
			);
		}
		const prepared = prepareArgs(argv, cwd);
		let stdin: Buffer | undefined;
		if (prepared.bodyFile) stdin = await readFile(prepared.bodyFile);
		else if (prepared.readStdin) stdin = await readAll(process.stdin);

		let response: Response;
		try {
			response = await fetch(`${config.url.replace(/\/+$/, "")}/v1/run`, {
				method: "POST",
				headers: { Authorization: `Bearer ${config.token}`, "Content-Type": "application/json" },
				body: JSON.stringify({ argv: prepared.argv, ...(stdin ? { stdin: stdin.toString("base64") } : {}) }),
				signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
			});
		} catch (error) {
			throw new ShimError(
				`the host taxdesk-docs broker is unreachable (${(error as Error).name})`,
				EXIT.unavailable,
				"The broker runs only while pi-local --sandbox is running; report this to the person.",
			);
		}
		const payload: any = await response.json().catch(() => ({}));
		if (!response.ok) {
			throw new ShimError(String(payload.error ?? `broker returned HTTP ${response.status}`), Number(payload.exit ?? EXIT.other), payload.hint);
		}
		for (const file of payload.files ?? []) {
			if (typeof file?.path !== "string" || !checkFilePath(file.path, prepared.outputs)) {
				throw new ShimError("the broker returned a file outside the requested --out path", EXIT.other);
			}
			await mkdir(path.dirname(file.path), { recursive: true, mode: 0o700 });
			await writeFile(file.path, Buffer.from(String(file.data ?? ""), "base64"), { mode: 0o600 });
			await chmod(file.path, 0o600);
		}
		if (payload.stdout) process.stdout.write(payload.stdout);
		if (payload.stderr) process.stderr.write(payload.stderr);
		return Number.isInteger(payload.exit) ? payload.exit : EXIT.other;
	} catch (error) {
		if (error instanceof ShimError) return fail(error);
		return fail(new ShimError((error as Error).message, EXIT.other));
	}
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
	main(process.argv.slice(2)).then((code) => {
		process.exitCode = code;
	});
}
