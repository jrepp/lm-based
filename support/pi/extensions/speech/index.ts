import { StringEnum } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execFile } from "node:child_process";
import { open, mkdir, mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import { listVoices, loadVoice, saveVoice } from "./voices.ts";

export const MODELS = ["qwen3-tts-0.6b-customvoice-8bit", "qwen3-tts-0.6b-base-8bit"];
export const VOICES = ["ryan", "aiden", "vivian", "serena", "uncle_fu", "dylan", "eric", "ono_anna", "sohee"] as const;
const Params = Type.Object({
	text: Type.String({ minLength: 1, maxLength: 4000 }),
	model: Type.Optional(Type.String({ description: `Individual speech model: ${MODELS.join(", ")}` })),
	voice: Type.Optional(StringEnum(VOICES, { description: "Pre-trained speaker. Defaults to /speech-voice selection (ryan initially). Selecting a voice uses CustomVoice; cannot combine with cloning." })),
	cloned_voice: Type.Optional(Type.String({ description: "Saved voice name created with clone_voice. Selects Base automatically; cannot combine with a preset or inline reference." })),
	language: Type.Optional(Type.String()),
	ref_audio: Type.Optional(Type.String({ description: "Local 1–30 second mono PCM16 WAV (Base voice cloning only)" })),
	ref_text: Type.Optional(Type.String({ description: "Exact transcript of the reference WAV" })),
	output: Type.Optional(Type.String({ description: "Save WAV at this path; existing files are refused" })),
	play: Type.Optional(Type.Boolean({ description: "Play on this Mac's default audio output (default true)" })),
});

export default function speech(pi: ExtensionAPI) {
	let selected = process.env.LM_BASED_SPEECH_MODEL || MODELS[0];
	let selectedClone: string | undefined;
	let selectedVoice: string = process.env.LM_BASED_SPEECH_VOICE || "ryan";
	if (!(VOICES as readonly string[]).includes(selectedVoice)) throw new Error(`Unknown speech voice: ${selectedVoice}`);
	pi.registerCommand("speech-voice", {
		description: "Select a pre-trained or saved cloned voice for speak",
		handler: async (args, ctx) => {
			const choices = [...VOICES, ...(await listVoices()).map(name => `clone:${name}`)];
			const choice = args.trim().toLowerCase() || (ctx.hasUI ? await ctx.ui.select("Speech voice", choices) : undefined);
			if (!choice) { ctx.ui.notify(`Speech voice: ${selectedClone ? `clone:${selectedClone}` : selectedVoice}. Choices: ${choices.join(", ")}`, "info"); return; }
			if (choice.startsWith("clone:")) {
				const name = choice.slice(6);
				await loadVoice(name);
				selectedClone = name;
				selected = MODELS[1];
				ctx.ui.notify(`Speech voice: clone:${name}`, "info");
				return;
			}
			if (!(VOICES as readonly string[]).includes(choice)) throw new Error(`Unknown speech voice: ${choice}`);
			selectedClone = undefined;
			selectedVoice = choice;
			selected = MODELS[0];
			ctx.ui.notify(`Speech voice: ${selectedVoice} (${selected})`, "info");
		},
	});
	pi.registerCommand("speech-model", {
		description: "Select the individual Qwen3-TTS speech model used by speak",
		handler: async (args, ctx) => {
			const choice = args.trim() || (ctx.hasUI ? await ctx.ui.select("Speech model", MODELS) : undefined);
			if (!choice) { ctx.ui.notify(`Speech model: ${selected}. Choices: ${MODELS.join(", ")}`, "info"); return; }
			if (!MODELS.includes(choice)) throw new Error(`Unknown speech model: ${choice}`);
			selectedClone = undefined;
			selected = choice;
			ctx.ui.notify(`Speech model: ${selected}`, "info");
		},
	});
	pi.registerTool({
		name: "clone_voice",
		label: "Clone voice from WAV",
		description: "Save a reusable voice from a local WAV, including a file path dragged into the terminal. " +
			"Requires name, reference WAV path and its exact transcript. Ask the user for the transcript if unknown; never invent it. " +
			"Use 1–30 seconds of clean single-speaker speech. On macOS, stereo/float WAV is converted to mono PCM16. " +
			"This saves reference audio, not trained weights. Existing names are refused. Then call speak with cloned_voice=name. " +
			"The saved voice also appears in /speech-voice as clone:name.",
		parameters: Type.Object({
			name: Type.String({ pattern: "^[a-z0-9][a-z0-9_-]{0,63}$", description: "Reusable voice name, e.g. my-voice" }),
			ref_audio: Type.String({ description: "Local WAV path from the user's drag/drop or attachment; quoted and space-escaped paths are accepted" }),
			ref_text: Type.String({ minLength: 1, maxLength: 4000, description: "Exact words spoken in the reference recording" }),
		}),
		execute: async (_id, params, signal, _update, ctx) => {
			const profile = await saveVoice(params.name, params.ref_audio, params.ref_text, ctx.cwd, signal);
			return { content: [{ type: "text", text: `Saved voice ${profile.name} (${profile.duration_seconds.toFixed(1)} seconds). Use speak with cloned_voice="${profile.name}" or /speech-voice clone:${profile.name}.` }],
				details: { name: profile.name, duration_seconds: profile.duration_seconds } };
		},
	});
	pi.registerTool({
		name: "speak",
		label: "Speak (Qwen3-TTS)",
		description: "Generate speech with a selectable local Qwen3-TTS model. Play through macOS audio or save a WAV. " +
			`Pre-trained voices: ${VOICES.join(", ")}. Use voice to select one, or omit it to use /speech-voice. ` +
			"Use cloned_voice for a voice saved with clone_voice, or supply ref_audio plus its exact ref_text directly. " +
			"The first call loads the model; allow several minutes. Use play=false and output to generate silently.",
		parameters: Params,
		execute: async (_id, params, signal, _update, ctx) => {
			const cloneName = params.cloned_voice || (!params.voice && !params.model && !params.ref_audio && !params.ref_text ? selectedClone : undefined);
			if (cloneName && (params.voice || params.ref_audio || params.ref_text)) throw new Error("Saved cloned voices cannot be combined with presets or inline references");
			const cloning = Boolean(cloneName || params.ref_audio || params.ref_text);
			const model = params.model || (cloning ? MODELS[1] : params.voice ? MODELS[0] : selected);
			if (!MODELS.includes(model)) throw new Error(`Unknown speech model: ${model}`);
			if (cloning && model !== MODELS[1]) throw new Error("Voice cloning requires the Base model");
			const savedVoice = cloneName ? await loadVoice(cloneName) : undefined;
			if (params.voice && !(VOICES as readonly string[]).includes(params.voice)) throw new Error(`Unknown speech voice: ${params.voice}`);
			if (params.voice && (model === MODELS[1] || params.ref_audio || params.ref_text)) throw new Error("Pre-trained voices cannot be combined with Base voice cloning");
			const play = params.play ?? true;
			if (!play && !params.output) throw new Error("Specify output when play=false");
			if (play && process.platform !== "darwin") throw new Error("Native playback requires macOS; use play=false and output");
			const body: Record<string, unknown> = { model, input: params.text, response_format: "wav", language: params.language || "English" };
			if (model === MODELS[0]) body.voice = params.voice || selectedVoice;
			if (savedVoice) { body.ref_text = savedVoice.ref_text; body.ref_audio = savedVoice.ref_audio; }
			if (params.ref_text) body.ref_text = params.ref_text;
			if (params.ref_audio) {
				const source = await open(path.resolve(ctx.cwd, params.ref_audio), "r");
				try {
					const limit = 4 * 1024 * 1024;
					if ((await source.stat()).size > limit) throw new Error("Reference exceeds 4 MiB");
					const buffer = Buffer.alloc(limit + 1);
					const { bytesRead } = await source.read(buffer, 0, buffer.length, 0);
					if (bytesRead > limit) throw new Error("Reference exceeds 4 MiB");
					body.ref_audio = buffer.subarray(0, bytesRead).toString("base64");
				} finally { await source.close(); }
			}
			const endpoint = process.env.LM_BASED_SPEECH_URL || `${process.env.LM_BASED_SWAP_URL || "http://127.0.0.1:8081"}/v1`;
			const headers: Record<string, string> = { "Content-Type": "application/json" };
			if (process.env.LM_TTS_API_KEY) headers.Authorization = `Bearer ${process.env.LM_TTS_API_KEY}`;
			const response = await fetch(`${endpoint.replace(/\/+$/, "")}/audio/speech`, {
				method: "POST", headers, body: JSON.stringify(body),
				signal: AbortSignal.any([...(signal ? [signal] : []), AbortSignal.timeout(300_000)]),
			});
			if (!response.ok) throw new Error(`Speech HTTP ${response.status}: ${(await response.text()).slice(0, 2000)}`);
			if (!response.headers.get("content-type")?.startsWith("audio/wav")) throw new Error("Speech endpoint did not return WAV");
			const audio = Buffer.from(await response.arrayBuffer());
			signal?.throwIfAborted();
			const directory = await mkdtemp(path.join(tmpdir(), "pi-speech-"));
			try {
				const output = params.output ? path.resolve(ctx.cwd, params.output) : path.join(directory, "speech.wav");
				await mkdir(path.dirname(output), { recursive: true });
				await writeFile(output, audio, { flag: "wx" });
				if (play) await promisify(execFile)("/usr/bin/afplay", [output], { signal });
				return { content: [{ type: "text", text: `${model}${body.voice ? ` (${body.voice})` : ""}: ${play ? "played" : "generated"} speech${params.output ? `; saved ${output}` : ""}` }], details: { model, voice: body.voice, cloned_voice: cloneName, output: params.output ? output : undefined, bytes: audio.length } };
			} finally { await rm(directory, { recursive: true, force: true }); }
		},
	});
}
