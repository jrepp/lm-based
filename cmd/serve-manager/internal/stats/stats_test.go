package stats

import (
	"testing"
	"time"
)

func TestParsePrometheusMetrics(t *testing.T) {
	metrics := ParsePrometheusMetrics(`
# HELP llamacpp:prompt_tokens_total Total prompt tokens
llamacpp:prompt_tokens_total 120
llamacpp:tokens_predicted_total{model="qwen"} 42
llamacpp:bad_value nope
not_enough_fields
`)

	if got := metrics["llamacpp:prompt_tokens_total"]; got != 120 {
		t.Fatalf("prompt tokens = %v, want 120", got)
	}
	if got := metrics["llamacpp:tokens_predicted_total"]; got != 42 {
		t.Fatalf("predicted tokens = %v, want 42", got)
	}
	if _, ok := metrics["llamacpp:bad_value"]; ok {
		t.Fatal("malformed metric value should be ignored")
	}
}

func TestBuildSnapshot(t *testing.T) {
	base := time.Unix(1_700_000_000, 0).UTC()
	samples := []Sample{
		{
			At: base,
			Metrics: map[string]float64{
				"llamacpp:prompt_tokens_total":            100,
				"llamacpp:tokens_predicted_total":         200,
				"llamacpp:prompt_seconds_total":           5,
				"llamacpp:tokens_predicted_seconds_total": 10,
			},
		},
		{
			At: base.Add(time.Second),
			Metrics: map[string]float64{
				"llamacpp:prompt_tokens_total":            130,
				"llamacpp:tokens_predicted_total":         260,
				"llamacpp:prompt_seconds_total":           8,
				"llamacpp:tokens_predicted_seconds_total": 14,
				"llamacpp:requests_processing":            1,
			},
			Slots: []SlotSample{
				{
					ID:                     1,
					NCtx:                   262144,
					Speculative:            true,
					IsProcessing:           true,
					NPromptTokens:          1000,
					NPromptTokensProcessed: 900,
					NPromptTokensCache:     800,
					NextToken: []struct {
						NRemain  int `json:"n_remain"`
						NDecoded int `json:"n_decoded"`
					}{
						{NRemain: 20, NDecoded: 3},
						{NRemain: 10, NDecoded: 4},
					},
					Params: SlotParams{
						SpeculativeTypes: "none,draft-mtp",
					},
				},
			},
		},
	}

	snapshot := BuildSnapshot("http://127.0.0.1:8001", time.Second, samples)

	if snapshot.SampleCount != 2 {
		t.Fatalf("sample count = %d, want 2", snapshot.SampleCount)
	}
	if got := snapshot.Rates["prompt_tokens_per_second"]; got != 30 {
		t.Fatalf("prompt token rate = %v, want 30", got)
	}
	if got := snapshot.Rates["predicted_tokens_per_second"]; got != 60 {
		t.Fatalf("predicted token rate = %v, want 60", got)
	}
	if got := snapshot.Gauges["llamacpp:requests_processing"]; got != 1 {
		t.Fatalf("requests processing = %v, want 1", got)
	}
	if len(snapshot.Slots) != 1 {
		t.Fatalf("slot count = %d, want 1", len(snapshot.Slots))
	}
	slot := snapshot.Slots[0]
	if slot.NDecoded != 7 || slot.NRemain != 30 {
		t.Fatalf("slot next token totals = decoded %d remain %d, want decoded 7 remain 30", slot.NDecoded, slot.NRemain)
	}
	if !slot.Speculative || slot.NCtx != 262144 {
		t.Fatalf("slot summary = %+v, want speculative with native context", slot)
	}
	if !slot.MTPActive || slot.DraftType != "draft-mtp" {
		t.Fatalf("slot mtp fields = %+v, want active draft-mtp", slot)
	}
}

func TestTrimWindow(t *testing.T) {
	base := time.Unix(1_700_000_000, 0).UTC()
	samples := []Sample{
		{At: base},
		{At: base.Add(500 * time.Millisecond)},
		{At: base.Add(1500 * time.Millisecond)},
	}

	trimmed := TrimWindow(samples, base.Add(1500*time.Millisecond), time.Second)
	if len(trimmed) != 2 {
		t.Fatalf("trimmed count = %d, want 2", len(trimmed))
	}
	if !trimmed[0].At.Equal(base.Add(500 * time.Millisecond)) {
		t.Fatalf("first retained sample = %s, want %s", trimmed[0].At, base.Add(500*time.Millisecond))
	}
}

func TestHistoryBucketsAndSummaries(t *testing.T) {
	base := time.Unix(1_700_000_000, 0).UTC()
	history := NewHistory(time.Second, 10*time.Second)
	for i := 0; i < 3; i++ {
		history.Observe(Sample{
			At: base.Add(time.Duration(i) * time.Second),
			Metrics: map[string]float64{
				"llamacpp:prompt_tokens_total":    float64(100 + i*10),
				"llamacpp:tokens_predicted_total": float64(200 + i*20),
				"llamacpp:requests_processing":    1,
			},
			Slots: []SlotSample{
				{
					ID:                     1,
					Speculative:            true,
					NPromptTokens:          1000 + i,
					NPromptTokensCache:     800 + i,
					Params:                 SlotParams{SpeculativeTypes: "none,draft-mtp"},
					NPromptTokensProcessed: 900,
				},
			},
		})
	}

	stats := history.Stats()
	if stats.BucketCount != 3 {
		t.Fatalf("bucket count = %d, want 3", stats.BucketCount)
	}
	if got := stats.Rates["predicted_tokens_per_second"].Mean; got != 20 {
		t.Fatalf("decode rate mean = %v, want 20", got)
	}
	if got := stats.Slots["mtp_active"].Mean; got != 1 {
		t.Fatalf("mtp active mean = %v, want 1", got)
	}

	buckets := history.Buckets()
	if len(buckets) != 3 {
		t.Fatalf("buckets = %d, want 3", len(buckets))
	}
	if buckets[1].Rates["prompt_tokens_per_second"].Last != 10 {
		t.Fatalf("bucket prompt rate = %v, want 10", buckets[1].Rates["prompt_tokens_per_second"].Last)
	}
}

func TestHistoryDeltaDeltaTrendCompaction(t *testing.T) {
	base := time.Unix(1_700_000_000, 0).UTC()
	history := NewHistory(time.Second, time.Hour)
	history.ConfigureTrend(3*time.Second, 8)
	for i := 0; i < 20; i++ {
		predicted := 100 + i*10
		if i == 8 {
			predicted += 80
		}
		history.Observe(Sample{
			At: base.Add(time.Duration(i) * time.Second),
			Metrics: map[string]float64{
				"llamacpp:tokens_predicted_total": float64(predicted),
				"llamacpp:prompt_tokens_total":    float64(50 + i),
			},
			Slots: []SlotSample{
				{
					ID:                 1,
					IsProcessing:       true,
					NPromptTokens:      1000 + i,
					NPromptTokensCache: 900,
				},
			},
		})
	}

	trend := history.trend.stats()
	if trend.PointCount > 8 {
		t.Fatalf("trend points = %d, want <= 8", trend.PointCount)
	}
	if trend.DroppedCount == 0 {
		t.Fatal("expected compacted trend to drop redundant points")
	}
	if got := trend.Points[len(trend.Points)-1].At; got != base.Add(19*time.Second).Format(time.RFC3339Nano) {
		t.Fatalf("last trend point = %s, want newest sample", got)
	}
}
