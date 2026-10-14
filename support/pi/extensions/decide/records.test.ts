import assert from "node:assert/strict";
import { test } from "node:test";
import { chunkDocument, detectFormat, extractRecords, parseDelimited, summarize, toCsv } from "./records.ts";

const opts = { chunkChars: 6000, documentName: "doc.md" };

test("detectFormat maps extensions", () => {
	assert.equal(detectFormat("a/b.CSV"), "csv");
	assert.equal(detectFormat("x.tsv"), "tsv");
	assert.equal(detectFormat("x.jsonl"), "ndjson");
	assert.equal(detectFormat("x.log"), "lines");
	assert.equal(detectFormat("notes.md"), "document");
	assert.equal(detectFormat("README"), "document");
});

test("parseDelimited handles quotes, embedded newlines, CRLF and BOM", () => {
	const rows = parseDelimited('﻿a,b\r\n1,"x, ""y"""\r\n2,"multi\nline"\n\n3,z', ",");
	assert.deepEqual(
		rows.map((r) => [r.cells, r.line]),
		[
			[["a", "b"], 1],
			[["1", 'x, "y"'], 2],
			[["2", "multi\nline"], 3],
			[["3", "z"], 6],
		],
	);
});

test("csv records keep the full row in source and filtered fields in state", () => {
	const { records, columns, parseErrors } = extractRecords("id,text,extra\n7,hello,x\n8,bye\n", {
		...opts,
		format: "csv",
		fields: ["text"],
	});
	assert.deepEqual(columns, ["id", "text", "extra"]);
	assert.deepEqual(records[0].state, { text: "hello" });
	assert.equal(records[0].source.id, "7");
	assert.equal(records[1].line, 3);
	assert.equal(parseErrors.length, 1);
});

test("tsv, ndjson, lines and json arrays", () => {
	assert.deepEqual(extractRecords("a\tb\n1\t2\n", { ...opts, format: "tsv" }).records[0].state, { a: "1", b: "2" });
	const nd = extractRecords('{"a":1}\n\nnot json\n[1,2]\n', { ...opts, format: "ndjson" });
	assert.deepEqual(
		nd.records.map((r) => [r.line, r.state]),
		[
			[1, { a: 1 }],
			[4, { value: [1, 2] }],
		],
	);
	assert.equal(nd.parseErrors[0].line, 3);
	const lines = extractRecords("first\n\nthird\n", { ...opts, format: "lines" });
	assert.deepEqual(lines.records.map((r) => r.state), [
		{ line: 1, text: "first" },
		{ line: 3, text: "third" },
	]);
	assert.equal(extractRecords('[{"a":1},{"a":2}]', { ...opts, format: "json" }).records.length, 2);
});

test("documents chunk on paragraph boundaries with start lines", () => {
	const text = "# Title\n\nPara one.\n\n\nPara two\ncontinues.\n";
	const chunks = chunkDocument(text, 20);
	assert.deepEqual(chunks, [
		{ text: "# Title\n\nPara one.", line: 1 },
		{ text: "Para two\ncontinues.", line: 6 },
	]);
	const { records } = extractRecords(text, { ...opts, format: "document", chunkChars: 20 });
	assert.deepEqual(records[1].state, { document: "doc.md", chunk: 2, of: 2, text: "Para two\ncontinues." });
});

test("oversized paragraphs are hard-split under the limit", () => {
	const chunks = chunkDocument(`${"x".repeat(25)}\n${"y".repeat(5)}`, 10);
	assert.ok(chunks.every((c) => c.text.length <= 10));
	assert.equal(chunks.map((c) => c.text.replace(/\n/g, "")).join(""), "x".repeat(25) + "y".repeat(5));
});

test("summarize aggregates per question type and ranks low confidence", () => {
	const record = (index: number) => ({ index, line: index + 2, state: { text: `row ${index}` }, source: {} });
	const results = [
		{
			record: record(0),
			id: "a",
			answers: {
				topic: { type: "choice" as const, choice: "bug", probabilities: { bug: 0.9, feature: 0.1 }, confidence: 0.8 },
				urgent: { type: "bool" as const, probability: 0.55 },
				severity: { type: "score" as const, score: 2.4, confidence: 0.7 },
			},
		},
		{
			record: record(1),
			answers: {
				topic: { type: "choice" as const, choice: "feature", probabilities: { bug: 0.4, feature: 0.6 }, confidence: 0.2 },
				urgent: { type: "bool" as const, probability: 0.05 },
				severity: { type: "score" as const, score: 0.6, confidence: 0.9 },
			},
		},
		{ record: record(2), error: "boom" },
	];
	const summary = summarize(results, 0.5);
	assert.equal(summary.failed, 1);
	assert.deepEqual((summary.questions.topic as any).counts, { bug: 1, feature: 1 });
	assert.equal((summary.questions.urgent as any).true, 1);
	assert.equal((summary.questions.severity as any).max, 2.4);
	assert.deepEqual(
		summary.lowConfidence.map((l) => [l.question, l.index]),
		[
			["urgent", 0],
			["topic", 1],
		],
	);
	const csv = toCsv(results, ["topic", "urgent"]);
	assert.equal(csv.split("\n")[0], "index,line,id,topic,topic_confidence,urgent,urgent_confidence,error");
	assert.equal(csv.split("\n")[1], "0,2,a,bug,0.8,true,0.1,");
	assert.equal(csv.split("\n")[3], "2,4,,,,,,boom");
});
