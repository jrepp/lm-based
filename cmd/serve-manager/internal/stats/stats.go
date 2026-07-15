package stats

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"
)

type Sample struct {
	At      time.Time
	Metrics map[string]float64
	Slots   []SlotSample
}

type SlotSample struct {
	ID                     int  `json:"id"`
	NCtx                   int  `json:"n_ctx"`
	Speculative            bool `json:"speculative"`
	IsProcessing           bool `json:"is_processing"`
	NPromptTokens          int  `json:"n_prompt_tokens"`
	NPromptTokensProcessed int  `json:"n_prompt_tokens_processed"`
	NPromptTokensCache     int  `json:"n_prompt_tokens_cache"`
	NextToken              []struct {
		NRemain  int `json:"n_remain"`
		NDecoded int `json:"n_decoded"`
	} `json:"next_token"`
	Params SlotParams `json:"params"`
}

type SlotParams struct {
	SpeculativeTypes string `json:"speculative.types"`
}

type Snapshot struct {
	ObservedAt       string             `json:"observed_at"`
	Source           string             `json:"source"`
	WindowSeconds    float64            `json:"window_seconds"`
	SampleCount      int                `json:"sample_count"`
	Counters         map[string]float64 `json:"counters"`
	Gauges           map[string]float64 `json:"gauges"`
	Rates            map[string]float64 `json:"rates"`
	Slots            []SlotStats        `json:"slots"`
	History          HistoryStats       `json:"history"`
	Buckets          []BucketStats      `json:"buckets"`
	RetentionSeconds float64            `json:"retention_seconds"`
	BucketSeconds    float64            `json:"bucket_seconds"`
	Trend            TrendStats         `json:"trend"`
}

type SlotStats struct {
	ID                     int      `json:"id"`
	NCtx                   int      `json:"n_ctx"`
	Speculative            bool     `json:"speculative"`
	IsProcessing           bool     `json:"is_processing"`
	NPromptTokens          int      `json:"n_prompt_tokens"`
	NPromptTokensProcessed int      `json:"n_prompt_tokens_processed"`
	NPromptTokensCache     int      `json:"n_prompt_tokens_cache"`
	NDecoded               int      `json:"n_decoded"`
	NRemain                int      `json:"n_remain"`
	MTPActive              bool     `json:"mtp_active"`
	SpeculativeTypes       []string `json:"speculative_types,omitempty"`
	DraftType              string   `json:"draft_type,omitempty"`
}

type HistoryStats struct {
	StartedAt       string                       `json:"started_at,omitempty"`
	UpdatedAt       string                       `json:"updated_at,omitempty"`
	DurationSeconds float64                      `json:"duration_seconds"`
	BucketCount     int                          `json:"bucket_count"`
	SampleCount     int                          `json:"sample_count"`
	Rates           map[string]StatSummary       `json:"rates"`
	Gauges          map[string]StatSummary       `json:"gauges"`
	Slots           map[string]StatSummary       `json:"slots"`
	MetricGroups    map[string]map[string]string `json:"metric_groups,omitempty"`
}

type BucketStats struct {
	Start       string                 `json:"start"`
	End         string                 `json:"end"`
	Seconds     float64                `json:"seconds"`
	SampleCount int                    `json:"sample_count"`
	Rates       map[string]StatSummary `json:"rates"`
	Gauges      map[string]StatSummary `json:"gauges"`
	Slots       map[string]StatSummary `json:"slots"`
}

type StatSummary struct {
	Count int     `json:"count"`
	Min   float64 `json:"min"`
	Max   float64 `json:"max"`
	Mean  float64 `json:"mean"`
	Last  float64 `json:"last"`
}

type TrendStats struct {
	Encoding      string            `json:"encoding"`
	RecentSeconds float64           `json:"recent_seconds"`
	MaxPoints     int               `json:"max_points"`
	SampleCount   int               `json:"sample_count"`
	PointCount    int               `json:"point_count"`
	DroppedCount  int               `json:"dropped_count"`
	StartedAt     string            `json:"started_at,omitempty"`
	UpdatedAt     string            `json:"updated_at,omitempty"`
	Metrics       map[string]string `json:"metrics"`
	Points        []TrendPoint      `json:"points"`
}

type TrendPoint struct {
	At      string             `json:"at"`
	Metrics map[string]float64 `json:"metrics"`
}

type History struct {
	bucketWidth time.Duration
	retention   time.Duration
	trend       trendStore
	previous    *Sample
	buckets     []metricBucket
	startedAt   time.Time
	updatedAt   time.Time
	sampleCount int
}

type metricBucket struct {
	start       time.Time
	end         time.Time
	sampleCount int
	rates       map[string]*statAccumulator
	gauges      map[string]*statAccumulator
	slots       map[string]*statAccumulator
}

type statAccumulator struct {
	count int
	min   float64
	max   float64
	sum   float64
	last  float64
}

type trendStore struct {
	recent      time.Duration
	maxPoints   int
	sampleCount int
	dropped     int
	points      []trendPoint
}

type trendPoint struct {
	at      time.Time
	metrics map[string]float64
}

type Poller struct {
	baseURL string
	client  *http.Client
}

func NewPoller(baseURL string, timeout time.Duration) *Poller {
	return &Poller{
		baseURL: strings.TrimRight(baseURL, "/"),
		client:  &http.Client{Timeout: timeout},
	}
}

func (p *Poller) Source() string {
	return p.baseURL
}

func (p *Poller) Poll() (Sample, error) {
	metrics, err := p.fetchPrometheusMetrics(p.baseURL + "/metrics")
	if err != nil {
		return Sample{}, err
	}
	slots, err := p.fetchSlots(p.baseURL + "/slots")
	if err != nil {
		return Sample{}, err
	}
	return Sample{
		At:      time.Now().UTC(),
		Metrics: metrics,
		Slots:   slots,
	}, nil
}

func (p *Poller) fetchPrometheusMetrics(url string) (map[string]float64, error) {
	resp, err := p.client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		io.Copy(io.Discard, resp.Body)
		return nil, fmt.Errorf("%s returned %s", url, resp.Status)
	}
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	return ParsePrometheusMetrics(string(data)), nil
}

func (p *Poller) fetchSlots(url string) ([]SlotSample, error) {
	resp, err := p.client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		io.Copy(io.Discard, resp.Body)
		return nil, fmt.Errorf("%s returned %s", url, resp.Status)
	}
	var slots []SlotSample
	if err := json.NewDecoder(resp.Body).Decode(&slots); err != nil {
		return nil, err
	}
	return slots, nil
}

func ParsePrometheusMetrics(text string) map[string]float64 {
	metrics := map[string]float64{}
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}
		name := fields[0]
		if idx := strings.IndexByte(name, '{'); idx >= 0 {
			name = name[:idx]
		}
		value, err := strconv.ParseFloat(fields[1], 64)
		if err != nil {
			continue
		}
		metrics[name] = value
	}
	return metrics
}

func BuildSnapshot(source string, window time.Duration, samples []Sample) Snapshot {
	if len(samples) == 0 {
		return Snapshot{
			ObservedAt:    time.Now().UTC().Format(time.RFC3339Nano),
			Source:        source,
			WindowSeconds: window.Seconds(),
			Counters:      map[string]float64{},
			Gauges:        map[string]float64{},
			Rates:         map[string]float64{},
		}
	}
	first := samples[0]
	last := samples[len(samples)-1]
	elapsed := last.At.Sub(first.At).Seconds()
	counters := selectMetrics(last.Metrics, counterMetricNames())
	gauges := selectMetrics(last.Metrics, gaugeMetricNames())
	rates := map[string]float64{}
	if elapsed > 0 {
		addCounterRate(rates, "prompt_tokens_per_second", first.Metrics, last.Metrics, "llamacpp:prompt_tokens_total", elapsed)
		addCounterRate(rates, "predicted_tokens_per_second", first.Metrics, last.Metrics, "llamacpp:tokens_predicted_total", elapsed)
		addCounterRate(rates, "prompt_seconds_per_second", first.Metrics, last.Metrics, "llamacpp:prompt_seconds_total", elapsed)
		addCounterRate(rates, "predicted_seconds_per_second", first.Metrics, last.Metrics, "llamacpp:tokens_predicted_seconds_total", elapsed)
	}
	return Snapshot{
		ObservedAt:    last.At.Format(time.RFC3339Nano),
		Source:        source,
		WindowSeconds: window.Seconds(),
		SampleCount:   len(samples),
		Counters:      counters,
		Gauges:        gauges,
		Rates:         rates,
		Slots:         summarizeSlots(last.Slots),
	}
}

func NewHistory(bucketWidth time.Duration, retention time.Duration) *History {
	if bucketWidth <= 0 {
		bucketWidth = 10 * time.Second
	}
	if retention <= 0 {
		retention = time.Hour
	}
	return &History{
		bucketWidth: bucketWidth,
		retention:   retention,
		trend: trendStore{
			recent:    5 * time.Minute,
			maxPoints: 1440,
		},
	}
}

func (h *History) ConfigureTrend(recent time.Duration, maxPoints int) {
	if recent > 0 {
		h.trend.recent = recent
	}
	if maxPoints > 0 {
		h.trend.maxPoints = maxPoints
	}
}

func (h *History) Observe(sample Sample) {
	if h.startedAt.IsZero() {
		h.startedAt = sample.At
	}
	h.updatedAt = sample.At
	h.sampleCount++

	bucket := h.bucketFor(sample.At)
	bucket.sampleCount++
	for name, value := range selectMetrics(sample.Metrics, gaugeMetricNames()) {
		bucket.addGauge(name, value)
	}
	for name, value := range slotMetricValues(sample.Slots) {
		bucket.addSlot(name, value)
	}
	pointMetrics := map[string]float64{}
	for name, value := range selectMetrics(sample.Metrics, gaugeMetricNames()) {
		pointMetrics[name] = value
	}
	for name, value := range slotMetricValues(sample.Slots) {
		pointMetrics[name] = value
	}
	if h.previous != nil {
		elapsed := sample.At.Sub(h.previous.At).Seconds()
		if elapsed > 0 {
			rates := map[string]float64{}
			addCounterRate(rates, "prompt_tokens_per_second", h.previous.Metrics, sample.Metrics, "llamacpp:prompt_tokens_total", elapsed)
			addCounterRate(rates, "predicted_tokens_per_second", h.previous.Metrics, sample.Metrics, "llamacpp:tokens_predicted_total", elapsed)
			addCounterRate(rates, "prompt_seconds_per_second", h.previous.Metrics, sample.Metrics, "llamacpp:prompt_seconds_total", elapsed)
			addCounterRate(rates, "predicted_seconds_per_second", h.previous.Metrics, sample.Metrics, "llamacpp:tokens_predicted_seconds_total", elapsed)
			for name, value := range rates {
				bucket.addRate(name, value)
				pointMetrics[name] = value
			}
		}
	}
	h.trend.observe(trendPoint{
		at:      sample.At,
		metrics: pointMetrics,
	})
	h.previous = &Sample{
		At:      sample.At,
		Metrics: copyMetrics(sample.Metrics),
		Slots:   append([]SlotSample{}, sample.Slots...),
	}
	h.trim(sample.At)
}

func (h *History) Attach(snapshot *Snapshot) {
	snapshot.History = h.Stats()
	snapshot.Buckets = h.Buckets()
	snapshot.RetentionSeconds = h.retention.Seconds()
	snapshot.BucketSeconds = h.bucketWidth.Seconds()
	snapshot.Trend = h.trend.stats()
}

func (h *History) Stats() HistoryStats {
	stats := HistoryStats{
		BucketCount:  len(h.buckets),
		SampleCount:  h.sampleCount,
		Rates:        map[string]StatSummary{},
		Gauges:       map[string]StatSummary{},
		Slots:        map[string]StatSummary{},
		MetricGroups: metricGroups(),
	}
	if !h.startedAt.IsZero() {
		stats.StartedAt = h.startedAt.Format(time.RFC3339Nano)
	}
	if !h.updatedAt.IsZero() {
		stats.UpdatedAt = h.updatedAt.Format(time.RFC3339Nano)
		stats.DurationSeconds = h.updatedAt.Sub(h.startedAt).Seconds()
	}
	rates := map[string]*statAccumulator{}
	gauges := map[string]*statAccumulator{}
	slots := map[string]*statAccumulator{}
	for _, bucket := range h.buckets {
		mergeAccumulators(rates, bucket.rates)
		mergeAccumulators(gauges, bucket.gauges)
		mergeAccumulators(slots, bucket.slots)
	}
	stats.Rates = summarizeAccumulators(rates)
	stats.Gauges = summarizeAccumulators(gauges)
	stats.Slots = summarizeAccumulators(slots)
	return stats
}

func (h *History) Buckets() []BucketStats {
	out := make([]BucketStats, 0, len(h.buckets))
	for _, bucket := range h.buckets {
		out = append(out, BucketStats{
			Start:       bucket.start.Format(time.RFC3339Nano),
			End:         bucket.end.Format(time.RFC3339Nano),
			Seconds:     bucket.end.Sub(bucket.start).Seconds(),
			SampleCount: bucket.sampleCount,
			Rates:       summarizeAccumulators(bucket.rates),
			Gauges:      summarizeAccumulators(bucket.gauges),
			Slots:       summarizeAccumulators(bucket.slots),
		})
	}
	return out
}

func TrimWindow(samples []Sample, newest time.Time, window time.Duration) []Sample {
	cutoff := newest.Add(-window)
	keepFrom := 0
	for keepFrom < len(samples) && samples[keepFrom].At.Before(cutoff) {
		keepFrom++
	}
	return samples[keepFrom:]
}

func (h *History) bucketFor(at time.Time) *metricBucket {
	start := at.Truncate(h.bucketWidth)
	if len(h.buckets) > 0 {
		last := &h.buckets[len(h.buckets)-1]
		if last.start.Equal(start) {
			return last
		}
	}
	h.buckets = append(h.buckets, metricBucket{
		start:  start,
		end:    start.Add(h.bucketWidth),
		rates:  map[string]*statAccumulator{},
		gauges: map[string]*statAccumulator{},
		slots:  map[string]*statAccumulator{},
	})
	return &h.buckets[len(h.buckets)-1]
}

func (h *History) trim(newest time.Time) {
	cutoff := newest.Add(-h.retention)
	keepFrom := 0
	for keepFrom < len(h.buckets) && h.buckets[keepFrom].end.Before(cutoff) {
		keepFrom++
	}
	h.buckets = h.buckets[keepFrom:]
	h.trend.trim(newest, h.retention)
}

func (s *trendStore) observe(point trendPoint) {
	s.sampleCount++
	s.points = append(s.points, point)
	s.compress(point.at)
}

func (s *trendStore) trim(newest time.Time, retention time.Duration) {
	if retention <= 0 {
		return
	}
	cutoff := newest.Add(-retention)
	keepFrom := 0
	for keepFrom < len(s.points) && s.points[keepFrom].at.Before(cutoff) {
		keepFrom++
	}
	s.dropped += keepFrom
	s.points = s.points[keepFrom:]
}

func (s *trendStore) compress(now time.Time) {
	if s.maxPoints <= 0 || len(s.points) <= s.maxPoints {
		return
	}
	recentCutoff := now.Add(-s.recent)
	older := make([]trendPoint, 0, len(s.points))
	recent := make([]trendPoint, 0, len(s.points))
	for _, point := range s.points {
		if point.at.Before(recentCutoff) {
			older = append(older, point)
		} else {
			recent = append(recent, point)
		}
	}
	budget := s.maxPoints - len(recent)
	if budget < 2 {
		budget = 2
	}
	if len(older) > budget {
		older = reduceDeltaDelta(older, budget)
	}
	next := append(older, recent...)
	if len(next) > s.maxPoints {
		s.dropped += len(next) - s.maxPoints
		next = next[len(next)-s.maxPoints:]
	}
	s.dropped += len(s.points) - len(next)
	s.points = next
}

func (s *trendStore) stats() TrendStats {
	stats := TrendStats{
		Encoding:      "delta-delta-compacted-v1",
		RecentSeconds: s.recent.Seconds(),
		MaxPoints:     s.maxPoints,
		SampleCount:   s.sampleCount,
		PointCount:    len(s.points),
		DroppedCount:  s.dropped,
		Metrics:       trendMetricDescriptions(),
		Points:        make([]TrendPoint, 0, len(s.points)),
	}
	if len(s.points) > 0 {
		stats.StartedAt = s.points[0].at.Format(time.RFC3339Nano)
		stats.UpdatedAt = s.points[len(s.points)-1].at.Format(time.RFC3339Nano)
	}
	for _, point := range s.points {
		stats.Points = append(stats.Points, TrendPoint{
			At:      point.at.Format(time.RFC3339Nano),
			Metrics: copyMetrics(point.metrics),
		})
	}
	return stats
}

func reduceDeltaDelta(points []trendPoint, target int) []trendPoint {
	if len(points) <= target || target < 2 {
		return points
	}
	stride := len(points) / target
	if stride < 2 {
		stride = 2
	}
	keep := make([]bool, len(points))
	keep[0] = true
	keep[len(points)-1] = true
	for i := stride; i < len(points)-1; i += stride {
		keep[i] = true
	}
	metrics := trendMetricNames()
	for _, name := range metrics {
		markDeltaDeltaChanges(points, keep, name)
	}
	out := make([]trendPoint, 0, target)
	for i, point := range points {
		if keep[i] {
			out = append(out, point)
		}
	}
	if len(out) <= target {
		return out
	}
	return thinPoints(out, target)
}

func markDeltaDeltaChanges(points []trendPoint, keep []bool, name string) {
	if len(points) < 3 {
		return
	}
	values := make([]float64, len(points))
	for i, point := range points {
		values[i] = point.metrics[name]
	}
	minValue, maxValue := values[0], values[0]
	for _, value := range values[1:] {
		if value < minValue {
			minValue = value
		}
		if value > maxValue {
			maxValue = value
		}
	}
	threshold := (maxValue - minValue) * 0.08
	if threshold < 0.01 {
		threshold = 0.01
	}
	previousDelta := values[1] - values[0]
	for i := 2; i < len(points); i++ {
		delta := values[i] - values[i-1]
		if abs(delta-previousDelta) >= threshold {
			keep[i-1] = true
		}
		previousDelta = delta
	}
}

func thinPoints(points []trendPoint, target int) []trendPoint {
	if len(points) <= target {
		return points
	}
	out := make([]trendPoint, 0, target)
	for i := 0; i < target; i++ {
		idx := i * (len(points) - 1) / (target - 1)
		out = append(out, points[idx])
	}
	return out
}

func (b *metricBucket) addRate(name string, value float64) {
	addValue(b.rates, name, value)
}

func (b *metricBucket) addGauge(name string, value float64) {
	addValue(b.gauges, name, value)
}

func (b *metricBucket) addSlot(name string, value float64) {
	addValue(b.slots, name, value)
}

func addValue(group map[string]*statAccumulator, name string, value float64) {
	acc := group[name]
	if acc == nil {
		acc = &statAccumulator{}
		group[name] = acc
	}
	acc.add(value)
}

func (a *statAccumulator) add(value float64) {
	if a.count == 0 || value < a.min {
		a.min = value
	}
	if a.count == 0 || value > a.max {
		a.max = value
	}
	a.count++
	a.sum += value
	a.last = value
}

func (a *statAccumulator) summary() StatSummary {
	if a.count == 0 {
		return StatSummary{}
	}
	return StatSummary{
		Count: a.count,
		Min:   a.min,
		Max:   a.max,
		Mean:  a.sum / float64(a.count),
		Last:  a.last,
	}
}

func mergeAccumulators(dst map[string]*statAccumulator, src map[string]*statAccumulator) {
	for name, acc := range src {
		merged := dst[name]
		if merged == nil {
			merged = &statAccumulator{}
			dst[name] = merged
		}
		if acc.count == 0 {
			continue
		}
		if merged.count == 0 || acc.min < merged.min {
			merged.min = acc.min
		}
		if merged.count == 0 || acc.max > merged.max {
			merged.max = acc.max
		}
		merged.count += acc.count
		merged.sum += acc.sum
		merged.last = acc.last
	}
}

func summarizeAccumulators(accumulators map[string]*statAccumulator) map[string]StatSummary {
	out := map[string]StatSummary{}
	for name, acc := range accumulators {
		out[name] = acc.summary()
	}
	return out
}

func selectMetrics(metrics map[string]float64, names []string) map[string]float64 {
	selected := map[string]float64{}
	for _, name := range names {
		if value, ok := metrics[name]; ok {
			selected[name] = value
		}
	}
	return selected
}

func gaugeMetricNames() []string {
	return []string{
		"llamacpp:prompt_tokens_seconds",
		"llamacpp:predicted_tokens_seconds",
		"llamacpp:requests_processing",
		"llamacpp:requests_deferred",
		"llamacpp:n_busy_slots_per_decode",
	}
}

func counterMetricNames() []string {
	return []string{
		"llamacpp:prompt_tokens_total",
		"llamacpp:prompt_seconds_total",
		"llamacpp:tokens_predicted_total",
		"llamacpp:tokens_predicted_seconds_total",
		"llamacpp:n_tokens_max",
	}
}

func metricGroups() map[string]map[string]string {
	return map[string]map[string]string{
		"rates": {
			"prompt_tokens_per_second":    "prompt throughput",
			"predicted_tokens_per_second": "decode throughput",
		},
		"slots": {
			"active_context_tokens": "active slot context",
			"cache_tokens":          "prompt cache tokens",
			"decoded_tokens":        "decoded tokens",
			"remaining_tokens":      "remaining generation tokens",
			"mtp_active":            "MTP speculative decoding active",
			"speculative_active":    "speculative decoding active",
		},
	}
}

func trendMetricNames() []string {
	return []string{
		"predicted_tokens_per_second",
		"prompt_tokens_per_second",
		"active_context_tokens",
		"cache_tokens",
		"decoded_tokens",
		"remaining_tokens",
		"mtp_active",
	}
}

func trendMetricDescriptions() map[string]string {
	return map[string]string{
		"predicted_tokens_per_second": "decode throughput",
		"prompt_tokens_per_second":    "prompt throughput",
		"active_context_tokens":       "active slot context",
		"cache_tokens":                "prompt cache tokens",
		"decoded_tokens":              "decoded tokens",
		"remaining_tokens":            "remaining generation tokens",
		"mtp_active":                  "MTP speculative decoding active",
	}
}

func slotMetricValues(slots []SlotSample) map[string]float64 {
	values := map[string]float64{}
	for _, slot := range summarizeSlots(slots) {
		if !slot.IsProcessing && len(slots) > 1 {
			continue
		}
		values["active_context_tokens"] = float64(slot.NPromptTokens)
		values["cache_tokens"] = float64(slot.NPromptTokensCache)
		values["decoded_tokens"] = float64(slot.NDecoded)
		values["remaining_tokens"] = float64(slot.NRemain)
		if slot.Speculative {
			values["speculative_active"] = 1
		}
		if slot.MTPActive {
			values["mtp_active"] = 1
		}
		break
	}
	return values
}

func abs(value float64) float64 {
	if value < 0 {
		return -value
	}
	return value
}

func copyMetrics(metrics map[string]float64) map[string]float64 {
	out := make(map[string]float64, len(metrics))
	for name, value := range metrics {
		out[name] = value
	}
	return out
}

func addCounterRate(out map[string]float64, outName string, first, last map[string]float64, metricName string, elapsed float64) {
	firstValue, firstOK := first[metricName]
	lastValue, lastOK := last[metricName]
	if !firstOK || !lastOK || lastValue < firstValue {
		return
	}
	out[outName] = (lastValue - firstValue) / elapsed
}

func summarizeSlots(slots []SlotSample) []SlotStats {
	out := make([]SlotStats, 0, len(slots))
	for _, slot := range slots {
		stats := SlotStats{
			ID:                     slot.ID,
			NCtx:                   slot.NCtx,
			Speculative:            slot.Speculative,
			IsProcessing:           slot.IsProcessing,
			NPromptTokens:          slot.NPromptTokens,
			NPromptTokensProcessed: slot.NPromptTokensProcessed,
			NPromptTokensCache:     slot.NPromptTokensCache,
		}
		for _, next := range slot.NextToken {
			stats.NDecoded += next.NDecoded
			stats.NRemain += next.NRemain
		}
		stats.SpeculativeTypes = parseSpeculativeTypes(slot.Params.SpeculativeTypes)
		for _, speculativeType := range stats.SpeculativeTypes {
			if speculativeType == "draft-mtp" {
				stats.MTPActive = true
				stats.DraftType = speculativeType
				break
			}
		}
		out = append(out, stats)
	}
	return out
}

func parseSpeculativeTypes(value string) []string {
	var out []string
	for _, part := range strings.Split(value, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		out = append(out, part)
	}
	return out
}
