package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"

	managerdashboard "lm-based/cmd/serve-manager/internal/dashboard"
	managerstats "lm-based/cmd/serve-manager/internal/stats"
)

type ServePolicy struct {
	APIVersion    string              `json:"api_version"`
	Ingress       IngressPolicy       `json:"ingress"`
	Workers       WorkerPolicy        `json:"workers"`
	Models        ModelPolicy         `json:"models"`
	Swap          SwapPolicy          `json:"swap"`
	Observability ObservabilityPolicy `json:"observability"`
	Policy        RuntimePolicy       `json:"policy"`
}

type IngressPolicy struct {
	PublicListen  string `json:"public_listen"`
	SwapListen    string `json:"swap_listen"`
	SwapUIEnabled bool   `json:"swap_ui_enabled"`
}

type WorkerPolicy struct {
	Host                    string    `json:"host"`
	PortRange               PortRange `json:"port_range"`
	DefaultRunMode          string    `json:"default_run_mode"`
	DefaultEnableRunCapture bool      `json:"default_enable_run_capture"`
}

type PortRange struct {
	Start int `json:"start"`
	End   int `json:"end"`
}

type ModelPolicy struct {
	Enabled      []string `json:"enabled"`
	Disabled     []string `json:"disabled"`
	Warm         []string `json:"warm"`
	OperatorOnly []string `json:"operator_only"`
}

type SwapPolicy struct {
	GlobalTTLSeconds int  `json:"global_ttl_seconds"`
	SendLoadingState bool `json:"send_loading_state"`
}

type ObservabilityPolicy struct {
	MetricsListen  string `json:"metrics_listen"`
	StructuredLogs bool   `json:"structured_logs"`
}

type RuntimePolicy struct {
	AllowNonGGUF            bool `json:"allow_non_gguf"`
	RequireLocalArtifact    bool `json:"require_local_artifact"`
	FailApplyOnMissingModel bool `json:"fail_apply_on_missing_model"`
}

type HostCapabilities struct {
	APIVersion string `json:"api_version"`
	Host       struct {
		ID    string `json:"id"`
		Class string `json:"class"`
	} `json:"host"`
	Backends struct {
		Supported []string          `json:"supported"`
		Preferred map[string]string `json:"preferred"`
	} `json:"backends"`
	Limits struct {
		MemoryClass                    string `json:"memory_class"`
		Accelerator                    string `json:"accelerator"`
		SupportsLargeBF16              bool   `json:"supports_large_bf16"`
		SupportsLongContextHeavyModels string `json:"supports_long_context_heavy_models"`
	} `json:"limits"`
	Profiles struct {
		Excluded  []string `json:"excluded"`
		Preferred []string `json:"preferred"`
	} `json:"profiles"`
}

type ModelRecord struct {
	Artifact struct {
		Filename     string `json:"filename"`
		LocalPath    string `json:"local_path"`
		Format       string `json:"format"`
		Quantization string `json:"quantization"`
	} `json:"artifact"`
	Model struct {
		Slug string `json:"slug"`
	} `json:"model"`
	Launcher struct {
		Profile        string            `json:"profile"`
		RecommendedEnv map[string]string `json:"recommended_env"`
	} `json:"launcher"`
	Source struct {
		ProvenanceStatus string `json:"provenance_status"`
	} `json:"source"`
	IndexPath string `json:"-"`
}

type ResolvedModel struct {
	Slug             string `json:"slug"`
	Format           string `json:"format"`
	Profile          string `json:"profile"`
	ArtifactPath     string `json:"artifact_path"`
	WorkerPort       int    `json:"worker_port"`
	WorkerCommand    string `json:"worker_command"`
	WorkerID         string `json:"worker_id"`
	ProvenanceStatus string `json:"provenance_status"`
	SidecarPath      string `json:"sidecar_path"`
}

type GenerationPlan struct {
	GenerationID      string          `json:"generation_id"`
	Mode              string          `json:"mode"`
	CreatedAt         string          `json:"created_at"`
	ProjectRoot       string          `json:"project_root"`
	RuntimeRoot       string          `json:"runtime_root"`
	PublicListen      string          `json:"public_listen"`
	SwapListen        string          `json:"swap_listen"`
	HaproxyMetrics    string          `json:"haproxy_metrics"`
	SupervisorMetrics string          `json:"supervisor_metrics"`
	BackendTarget     string          `json:"backend_target"`
	Models            []ResolvedModel `json:"models"`
}

type ValidationResult struct {
	GenerationID string   `json:"generation_id"`
	Mode         string   `json:"mode"`
	Valid        bool     `json:"valid"`
	Errors       []string `json:"errors"`
	Warnings     []string `json:"warnings"`
}

type DesiredState struct {
	GenerationID  string `json:"generation_id"`
	Mode          string `json:"mode"`
	PlannedAt     string `json:"planned_at"`
	GenerationDir string `json:"generation_dir"`
}

type ActivationResult struct {
	GenerationID string   `json:"generation_id"`
	Mode         string   `json:"mode"`
	Activated    bool     `json:"activated"`
	ActivatedAt  string   `json:"activated_at,omitempty"`
	Errors       []string `json:"errors,omitempty"`
}

type runtimePaths struct {
	projectRoot string
	runtimeRoot string
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}

	paths, err := resolvePaths()
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}

	switch os.Args[1] {
	case "plan":
		os.Exit(runPlan(paths, os.Args[2:]))
	case "doctor":
		os.Exit(runDoctor(paths, os.Args[2:]))
	case "status":
		os.Exit(runStatus(paths, os.Args[2:]))
	case "stats":
		os.Exit(runStats(paths, os.Args[2:]))
	case "stats-poll":
		os.Exit(runStatsPoll(paths, os.Args[2:]))
	case "dashboard":
		os.Exit(runDashboard(paths, os.Args[2:]))
	case "apply":
		os.Exit(runApply(paths, os.Args[2:]))
	case "stop":
		os.Exit(runStop(paths, os.Args[2:]))
	case "logs":
		os.Exit(runLogs(paths, os.Args[2:]))
	default:
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Println("serve-manager <plan|apply|status|stats|stats-poll|dashboard|doctor|stop|logs>")
}

func resolvePaths() (runtimePaths, error) {
	root, err := os.Getwd()
	if err != nil {
		return runtimePaths{}, err
	}
	return runtimePaths{
		projectRoot: root,
		runtimeRoot: filepath.Join(root, ".runtime", "serve-manager"),
	}, nil
}

func runPlan(paths runtimePaths, args []string) int {
	fs := flag.NewFlagSet("plan", flag.ContinueOnError)
	mode := fs.String("mode", "managed", "stack mode: direct or managed")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	plan, validation, generationDir, err := buildAndWritePlan(paths, *mode)
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	fmt.Printf("generation: %s\n", plan.GenerationID)
	fmt.Printf("mode:       %s\n", plan.Mode)
	fmt.Printf("dir:        %s\n", generationDir)
	for _, warning := range validation.Warnings {
		fmt.Printf("warning:    %s\n", warning)
	}
	if !validation.Valid {
		for _, failure := range validation.Errors {
			fmt.Printf("error:      %s\n", failure)
		}
		return 1
	}
	return 0
}

func runDoctor(paths runtimePaths, args []string) int {
	fs := flag.NewFlagSet("doctor", flag.ContinueOnError)
	mode := fs.String("mode", "managed", "stack mode: direct or managed")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	plan, validation, _, err := buildAndWritePlan(paths, *mode)
	if err != nil {
		fmt.Fprintln(os.Stderr, "fail config:", err)
		return 1
	}
	failures := append([]string{}, validation.Errors...)

	checks := []struct {
		name string
		ok   bool
		note string
	}{
		{"serve-policy", true, filepath.Join(paths.projectRoot, "serve-policy.yaml")},
		{"host-capabilities", true, filepath.Join(paths.projectRoot, "host-capabilities.yaml")},
		{"run-server", fileExists(filepath.Join(paths.projectRoot, "run-server.py")), filepath.Join(paths.projectRoot, "run-server.py")},
		{"haproxy", lookPath("haproxy") != "", "required for apply"},
	}
	if *mode == "managed" {
		checks = append(checks, struct {
			name string
			ok   bool
			note string
		}{"llama-swap", findLlamaSwapBinary() != "", "required for managed apply"})
	}
	for _, check := range checks {
		if check.ok {
			fmt.Printf("ok   %-18s %s\n", check.name, check.note)
		} else {
			fmt.Printf("fail %-18s %s\n", check.name, check.note)
			failures = append(failures, check.name)
		}
	}
	portTargets := []struct {
		name    string
		address string
	}{
		{"public", plan.PublicListen},
		{"haproxy-metrics", plan.HaproxyMetrics},
		{"supervisor-metrics", plan.SupervisorMetrics},
	}
	if *mode == "managed" {
		portTargets = append(portTargets, struct {
			name    string
			address string
		}{"swap", plan.SwapListen})
	}
	for _, target := range portTargets {
		if err := ensurePortFree(target.address); err != nil {
			fmt.Printf("fail %-18s %s\n", target.name, err)
			failures = append(failures, target.name)
		} else {
			fmt.Printf("ok   %-18s %s\n", target.name, target.address)
		}
	}
	for _, model := range plan.Models {
		if fileExists(model.ArtifactPath) {
			fmt.Printf("ok   %-18s %s\n", model.Slug, model.ArtifactPath)
		} else {
			msg := fmt.Sprintf("missing artifact for %s: %s", model.Slug, model.ArtifactPath)
			fmt.Printf("fail %-18s %s\n", model.Slug, msg)
			failures = append(failures, msg)
		}
	}
	return boolExit(len(failures) == 0)
}

func runStatus(paths runtimePaths, args []string) int {
	_ = args
	activeGeneration := strings.TrimSpace(readText(filepath.Join(paths.runtimeRoot, "active-generation")))
	desiredRaw := readText(filepath.Join(paths.runtimeRoot, "desired.json"))
	fmt.Printf("runtime:            %s\n", paths.runtimeRoot)
	if activeGeneration == "" {
		fmt.Println("active generation:  none")
	} else {
		fmt.Printf("active generation:  %s\n", activeGeneration)
	}
	if desiredRaw != "" {
		var desired DesiredState
		if json.Unmarshal([]byte(desiredRaw), &desired) == nil {
			fmt.Printf("desired generation: %s (%s)\n", desired.GenerationID, desired.Mode)
		}
	}
	for _, component := range []string{"haproxy", "llama-swap"} {
		pidPath := filepath.Join(paths.runtimeRoot, "pids", component+".pid")
		pid := strings.TrimSpace(readText(pidPath))
		state := "stopped"
		if pid != "" && processRunning(pid) {
			state = "running"
		}
		fmt.Printf("%-18s %s", component+":", state)
		if pid != "" {
			fmt.Printf(" (pid=%s)", pid)
		}
		fmt.Println()
	}
	policy, policyErr := loadServePolicy(filepath.Join(paths.projectRoot, "serve-policy.yaml"))
	records, recordsErr := loadModelRecords(filepath.Join(paths.projectRoot, "models"))
	switch {
	case policyErr == nil && recordsErr == nil:
		enabled := policy.Models.Enabled
		fmt.Printf("models:             hot=%d all=%d\n", len(enabled), len(records))
		if len(enabled) == 0 {
			fmt.Println("  hot (enabled):    (none declared; routing includes all models)")
		} else {
			fmt.Printf("  hot (enabled):    %s\n", strings.Join(enabled, ", "))
		}
	case policyErr != nil:
		fmt.Println("models:             (serve-policy.yaml unavailable)")
	default:
		fmt.Println("models:             (model index unavailable)")
	}
	return 0
}

func runStats(paths runtimePaths, args []string) int {
	fs := flag.NewFlagSet("stats", flag.ContinueOnError)
	output := fs.String("output", filepath.Join(paths.runtimeRoot, "stats", "llama-server.json"), "rolling stats JSON file")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	data, err := os.ReadFile(*output)
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	fmt.Print(string(data))
	return 0
}

func runStatsPoll(paths runtimePaths, args []string) int {
	fs := flag.NewFlagSet("stats-poll", flag.ContinueOnError)
	baseURL := fs.String("url", "http://127.0.0.1:8001", "llama-server base URL")
	interval := fs.Duration("interval", 200*time.Millisecond, "poll interval")
	window := fs.Duration("window", time.Second, "rolling stats window")
	bucket := fs.Duration("bucket", 10*time.Second, "history bucket width")
	retention := fs.Duration("retention", time.Hour, "history retention")
	trendRecent := fs.Duration("trend-recent", 5*time.Minute, "uncompressed recent trend horizon")
	trendPoints := fs.Int("trend-points", 1440, "maximum compacted trend points")
	timeout := fs.Duration("timeout", 10*time.Second, "HTTP timeout")
	output := fs.String("output", filepath.Join(paths.runtimeRoot, "stats", "llama-server.json"), "rolling stats JSON file")
	once := fs.Bool("once", false, "write one sample and exit")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *interval <= 0 {
		fmt.Fprintln(os.Stderr, "error: interval must be positive")
		return 2
	}
	if *window <= 0 {
		fmt.Fprintln(os.Stderr, "error: window must be positive")
		return 2
	}
	if *timeout <= 0 {
		fmt.Fprintln(os.Stderr, "error: timeout must be positive")
		return 2
	}
	if *bucket <= 0 {
		fmt.Fprintln(os.Stderr, "error: bucket must be positive")
		return 2
	}
	if *retention <= 0 {
		fmt.Fprintln(os.Stderr, "error: retention must be positive")
		return 2
	}
	if *trendRecent <= 0 {
		fmt.Fprintln(os.Stderr, "error: trend-recent must be positive")
		return 2
	}
	if *trendPoints < 2 {
		fmt.Fprintln(os.Stderr, "error: trend-points must be at least 2")
		return 2
	}

	poller := managerstats.NewPoller(*baseURL, *timeout)
	history := managerstats.NewHistory(*bucket, *retention)
	history.ConfigureTrend(*trendRecent, *trendPoints)
	var samples []managerstats.Sample
	for {
		sample, err := poller.Poll()
		if err != nil {
			fmt.Fprintln(os.Stderr, "poll warning:", err)
		} else {
			history.Observe(sample)
			samples = append(samples, sample)
			samples = managerstats.TrimWindow(samples, sample.At, *window)
			snapshot := managerstats.BuildSnapshot(poller.Source(), *window, samples)
			history.Attach(&snapshot)
			if err := writeJSON(*output, snapshot); err != nil {
				fmt.Fprintln(os.Stderr, "error:", err)
				return 1
			}
			if *once {
				fmt.Printf("wrote %s\n", *output)
				return 0
			}
		}
		time.Sleep(*interval)
	}
}

func runDashboard(paths runtimePaths, args []string) int {
	fs := flag.NewFlagSet("dashboard", flag.ContinueOnError)
	listen := fs.String("listen", "127.0.0.1:9092", "dashboard listen address")
	statsPath := fs.String("stats", filepath.Join(paths.runtimeRoot, "stats", "llama-server.json"), "rolling stats JSON file")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	handler, err := managerdashboard.NewHandler(managerdashboard.Config{
		StatsPath: *statsPath,
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	fmt.Printf("dashboard: http://%s\n", *listen)
	if err := http.ListenAndServe(*listen, handler); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	return 0
}

func runApply(paths runtimePaths, args []string) int {
	fs := flag.NewFlagSet("apply", flag.ContinueOnError)
	mode := fs.String("mode", "managed", "stack mode: direct or managed")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	plan, validation, generationDir, err := buildAndWritePlan(paths, *mode)
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	activation := ActivationResult{
		GenerationID: plan.GenerationID,
		Mode:         plan.Mode,
	}
	if !validation.Valid {
		activation.Errors = append(activation.Errors, validation.Errors...)
		_ = writeJSON(filepath.Join(generationDir, "activation.json"), activation)
		fmt.Fprintln(os.Stderr, "plan is invalid")
		return 1
	}
	if err := stopManagedChildren(paths); err != nil {
		activation.Errors = append(activation.Errors, err.Error())
		_ = writeJSON(filepath.Join(generationDir, "activation.json"), activation)
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	if plan.Mode == "managed" {
		if err := startLlamaSwap(paths, plan, generationDir); err != nil {
			activation.Errors = append(activation.Errors, err.Error())
			_ = writeJSON(filepath.Join(generationDir, "activation.json"), activation)
			fmt.Fprintln(os.Stderr, "error:", err)
			return 1
		}
		if err := waitForHTTP("http://"+plan.SwapListen+"/health", 20*time.Second); err != nil {
			activation.Errors = append(activation.Errors, err.Error())
			_ = writeJSON(filepath.Join(generationDir, "activation.json"), activation)
			fmt.Fprintln(os.Stderr, "error:", err)
			return 1
		}
	}
	if err := startHAProxy(paths, plan, generationDir); err != nil {
		activation.Errors = append(activation.Errors, err.Error())
		_ = writeJSON(filepath.Join(generationDir, "activation.json"), activation)
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	if err := waitForHTTP("http://"+plan.PublicListen+"/health", 20*time.Second); err != nil {
		activation.Errors = append(activation.Errors, err.Error())
		_ = writeJSON(filepath.Join(generationDir, "activation.json"), activation)
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	activation.Activated = true
	activation.ActivatedAt = time.Now().UTC().Format(time.RFC3339)
	if err := writeText(filepath.Join(paths.runtimeRoot, "active-generation"), plan.GenerationID+"\n"); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	if err := writeJSON(filepath.Join(generationDir, "activation.json"), activation); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	fmt.Printf("activated generation %s (%s)\n", plan.GenerationID, plan.Mode)
	return 0
}

func runStop(paths runtimePaths, args []string) int {
	_ = args
	if err := stopManagedChildren(paths); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	fmt.Println("stopped managed staging components")
	return 0
}

func runLogs(paths runtimePaths, args []string) int {
	fs := flag.NewFlagSet("logs", flag.ContinueOnError)
	component := fs.String("component", "haproxy", "component: haproxy or llama-swap")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	logPath := filepath.Join(paths.runtimeRoot, "logs", *component+".log")
	data, err := os.ReadFile(logPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		return 1
	}
	fmt.Print(string(data))
	return 0
}

func buildAndWritePlan(paths runtimePaths, mode string) (GenerationPlan, ValidationResult, string, error) {
	if mode != "direct" && mode != "managed" {
		return GenerationPlan{}, ValidationResult{}, "", fmt.Errorf("unsupported mode %q", mode)
	}
	policy, err := loadServePolicy(filepath.Join(paths.projectRoot, "serve-policy.yaml"))
	if err != nil {
		return GenerationPlan{}, ValidationResult{}, "", err
	}
	capabilities, err := loadHostCapabilities(filepath.Join(paths.projectRoot, "host-capabilities.yaml"))
	if err != nil {
		return GenerationPlan{}, ValidationResult{}, "", err
	}
	_ = capabilities
	records, err := loadModelRecords(filepath.Join(paths.projectRoot, "models"))
	if err != nil {
		return GenerationPlan{}, ValidationResult{}, "", err
	}
	generationID := fmt.Sprintf("%s-%s", time.Now().UTC().Format("20060102T150405.000000000Z"), mode)
	plan, validation := resolvePlan(paths, policy, records, generationID, mode)
	generationDir := filepath.Join(paths.runtimeRoot, "generations", generationID)
	if err := os.MkdirAll(generationDir, 0o755); err != nil {
		return GenerationPlan{}, ValidationResult{}, "", err
	}
	if err := writeText(filepath.Join(generationDir, "haproxy.cfg"), renderHAProxyConfig(plan)); err != nil {
		return GenerationPlan{}, ValidationResult{}, "", err
	}
	if err := writeText(filepath.Join(generationDir, "llama-swap.yaml"), renderLlamaSwapConfig(plan, policy)); err != nil {
		return GenerationPlan{}, ValidationResult{}, "", err
	}
	if err := writeJSON(filepath.Join(generationDir, "plan.json"), plan); err != nil {
		return GenerationPlan{}, ValidationResult{}, "", err
	}
	if err := writeJSON(filepath.Join(generationDir, "validation.json"), validation); err != nil {
		return GenerationPlan{}, ValidationResult{}, "", err
	}
	if err := writeJSON(filepath.Join(paths.runtimeRoot, "desired.json"), DesiredState{
		GenerationID:  plan.GenerationID,
		Mode:          plan.Mode,
		PlannedAt:     time.Now().UTC().Format(time.RFC3339),
		GenerationDir: generationDir,
	}); err != nil {
		return GenerationPlan{}, ValidationResult{}, "", err
	}
	if err := writeJSON(filepath.Join(paths.runtimeRoot, "observed.json"), map[string]any{
		"host_id":     capabilities.Host.ID,
		"host_class":  capabilities.Host.Class,
		"planned_at":  time.Now().UTC().Format(time.RFC3339),
		"models_seen": len(records),
		"mode":        mode,
	}); err != nil {
		return GenerationPlan{}, ValidationResult{}, "", err
	}
	return plan, validation, generationDir, nil
}

func resolvePlan(paths runtimePaths, policy ServePolicy, records []ModelRecord, generationID, mode string) (GenerationPlan, ValidationResult) {
	modelsBySlug := map[string]ModelRecord{}
	for _, record := range records {
		modelsBySlug[record.Model.Slug] = record
	}
	enabled := policy.Models.Enabled
	if len(enabled) == 0 {
		for slug := range modelsBySlug {
			enabled = append(enabled, slug)
		}
		sort.Strings(enabled)
	}
	disabled := make(map[string]struct{}, len(policy.Models.Disabled))
	for _, slug := range policy.Models.Disabled {
		disabled[slug] = struct{}{}
	}
	validation := ValidationResult{
		GenerationID: generationID,
		Mode:         mode,
		Valid:        true,
	}
	port := policy.Workers.PortRange.Start
	var models []ResolvedModel
	for _, slug := range enabled {
		if _, skip := disabled[slug]; skip {
			continue
		}
		record, ok := modelsBySlug[slug]
		if !ok {
			msg := fmt.Sprintf("enabled model %s has no sidecar", slug)
			validation.Errors = append(validation.Errors, msg)
			validation.Valid = false
			continue
		}
		artifactPath := resolveArtifactPath(paths.projectRoot, record)
		if policy.Policy.RequireLocalArtifact && !fileExists(artifactPath) {
			msg := fmt.Sprintf("local artifact missing for %s: %s", slug, artifactPath)
			if policy.Policy.FailApplyOnMissingModel {
				validation.Errors = append(validation.Errors, msg)
				validation.Valid = false
			} else {
				validation.Warnings = append(validation.Warnings, msg)
			}
		}
		if port > policy.Workers.PortRange.End {
			validation.Errors = append(validation.Errors, "worker port range exhausted")
			validation.Valid = false
			break
		}
		workerID := fmt.Sprintf("%s-%s", generationID, slug)
		models = append(models, ResolvedModel{
			Slug:             slug,
			Format:           record.Artifact.Format,
			Profile:          profileForRecord(record),
			ArtifactPath:     artifactPath,
			WorkerPort:       port,
			WorkerCommand:    buildWorkerCommand(policy, generationID, workerID, slug, port),
			WorkerID:         workerID,
			ProvenanceStatus: record.Source.ProvenanceStatus,
			SidecarPath:      record.IndexPath,
		})
		port++
	}
	backendTarget := "127.0.0.1:8001"
	if mode == "managed" {
		backendTarget = policy.Ingress.SwapListen
	}
	return GenerationPlan{
		GenerationID:      generationID,
		Mode:              mode,
		CreatedAt:         time.Now().UTC().Format(time.RFC3339),
		ProjectRoot:       paths.projectRoot,
		RuntimeRoot:       paths.runtimeRoot,
		PublicListen:      policy.Ingress.PublicListen,
		SwapListen:        policy.Ingress.SwapListen,
		HaproxyMetrics:    "127.0.0.1:8405",
		SupervisorMetrics: policy.Observability.MetricsListen,
		BackendTarget:     backendTarget,
		Models:            models,
	}, validation
}

func loadServePolicy(path string) (ServePolicy, error) {
	var policy ServePolicy
	if err := loadJSON(path, &policy); err != nil {
		return ServePolicy{}, err
	}
	return policy, nil
}

func loadHostCapabilities(path string) (HostCapabilities, error) {
	var capabilities HostCapabilities
	if err := loadJSON(path, &capabilities); err != nil {
		return HostCapabilities{}, err
	}
	return capabilities, nil
}

func loadJSON(path string, out any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	return decoder.Decode(out)
}

func loadModelRecords(modelsDir string) ([]ModelRecord, error) {
	entries, err := os.ReadDir(modelsDir)
	if err != nil {
		return nil, err
	}
	var records []ModelRecord
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		path := filepath.Join(modelsDir, entry.Name())
		var record ModelRecord
		if err := loadJSON(path, &record); err != nil {
			return nil, fmt.Errorf("%s: %w", path, err)
		}
		record.IndexPath = path
		records = append(records, record)
	}
	sort.Slice(records, func(i, j int) bool {
		return records[i].Model.Slug < records[j].Model.Slug
	})
	return records, nil
}

func resolveArtifactPath(projectRoot string, record ModelRecord) string {
	localPath := record.Artifact.LocalPath
	if localPath == "" {
		localPath = record.Artifact.Filename
	}
	if filepath.IsAbs(localPath) {
		return localPath
	}
	projectRelative := filepath.Join(projectRoot, localPath)
	if fileExists(projectRelative) {
		return projectRelative
	}
	return filepath.Join(projectRoot, "artifacts", localPath)
}

func profileForRecord(record ModelRecord) string {
	if profile := record.Launcher.RecommendedEnv["PROFILE"]; profile != "" {
		return profile
	}
	if record.Launcher.Profile != "" {
		return record.Launcher.Profile
	}
	return "auto"
}

func buildWorkerCommand(policy ServePolicy, generationID, workerID, slug string, port int) string {
	parts := []string{
		"MODEL_SLUG=" + shellQuote(slug),
		"HOST=" + shellQuote(policy.Workers.Host),
		"PORT=" + strconv.Itoa(port),
		"RUN_MODE=" + shellQuote(policy.Workers.DefaultRunMode),
		"SUPERVISOR_GENERATION=" + shellQuote(generationID),
		"SUPERVISOR_WORKER_ID=" + shellQuote(workerID),
		"ENABLE_RUN_CAPTURE=0",
		"./run-server.py",
	}
	return strings.Join(parts, " ")
}

func renderHAProxyConfig(plan GenerationPlan) string {
	return fmt.Sprintf(`global
  log stdout format raw local0
  maxconn 1024

defaults
  log global
  mode http
  option httplog
  option http-buffer-request
  timeout connect 5s
  timeout client 1m
  timeout server 1m
  timeout http-request 30s
  timeout tunnel 1h

frontend local_ingress
  bind %s
  default_backend managed_backend

frontend metrics
  bind %s
  http-request use-service prometheus-exporter if { path /metrics }
  no log

backend managed_backend
  option httpchk GET /health
  http-check expect status 200
  server local_target %s check
`, plan.PublicListen, plan.HaproxyMetrics, plan.BackendTarget)
}

func renderLlamaSwapConfig(plan GenerationPlan, policy ServePolicy) string {
	var b strings.Builder
	fmt.Fprintf(&b, "healthCheckTimeout: 120\n")
	fmt.Fprintf(&b, "logLevel: info\n")
	fmt.Fprintf(&b, "logToStdout: proxy\n")
	fmt.Fprintf(&b, "startPort: %d\n", policy.Workers.PortRange.Start)
	fmt.Fprintf(&b, "sendLoadingState: %t\n", policy.Swap.SendLoadingState)
	fmt.Fprintf(&b, "includeAliasesInList: false\n")
	fmt.Fprintf(&b, "globalTTL: %d\n", policy.Swap.GlobalTTLSeconds)
	fmt.Fprintf(&b, "models:\n")
	for _, model := range plan.Models {
		fmt.Fprintf(&b, "  %s:\n", model.Slug)
		fmt.Fprintf(&b, "    cmd: %q\n", model.WorkerCommand)
		fmt.Fprintf(&b, "    checkEndpoint: /health\n")
	}
	return b.String()
}

func startHAProxy(paths runtimePaths, plan GenerationPlan, generationDir string) error {
	binary := lookPath("haproxy")
	if binary == "" {
		return errors.New("haproxy binary not found on PATH")
	}
	cfgPath := filepath.Join(generationDir, "haproxy.cfg")
	pidPath := filepath.Join(paths.runtimeRoot, "pids", "haproxy.pid")
	logPath := filepath.Join(paths.runtimeRoot, "logs", "haproxy.log")
	return startManagedProcess(binary, []string{"-db", "-f", cfgPath, "-p", pidPath}, logPath, pidPath)
}

func startLlamaSwap(paths runtimePaths, plan GenerationPlan, generationDir string) error {
	binary := findLlamaSwapBinary()
	if binary == "" {
		return errors.New("llama-swap binary not found on PATH or LLAMA_SWAP_BIN")
	}
	cfgPath := filepath.Join(generationDir, "llama-swap.yaml")
	pidPath := filepath.Join(paths.runtimeRoot, "pids", "llama-swap.pid")
	logPath := filepath.Join(paths.runtimeRoot, "logs", "llama-swap.log")
	args := []string{"--config", cfgPath, "--listen", plan.SwapListen, "--log-level", "info"}
	return startManagedProcess(binary, args, logPath, pidPath)
}

func startManagedProcess(binary string, args []string, logPath string, pidPath string) error {
	if err := os.MkdirAll(filepath.Dir(logPath), 0o755); err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(pidPath), 0o755); err != nil {
		return err
	}
	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return err
	}
	defer logFile.Close()
	cmd := exec.Command(binary, args...)
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := cmd.Start(); err != nil {
		return err
	}
	return writeText(pidPath, fmt.Sprintf("%d\n", cmd.Process.Pid))
}

func stopManagedChildren(paths runtimePaths) error {
	var errs []string
	for _, component := range []string{"llama-swap", "haproxy"} {
		if err := stopManagedProcess(filepath.Join(paths.runtimeRoot, "pids", component+".pid")); err != nil {
			errs = append(errs, err.Error())
		}
	}
	if len(errs) > 0 {
		return errors.New(strings.Join(errs, "; "))
	}
	return nil
}

func stopManagedProcess(pidPath string) error {
	pidValue := strings.TrimSpace(readText(pidPath))
	if pidValue == "" {
		return nil
	}
	pid, err := strconv.Atoi(pidValue)
	if err != nil {
		return err
	}
	process, err := os.FindProcess(pid)
	if err != nil {
		return err
	}
	if err := process.Signal(syscall.SIGTERM); err != nil && !errors.Is(err, os.ErrProcessDone) {
		return err
	}
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		if !processRunning(pidValue) {
			_ = os.Remove(pidPath)
			return nil
		}
		time.Sleep(200 * time.Millisecond)
	}
	if err := process.Signal(syscall.SIGKILL); err != nil && !errors.Is(err, os.ErrProcessDone) {
		return err
	}
	_ = os.Remove(pidPath)
	return nil
}

func processRunning(pidValue string) bool {
	pid, err := strconv.Atoi(pidValue)
	if err != nil {
		return false
	}
	process, err := os.FindProcess(pid)
	if err != nil {
		return false
	}
	err = process.Signal(syscall.Signal(0))
	return err == nil
}

func waitForHTTP(url string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	client := &http.Client{Timeout: 2 * time.Second}
	for time.Now().Before(deadline) {
		resp, err := client.Get(url)
		if err == nil {
			io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return nil
			}
		}
		time.Sleep(500 * time.Millisecond)
	}
	return fmt.Errorf("timed out waiting for %s", url)
}

func lookPath(name string) string {
	path, err := exec.LookPath(name)
	if err != nil {
		return ""
	}
	return path
}

func findLlamaSwapBinary() string {
	if env := os.Getenv("LLAMA_SWAP_BIN"); env != "" && fileExists(env) {
		return env
	}
	return lookPath("llama-swap")
}

func ensurePortFree(address string) error {
	listener, err := net.Listen("tcp", address)
	if err != nil {
		return err
	}
	return listener.Close()
}

func writeJSON(path string, payload any) error {
	data, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return err
	}
	return writeText(path, string(data)+"\n")
}

func writeText(path string, value string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, []byte(value), 0o644)
}

func readText(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return string(data)
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func boolExit(ok bool) int {
	if ok {
		return 0
	}
	return 1
}

func shellQuote(value string) string {
	if value == "" {
		return "''"
	}
	return "'" + strings.ReplaceAll(value, "'", `'"'"'`) + "'"
}
