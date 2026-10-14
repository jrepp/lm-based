/**
 * llama-swap status for the lm-based provider.
 *
 * llama-swap lists every configured model on /v1/models but only loads one
 * at a time; /running reports what is actually in memory. This extension joins
 * the two so Pi shows which models are loaded and which need a cold swap:
 *
 *   - footer status: the model llama-swap currently holds and its state
 *   - model_select: warns when the chosen model is unloaded
 *   - /swap: lists models with loaded/unloaded markers and switches to one
 *
 * ./pi-local sets LM_BASED_SWAP_URL (llama-swap root, no /v1) and
 * LM_BASED_PROVIDER when it routes through llama-swap; otherwise this is inert.
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const STATUS_KEY = "llama-swap";
const POLL_MS = 3000;
const REQUEST_TIMEOUT_MS = 2000;

interface SwapModel {
	id: string;
	name?: string;
	state: string; // llama-swap process state, or "unloaded"
}

async function getJson(url: string): Promise<any> {
	const response = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
	if (!response.ok) throw new Error(`${url} returned ${response.status}`);
	return response.json();
}

export async function swapModels(root: string): Promise<SwapModel[]> {
	const [models, running] = await Promise.all([getJson(`${root}/v1/models`), getJson(`${root}/running`)]);
	const states = new Map<string, string>();
	for (const entry of running?.running ?? []) {
		if (typeof entry?.model === "string") states.set(entry.model, String(entry.state ?? "unknown"));
	}
	return (models?.data ?? [])
		.filter((entry: any) => typeof entry?.id === "string")
		.map((entry: any) => ({ id: entry.id, name: entry.name, state: states.get(entry.id) ?? "unloaded" }));
}

function statusText(models: SwapModel[]): string {
	const loaded = models.filter((model) => model.state !== "unloaded");
	if (loaded.length === 0) return `swap: nothing loaded (${models.length} available)`;
	return `swap: ${loaded.map((model) => `${model.id} ${model.state}`).join(", ")}`;
}

function marker(model: SwapModel, current: string | undefined): string {
	const dot = model.state === "ready" ? "●" : model.state === "unloaded" ? "○" : "◐";
	const suffix = model.id === current ? "  (current)" : "";
	return `${dot} ${model.id} — ${model.state}${suffix}`;
}

export default function llamaSwapStatus(pi: ExtensionAPI) {
	const root = process.env.LM_BASED_SWAP_URL?.replace(/\/+$/, "");
	const provider = process.env.LM_BASED_PROVIDER ?? "lm-based";
	if (!root) return;

	let timer: ReturnType<typeof setInterval> | undefined;
	let last: SwapModel[] = [];

	const refresh = async (ctx: ExtensionContext) => {
		try {
			last = await swapModels(root);
			ctx.ui.setStatus(STATUS_KEY, statusText(last));
		} catch {
			ctx.ui.setStatus(STATUS_KEY, "swap: unreachable");
		}
	};

	pi.on("session_start", async (_event, ctx) => {
		if (!ctx.hasUI) return;
		await refresh(ctx);
		timer ??= setInterval(() => void refresh(ctx), POLL_MS);
	});

	pi.on("session_shutdown", async () => {
		if (timer) clearInterval(timer);
		timer = undefined;
	});

	pi.on("model_select", async (event, ctx) => {
		if (event.model.provider !== provider || event.source === "restore" || !ctx.hasUI) return;
		await refresh(ctx);
		const target = last.find((model) => model.id === event.model.id);
		if (target?.state !== "unloaded") return;
		const holding = last.filter((model) => model.state !== "unloaded").map((model) => model.id);
		const evicts = holding.length ? `; llama-swap will unload ${holding.join(", ")}` : "";
		ctx.ui.notify(`${target.id} is not loaded — the next request cold-loads it${evicts}`, "warning");
	});

	pi.registerCommand("swap", {
		description: "Show llama-swap models (loaded/unloaded) and switch to one",
		handler: async (_args, ctx) => {
			await refresh(ctx);
			if (last.length === 0) {
				ctx.ui.notify("llama-swap reports no models", "warning");
				return;
			}
			const current = ctx.model?.provider === provider ? ctx.model.id : undefined;
			// Only offer models Pi can select (./pi-local skips decision models and unknown slugs).
			const choices = last.filter((model) => ctx.modelRegistry.find(provider, model.id));
			const labels = choices.map((model) => marker(model, current));
			if (!ctx.hasUI) {
				console.log(labels.join("\n"));
				return;
			}
			const choice = await ctx.ui.select("llama-swap models  (● loaded  ○ unloaded)", labels);
			if (!choice) return;
			const picked = choices[labels.indexOf(choice)];
			const model = ctx.modelRegistry.find(provider, picked.id);
			if (model) await pi.setModel(model);
		},
	});
}
