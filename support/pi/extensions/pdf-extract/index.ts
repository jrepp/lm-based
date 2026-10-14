/**
 * PDF/image extraction through the GLM-OCR model on the lm-based serving ports.
 *
 * pdf_extract(path, pages?, prompt?) sends page images to the local GLM-OCR
 * worker (llama-server + mmproj behind llama-swap) and returns per-page text.
 * PDFs are rasterized locally with Ghostscript; images pass through as-is.
 *
 * ./pi-local sets LM_BASED_SWAP_URL (llama-swap root, no /v1); LM_BASED_OCR_MODEL
 * overrides the parsing model (default glm-ocr-q8_0). Requests hot-swap the
 * worker in on demand, so this coexists with whatever else llama-swap holds.
 */

import { Type, type Static } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";

const execFileP = promisify(execFile);

const DEFAULT_SWAP_ROOT = "http://127.0.0.1:8081";
const DEFAULT_MODEL = "glm-ocr-q8_0";
const DEFAULT_PROMPT = "Text Recognition:";
const GS_DPI = "150";
const MAX_PAGES = 100;
const GS_TIMEOUT_MS = 120_000;
const OCR_TIMEOUT_MS = 300_000; // the first call cold-boots the llama-swap worker

const IMAGE_EXT = new Set([".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"]);

const Params = Type.Object({
	path: Type.String({ description: "Absolute path to a PDF or image file" }),
	pages: Type.Optional(
		Type.String({ description: 'Pages to parse, e.g. "1-3,7" (PDFs only; default: every page)' }),
	),
	prompt: Type.Optional(
		Type.String({
			description:
				'OCR task prompt; GLM-OCR understands "Text Recognition:", "Formula Recognition:", "Table Recognition:" (default "Text Recognition:")',
		}),
	),
});

/** "1-3,7" -> [1, 2, 3, 7] validated against the document; invalid parts are ignored. */
export function parsePageRanges(spec: string, pageCount: number): number[] {
	const wanted = new Set<number>();
	for (const part of spec.split(",")) {
		const range = part.trim().split("-").map((n) => Number.parseInt(n, 10));
		if (range.length === 2 && range.every((n) => Number.isInteger(n))) {
			const [lo, hi] = range.sort((a, b) => a - b);
			for (let page = Math.max(1, lo); page <= Math.min(pageCount, hi); page++) wanted.add(page);
		} else if (range.length === 1 && Number.isInteger(range[0]) && range[0] >= 1 && range[0] <= pageCount) {
			wanted.add(range[0]);
		}
	}
	return [...wanted].sort((a, b) => a - b);
}

async function rasterizePdf(
	pdfPath: string,
	pages: number[] | null,
): Promise<{ page: number; file: string }[]> {
	const dir = await mkdtemp(path.join(tmpdir(), "pdf-extract-"));
	const pattern = path.join(dir, "page-%03d.png");
	const args = [
		"-dNOPAUSE",
		"-dBATCH",
		"-dQUIET",
		"-dSAFER",
		`-r${GS_DPI}`,
		"-sDEVICE=png16m",
		`-sOutputFile=${pattern}`,
	];
	if (pages) {
		if (pages.length === 0) return [];
		args.push(`-dFirstPage=${pages[0]}`, `-dLastPage=${pages[pages.length - 1]}`);
	}
	args.push(pdfPath);
	try {
		await execFileP("gs", args, { timeout: GS_TIMEOUT_MS });
	} catch (error) {
		await rm(dir, { recursive: true, force: true });
		throw new Error(`Ghostscript failed to rasterize ${pdfPath}: ${error}`);
	}

	const produced = (await readdir(dir)).filter((f) => f.endsWith(".png")).sort();
	const selected = pages ?? produced.map((_, index) => index + 1);
	const first = pages ? pages[0] : 1;
	const result = selected.flatMap((page) => {
		const ordinal = page - first; // gs numbers outputs from FirstPage
		const file = produced[ordinal];
		return file ? [{ page, file: path.join(dir, file) }] : [];
	});
	if (result.length === 0) await rm(dir, { recursive: true, force: true });
	return result;
}

export async function ocrImage(
	root: string,
	model: string,
	prompt: string,
	imagePath: string,
): Promise<string> {
	const ext = path.extname(imagePath).slice(1).toLowerCase().replace("jpeg", "jpg");
	const base64 = (await readFile(imagePath)).toString("base64");
	const response = await fetch(`${root}/v1/chat/completions`, {
		method: "POST",
		headers: { "content-type": "application/json" },
		signal: AbortSignal.timeout(OCR_TIMEOUT_MS),
		body: JSON.stringify({
			model,
			messages: [
				{
					role: "user",
					content: [
						{ type: "image_url", image_url: { url: `data:image/${ext || "png"};base64,${base64}` } },
						{ type: "text", text: prompt },
					],
				},
			],
			max_tokens: 8192,
			temperature: 0.0,
		}),
	});
	if (!response.ok) {
		throw new Error(`OCR request to ${root} failed: ${response.status} ${await response.text()}`);
	}
	const payload: any = await response.json();
	const content = payload?.choices?.[0]?.message?.content;
	if (typeof content !== "string") throw new Error(`OCR response for ${imagePath} had no text content`);
	return content.trim();
}

export function resolveSwapRoot(): string {
	return (process.env.LM_BASED_SWAP_URL?.replace(/\/+$/u, "")) || DEFAULT_SWAP_ROOT;
}

export default function pdfExtract(pi: ExtensionAPI) {
	pi.registerTool({
		name: "pdf_extract",
		label: "PDF extract (GLM-OCR)",
		description:
			"Parse a PDF or image into text/markdown with the local GLM-OCR vision model (served on the lm-based ports). " +
			"PDFs are rasterized with Ghostscript at 150 DPI; each page is recognized independently. " +
			'Task prompts: "Text Recognition:" (default), "Formula Recognition:", "Table Recognition:". ' +
			"The first call may take a while while llama-swap cold-loads the model.",
		promptSnippet: "pdf_extract(path, pages?, prompt?): parse a PDF/image to text via local GLM-OCR",
		parameters: Params,
		execute: async (_toolCallId, params: Static<typeof Params>) => {
			const root = resolveSwapRoot();
			const model = process.env.LM_BASED_OCR_MODEL || DEFAULT_MODEL;
			const prompt = params.prompt || DEFAULT_PROMPT;
			const file = path.resolve(params.path);
			const ext = path.extname(file).toLowerCase();

			let pageFiles: { page: number; file: string }[];
			if (IMAGE_EXT.has(ext)) {
				pageFiles = [{ page: 1, file }];
			} else if (ext === ".pdf") {
				const spec = params.pages?.trim();
				const pages = spec ? parsePageRanges(spec, MAX_PAGES) : null;
				if (spec && pages!.length === 0) {
					throw new Error(`No valid pages in "${spec}" (pages are 1-based)`);
				}
				pageFiles = await rasterizePdf(file, pages);
			} else {
				throw new Error(`Unsupported file type "${ext}": use a PDF or an image`);
			}
			if (pageFiles.length === 0) throw new Error(`No pages to parse in ${file}`);

			const sections: string[] = [];
			try {
				for (const { page, file: image } of pageFiles) {
					const text = await ocrImage(root, model, prompt, image);
					sections.push(pageFiles.length > 1 ? `## Page ${page}\n\n${text}` : text);
				}
			} finally {
				if (pageFiles.some((p) => p.file !== file)) {
					await rm(path.dirname(pageFiles[0].file), { recursive: true, force: true });
				}
			}

			return {
				content: [{ type: "text", text: sections.join("\n\n") }],
				details: undefined,
			};
		},
	});
}
