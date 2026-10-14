/**
 * decide_records: run a local decision model over every record of a file.
 *
 * The chat model writes typed questions (bool / choice / score); this tool
 * extracts records from a CSV, TSV, NDJSON/JSONL, JSON array, line-oriented log,
 * or a prose document (paragraph-aligned chunks), sends each record to the
 * decision model through Pi's classifier API, writes per-record answers to a
 * results file, and returns only a summary — so a large file never enters the
 * chat model's context.
 *
 * ./pi-local passes lm-based decision models (kev) in LM_BASED_CLASSIFIERS; this
 * extension registers them as the `lm-based-decision` provider (models.json cannot
 * declare classifier models). They are reached through llama-swap's /upstream
 * passthrough. LM_BASED_DECISION_MODEL picks a non-default classifier.
 */

import { StringEnum } from "@earendil-works/pi-ai";
import { classify as systemOneClassify } from "@earendil-works/pi-ai/api/typesafe-system-one";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { stat, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { Type } from "typebox";
import {
	type Answer,
	detectFormat,
	extractRecords,
	type Format,
	type SourceRecord,
	summarize,
	toCsv,
} from "./records.ts";

const MAX_FILE_BYTES = 256 * 1024 * 1024;
const DEFAULT_LIMIT = 1000;
const MAX_LIMIT = 50_000;
const DEFAULT_CONCURRENCY = 8; // kev batches concurrent requests on its model thread
const MAX_CONCURRENCY = 32;
const DEFAULT_CHUNK_CHARS = 6000;
const FAIL_FAST_AFTER = 5; // consecutive failures before any success abort the run

const Question = Type.Object({
	type: StringEnum(["bool", "choice", "score"] as const, {
		description: "bool: yes/no probability; choice: pick one named option; score: ordered levels",
	}),
	instructions: Type.String({ description: "What to decide about each record, phrased as a question" }),
	criteria: Type.Optional(
		Type.Union([Type.Record(Type.String(), Type.String()), Type.Array(Type.String())], {
			description:
				'choice: {"option": "when to pick it", ...} (required). bool: optional {"true": "...", "false": "..."}. ' +
				"score: ordered list of level descriptions, lowest first (required).",
		}),
	),
});

const Params = Type.Object({
	path: Type.String({ description: "File to process (relative to the working directory or absolute)" }),
	questions: Type.Record(Type.String(), Question, {
		description: "Questions keyed by a short snake_case id; every record is asked every question",
	}),
	format: Type.Optional(
		StringEnum(["auto", "csv", "tsv", "ndjson", "json", "lines", "document"] as const, {
			description:
				"auto (default) uses the extension: .csv .tsv .ndjson/.jsonl .json .log=lines, anything else = document chunks",
		}),
	),
	fields: Type.Optional(
		Type.Array(Type.String(), { description: "Only send these columns/keys to the decision model (default: all)" }),
	),
	id_field: Type.Optional(Type.String({ description: "Column/key copied into results as the record id" })),
	context: Type.Optional(
		Type.String({ description: "Shared background added to every record as `task_context`" }),
	),
	offset: Type.Optional(Type.Integer({ minimum: 0, description: "Skip this many records first (default 0)" })),
	limit: Type.Optional(
		Type.Integer({ minimum: 1, maximum: MAX_LIMIT, description: `Max records to process (default ${DEFAULT_LIMIT})` }),
	),
	chunk_chars: Type.Optional(
		Type.Integer({ minimum: 200, description: `document format: max characters per chunk (default ${DEFAULT_CHUNK_CHARS})` }),
	),
	output: Type.Optional(
		Type.String({ description: "Results file; .csv writes CSV, anything else NDJSON (default: <path>.decisions.ndjson)" }),
	),
	min_confidence: Type.Optional(
		Type.Number({ minimum: 0, maximum: 1, description: "Flag answers below this confidence (default 0.5)" }),
	),
	concurrency: Type.Optional(Type.Integer({ minimum: 1, maximum: MAX_CONCURRENCY })),
	model: Type.Optional(Type.String({ description: "Classifier model id (default: the lm-based decision model)" })),
});

function validateQuestions(questions: Record<string, { type: string; criteria?: unknown }>): void {
	const ids = Object.keys(questions);
	if (ids.length === 0) throw new Error("questions must contain at least one question");
	for (const [id, question] of Object.entries(questions)) {
		const criteria = question.criteria;
		if (question.type === "choice" && (!criteria || Array.isArray(criteria) || Object.keys(criteria).length < 2)) {
			throw new Error(`question ${id}: choice needs criteria as an object with at least two options`);
		}
		if (question.type === "score" && (!Array.isArray(criteria) || criteria.length < 2)) {
			throw new Error(`question ${id}: score needs criteria as a list of at least two levels, lowest first`);
		}
		if (question.type === "bool" && Array.isArray(criteria)) {
			throw new Error(`question ${id}: bool criteria must be an object like {"true": "...", "false": "..."}`);
		}
	}
}

const PROVIDER = "lm-based-decision";

function configuredClassifiers(): any[] {
	try {
		const parsed = JSON.parse(process.env.LM_BASED_CLASSIFIERS ?? "[]");
		return Array.isArray(parsed) ? parsed : [];
	} catch {
		return [];
	}
}

export default function decideExtension(pi: ExtensionAPI) {
	const provider = PROVIDER;
	const classifierModels = configuredClassifiers();
	if (classifierModels.length) {
		pi.registerProvider(PROVIDER, {
			name: "lm-based decision models",
			baseUrl: classifierModels[0].baseUrl,
			apiKey: "local",
			models: classifierModels.map((model) => ({ ...model, type: "classifier" })),
			// Reuse pi-ai's TypeSafe System One client; kev speaks that protocol.
			classifiers: { "typesafe-system-one": { classify: systemOneClassify } },
		} as any);
	}

	pi.registerTool(
		defineTool({
			name: "decide_records",
			label: "Decide records",
			description:
				"Classify, label, filter, or score every record of a CSV/TSV/NDJSON/JSON file, line-oriented log, or " +
				"document (paragraph chunks) with a local decision model. You supply typed questions; the tool writes " +
				"per-record answers to a results file and returns counts, distributions, and the least confident records.",
			promptSnippet: "Bulk-classify file records with typed questions via the local decision model",
			promptGuidelines: [
				"Use decide_records instead of reading a large data file into context when the task is to label, filter, triage, or score its records.",
				"Phrase each question so it can be answered from one record alone; put shared background in `context`.",
				"Start with a small `limit` (e.g. 20) to check the questions behave, then rerun on the full file.",
				"Answers are probabilistic: review `low_confidence` records yourself rather than trusting them blindly.",
				"Read the results file (or filter it with bash/jq) for follow-up; do not ask for every record in chat.",
			],
			parameters: Params,

			async execute(_toolCallId, params, signal, onUpdate, ctx) {
				validateQuestions(params.questions);

				const filePath = path.resolve(ctx.cwd ?? process.cwd(), params.path);
				const info = await stat(filePath);
				if (!info.isFile()) throw new Error(`${filePath} is not a file`);
				if (info.size > MAX_FILE_BYTES) throw new Error(`${filePath} is larger than ${MAX_FILE_BYTES} bytes`);

				const modelId = params.model ?? process.env.LM_BASED_DECISION_MODEL;
				const classifiers = ctx.modelRegistry.getModelsOfType("classifier", provider);
				const model = modelId
					? ctx.modelRegistry.getModelOfType("classifier", provider, modelId)
					: classifiers[0];
				if (!model) {
					const known = classifiers.map((m) => m.id).join(", ") || "none";
					throw new Error(
						`no ${provider} classifier model${modelId ? ` named ${modelId}` : ""} (registered: ${known}); ` +
							"start Pi with ./pi-local while llama-swap serves a decision model. " +
							"Tell the user the decision model is unavailable; do not substitute your own classification.",
					);
				}

				const format: Format = !params.format || params.format === "auto" ? detectFormat(filePath) : params.format;
				const text = await readFile(filePath, "utf8");
				const extracted = extractRecords(text, {
					format,
					fields: params.fields,
					chunkChars: params.chunk_chars ?? DEFAULT_CHUNK_CHARS,
					documentName: path.basename(filePath),
				});
				const offset = params.offset ?? 0;
				const limit = params.limit ?? DEFAULT_LIMIT;
				const selected = extracted.records.slice(offset, offset + limit);
				if (selected.length === 0) {
					throw new Error(`no records to process (found ${extracted.records.length} ${format} records, offset ${offset})`);
				}

				const questions = params.questions as Record<string, any>;
				const results: { record: SourceRecord; id?: unknown; answers?: Record<string, Answer>; error?: string }[] =
					new Array(selected.length);
				let next = 0;
				let done = 0;
				let succeeded = 0;
				let consecutiveFailures = 0;
				let fatal: string | undefined;
				let lastUpdate = 0;
				const started = Date.now();

				const report = () => {
					const now = Date.now();
					if (!onUpdate || (now - lastUpdate < 500 && done < selected.length)) return;
					lastUpdate = now;
					onUpdate({
						content: [{ type: "text", text: `decide_records: ${done}/${selected.length} records (${model.id})` }],
						details: { done, total: selected.length },
					});
				};

				const worker = async () => {
					while (!fatal && !signal?.aborted) {
						const position = next++;
						if (position >= selected.length) return;
						const record = selected[position];
						const id = params.id_field ? record.source[params.id_field] : undefined;
						const state = params.context ? { task_context: params.context, ...record.state } : record.state;
						const result = await ctx.modelRegistry.classify(model, { state: state as any, questions }, { signal });
						if (result.stopReason === "stop") {
							results[position] = { record, id, answers: result.answers as Record<string, Answer> };
							succeeded++;
							consecutiveFailures = 0;
						} else {
							const error = result.errorMessage ?? result.stopReason;
							results[position] = { record, id, error };
							consecutiveFailures++;
							if (succeeded === 0 && consecutiveFailures >= FAIL_FAST_AFTER) fatal = error;
						}
						done++;
						report();
					}
				};
				const concurrency = Math.min(params.concurrency ?? DEFAULT_CONCURRENCY, selected.length);
				await Promise.all(Array.from({ length: concurrency }, worker));

				if (fatal) {
					throw new Error(
						`decision model ${model.id} failed on every request: ${fatal}. ` +
							"Report this to the user; do not substitute your own classification.",
					);
				}
				const finished = results.filter(Boolean);
				const questionIds = Object.keys(questions);

				const output = path.resolve(ctx.cwd ?? process.cwd(), params.output ?? `${params.path}.decisions.ndjson`);
				const body = output.toLowerCase().endsWith(".csv")
					? toCsv(finished, questionIds)
					: finished
							.map((r) =>
								JSON.stringify({
									index: r.record.index,
									line: r.record.line,
									...(r.id === undefined ? {} : { id: r.id }),
									...(r.answers ? { answers: r.answers } : { error: r.error }),
								}),
							)
							.join("\n") + "\n";
				await writeFile(output, body);

				const summary = summarize(finished, params.min_confidence ?? 0.5);
				const firstError = finished.find((r) => r.error)?.error;
				const payload = {
					model: model.id,
					file: filePath,
					format,
					records_in_file: extracted.records.length,
					processed: finished.length,
					offset,
					truncated: offset + selected.length < extracted.records.length,
					aborted: Boolean(signal?.aborted) && finished.length < selected.length,
					classified: summary.classified,
					failed: summary.failed,
					...(firstError ? { first_error: firstError } : {}),
					...(extracted.parseErrors.length
						? { parse_errors: extracted.parseErrors.length, first_parse_errors: extracted.parseErrors.slice(0, 3) }
						: {}),
					seconds: Math.round((Date.now() - started) / 100) / 10,
					output,
					questions: summary.questions,
					low_confidence: summary.lowConfidence,
				};
				return {
					content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
					details: payload,
				};
			},
		}),
	);
}
