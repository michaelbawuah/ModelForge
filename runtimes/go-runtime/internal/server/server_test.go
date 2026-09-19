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

func testServerWithFaults(faults FaultConfig) *Server {
	logger := slog.New(
		slog.NewTextHandler(io.Discard, nil),
	)

	return NewWithFaults(runtimeengine.New(), logger, faults)
}

func predictionBody() []byte {
	return []byte(`{
		"inputs": 10,
		"model": {
			"model_version_id": 1,
			"version": "1.0.0",
			"framework": "go-linear",
			"artifact_uri": "/tmp/model",
			"checksum": "abc123"
		}
	}`)
}

func TestHealth(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "/health", nil)
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
	request := httptest.NewRequest(
		http.MethodPost,
		"/predict",
		bytes.NewReader(predictionBody()),
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

func TestInjectedFailureIsDeterministic(t *testing.T) {
	runtimeServer := testServerWithFaults(
		FaultConfig{
			FailEvery: 2,
		},
	)

	for index, expectedStatus := range []int{
		http.StatusOK,
		http.StatusServiceUnavailable,
		http.StatusOK,
		http.StatusServiceUnavailable,
	} {
		request := httptest.NewRequest(
			http.MethodPost,
			"/predict",
			bytes.NewReader(predictionBody()),
		)
		recorder := httptest.NewRecorder()

		runtimeServer.Handler().ServeHTTP(recorder, request)

		if recorder.Code != expectedStatus {
			t.Fatalf(
				"request %d status = %d, want %d",
				index+1,
				recorder.Code,
				expectedStatus,
			)
		}
	}
}

func TestRuntimeAuthRejectsMissingBearerToken(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	runtimeServer := NewWithOptions(
		runtimeengine.New(),
		logger,
		Options{AuthToken: "runtime-secret"},
	)

	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	recorder := httptest.NewRecorder()

	runtimeServer.Handler().ServeHTTP(recorder, request)

	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", recorder.Code, http.StatusUnauthorized)
	}
	if recorder.Header().Get("WWW-Authenticate") != "Bearer" {
		t.Fatalf("missing bearer challenge")
	}
}

func TestRuntimeAuthAcceptsBearerToken(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	runtimeServer := NewWithOptions(
		runtimeengine.New(),
		logger,
		Options{AuthToken: "runtime-secret"},
	)

	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	request.Header.Set("Authorization", "Bearer runtime-secret")
	recorder := httptest.NewRecorder()

	runtimeServer.Handler().ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", recorder.Code, http.StatusOK)
	}
}
