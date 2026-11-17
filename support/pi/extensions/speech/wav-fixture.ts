export function wav(channels = 1, seconds = 1): Buffer {
	const frames = 24000 * seconds, data = Buffer.alloc(44 + frames * channels * 2);
	data.write("RIFF", 0); data.writeUInt32LE(data.length - 8, 4); data.write("WAVEfmt ", 8);
	data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(channels, 22);
	data.writeUInt32LE(24000, 24); data.writeUInt32LE(24000 * channels * 2, 28);
	data.writeUInt16LE(channels * 2, 32); data.writeUInt16LE(16, 34); data.write("data", 36); data.writeUInt32LE(data.length - 44, 40);
	return data;
}
