package stats

import (
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"
)

// Captures from a real MLX service, including a cancelled generation. No live dependency.
func TestFlashLoopCapturedMetrics(t *testing.T) {
	metrics, err := os.ReadFile("testdata/flashloop.prom")
	if err != nil {
		t.Fatal(err)
	}
	slots, err := os.ReadFile("testdata/flashloop-slots.json")
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/metrics":
			w.Write(metrics)
		case "/slots":
			w.Write(slots)
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()
	sample, err := NewPoller(server.URL, time.Second).Poll()
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"llamacpp:prompt_tokens_total", "llamacpp:tokens_predicted_total", "llamacpp:prompt_seconds_total", "llamacpp:tokens_predicted_seconds_total"} {
		if sample.Metrics[name] <= 0 {
			t.Fatalf("missing positive counter %s", name)
		}
	}
	if len(sample.Slots) != 1 {
		t.Fatalf("slots = %v", sample.Slots)
	}
	slot := sample.Slots[0]
	if slot.IsProcessing || slot.NCtx != 3072 {
		t.Fatalf("incorrect idle MLX slot: %+v", slot)
	}
	snapshot := BuildSnapshot(server.URL, time.Second, []Sample{sample})
	if snapshot.Counters["llamacpp:tokens_predicted_total"] != sample.Metrics["llamacpp:tokens_predicted_total"] {
		t.Fatalf("generated token counter lost in dashboard snapshot: %+v", snapshot)
	}
}
