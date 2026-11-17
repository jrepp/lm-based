import assert from "node:assert/strict";
import test from "node:test";
import { droppedPath, validateWav, voiceName } from "./voices.ts";

import { wav } from "./wav-fixture.ts";

test("terminal drag/drop paths are decoded without shell evaluation", () => {
	for (const input of ["'/tmp/my voice.wav'", '"/tmp/my voice.wav"', "/tmp/my\\ voice.wav", "file:///tmp/my%20voice.wav"]) assert.equal(droppedPath(input, "/"), "/tmp/my voice.wav");
	assert.equal(droppedPath("'$(touch bad).wav'", "/tmp"), "/tmp/$(touch bad).wav");
});

test("voice references require valid, bounded mono PCM16 and safe names", () => {
	assert.equal(validateWav(wav()), 1);
	assert.throws(() => validateWav(wav(2)), /mono/);
	assert.throws(() => validateWav(wav(1, 31)), /1–30/);
	assert.throws(() => validateWav(wav().subarray(0, 100)), /Truncated/);
	assert.throws(() => voiceName("../escape"), /Voice name/);
	assert.throws(() => voiceName(""), /Voice name/);
});
