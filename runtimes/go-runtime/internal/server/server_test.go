package server

import (
	"bytes"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	runtimeengine "github.com/michaelbawuah/ModelForge/runtimes/go-runtime/internal/runtime"
)

func testServer() *Server {
	logger := slog.New(
		slog.NewTextHandler(io.Discard, nil),
	)

	return New(runtimeengine.New(), logger)
}

func TestHealth(t *testing.T) {
	request := httptest.NewRequest(
		http.MethodGet,
		"/health",
		nil,
	)

	recorder := httptest.NewRecorder()

	testServer().Handler().ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"status = %d, want %d",
			recorder.Code,
			http.StatusOK,
		)
	}

	if !strings.Contains(recorder.Body.String(), `"status":"healthy"`) {
		t.Fatalf("unexpected response: %s", recorder.Body.String())
	}
}

func TestPredict(t *testing.T) {
	body := []byte(`{
		"inputs": 10,
		"model": {
			"model_version_id": 1,
			"version": "1.0.0",
			"framework": "go-linear",
			"artifact_uri": "/tmp/model",
			"checksum": "abc123"
		}
	}`)

	request := httptest.NewRequest(
		http.MethodPost,
		"/predict",
		bytes.NewReader(body),
	)

	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	testServer().Handler().ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"status = %d, want %d; body=%s",
			recorder.Code,
			http.StatusOK,
			recorder.Body.String(),
		)
	}

	if !strings.Contains(recorder.Body.String(), `"prediction":21`) {
		t.Fatalf("unexpected response: %s", recorder.Body.String())
	}
}

func TestPredictRejectsMalformedJSON(t *testing.T) {
	request := httptest.NewRequest(
		http.MethodPost,
		"/predict",
		strings.NewReader(`{"inputs":`),
	)

	recorder := httptest.NewRecorder()

	testServer().Handler().ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf(
			"status = %d, want %d",
			recorder.Code,
			http.StatusBadRequest,
		)
	}
}
