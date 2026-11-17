import { open, mkdir, readdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const MAX_BYTES = 4 * 1024 * 1024;
export function voicesDirectory(): string {
	return process.env.LM_BASED_VOICES_DIR || fileURLToPath(new URL("../../../../.runtime/voices/", import.meta.url));
}

export function voiceName(name: string): string {
	if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(name)) throw new Error("Voice name must be 1–64 lowercase letters, digits, underscores or hyphens");
	return name;
}

/** Terminal drops often insert a quoted path or backslash-escaped spaces. Never execute it. */
export function droppedPath(value: string, cwd: string): string {
	let result = value.trim();
	if ((result.startsWith('"') && result.endsWith('"')) || (result.startsWith("'") && result.endsWith("'"))) result = result.slice(1, -1);
	else result = result.replace(/\\([\s()'"\\])/g, "$1");
	if (result.startsWith("file://")) result = fileURLToPath(result);
	return path.resolve(cwd, result);
}

async function boundedRead(file: string, limit: number): Promise<Buffer> {
	const source = await open(file, "r");
	try {
		const info = await source.stat();
		if (!info.isFile() || info.size > limit) throw new Error(`Reference must be a regular file no larger than ${limit / 1024 / 1024} MiB`);
		const data = Buffer.alloc(Math.min(info.size + 1, limit + 1));
		let offset = 0;
		while (offset < data.length) {
			const { bytesRead } = await source.read(data, offset, data.length - offset, offset);
			if (!bytesRead) break;
			offset += bytesRead;
		}
		if (offset > limit || offset > info.size) throw new Error("Reference changed while reading; retry with a stable file");
		return data.subarray(0, offset);
	} finally { await source.close(); }
}

export function validateWav(audio: Buffer): number {
	if (audio.length > MAX_BYTES) throw new Error("Reference WAV exceeds 4 MiB");
	if (audio.length < 44 || audio.toString("ascii", 0, 4) !== "RIFF" || audio.toString("ascii", 8, 12) !== "WAVE") throw new Error("Reference is not a WAV file");
	const end = audio.readUInt32LE(4) + 8;
	if (end > audio.length) throw new Error("Truncated WAV file");
	let rate = 0, size = -1;
	for (let offset = 12; offset + 8 <= end;) {
		const id = audio.toString("ascii", offset, offset + 4);
		const length = audio.readUInt32LE(offset + 4);
		const start = offset + 8;
		if (start + length > end) throw new Error("Truncated WAV chunk");
		if (id === "fmt ") {
			if (length < 16 || audio.readUInt16LE(start) !== 1 || audio.readUInt16LE(start + 2) !== 1 || audio.readUInt16LE(start + 14) !== 16) throw new Error("Reference WAV must be mono PCM16");
			rate = audio.readUInt32LE(start + 4);
			if (!rate || audio.readUInt16LE(start + 12) !== 2 || audio.readUInt32LE(start + 8) !== rate * 2) throw new Error("Invalid WAV sample format");
		}
		if (id === "data") size = length;
		offset = start + length + (length % 2);
	}
	const duration = size / (rate * 2);
	if (size < 0 || size % 2 || !Number.isFinite(duration) || duration < 1 || duration > 30) throw new Error("Reference WAV must contain 1–30 seconds of speech");
	return duration;
}

export type SavedVoice = { name: string; ref_text: string; ref_audio: string; duration_seconds: number };

export async function listVoices(): Promise<string[]> {
	try { return (await readdir(voicesDirectory())).filter(name => /^[a-z0-9][a-z0-9_-]{0,63}\.json$/.test(name)).map(name => name.slice(0, -5)).sort(); }
	catch (error: any) { if (error.code === "ENOENT") return []; throw error; }
}

export async function loadVoice(name: string): Promise<SavedVoice> {
	const file = path.join(voicesDirectory(), `${voiceName(name)}.json`);
	const profile = JSON.parse((await boundedRead(file, 6 * 1024 * 1024)).toString("utf8"));
	if (profile.name !== name || typeof profile.ref_text !== "string" || !profile.ref_text.trim() || profile.ref_text.length > 4000 || typeof profile.ref_audio !== "string") throw new Error("Invalid saved voice profile");
	validateWav(Buffer.from(profile.ref_audio, "base64"));
	return profile;
}

export async function saveVoice(name: string, input: string, transcript: string, cwd: string, signal?: AbortSignal): Promise<SavedVoice> {
	voiceName(name);
	if (!transcript.trim() || transcript.length > 4000) throw new Error("Provide the exact reference transcript (1–4000 characters); do not invent it");
	signal?.throwIfAborted();
	const source = droppedPath(input, cwd);
	let audio = await boundedRead(source, 32 * 1024 * 1024);
	let duration: number;
	try { duration = validateWav(audio); }
	catch (error) {
		// Convert WAV encodings such as stereo/float with Apple's native converter.
		if (process.platform !== "darwin" || audio.toString("ascii", 0, 4) !== "RIFF" || audio.toString("ascii", 8, 12) !== "WAVE") throw error;
		const directory = await mkdtemp(path.join(tmpdir(), "pi-voice-import-"));
		try {
			const copy = path.join(directory, "source.wav"), converted = path.join(directory, "mono.wav");
			await writeFile(copy, audio, { mode: 0o600 });
			await promisify(execFile)("/usr/bin/afconvert", ["-f", "WAVE", "-d", "LEI16@24000", "-c", "1", copy, converted], { signal, timeout: 30_000 });
			audio = await boundedRead(converted, MAX_BYTES);
			duration = validateWav(audio);
		} finally { await rm(directory, { recursive: true, force: true }); }
	}
	const profile: SavedVoice = { name, ref_text: transcript, ref_audio: audio.toString("base64"), duration_seconds: duration };
	signal?.throwIfAborted();
	await mkdir(voicesDirectory(), { recursive: true, mode: 0o700 });
	await writeFile(path.join(voicesDirectory(), `${name}.json`), JSON.stringify(profile) + "\n", { flag: "wx", mode: 0o600 });
	return profile;
}
