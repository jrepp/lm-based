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
 * Two shapes, one engine (chain.ts):
 *   - `questions` (single stage, the original shape; results keep their original layout)
 *   - `stages`: ordered stages, each with its own questions, an optional `when` filter on
 *     earlier stages' answers, few-shot `examples`, and an `abstain` ("unsure") option;
 *     records flow through all stages in one call and stop where they abstain or are filtered.
 *
 * ./pi-local passes lm-based decision models (kev) in LM_BASED_CLASSIFIERS; this
 * extension registers them as the `lm-based-decision` provider (models.json cannot
 * declare classifier models). They are reached through llama-swap's /upstream
 * passthrough. LM_BASED_DECISION_MODEL picks a non-default classifier.
 */

import { StringEnum } from "@earendil-works/pi-ai";
import { classify as systemOneClassify } from "@earendil-works/pi-ai/api/typesafe-system-one";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { stat, readFile, writeFile, mkdtemp, rename, rm } from "node:fs/promises";
import path from "node:path";
import { Type } from "typebox";
import {
	type ChainResult,
	type Classify,
	chainCsv,
	chainRecordJson,
	decideRecord,
	type Example,
	MAX_EXAMPLES,
	selectExamples,
	type StageSpec,
	summarizeChain,
	validateQuestions,
	validateStages,
} from "./chain.ts";
import {
	type DecisionResult,
	detectFormat,
	extractRecords,
	type Format,
	summarize,
	toCsv,
	withCalibration,
} from "./records.ts";

const MAX_FILE_BYTES = 256 * 1024 * 1024;
const DEFAULT_LIMIT = 1000;
const MAX_LIMIT = 50_000;
const DEFAULT_CONCURRENCY = 8; // kev batches concurrent requests on its model thread
const MAX_CONCURRENCY = 32;
const DEFAULT_CHUNK_CHARS = 6000;
const FAIL_FAST_AFTER = 5; // consecutive failures before any success abort the run
const DEFAULT_EXAMPLES_LIMIT = 12;
const SINGLE_STAGE = "main";

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

const Questions = Type.Record(Type.String(), Question, {
	description: "Questions keyed by a short snake_case id; every record reaching the stage is asked every question",
});

const Abstain = Type.Object(
	{
		choice: Type.Optional(
			Type.String({ description: 'Option added to each choice question meaning "unsure", e.g. "unsure"' }),
		),
		description: Type.Optional(Type.String({ description: "When to pick the abstain option" })),
		min_confidence: Type.Optional(
			Type.Number({ minimum: 0, maximum: 1, description: "Answers below this confidence also count as unsure" }),
		),
		min_margin: Type.Optional(
			Type.Number({
				minimum: 0,
				maximum: 1,
				description: "Answers whose top probability leads the runner-up by less than this count as unsure",
			}),
		),
	},
	{ description: "Let the decision model abstain; unsure records are reported, not forced into an option" },
);

const Examples = Type.Array(
	Type.Object({
		record: Type.Record(Type.String(), Type.Unknown(), { description: "A record like the ones being decided" }),
		answers: Type.Record(Type.String(), Type.Union([Type.String(), Type.Boolean(), Type.Number()]), {
			description: "Its known answer per question id (choice: option name, bool: true/false, score: level index)",
		}),
	}),
	{ maxItems: MAX_EXAMPLES, description: "Few-shot examples with known answers, shown to the decision model" },
);

const ExamplesFrom = Type.Object(
	{
		path: Type.String({ description: "File of already-labeled records (same formats as `path`)" }),
		answer_fields: Type.Record(Type.String(), Type.String(), {
			description: 'question id -> column holding its known answer, e.g. {"category": "category"}',
		}),
		limit: Type.Optional(
			Type.Integer({ minimum: 1, maximum: MAX_EXAMPLES, description: `Examples to pick (default ${DEFAULT_EXAMPLES_LIMIT}), balanced across answers` }),
		),
	},
	{ description: "Pick few-shot examples from rows already labeled by a person" },
);

const Condition = Type.Object({
	stage: Type.String({ description: "An earlier stage id" }),
	question: Type.String({ description: "A question id of that stage" }),
	is: Type.Optional(
		Type.Union([Type.Boolean(), Type.String(), Type.Array(Type.String())], {
			description: "bool: true/false (default true); choice: an option or list of options",
		}),
	),
	min_probability: Type.Optional(Type.Number({ minimum: 0, maximum: 1 })),
	min_confidence: Type.Optional(Type.Number({ minimum: 0, maximum: 1 })),
	min_score: Type.Optional(Type.Number()),
	max_score: Type.Optional(Type.Number()),
});

const Stage = Type.Object({
	id: Type.String({ description: "snake_case stage id" }),
	questions: Questions,
	when: Type.Optional(
		Type.Union([Condition, Type.Array(Condition)], {
			description: "Run this stage only for records whose earlier answers match (all conditions)",
		}),
	),
	otherwise: Type.Optional(
		StringEnum(["stop", "continue"] as const, {
			description: "Records failing `when`: stop here (default, marked filtered) or skip this stage and continue (branches)",
		}),
	),
	examples: Type.Optional(Examples),
	examples_from: Type.Optional(ExamplesFrom),
	abstain: Type.Optional(Abstain),
	context: Type.Optional(Type.String({ description: "Background for this stage (default: the top-level context)" })),
});

const Params = Type.Object({
	path: Type.String({ description: "File to process (relative to the working directory or absolute)" }),
	questions: Type.Optional(Questions),
	stages: Type.Optional(
		Type.Array(Stage, {
			minItems: 1,
			description:
				"Chained decisions instead of `questions`: ordered stages; each may filter on earlier stages' answers. " +
				"Records stop at the first stage where they abstain or fail a filter.",
		}),
	),
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
	examples: Type.Optional(Examples),
	examples_from: Type.Optional(ExamplesFrom),
	abstain: Type.Optional(Abstain),
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

const PROVIDER = "lm-based-decision";

async function checkOutputPath(input: string, output: string): Promise<void> {
	if (input === output) throw new Error("output must not overwrite the input file");
	const source = await stat(input);
	try {
		const target = await stat(output);
		if (source.dev === target.dev && source.ino === target.ino) {
			throw new Error("output must not overwrite the input file (including links)");
		}
	} catch (error) {
		if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
	}
}

function configuredClassifiers(): any[] {
	try {
		const parsed = JSON.parse(process.env.LM_BASED_CLASSIFIERS ?? "[]");
		return Array.isArray(parsed) ? parsed : [];
	} catch {
		return [];
	}
}

async function loadRecords(filePath: string, format: Format, fields: string[] | undefined, chunkChars: number) {
	const info = await stat(filePath);
	if (!info.isFile()) throw new Error(`${filePath} is not a file`);
	if (info.size > MAX_FILE_BYTES) throw new Error(`${filePath} is larger than ${MAX_FILE_BYTES} bytes`);
	return extractRecords(await readFile(filePath, "utf8"), {
		format,
		fields,
		chunkChars,
		documentName: path.basename(filePath),
	});
}

/** Stages from either parameter shape, with `examples_from` resolved into examples. */
async function resolveStages(params: any, cwd: string): Promise<StageSpec[]> {
	if (params.questions && params.stages) throw new Error("give either `questions` or `stages`, not both");
	if (!params.questions && !params.stages) throw new Error("give `questions` (one stage) or `stages` (chained decisions)");
	if (params.stages && (params.examples || params.examples_from || params.abstain)) {
		throw new Error("with `stages`, put examples, examples_from and abstain on each stage");
	}
	if (params.questions) validateQuestions(params.questions);
	const raw: any[] = params.stages ?? [
		{
			id: SINGLE_STAGE,
			questions: params.questions,
			examples: params.examples,
			examples_from: params.examples_from,
			abstain: params.abstain,
		},
	];
	const stages: StageSpec[] = [];
	for (const stage of raw) {
		let examples: Example[] = [...(stage.examples ?? [])];
		if (stage.examples_from) {
			const source = path.resolve(cwd, stage.examples_from.path);
			const answerFields: Record<string, string> = stage.examples_from.answer_fields ?? {};
			const fields = params.fields ? [...params.fields, ...Object.values(answerFields)] : undefined;
			const labeled = await loadRecords(source, detectFormat(source), fields, DEFAULT_CHUNK_CHARS);
			const room = Math.max(0, MAX_EXAMPLES - examples.length);
			const limit = Math.min(stage.examples_from.limit ?? DEFAULT_EXAMPLES_LIMIT, room);
			examples = [...examples, ...selectExamples(labeled.records, stage, answerFields, limit)];
		}
		const { examples_from: _from, ...rest } = stage;
		stages.push({
			...rest,
			context: stage.context ?? params.context,
			...(examples.length ? { examples } : { examples: undefined }),
		});
	}
	validateStages(stages);
	return stages;
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
				"document (paragraph chunks) with a local decision model. You supply typed questions, or chained `stages` " +
				"(e.g. a bool relevance question, then a choice question only for relevant records); the tool writes " +
				"per-record answers to a results file and returns counts, calibration figures, and the least confident records.",
			promptSnippet: "Bulk-classify file records with typed questions or chained stages via the local decision model",
			promptGuidelines: [
				"Use decide_records instead of reading a large data file into context when the task is to label, filter, triage, or score its records.",
				"Phrase each question so it can be answered from one record alone; put shared background in `context`.",
				"Start with a small `limit` (e.g. 20) to check the questions behave, then rerun on the full file.",
				"Prefer two stages over one big choice: a bool question that filters (is this record in scope?), then a choice over a short list of options with `when` on the first stage's answer.",
				"Give choice stages an abstain option (`abstain: {choice: \"unsure\"}`) instead of inventing confidence thresholds afterwards; report unsure records to the person.",
				"When records already labeled by a person exist, pass a few as `examples` or `examples_from` (balanced across answers).",
				"Confidence for choice questions is normalized over the option count (0 = uniform); read `mean_top_probability` and `mean_margin` too.",
				"Answers are probabilistic: review `low_confidence` records yourself rather than trusting them blindly.",
				"Read the results file (or filter it with bash/jq) for follow-up; do not ask for every record in chat. Quote counts only from the tool's output.",
			],
			parameters: Params,

			async execute(_toolCallId, params, signal, onUpdate, ctx) {
				signal?.throwIfAborted();
				const cwd = ctx.cwd ?? process.cwd();
				const staged = Boolean((params as any).stages);
				const stages = await resolveStages(params, cwd);

				const filePath = path.resolve(cwd, params.path);
				const info = await stat(filePath);
				if (!info.isFile()) throw new Error(`${filePath} is not a file`);
				if (info.size > MAX_FILE_BYTES) throw new Error(`${filePath} is larger than ${MAX_FILE_BYTES} bytes`);
				const output = path.resolve(cwd, params.output ?? `${params.path}.decisions.ndjson`);
				await checkOutputPath(filePath, output);

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
				const extracted = await loadRecords(filePath, format, params.fields, params.chunk_chars ?? DEFAULT_CHUNK_CHARS);
				const offset = params.offset ?? 0;
				const limit = params.limit ?? DEFAULT_LIMIT;
				const selected = extracted.records.slice(offset, offset + limit);
				if (selected.length === 0) {
					throw new Error(`no records to process (found ${extracted.records.length} ${format} records, offset ${offset})`);
				}

				const results: ChainResult[] = new Array(selected.length);
				let next = 0;
				let done = 0;
				let succeeded = 0;
				let consecutiveFailures = 0;
				let calls = 0;
				let fatal: string | undefined;
				let lastUpdate = 0;
				const started = Date.now();

				const classify: Classify = async (state, questions) => {
					calls++;
					const result = await ctx.modelRegistry.classify(model, { state: state as any, questions: questions as any }, { signal });
					if (result.stopReason === "stop") {
						succeeded++;
						consecutiveFailures = 0;
						return { answers: result.answers as any };
					}
					const error = result.errorMessage ?? result.stopReason;
					consecutiveFailures++;
					if (succeeded === 0 && consecutiveFailures >= FAIL_FAST_AFTER) fatal = error;
					return { error };
				};

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
						results[position] = await decideRecord(record, stages, classify, id);
						done++;
						report();
					}
				};
				const concurrency = Math.min(params.concurrency ?? DEFAULT_CONCURRENCY, selected.length);
				await Promise.all(Array.from({ length: concurrency }, worker));
				signal?.throwIfAborted();

				if (fatal) {
					throw new Error(
						`decision model ${model.id} failed on every request: ${fatal}. ` +
							"Report this to the user; do not substitute your own classification.",
					);
				}
				const finished = results.filter(Boolean);
				const minConfidence = params.min_confidence ?? 0.5;
				const csv = output.toLowerCase().endsWith(".csv");
				const abstainUsed = stages.some((stage) => stage.abstain);

				// Single stage keeps the original results layout (plus calibration fields on answers).
				const flat: DecisionResult[] = finished.map((r) => {
					const stage = r.stages[SINGLE_STAGE] ?? {};
					return {
						record: r.record,
						id: r.id,
						...(stage.answers ? { answers: stage.answers } : { error: stage.error }),
						...(stage.abstained ? { abstained: stage.abstained } : {}),
					};
				});
				const body = staged
					? csv
						? chainCsv(finished, stages)
						: finished.map((r) => JSON.stringify(chainRecordJson(r))).join("\n") + "\n"
					: csv
						? toCsv(flat, Object.keys(stages[0].questions), abstainUsed)
						: flat
								.map((r) =>
									JSON.stringify({
										index: r.record.index,
										line: r.record.line,
										...(r.id === undefined ? {} : { id: r.id }),
										...(r.answers
											? { answers: Object.fromEntries(Object.entries(r.answers).map(([q, a]) => [q, withCalibration(a)])) }
											: { error: r.error }),
										...(r.abstained ? { abstained: r.abstained } : {}),
									}),
								)
								.join("\n") + "\n";
				// Publish a complete result atomically. Cancellation or a failed write
				// leaves a previous successful result intact.
				const temporary = await mkdtemp(path.join(path.dirname(output), ".decide-"));
				try {
					const stagedFile = path.join(temporary, "results");
					await writeFile(stagedFile, body, { signal, mode: 0o600 });
					await checkOutputPath(filePath, output);
					signal?.throwIfAborted();
					await rename(stagedFile, output);
				} finally {
					await rm(temporary, { recursive: true, force: true });
				}

				const firstError = finished.flatMap((r) => Object.values(r.stages)).find((s) => s.error)?.error;
				const examplesUsed = Object.fromEntries(
					stages.filter((stage) => stage.examples?.length).map((stage) => [stage.id, stage.examples!.length]),
				);
				const common = {
					model: model.id,
					file: filePath,
					format,
					records_in_file: extracted.records.length,
					processed: finished.length,
					offset,
					truncated: offset + selected.length < extracted.records.length,
					aborted: Boolean(signal?.aborted) && finished.length < selected.length,
					classifier_calls: calls,
					...(Object.keys(examplesUsed).length ? { examples: examplesUsed } : {}),
					...(firstError ? { first_error: firstError } : {}),
					...(extracted.parseErrors.length
						? { parse_errors: extracted.parseErrors.length, first_parse_errors: extracted.parseErrors.slice(0, 3) }
						: {}),
					seconds: Math.round((Date.now() - started) / 100) / 10,
					output,
				};
				let payload: Record<string, unknown>;
				if (staged) {
					const summary = summarizeChain(finished, stages, minConfidence);
					payload = { ...common, ...summary };
				} else {
					const summary = summarize(flat, minConfidence);
					const unsure = flat.filter((r) => r.abstained?.length).length;
					payload = {
						...common,
						classified: summary.classified,
						failed: summary.failed,
						...(abstainUsed ? { abstained: unsure } : {}),
						questions: summary.questions,
						low_confidence: summary.lowConfidence,
					};
				}
				return {
					content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
					details: payload,
				};
			},
		}),
	);
}
