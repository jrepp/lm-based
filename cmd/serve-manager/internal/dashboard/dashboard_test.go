package dashboard

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestHandlerServesStatsAndEmbeddedPage(t *testing.T) {
	statsPath := filepath.Join(t.TempDir(), "llama-server.json")
	if err := os.WriteFile(statsPath, []byte(`{"sample_count":2}`), 0o644); err != nil {
		t.Fatal(err)
	}
	handler, err := NewHandler(Config{StatsPath: statsPath})
	if err != nil {
		t.Fatal(err)
	}

	statsResponse := httptest.NewRecorder()
	statsRequest := httptest.NewRequest(http.MethodGet, "/api/stats", nil)
	handler.ServeHTTP(statsResponse, statsRequest)
	if statsResponse.Code != http.StatusOK {
		t.Fatalf("/api/stats status = %d, want %d", statsResponse.Code, http.StatusOK)
	}
	if got := strings.TrimSpace(statsResponse.Body.String()); got != `{"sample_count":2}` {
		t.Fatalf("/api/stats body = %q", got)
	}

	pageResponse := httptest.NewRecorder()
	pageRequest := httptest.NewRequest(http.MethodGet, "/", nil)
	handler.ServeHTTP(pageResponse, pageRequest)
	if pageResponse.Code != http.StatusOK {
		t.Fatalf("/ status = %d, want %d", pageResponse.Code, http.StatusOK)
	}
	if !strings.Contains(pageResponse.Body.String(), "Model Performance") {
		t.Fatal("embedded page did not contain expected title")
	}
}
