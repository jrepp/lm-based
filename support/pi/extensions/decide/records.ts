/**
 * Record extraction and result summaries for the decide_records tool.
 *
 * Pure functions with no Pi imports so they can be tested with plain node:
 *   node --test support/pi/extensions/decide/records.test.ts
 */

export type Format = "csv" | "tsv" | "ndjson" | "json" | "lines" | "document";

export interface SourceRecord {
	index: number; // 0-based position among extracted records
	line: number; // 1-based line in the source file where the record starts
	state: Record<string, unknown>; // what the decision model sees (after `fields`)
	source: Record<string, unknown>; // the full row, for id lookup
}

export interface ExtractOptions {
	format: Format;
	fields?: string[];
	chunkChars: number;
	documentName: string;
}

export interface ExtractResult {
	records: SourceRecord[];
	columns: string[];
	parseErrors: { line: number; message: string }[];
}

const EXTENSION_FORMATS: Record<string, Format> = {
	".csv": "csv",
	".tsv": "tsv",
	".tab": "tsv",
	".ndjson": "ndjson",
	".jsonl": "ndjson",
	".json": "json",
	".log": "lines",
};

export function detectFormat(filePath: string): Format {
	const dot = filePath.lastIndexOf(".");
	const ext = dot >= 0 ? filePath.slice(dot).toLowerCase() : "";
	return EXTENSION_FORMATS[ext] ?? "document";
}

/** RFC 4180 rows with the 1-based line each row starts on. Quoted fields may span lines. */
export function parseDelimited(text: string, delimiter: string): { cells: string[]; line: number }[] {
	const rows: { cells: string[]; line: number }[] = [];
	let cells: string[] = [];
	let field = "";
	let quoted = false;
	let line = 1;
	let rowLine = 1;
	let i = 0;
	if (text.charCodeAt(0) === 0xfeff) i = 1; // BOM
	for (; i < text.length; i++) {
		const ch = text[i];
		if (quoted) {
			if (ch === '"') {
				if (text[i + 1] === '"') {
					field += '"';
					i++;
				} else {
					quoted = false;
				}
			} else {
				if (ch === "\n") line++;
				field += ch;
			}
			continue;
		}
		if (ch === '"' && field === "") {
			quoted = true;
		} else if (ch === delimiter) {
			cells.push(field);
			field = "";
		} else if (ch === "\n" || ch === "\r") {
			if (ch === "\r" && text[i + 1] === "\n") i++;
			cells.push(field);
			if (cells.length > 1 || cells[0] !== "") rows.push({ cells, line: rowLine });
			cells = [];
			field = "";
			line++;
			rowLine = line;
		} else {
			field += ch;
		}
	}
	if (field !== "" || cells.length > 0) {
		cells.push(field);
		if (cells.length > 1 || cells[0] !== "") rows.push({ cells, line: rowLine });
	}
	return rows;
}

function pick(state: Record<string, unknown>, fields?: string[]): Record<string, unknown> {
	if (!fields?.length) return state;
	const out: Record<string, unknown> = {};
	for (const field of fields) if (field in state) out[field] = state[field];
	return out;
}

function asObject(value: unknown): Record<string, unknown> {
	return value !== null && typeof value === "object" && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: { value };
}

/** Split a document into paragraph-aligned chunks of at most `limit` characters. */
export function chunkDocument(text: string, limit: number): { text: string; line: number }[] {
	const chunks: { text: string; line: number }[] = [];
	let current = "";
	let currentLine = 1;
	let line = 1;
	const flush = () => {
		if (current.trim()) chunks.push({ text: current.trim(), line: currentLine });
		current = "";
	};
	for (const paragraph of text.split(/(\n[ \t]*\n+)/)) {
		const isSeparator = /^\n[ \t]*\n+$/.test(paragraph);
		if (!isSeparator && paragraph.trim()) {
			if (current && current.length + paragraph.length + 2 > limit) flush();
			if (!current) currentLine = line;
			if (paragraph.length > limit) {
				// A single oversized paragraph: hard-split on line boundaries, then characters.
				flush();
				let piece = "";
				let pieceLine = line;
				let offset = line;
				for (const row of paragraph.split("\n")) {
					if (piece && piece.length + row.length + 1 > limit) {
						chunks.push({ text: piece, line: pieceLine });
						piece = "";
					}
					if (!piece) pieceLine = offset;
					for (let start = 0; start < row.length; start += limit) {
						const slice = row.slice(start, start + limit);
						if (piece && piece.length + slice.length + 1 > limit) {
							chunks.push({ text: piece, line: pieceLine });
							piece = "";
							pieceLine = offset;
						}
						piece = piece ? `${piece}\n${slice}` : slice;
					}
					offset++;
				}
				if (piece.trim()) chunks.push({ text: piece, line: pieceLine });
			} else {
				current = current ? `${current}\n\n${paragraph}` : paragraph;
			}
		}
		line += (paragraph.match(/\n/g) ?? []).length;
	}
	flush();
	return chunks;
}

export function extractRecords(text: string, options: ExtractOptions): ExtractResult {
	const parseErrors: ExtractResult["parseErrors"] = [];
	const records: SourceRecord[] = [];
	let columns: string[] = [];
	const push = (line: number, state: Record<string, unknown>) =>
		records.push({ index: records.length, line, state: pick(state, options.fields), source: state });

	switch (options.format) {
		case "csv":
		case "tsv": {
			const rows = parseDelimited(text, options.format === "csv" ? "," : "\t");
			const header = rows.shift();
			if (!header) break;
			columns = header.cells.map((name, i) => name.trim() || `column_${i + 1}`);
			for (const row of rows) {
				if (row.cells.length !== columns.length) {
					parseErrors.push({
						line: row.line,
						message: `expected ${columns.length} fields, found ${row.cells.length}`,
					});
				}
				const state: Record<string, unknown> = {};
				columns.forEach((name, i) => {
					state[name] = row.cells[i] ?? "";
				});
				push(row.line, state);
			}
			break;
		}
		case "ndjson": {
			text.split(/\r?\n/).forEach((raw, i) => {
				if (!raw.trim()) return;
				try {
					push(i + 1, asObject(JSON.parse(raw)));
				} catch (error) {
					parseErrors.push({ line: i + 1, message: (error as Error).message });
				}
			});
			break;
		}
		case "json": {
			const value = JSON.parse(text);
			const items = Array.isArray(value) ? value : [value];
			items.forEach((item) => push(1, asObject(item)));
			break;
		}
		case "lines": {
			text.split(/\r?\n/).forEach((raw, i) => {
				if (raw.trim()) push(i + 1, { line: i + 1, text: raw });
			});
			break;
		}
		case "document": {
			const chunks = chunkDocument(text, options.chunkChars);
			chunks.forEach((chunk, i) =>
				push(chunk.line, { document: options.documentName, chunk: i + 1, of: chunks.length, text: chunk.text }),
			);
			break;
		}
	}
	if (!columns.length && records.length) columns = Object.keys(records[0].state);
	return { records, columns, parseErrors };
}

// ─── answers ────────────────────────────────────────────────────────────────

export type Answer =
	| { type: "choice"; choice: string; probabilities: Record<string, number>; confidence: number }
	| { type: "score"; score: number; confidence: number }
	| { type: "bool"; probability: number };

/** Normalized confidence in [0, 1]; for bool questions, distance from a coin flip. */
export function confidenceOf(answer: Answer): number {
	return answer.type === "bool" ? Math.abs(answer.probability * 2 - 1) : answer.confidence;
}

export function answerValue(answer: Answer): string | number | boolean {
	if (answer.type === "choice") return answer.choice;
	if (answer.type === "score") return answer.score;
	return answer.probability >= 0.5;
}

interface QuestionStats {
	type: Answer["type"];
	answered: number;
	confidenceSum: number;
	choices: Record<string, number>;
	trueCount: number;
	probabilitySum: number;
	scores: number[];
}

export interface Summary {
	total: number;
	classified: number;
	failed: number;
	questions: Record<string, unknown>;
	lowConfidence: { index: number; line: number; id?: unknown; question: string; answer: unknown; confidence: number; preview: string }[];
}

export function preview(state: Record<string, unknown>, length = 120): string {
	const text = typeof state.text === "string" ? state.text : JSON.stringify(state);
	const flat = text.replace(/\s+/g, " ").trim();
	return flat.length > length ? `${flat.slice(0, length - 1)}…` : flat;
}

export function summarize(
	results: { record: SourceRecord; id?: unknown; answers?: Record<string, Answer>; error?: string }[],
	minConfidence: number,
	maxLowConfidence = 10,
): Summary {
	const stats = new Map<string, QuestionStats>();
	const low: Summary["lowConfidence"] = [];
	let failed = 0;
	for (const result of results) {
		if (!result.answers) {
			failed++;
			continue;
		}
		for (const [question, answer] of Object.entries(result.answers)) {
			let s = stats.get(question);
			if (!s) {
				s = { type: answer.type, answered: 0, confidenceSum: 0, choices: {}, trueCount: 0, probabilitySum: 0, scores: [] };
				stats.set(question, s);
			}
			const confidence = confidenceOf(answer);
			s.answered++;
			s.confidenceSum += confidence;
			if (answer.type === "choice") s.choices[answer.choice] = (s.choices[answer.choice] ?? 0) + 1;
			if (answer.type === "bool") {
				s.probabilitySum += answer.probability;
				if (answer.probability >= 0.5) s.trueCount++;
			}
			if (answer.type === "score") s.scores.push(answer.score);
			if (confidence < minConfidence) {
				low.push({
					index: result.record.index,
					line: result.record.line,
					...(result.id === undefined ? {} : { id: result.id }),
					question,
					answer: answerValue(answer),
					confidence: Math.round(confidence * 1000) / 1000,
					preview: preview(result.record.state),
				});
			}
		}
	}
	const round = (value: number) => Math.round(value * 1000) / 1000;
	const questions: Record<string, unknown> = {};
	for (const [question, s] of stats) {
		const base = { type: s.type, answered: s.answered, mean_confidence: round(s.confidenceSum / s.answered) };
		if (s.type === "choice") {
			questions[question] = { ...base, counts: Object.fromEntries(Object.entries(s.choices).sort((a, b) => b[1] - a[1])) };
		} else if (s.type === "bool") {
			questions[question] = { ...base, true: s.trueCount, false: s.answered - s.trueCount, mean_probability: round(s.probabilitySum / s.answered) };
		} else {
			const sorted = [...s.scores].sort((a, b) => a - b);
			const histogram: Record<string, number> = {};
			for (const score of sorted) histogram[String(Math.round(score))] = (histogram[String(Math.round(score))] ?? 0) + 1;
			questions[question] = {
				...base,
				mean: round(sorted.reduce((sum, v) => sum + v, 0) / sorted.length),
				min: round(sorted[0]),
				median: round(sorted[Math.floor(sorted.length / 2)]),
				max: round(sorted[sorted.length - 1]),
				histogram,
			};
		}
	}
	low.sort((a, b) => a.confidence - b.confidence);
	return {
		total: results.length,
		classified: results.length - failed,
		failed,
		questions,
		lowConfidence: low.slice(0, maxLowConfidence),
	};
}

// ─── output ─────────────────────────────────────────────────────────────────

function csvCell(value: unknown): string {
	const text = value === undefined || value === null ? "" : typeof value === "string" ? value : JSON.stringify(value);
	return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** CSV header + rows: record position, the id column, then one or two columns per question. */
export function toCsv(
	results: { record: SourceRecord; id?: unknown; answers?: Record<string, Answer>; error?: string }[],
	questions: string[],
): string {
	const header = ["index", "line", "id"];
	for (const question of questions) header.push(question, `${question}_confidence`);
	header.push("error");
	const lines = [header.join(",")];
	for (const result of results) {
		const row: unknown[] = [result.record.index, result.record.line, result.id];
		for (const question of questions) {
			const answer = result.answers?.[question];
			row.push(answer ? answerValue(answer) : "", answer ? Math.round(confidenceOf(answer) * 1000) / 1000 : "");
		}
		row.push(result.error ?? "");
		lines.push(row.map(csvCell).join(","));
	}
	return `${lines.join("\n")}\n`;
}
