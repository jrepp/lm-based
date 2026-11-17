package dashboard

import (
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"net/url"
	"sort"
	"sync"
	"time"

	"lm-based/cmd/serve-manager/internal/stats"
)

type modelView struct {
	ID           string          `json:"id"`
	State        string          `json:"state"`
	MetricsError string          `json:"metrics_error,omitempty"`
	Snapshot     *stats.Snapshot `json:"snapshot,omitempty"`
	Stale        bool            `json:"stale"`
	Rolling      *rollingStats   `json:"rolling,omitempty"`
}
type rollingStats struct {
	ContextAvailable bool                     `json:"context_available"`
	CacheAvailable   bool                     `json:"cache_available"`
	WindowSeconds    float64                  `json:"window_seconds"`
	ObservedSeconds  float64                  `json:"observed_seconds"`
	Distributions    map[string]*distribution `json:"distributions"`
	Generated        float64                  `json:"generated"`
	Processed        float64                  `json:"processed"`
	Context          float64                  `json:"context"`
	Cache            float64                  `json:"cache"`
}

type modelHistory struct {
	snapshot *stats.Snapshot
	rolling  *rollingStats
	lastSeen time.Time
	source   string
	samples  []stats.Sample
	history  *stats.History
}
type fleet struct {
	mu        sync.Mutex
	url       string
	client    *http.Client
	histories map[string]*modelHistory
	cached    []modelView
	updated   time.Time
}

func (f *fleet) get(path string, value any) error {
	resp, err := f.client.Get(f.url + path)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("discovery returned %s", resp.Status)
	}
	return json.NewDecoder(resp.Body).Decode(value)
}
func (f *fleet) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		http.Error(w, "method not allowed", 405)
		return
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	if time.Since(f.updated) >= time.Second {
		var catalog struct {
			Data []struct {
				ID string `json:"id"`
			} `json:"data"`
		}
		var running struct {
			Running []struct {
				Model string `json:"model"`
				State string `json:"state"`
				Proxy string `json:"proxy"`
			} `json:"running"`
		}
		if err := f.get("/v1/models", &catalog); err != nil {
			http.Error(w, err.Error(), 503)
			return
		}
		if err := f.get("/running", &running); err != nil {
			http.Error(w, err.Error(), 503)
			return
		}
		views := make([]modelView, len(catalog.Data))

		var workers sync.WaitGroup
		for i, model := range catalog.Data {
			views[i] = modelView{ID: model.ID, State: "unloaded"}
			if h := f.histories[model.ID]; h != nil {
				views[i].Snapshot = h.snapshot
				views[i].Rolling = h.rolling
				views[i].Stale = h.snapshot != nil
			}
			for _, process := range running.Running {
				if process.Model != model.ID {
					continue
				}
				views[i].State = process.State
				// Probe only already-running loopback workers; never route through swap and load a model.
				u, err := url.Parse(process.Proxy)
				if err != nil || u.Scheme != "http" || (u.Hostname() != "localhost" && u.Hostname() != "127.0.0.1" && u.Hostname() != "::1") {
					views[i].MetricsError = "worker metrics require a local HTTP endpoint"
					continue
				}

				h := f.histories[model.ID]
				if h == nil {
					h = &modelHistory{source: process.Proxy, history: stats.NewHistory(10*time.Second, time.Hour)}
					f.histories[model.ID] = h
				}
				if h.source != process.Proxy {
					h.source = process.Proxy
					h.samples = nil
				}
				h.lastSeen = time.Now()
				workers.Add(1)
				go func(index int, h *modelHistory) {
					defer workers.Done()
					sample, err := stats.NewPoller(h.source, 3*time.Second).Poll()
					if err != nil {
						views[index].MetricsError = "worker does not expose usable /metrics and /slots: " + err.Error()
						return
					}
					h.history.Observe(sample)
					// Counter resets identify a restarted worker; do not mix rate baselines.
					if len(h.samples) > 0 && sample.Metrics["llamacpp:tokens_predicted_total"] < h.samples[len(h.samples)-1].Metrics["llamacpp:tokens_predicted_total"] {
						h.samples = nil
					}
					h.samples = stats.TrimWindow(append(h.samples, sample), sample.At, 30*time.Second)
					snapshot := stats.BuildSnapshot(h.source, 30*time.Second, h.samples)
					h.history.Attach(&snapshot)
					h.snapshot = &snapshot
					h.rolling = rollingAverages(h.samples)
					views[index].Snapshot = h.snapshot
					views[index].Rolling = h.rolling
					views[index].Stale = false
				}(i, h)
				break
			}
		}
		workers.Wait()
		for id, h := range f.histories {
			if time.Since(h.lastSeen) > time.Hour {
				delete(f.histories, id)
			}
		}
		f.cached = views
		f.updated = time.Now()
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(map[string]any{"models": f.cached, "observed_at": f.updated.UTC()})
}

// Time-weight gauge averages so a slow poll does not get the same weight as
// several quick polls. Rates are counter deltas over the same window.
func rollingAverages(samples []stats.Sample) *rollingStats {
	result := &rollingStats{WindowSeconds: 30, Distributions: map[string]*distribution{}}
	values := map[string][]float64{"decode": {}, "prompt": {}, "context": {}, "cache": {}}
	for i, sample := range samples {
		var context, cache float64
		contextOK, cacheOK := len(sample.Slots) > 0, len(sample.Slots) > 0
		for _, slot := range sample.Slots {
			context += float64(slot.NPromptTokens)
			contextOK = contextOK && !slot.ContextMissing
			cacheOK = cacheOK && !slot.CacheMissing
			cache += float64(slot.NPromptTokensCache)
		}
		if contextOK {
			values["context"] = append(values["context"], context)
		}
		if cacheOK {
			values["cache"] = append(values["cache"], cache)
		}
		if i == 0 {
			continue
		}
		previous := samples[i-1]
		seconds := sample.At.Sub(previous.At).Seconds()
		if seconds <= 0 {
			continue
		}
		result.ObservedSeconds += seconds
		for name, metric := range map[string]string{"decode": "llamacpp:tokens_predicted_total", "prompt": "llamacpp:prompt_tokens_total"} {
			current, ok := sample.Metrics[metric]
			before, had := previous.Metrics[metric]
			if !ok || !had || current < before {
				continue
			}
			delta := current - before
			values[name] = append(values[name], delta/seconds)
			if name == "decode" {
				result.Generated += delta
			} else {
				result.Processed += delta
			}
		}
	}
	for name, samples := range values {
		result.Distributions[name] = summarizeDistribution(samples)
	}
	var contextWeight, cacheWeight float64
	for i, sample := range samples {
		seconds := 1.0
		if len(samples) > 1 {
			if i == len(samples)-1 {
				break
			}
			seconds = samples[i+1].At.Sub(sample.At).Seconds()
		}
		contextOK, cacheOK := len(sample.Slots) > 0, len(sample.Slots) > 0
		var context, cache float64
		for _, slot := range sample.Slots {
			contextOK = contextOK && !slot.ContextMissing
			cacheOK = cacheOK && !slot.CacheMissing
			context += float64(slot.NPromptTokens)
			cache += float64(slot.NPromptTokensCache)
		}
		if contextOK {
			result.Context += context * seconds
			contextWeight += seconds
		}
		if cacheOK {
			result.Cache += cache * seconds
			cacheWeight += seconds
		}
	}
	if contextWeight > 0 {
		result.Context /= contextWeight
		result.ContextAvailable = true
	}
	if cacheWeight > 0 {
		result.Cache /= cacheWeight
		result.CacheAvailable = true
	}
	return result
}

type distribution struct {
	Count  int     `json:"count"`
	Min    float64 `json:"min"`
	Q1     float64 `json:"q1"`
	Median float64 `json:"median"`
	Q3     float64 `json:"q3"`
	Max    float64 `json:"max"`
}

func summarizeDistribution(values []float64) *distribution {
	if len(values) == 0 {
		return nil
	}
	sort.Float64s(values)
	quantile := func(q float64) float64 {
		position := q * float64(len(values)-1)
		lo := int(math.Floor(position))
		hi := int(math.Ceil(position))
		return values[lo] + (values[hi]-values[lo])*(position-float64(lo))
	}
	return &distribution{Count: len(values), Min: values[0], Q1: quantile(.25), Median: quantile(.5), Q3: quantile(.75), Max: values[len(values)-1]}
}
