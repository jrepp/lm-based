import assert from "node:assert/strict";
import { test } from "node:test";
import {
	abstainedQuestions,
	buildState,
	chainCsv,
	type Classify,
	decideRecord,
	effectiveQuestions,
	selectExamples,
	type StageSpec,
	summarizeChain,
	validateStages,
} from "./chain.ts";
import { calibrationOf, extractRecords, type SourceRecord } from "./records.ts";

const record = (index: number, state: Record<string, unknown>): SourceRecord => ({ index, line: index + 2, state, source: state });

// The tax use: is a bank row a tax-relevant household payment, then which category.
const taxStages = (): StageSpec[] => [
	{
		id: "relevance",
		questions: {
			tax_relevant: {
				type: "bool",
				instructions:
					"Is this a tax-relevant household payment (not a transfer between own accounts, utility, loan or card payment)?",
			},
		},
	},
	{
		id: "category",
		when: { stage: "relevance", question: "tax_relevant", is: true, min_probability: 0.8 },
		questions: {
			category: {
				type: "choice",
				instructions: "Which tax category is this payment?",
				criteria: { medical: "doctors, pharmacy", charity: "donations", childcare: "daycare, nanny" },
			},
		},
		abstain: { choice: "unsure" },
	},
];

const choice = (name: string, probabilities: Record<string, number>, confidence = 0.5) => ({
	type: "choice" as const,
	choice: name,
	probabilities,
	confidence,
});

/** A fake kev keyed on the record's payee. */
const fakeKev: Classify = async (state, questions) => {
	const payee = String((state.record as any)?.payee ?? state.payee);
	if (payee === "boom") return { error: "HTTP 500" };
	if ("tax_relevant" in questions) {
		const p = { "own transfer": 0.05, "pharmacy": 0.95, "mystery": 0.93, "maybe clinic": 0.7 }[payee] ?? 0.5;
		return { answers: { tax_relevant: { type: "bool", probability: p } } };
	}
	assert.ok("unsure" in (questions.category.criteria as Record<string, string>), "abstain option is offered");
	if (payee === "mystery") return { answers: { category: choice("unsure", { medical: 0.2, charity: 0.2, childcare: 0.1, unsure: 0.5 }) } };
	return { answers: { category: choice("medical", { medical: 0.7, charity: 0.2, childcare: 0.05, unsure: 0.05 }, 0.6) } };
};

test("validateStages accepts the tax chain and rejects bad graphs", () => {
	validateStages(taxStages());
	const bad: [string, (stages: StageSpec[]) => void, RegExp][] = [
		["forward reference", (s) => { s[1].when = { stage: "later", question: "x" }; }, /not an earlier stage/],
		["self reference", (s) => { s[1].when = { stage: "category", question: "category" }; }, /not an earlier stage/],
		["unknown question", (s) => { s[1].when = { stage: "relevance", question: "nope" }; }, /unknown question/],
		["first stage filter", (s) => { s[0].when = { stage: "relevance", question: "tax_relevant" }; }, /first stage/],
		["duplicate id", (s) => { s[1].id = "relevance"; }, /duplicate/],
		["bad id", (s) => { s[1].id = "Category!"; }, /snake_case/],
		["bool is string", (s) => { s[1].when = { stage: "relevance", question: "tax_relevant", is: "yes" }; }, /true or false/],
		["abstain without choice", (s) => { s[0].abstain = { choice: "unsure" }; }, /needs a choice question/],
		["threshold range", (s) => { s[1].abstain = { min_margin: 2 }; }, /0 to 1/],
		["example option", (s) => { s[1].examples = [{ record: {}, answers: { category: "rent" } }]; }, /one of the options/],
		["example question", (s) => { s[1].examples = [{ record: {}, answers: { other: "x" } }]; }, /unknown question/],
		["too many stages", (s) => { for (let i = 0; i < 6; i++) s.push({ id: `s${i}`, questions: s[0].questions }); }, /at most 6/],
	];
	for (const [name, mutate, error] of bad) {
		const stages = taxStages();
		mutate(stages);
		assert.throws(() => validateStages(stages), error, name);
	}
	const branch = taxStages();
	branch[1].when = { stage: "relevance", question: "tax_relevant", is: "unsure" as any };
	assert.throws(() => validateStages(branch), /true or false/);
	const onChoice = taxStages();
	onChoice.push({ id: "detail", when: { stage: "category", question: "category", is: ["medical", "unsure"] }, questions: onChoice[0].questions });
	validateStages(onChoice); // the abstain option is a valid filter value
});

test("effectiveQuestions adds the abstain option and buildState keeps the legacy shape", () => {
	const [, category] = taxStages();
	assert.deepEqual(Object.keys(effectiveQuestions(category).category.criteria as object), ["medical", "charity", "childcare", "unsure"]);
	const relevance = taxStages()[0];
	assert.equal(effectiveQuestions(relevance), relevance.questions); // no abstain: questions unchanged
	assert.deepEqual(buildState({ payee: "x" }), { payee: "x" });
	assert.deepEqual(buildState({ payee: "x" }, "bank rows"), { task_context: "bank rows", payee: "x" });
	const withExamples = buildState({ payee: "x" }, "bank rows", [{ record: { payee: "cvs" }, answers: { category: "medical" } }]);
	assert.deepEqual(Object.keys(withExamples), ["task_context", "note", "labeled_examples", "record"]);
	assert.deepEqual(withExamples.record, { payee: "x" });
});

test("records flow through the stages and stop where they are filtered, abstain or fail", async () => {
	const stages = taxStages();
	const rows = ["own transfer", "pharmacy", "mystery", "maybe clinic", "boom"].map((payee, i) => record(i, { payee }));
	const results = await Promise.all(rows.map((r) => decideRecord(r, stages, fakeKev, r.state.payee)));
	assert.deepEqual(
		results.map((r) => [r.id, r.outcome, r.stopped_at ?? null, r.path.join(">")]),
		[
			["own transfer", "filtered", "category", "relevance"],
			["pharmacy", "complete", null, "relevance>category"],
			["mystery", "abstained", "category", "relevance>category"],
			["maybe clinic", "filtered", "category", "relevance"], // true, but below min_probability 0.8
			["boom", "error", "relevance", ""],
		],
	);
	assert.deepEqual(results[2].stages.category.abstained, ["category"]);

	const summary = summarizeChain(results, stages, 0.5);
	assert.deepEqual(summary.outcomes, { complete: 1, filtered: 2, abstained: 1, error: 1 });
	assert.deepEqual(summary.stopped_at, { category: { filtered: 2, abstained: 1 }, relevance: { error: 1 } });
	assert.deepEqual(summary.paths, {
		"relevance | filtered@category": 2,
		"relevance>category": 1,
		"relevance>category | abstained@category": 1,
		"(none) | error@relevance": 1,
	});
	const category = summary.stages.category as any;
	assert.equal(category.reached, 2);
	assert.equal(category.filtered, 2);
	assert.equal(category.abstained, 1);
	assert.equal(category.questions.category.options, 4);
	assert.equal(category.questions.category.uniform_probability, 0.25);
	assert.equal(category.questions.category.abstained, 1);
	assert.equal((summary.stages.relevance as any).errors, 1);
	assert.ok(summary.low_confidence.some((entry: any) => entry.stage === "category" && entry.abstained));

	const csv = chainCsv(results, stages).split("\n");
	assert.equal(
		csv[0],
		"index,line,id,outcome,stopped_at,relevance.tax_relevant,relevance.tax_relevant_confidence,category.category,category.category_confidence,category.category_margin,abstained,error",
	);
	assert.equal(csv[2], "1,3,pharmacy,complete,,true,0.9,medical,0.6,0.5,,");
	assert.equal(csv[5], "4,6,boom,error,relevance,,,,,,,HTTP 500");
});

test("otherwise: continue makes branches; thresholds abstain without an extra option", async () => {
	const stages: StageSpec[] = [
		taxStages()[0],
		{ ...taxStages()[1], otherwise: "continue", abstain: { min_margin: 0.3 } },
		{
			id: "transfer_kind",
			when: { stage: "relevance", question: "tax_relevant", is: false },
			questions: { kind: { type: "choice", instructions: "What kind?", criteria: { transfer: "own accounts", loan: "loan or card" } } },
		},
	];
	validateStages(stages);
	const classify: Classify = async (state, questions) => {
		if ("tax_relevant" in questions) return { answers: { tax_relevant: { type: "bool", probability: state.payee === "own transfer" ? 0.1 : 0.95 } } };
		if ("kind" in questions) return { answers: { kind: choice("transfer", { transfer: 0.9, loan: 0.1 }, 0.8) } };
		return { answers: { category: choice("medical", { medical: 0.5, charity: 0.4, childcare: 0.1 }, 0.25) } };
	};
	const transfer = await decideRecord(record(0, { payee: "own transfer" }), stages, classify);
	assert.equal(transfer.outcome, "complete");
	assert.deepEqual(transfer.stages.category, { skipped: true });
	assert.deepEqual(transfer.path, ["relevance", "transfer_kind"]);
	const close = await decideRecord(record(1, { payee: "pharmacy" }), stages, classify);
	assert.equal(close.outcome, "abstained"); // margin 0.1 < 0.3
	assert.equal(close.stopped_at, "category");
	const summary = summarizeChain([transfer, close], stages, 0.5);
	assert.equal((summary.stages.category as any).skipped, 1);
	assert.equal((summary.stages.transfer_kind as any).reached, 1);
});

test("abstain thresholds and calibration figures", () => {
	const stage: StageSpec = { id: "s", questions: { ok: { type: "bool", instructions: "?" } }, abstain: { min_confidence: 0.5 } };
	assert.deepEqual(abstainedQuestions(stage, { ok: { type: "bool", probability: 0.7 } }), ["ok"]);
	assert.deepEqual(abstainedQuestions(stage, { ok: { type: "bool", probability: 0.9 } }), []);
	assert.deepEqual(abstainedQuestions({ ...stage, abstain: undefined }, { ok: { type: "bool", probability: 0.5 } }), []);
	assert.deepEqual(calibrationOf(choice("b", { a: 0.3, b: 0.45, c: 0.25 })), {
		top_probability: 0.45,
		runner_up: "a",
		runner_up_probability: 0.3,
		margin: 0.15,
		options: 3,
	});
	assert.deepEqual(calibrationOf({ type: "bool", probability: 0.2 }), { top_probability: 0.8, margin: 0.6 });
	assert.equal(calibrationOf({ type: "score", score: 1, confidence: 0.4 }), undefined);
});

test("selectExamples picks labeled rows round-robin across answers and drops the label from the record", () => {
	const ndjson = [
		{ payee: "cvs", amount: 12, category: "medical" },
		{ payee: "walgreens", amount: 9, category: "medical" },
		{ payee: "kaiser", amount: 40, category: "medical" },
		{ payee: "red cross", amount: 50, category: "charity" },
		{ payee: "landlord", amount: 2000, category: "rent" }, // not an option: skipped
		{ payee: "unlabeled", amount: 1, category: "" },
		{ payee: "daycare", amount: 900, category: "childcare" },
	]
		.map((row) => JSON.stringify(row))
		.join("\n");
	const { records } = extractRecords(ndjson, { format: "ndjson", chunkChars: 6000, documentName: "x" });
	const examples = selectExamples(records, taxStages()[1], { category: "category" }, 4);
	assert.deepEqual(
		examples.map((e) => [e.record.payee, e.answers.category]),
		[
			["cvs", "medical"],
			["red cross", "charity"],
			["daycare", "childcare"],
			["walgreens", "medical"],
		],
	);
	assert.ok(!("category" in examples[0].record));
	const bools = selectExamples(
		extractRecords("payee,relevant\na,yes\nb,no\nc,maybe\n", { format: "csv", chunkChars: 6000, documentName: "x" }).records,
		taxStages()[0],
		{ tax_relevant: "relevant" },
		10,
	);
	assert.deepEqual(bools.map((e) => e.answers.tax_relevant), [true, false]);
});
