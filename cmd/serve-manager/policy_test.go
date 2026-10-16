package main

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestLoadServePolicyMergesLocalOverlay(t *testing.T) {
	dir := t.TempDir()
	base := `{"ingress": {"swap_listen": "127.0.0.1:8081", "public_listen": "127.0.0.1:8080"},
		"models": {"enabled": ["a", "b"], "warm": ["a"]}}`
	overlay := `{"ingress": {"swap_listen": "127.0.0.1:9081"}, "models": {"enabled": ["c"]}}`
	if err := os.WriteFile(filepath.Join(dir, "serve-policy.yaml"), []byte(base), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "serve-policy.local.yaml"), []byte(overlay), 0o644); err != nil {
		t.Fatal(err)
	}
	policy, err := loadServePolicy(filepath.Join(dir, "serve-policy.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if policy.Ingress.SwapListen != "127.0.0.1:9081" || policy.Ingress.PublicListen != "127.0.0.1:8080" {
		t.Fatalf("ingress not merged: %+v", policy.Ingress)
	}
	if !reflect.DeepEqual(policy.Models.Enabled, []string{"c"}) {
		t.Fatalf("enabled list should be replaced, got %v", policy.Models.Enabled)
	}
	if !reflect.DeepEqual(policy.Models.Warm, []string{"a"}) {
		t.Fatalf("warm list should be kept, got %v", policy.Models.Warm)
	}
}

func TestLoadServePolicyWithoutOverlay(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "serve-policy.yaml")
	if err := os.WriteFile(path, []byte(`{"models": {"enabled": ["a"]}}`), 0o644); err != nil {
		t.Fatal(err)
	}
	policy, err := loadServePolicy(path)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(policy.Models.Enabled, []string{"a"}) {
		t.Fatalf("got %v", policy.Models.Enabled)
	}
}
