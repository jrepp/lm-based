package dashboard

import (
	"encoding/json"
	"lm-based/cmd/serve-manager/internal/stats"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestFleetDiscoversWorkersWithoutLoadingModels(t *testing.T) {
	worker := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/metrics":
			w.Write([]byte("llamacpp:tokens_predicted_total 42\n"))
		case "/slots":
			w.Write([]byte("[]"))
		default:
			t.Errorf("unexpected worker request %s", r.URL.Path)
			http.NotFound(w, r)
		}
	}))
	defer worker.Close()
	unsupported := httptest.NewServer(http.NotFoundHandler())
	defer unsupported.Close()
	swap := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/v1/models":
			w.Write([]byte(`{"data":[{"id":"qwen"},{"id":"ocr"},{"id":"kev"},{"id":"sleeping"}]}`))
		case "/running":
			json.NewEncoder(w).Encode(map[string]any{"running": []map[string]string{{"model": "qwen", "state": "ready", "proxy": worker.URL}, {"model": "ocr", "state": "ready", "proxy": worker.URL}, {"model": "kev", "state": "ready", "proxy": unsupported.URL}}})
		default:
			t.Errorf("unexpected swap request %s", r.URL.Path)
			http.NotFound(w, r)
		}
	}))
	defer swap.Close()
	handler, err := NewHandler(Config{SwapURL: swap.URL})
	if err != nil {
		t.Fatal(err)
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest("GET", "/api/models", nil))
	if response.Code != 200 {
		t.Fatal(response.Body.String())
	}
	var result struct {
		Models []modelView `json:"models"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if len(result.Models) != 4 {
		t.Fatal(result)
	}
	for _, i := range []int{0, 1} {
		if result.Models[i].Snapshot == nil {
			t.Fatalf("missing snapshot: %+v", result.Models[i])
		}
	}
	if result.Models[2].MetricsError == "" || result.Models[2].Snapshot != nil {
		t.Fatal("unsupported telemetry must be explicit")
	}
	if result.Models[3].State != "unloaded" || result.Models[3].Snapshot != nil {
		t.Fatal("unloaded model misrepresented")
	}
}

func TestFleetRetainsSnapshotAcrossFailureAndUnload(t *testing.T) {
	var unavailable atomic.Bool
	var unloaded atomic.Bool
	worker := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if unavailable.Load() {
			http.Error(w, "busy", 503)
			return
		}
		if r.URL.Path == "/metrics" {
			w.Write([]byte("llamacpp:tokens_predicted_total 42\n"))
		} else {
			w.Write([]byte("[]"))
		}
	}))
	defer worker.Close()
	swap := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/models" {
			w.Write([]byte(`{"data":[{"id":"qwen"}]}`))
			return
		}
		if unloaded.Load() {
			w.Write([]byte(`{"running":[]}`))
			return
		}
		json.NewEncoder(w).Encode(map[string]any{"running": []map[string]string{{"model": "qwen", "state": "ready", "proxy": worker.URL}}})
	}))
	defer swap.Close()
	f := &fleet{url: swap.URL, client: swap.Client(), histories: map[string]*modelHistory{}}
	poll := func() modelView {
		f.updated = time.Time{}
		response := httptest.NewRecorder()
		f.ServeHTTP(response, httptest.NewRequest("GET", "/api/models", nil))
		if response.Code != 200 {
			t.Fatal(response.Body.String())
		}
		var result struct {
			Models []modelView `json:"models"`
		}
		json.Unmarshal(response.Body.Bytes(), &result)
		return result.Models[0]
	}
	first := poll()
	history := f.histories["qwen"].history
	if first.Stale || first.Snapshot == nil || first.Snapshot.WindowSeconds != 30 {
		t.Fatal(first)
	}
	unavailable.Store(true)
	failed := poll()
	if !failed.Stale || failed.Snapshot == nil || failed.Snapshot.ObservedAt != first.Snapshot.ObservedAt {
		t.Fatal("failed poll discarded last good data")
	}
	unloaded.Store(true)
	absent := poll()
	if !absent.Stale || absent.State != "unloaded" || absent.Snapshot == nil {
		t.Fatal("unload discarded history")
	}
	unavailable.Store(false)
	unloaded.Store(false)
	recovered := poll()
	if recovered.Stale || recovered.Snapshot == nil || f.histories["qwen"].history != history {
		t.Fatal("recovery reset history")
	}
}

func TestRollingGaugesUseElapsedTime(t *testing.T) {
	start := time.Now()
	result := rollingAverages([]stats.Sample{
		{At: start, Slots: []stats.SlotSample{{NPromptTokens: 100, NPromptTokensCache: 20}}},
		{At: start.Add(10 * time.Second), Slots: []stats.SlotSample{{NPromptTokens: 400, NPromptTokensCache: 80}}},
		{At: start.Add(30 * time.Second), Slots: []stats.SlotSample{{NPromptTokens: 9999}}},
	})
	if result.Context != 300 || result.Cache != 60 {
		t.Fatalf("unexpected rolling gauges: %+v", result)
	}
}

func TestBoxPlotQuartilesAndRollingTotals(t *testing.T) {
	d := summarizeDistribution([]float64{4, 0, 3, 1, 2})
	if d.Min != 0 || d.Q1 != 1 || d.Median != 2 || d.Q3 != 3 || d.Max != 4 {
		t.Fatalf("incorrect quartiles: %+v", d)
	}
	if summarizeDistribution(nil) != nil {
		t.Fatal("missing data must not look like zero activity")
	}
	flat := summarizeDistribution([]float64{0, 0, 0})
	if flat.Median != 0 || flat.Count != 3 {
		t.Fatal(flat)
	}
	start := time.Now()
	r := rollingAverages([]stats.Sample{
		{At: start, Metrics: map[string]float64{"llamacpp:tokens_predicted_total": 100}},
		{At: start.Add(10 * time.Second), Metrics: map[string]float64{"llamacpp:tokens_predicted_total": 120}},
		{At: start.Add(30 * time.Second), Metrics: map[string]float64{"llamacpp:tokens_predicted_total": 200}},
	})
	if r.Generated != 100 || r.ObservedSeconds != 30 || r.Distributions["decode"].Median != 3 {
		t.Fatalf("incorrect interval rates/totals: %+v", r)
	}
	if r.Distributions["prompt"] != nil {
		t.Fatal("unreported prompt usage must remain unavailable")
	}
}

func TestMissingSlotCountsAreNotZeroDistributions(t *testing.T) {
	var slots []stats.SlotSample
	if err := json.Unmarshal([]byte(`[{"id":0,"is_processing":true}]`), &slots); err != nil {
		t.Fatal(err)
	}
	result := rollingAverages([]stats.Sample{{At: time.Now(), Slots: slots}})
	if result.ContextAvailable || result.CacheAvailable || result.Distributions["context"] != nil || result.Distributions["cache"] != nil {
		t.Fatal("missing slot fields became measured zeroes")
	}
	var zero []stats.SlotSample
	if err := json.Unmarshal([]byte(`[{"id":0,"n_prompt_tokens":0,"n_prompt_tokens_cache":0}]`), &zero); err != nil {
		t.Fatal(err)
	}
	result = rollingAverages([]stats.Sample{{At: time.Now(), Slots: zero}})
	if !result.ContextAvailable || result.Distributions["context"] == nil {
		t.Fatal("explicit zero is a valid observation")
	}
}
