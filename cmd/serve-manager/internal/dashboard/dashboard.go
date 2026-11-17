package dashboard

import (
	"embed"
	"io/fs"
	"net/http"
	"os"
	"time"
)

//go:embed assets/*
var embeddedAssets embed.FS

type Config struct {
	StatsPath string
	SwapURL   string
}

func NewHandler(config Config) (http.Handler, error) {
	assets, err := fs.Sub(embeddedAssets, "assets")
	if err != nil {
		return nil, err
	}

	mux := http.NewServeMux()
	if config.SwapURL != "" {
		mux.Handle("/api/models", &fleet{url: config.SwapURL, client: &http.Client{Timeout: 2 * time.Second}, histories: make(map[string]*modelHistory)})
	}
	mux.HandleFunc("/api/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", http.MethodGet)
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		data, err := os.ReadFile(config.StatsPath)
		if err != nil {
			http.Error(w, err.Error(), http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(data)
	})
	mux.Handle("/", http.FileServer(http.FS(assets)))
	return mux, nil
}
