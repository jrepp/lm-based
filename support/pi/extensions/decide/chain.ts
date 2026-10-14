/**
 * Chained decisions for decide_records: ordered stages, abstain, and few-shot examples.
 *
 * Pure (no Pi imports); the classifier is injected so tests drive it with a fake:
 *   node --test support/pi/extensions/decide/chain.test.ts
 *
 * A stage asks its own typed questions of each record that reaches it. Stage N may carry a
 * `when` filter on the answers of stages before it ("category runs only where relevant was
 * true with probability >= 0.8"). A record stops at the first stage where it abstains (picks
 * the abstain option, or falls below the stage's abstain thresholds), errors, or fails a
 * filter (unless that stage says `otherwise: "continue"`, which skips it and lets the record
 * go on to later stages: that is how branches are written). Every answer, its probabilities
 * and confidence, and where the record stopped go to the results file.
 *
 * kev (TypeSafe System One) has no abstain or few-shot API of its own: abstain is an extra
 * option added to choice questions plus thresholds applied here, and examples travel inside
 * `state` ahead of the record (a shared prefix, which kev's prefix cache reuses).
 */

import {
	type Answer,
	answerValue,
	calibrationOf,
	confidenceOf,
	csvCell,
	type DecisionResult,
	type SourceRecord,
	summarize,
	withCalibration,
} from "./records.ts";

export const MAX_STAGES = 6;
export const MAX_EXAMPLES = 24;
export const MAX_EXAMPLE_CHARS = 12_000; // all examples of a stage, as JSON
const STAGE_ID = /^[a-z][a-z0-9_]{0,39}$/;
export const DEFAULT_ABSTAIN_DESCRIPTION =
	"None of the other options clearly applies, or the record does not say enough to decide.";
const EXAMPLES_NOTE = "labeled_examples are records already decided by a person; answer only for `record`.";

export type QuestionType = "bool" | "choice" | "score";

export interface QuestionSpec {
	type: QuestionType;
	instructions: string;
	criteria?: Record<string, string> | string[];
}

export interface Example {
	record: Record<string, unknown>;
	answers: Record<string, string | boolean | number>;
}

export interface AbstainSpec {
	/** Option added to every choice question of the stage; picking it means "unsure". */
	choice?: string;
	description?: string;
	/** Answers below this confidence count as unsure (bool: |2p - 1|; choice: kev's normalized confidence). */
	min_confidence?: number;
	/** Choice and bool answers whose top probability leads the runner-up by less than this count as unsure. */
	min_margin?: number;
}

export interface Condition {
	stage: string;
	question: string;
	/** bool: true/false. choice: an option or a list of options. */
	is?: boolean | string | string[];
	/** Probability of the matched value (bool: of `is`, default true; choice: of the chosen option). */
	min_probability?: number;
	min_confidence?: number;
	min_score?: number;
	max_score?: number;
}

export interface StageSpec {
	id: string;
	questions: Record<string, QuestionSpec>;
	when?: Condition | Condition[];
	otherwise?: "stop" | "continue";
	examples?: Example[];
	abstain?: AbstainSpec;
	context?: string;
}

export type Outcome = "complete" | "filtered" | "abstained" | "error";

export interface StageResult {
	answers?: Record<string, Answer>;
	abstained?: string[];
	error?: string;
	skipped?: true; // `when` failed and the stage said otherwise: "continue"
}

export interface ChainResult {
	record: SourceRecord;
	id?: unknown;
	outcome: Outcome;
	stopped_at?: string;
	path: string[]; // stages that answered, in order
	stages: Record<string, StageResult>;
}

// ─── validation ─────────────────────────────────────────────────────────────

export function validateQuestions(questions: Record<string, { type: string; criteria?: unknown }>, where = ""): void {
	const ids = Object.keys(questions ?? {});
	if (ids.length === 0) throw new Error(`${where}questions must contain at least one question`);
	for (const [id, question] of Object.entries(questions)) {
		const criteria = question.criteria;
		if (question.type === "choice" && (!criteria || Array.isArray(criteria) || Object.keys(criteria).length < 2)) {
			throw new Error(`${where}question ${id}: choice needs criteria as an object with at least two options`);
		}
		if (question.type === "score" && (!Array.isArray(criteria) || criteria.length < 2)) {
			throw new Error(`${where}question ${id}: score needs criteria as a list of at least two levels, lowest first`);
		}
		if (question.type === "bool" && Array.isArray(criteria)) {
			throw new Error(`${where}question ${id}: bool criteria must be an object like {"true": "...", "false": "..."}`);
		}
	}
}

function unit(value: unknown, label: string): void {
	if (value !== undefined && (typeof value !== "number" || !(value >= 0 && value <= 1))) {
		throw new Error(`${label} must be a number from 0 to 1`);
	}
}

function options(question: QuestionSpec, abstain?: AbstainSpec): string[] {
	if (question.type !== "choice") return [];
	const names = Object.keys(question.criteria as Record<string, string>);
	return abstain?.choice && !names.includes(abstain.choice) ? [...names, abstain.choice] : names;
}

export function conditionsOf(stage: StageSpec): Condition[] {
	return stage.when === undefined ? [] : Array.isArray(stage.when) ? stage.when : [stage.when];
}

/** Check the stage graph: ids, questions, abstain, examples, and that filters only look back. */
export function validateStages(stages: StageSpec[]): void {
	if (!Array.isArray(stages) || stages.length === 0) throw new Error("stages must list at least one stage");
	if (stages.length > MAX_STAGES) throw new Error(`at most ${MAX_STAGES} stages`);
	const seen = new Map<string, StageSpec>();
	stages.forEach((stage, position) => {
		const where = `stage ${stage?.id ?? position + 1}: `;
		if (typeof stage?.id !== "string" || !STAGE_ID.test(stage.id)) {
			throw new Error(`${where}id must be snake_case (a-z, 0-9, _), starting with a letter`);
		}
		if (seen.has(stage.id)) throw new Error(`${where}duplicate stage id`);
		validateQuestions(stage.questions, where);
		const abstain = stage.abstain;
		if (abstain) {
			unit(abstain.min_confidence, `${where}abstain.min_confidence`);
			unit(abstain.min_margin, `${where}abstain.min_margin`);
			if (abstain.choice !== undefined) {
				if (typeof abstain.choice !== "string" || !abstain.choice.trim()) throw new Error(`${where}abstain.choice must be a name`);
				if (!Object.values(stage.questions).some((q) => q.type === "choice")) {
					throw new Error(`${where}abstain.choice needs a choice question in the stage`);
				}
			}
		}
		validateExamples(stage, where);
		const conditions = conditionsOf(stage);
		if (position === 0 && conditions.length) throw new Error(`${where}the first stage cannot have a when filter`);
		if (stage.otherwise !== undefined && stage.otherwise !== "stop" && stage.otherwise !== "continue") {
			throw new Error(`${where}otherwise must be "stop" or "continue"`);
		}
		for (const condition of conditions) {
			const earlier = seen.get(condition?.stage);
			if (!earlier) {
				throw new Error(
					`${where}when refers to stage ${JSON.stringify(condition?.stage)}, which is not an earlier stage (filters only look back)`,
				);
			}
			const question = earlier.questions[condition.question];
			if (!question) throw new Error(`${where}when refers to unknown question ${condition.stage}.${condition.question}`);
			unit(condition.min_probability, `${where}when.min_probability`);
			unit(condition.min_confidence, `${where}when.min_confidence`);
			if (question.type === "bool" && condition.is !== undefined && typeof condition.is !== "boolean") {
				throw new Error(`${where}when.is must be true or false for bool question ${condition.question}`);
			}
			if (question.type === "choice" && condition.is !== undefined) {
				const allowed = options(question, earlier.abstain);
				const wanted = Array.isArray(condition.is) ? condition.is : [condition.is];
				const unknown = wanted.filter((value) => typeof value !== "string" || !allowed.includes(value));
				if (unknown.length || !wanted.length) {
					throw new Error(`${where}when.is names unknown options of ${condition.question}: ${JSON.stringify(unknown)}`);
				}
			}
			if (question.type === "score" && condition.is !== undefined) {
				throw new Error(`${where}when on score question ${condition.question}: use min_score / max_score`);
			}
			if (question.type !== "score" && (condition.min_score !== undefined || condition.max_score !== undefined)) {
				throw new Error(`${where}min_score / max_score only apply to score questions`);
			}
		}
		seen.set(stage.id, stage);
	});
}

function validateExamples(stage: StageSpec, where: string): void {
	const examples = stage.examples ?? [];
	if (!Array.isArray(examples)) throw new Error(`${where}examples must be a list`);
	if (examples.length > MAX_EXAMPLES) throw new Error(`${where}at most ${MAX_EXAMPLES} examples`);
	if (JSON.stringify(examples).length > MAX_EXAMPLE_CHARS) {
		throw new Error(`${where}examples are longer than ${MAX_EXAMPLE_CHARS} characters; use fewer or narrower fields`);
	}
	for (const [i, example] of examples.entries()) {
		if (!example || typeof example.record !== "object" || typeof example.answers !== "object") {
			throw new Error(`${where}example ${i + 1} needs {record, answers}`);
		}
		for (const [qid, value] of Object.entries(example.answers)) {
			const question = stage.questions[qid];
			if (!question) throw new Error(`${where}example ${i + 1} answers unknown question ${qid}`);
			if (question.type === "bool" && typeof value !== "boolean") throw new Error(`${where}example ${i + 1}: ${qid} must be true/false`);
			if (question.type === "choice" && !options(question, stage.abstain).includes(String(value))) {
				throw new Error(`${where}example ${i + 1}: ${qid} must be one of the options`);
			}
			if (question.type === "score") {
				const levels = (question.criteria as string[]).length;
				if (typeof value !== "number" || value < 0 || value > levels - 1) {
					throw new Error(`${where}example ${i + 1}: ${qid} must be a level index 0..${levels - 1}`);
				}
			}
		}
	}
}

// ─── per-record logic ───────────────────────────────────────────────────────

/** The questions sent to the classifier: choice questions gain the abstain option. */
export function effectiveQuestions(stage: StageSpec): Record<string, QuestionSpec> {
	const choice = stage.abstain?.choice;
	if (!choice) return stage.questions;
	const out: Record<string, QuestionSpec> = {};
	for (const [id, question] of Object.entries(stage.questions)) {
		const criteria = question.criteria as Record<string, string>;
		out[id] =
			question.type === "choice" && !(choice in criteria)
				? { ...question, criteria: { ...criteria, [choice]: stage.abstain?.description ?? DEFAULT_ABSTAIN_DESCRIPTION } }
				: question;
	}
	return out;
}

/** What the classifier sees. Without examples this is exactly the legacy shape. */
export function buildState(state: Record<string, unknown>, context?: string, examples?: Example[]): Record<string, unknown> {
	if (!examples?.length) return context ? { task_context: context, ...state } : state;
	return {
		...(context ? { task_context: context } : {}),
		note: EXAMPLES_NOTE,
		labeled_examples: examples.map((example) => ({ record: example.record, answers: example.answers })),
		record: state,
	};
}

/** Questions of the stage whose answers count as "unsure". */
export function abstainedQuestions(stage: StageSpec, answers: Record<string, Answer>): string[] {
	const abstain = stage.abstain;
	if (!abstain) return [];
	const unsure: string[] = [];
	for (const [id, answer] of Object.entries(answers)) {
		if (!(id in stage.questions)) continue;
		const calibration = calibrationOf(answer);
		if (
			(answer.type === "choice" && abstain.choice !== undefined && answer.choice === abstain.choice) ||
			(abstain.min_confidence !== undefined && confidenceOf(answer) < abstain.min_confidence) ||
			(abstain.min_margin !== undefined && calibration !== undefined && calibration.margin < abstain.min_margin)
		) {
			unsure.push(id);
		}
	}
	return unsure;
}

export function conditionHolds(condition: Condition, stages: Record<string, StageResult>): boolean {
	const result = stages[condition.stage];
	const answer = result?.answers?.[condition.question];
	if (!answer || result?.abstained?.includes(condition.question)) return false;
	if (condition.min_confidence !== undefined && confidenceOf(answer) < condition.min_confidence) return false;
	if (answer.type === "bool") {
		const wanted = condition.is === undefined ? true : condition.is;
		if (condition.min_probability !== undefined) {
			return (wanted ? answer.probability : 1 - answer.probability) >= condition.min_probability;
		}
		return answerValue(answer) === wanted;
	}
	if (answer.type === "choice") {
		if (condition.is !== undefined) {
			const wanted = Array.isArray(condition.is) ? condition.is : [condition.is];
			if (!wanted.includes(answer.choice)) return false;
		}
		const probability = answer.probabilities?.[answer.choice] ?? 0;
		return condition.min_probability === undefined || probability >= condition.min_probability;
	}
	if (condition.min_score !== undefined && answer.score < condition.min_score) return false;
	if (condition.max_score !== undefined && answer.score > condition.max_score) return false;
	return true;
}

export type Classify = (
	state: Record<string, unknown>,
	questions: Record<string, QuestionSpec>,
) => Promise<{ answers: Record<string, Answer> } | { error: string }>;

/** Run one record through the stages. */
export async function decideRecord(
	record: SourceRecord,
	stages: StageSpec[],
	classify: Classify,
	id?: unknown,
): Promise<ChainResult> {
	const result: ChainResult = { record, ...(id === undefined ? {} : { id }), outcome: "complete", path: [], stages: {} };
	for (const stage of stages) {
		const conditions = conditionsOf(stage);
		if (conditions.length && !conditions.every((condition) => conditionHolds(condition, result.stages))) {
			if (stage.otherwise === "continue") {
				result.stages[stage.id] = { skipped: true };
				continue;
			}
			result.outcome = "filtered";
			result.stopped_at = stage.id;
			return result;
		}
		const response = await classify(buildState(record.state, stage.context, stage.examples), effectiveQuestions(stage));
		if ("error" in response) {
			result.stages[stage.id] = { error: response.error };
			result.outcome = "error";
			result.stopped_at = stage.id;
			return result;
		}
		const abstained = abstainedQuestions(stage, response.answers);
		result.stages[stage.id] = { answers: response.answers, ...(abstained.length ? { abstained } : {}) };
		result.path.push(stage.id);
		if (abstained.length) {
			result.outcome = "abstained";
			result.stopped_at = stage.id;
			return result;
		}
	}
	return result;
}

// ─── few-shot examples from labeled rows ────────────────────────────────────

/**
 * Pick up to `limit` examples from already-labeled records, round-robin across answer values
 * so a dominant class does not crowd out the rest. `answerFields` maps question id -> the
 * column holding its known answer; rows whose value is not a valid answer are skipped.
 */
export function selectExamples(
	records: SourceRecord[],
	stage: Pick<StageSpec, "questions" | "abstain">,
	answerFields: Record<string, string>,
	limit: number,
): Example[] {
	const parse = (qid: string, raw: unknown): string | boolean | number | undefined => {
		const question = stage.questions[qid];
		if (!question || raw === undefined || raw === null || raw === "") return undefined;
		if (question.type === "bool") {
			const text = String(raw).trim().toLowerCase();
			return ["true", "yes", "1"].includes(text) ? true : ["false", "no", "0"].includes(text) ? false : undefined;
		}
		if (question.type === "choice") return options(question, stage.abstain).includes(String(raw)) ? String(raw) : undefined;
		const level = Number(raw);
		return Number.isInteger(level) && level >= 0 && level < (question.criteria as string[]).length ? level : undefined;
	};
	const groups = new Map<string, Example[]>();
	for (const record of records) {
		const answers: Example["answers"] = {};
		let complete = true;
		for (const [qid, column] of Object.entries(answerFields)) {
			const value = parse(qid, record.source[column]);
			if (value === undefined) {
				complete = false;
				break;
			}
			answers[qid] = value;
		}
		if (!complete || !Object.keys(answers).length) continue;
		const state = { ...record.state };
		for (const column of Object.values(answerFields)) delete state[column];
		const key = JSON.stringify(answers);
		groups.set(key, [...(groups.get(key) ?? []), { record: state, answers }]);
	}
	const picked: Example[] = [];
	const queues = [...groups.values()];
	while (picked.length < limit && queues.some((queue) => queue.length)) {
		for (const queue of queues) {
			const next = queue.shift();
			if (next && picked.length < limit) picked.push(next);
		}
	}
	return picked;
}

// ─── reporting ──────────────────────────────────────────────────────────────

export function chainRecordJson(result: ChainResult): Record<string, unknown> {
	const stages: Record<string, unknown> = {};
	for (const [id, stage] of Object.entries(result.stages)) {
		stages[id] = stage.answers
			? {
					answers: Object.fromEntries(Object.entries(stage.answers).map(([q, a]) => [q, withCalibration(a)])),
					...(stage.abstained ? { abstained: stage.abstained } : {}),
				}
			: stage;
	}
	return {
		index: result.record.index,
		line: result.record.line,
		...(result.id === undefined ? {} : { id: result.id }),
		outcome: result.outcome,
		...(result.stopped_at ? { stopped_at: result.stopped_at } : {}),
		stages,
	};
}

export function chainCsv(results: ChainResult[], stages: StageSpec[]): string {
	const header = ["index", "line", "id", "outcome", "stopped_at"];
	const columns: { stage: string; question: string; type: QuestionType }[] = [];
	for (const stage of stages) {
		for (const [question, spec] of Object.entries(stage.questions)) {
			columns.push({ stage: stage.id, question, type: spec.type });
			header.push(`${stage.id}.${question}`, `${stage.id}.${question}_confidence`);
			if (spec.type === "choice") header.push(`${stage.id}.${question}_margin`);
		}
	}
	header.push("abstained", "error");
	const lines = [header.join(",")];
	for (const result of results) {
		const row: unknown[] = [result.record.index, result.record.line, result.id, result.outcome, result.stopped_at ?? ""];
		for (const column of columns) {
			const answer = result.stages[column.stage]?.answers?.[column.question];
			row.push(answer ? answerValue(answer) : "", answer ? Math.round(confidenceOf(answer) * 1000) / 1000 : "");
			if (column.type === "choice") row.push(answer ? (calibrationOf(answer)?.margin ?? "") : "");
		}
		const abstained = Object.entries(result.stages).flatMap(([stage, r]) => (r.abstained ?? []).map((q) => `${stage}.${q}`));
		const error = Object.values(result.stages).find((r) => r.error)?.error ?? "";
		row.push(abstained.join(";"), error);
		lines.push(row.map(csvCell).join(","));
	}
	return `${lines.join("\n")}\n`;
}

export interface ChainSummary {
	total: number;
	outcomes: Record<Outcome, number>;
	stopped_at: Record<string, Partial<Record<Exclude<Outcome, "complete">, number>>>;
	paths: Record<string, number>;
	stages: Record<string, unknown>;
	low_confidence: unknown[];
}

/** Counts per outcome, per stage (reached / skipped / filtered / abstained / errors) and per path. */
export function summarizeChain(results: ChainResult[], stages: StageSpec[], minConfidence: number, maxLow = 10): ChainSummary {
	const outcomes: Record<Outcome, number> = { complete: 0, filtered: 0, abstained: 0, error: 0 };
	const stoppedAt: ChainSummary["stopped_at"] = {};
	const paths: Record<string, number> = {};
	for (const result of results) {
		outcomes[result.outcome]++;
		if (result.stopped_at && result.outcome !== "complete") {
			const counts = (stoppedAt[result.stopped_at] ??= {});
			counts[result.outcome] = (counts[result.outcome] ?? 0) + 1;
		}
		const key =
			(result.path.join(">") || "(none)") +
			(result.outcome === "complete" ? "" : ` | ${result.outcome}@${result.stopped_at}`);
		paths[key] = (paths[key] ?? 0) + 1;
	}
	const perStage: Record<string, unknown> = {};
	const low: unknown[] = [];
	for (const stage of stages) {
		const answered: DecisionResult[] = [];
		let skipped = 0;
		let reached = 0;
		let errors = 0;
		for (const result of results) {
			const stageResult = result.stages[stage.id];
			if (stageResult?.skipped) skipped++;
			if (stageResult && !stageResult.skipped) reached++;
			if (stageResult?.error) errors++;
			if (stageResult?.answers) {
				answered.push({ record: result.record, id: result.id, answers: stageResult.answers, abstained: stageResult.abstained });
			}
		}
		const summary = summarize(answered, minConfidence, maxLow);
		perStage[stage.id] = {
			reached,
			...(skipped ? { skipped } : {}),
			filtered: stoppedAt[stage.id]?.filtered ?? 0,
			abstained: stoppedAt[stage.id]?.abstained ?? 0,
			errors,
			questions: summary.questions,
		};
		low.push(...summary.lowConfidence.map((entry) => ({ stage: stage.id, ...entry })));
	}
	low.sort((a: any, b: any) => a.confidence - b.confidence);
	return {
		total: results.length,
		outcomes,
		stopped_at: stoppedAt,
		paths: Object.fromEntries(Object.entries(paths).sort((a, b) => b[1] - a[1])),
		stages: perStage,
		low_confidence: low.slice(0, maxLow),
	};
}
