package server

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"sync/atomic"
	"time"

	runtimeengine "github.com/michaelbawuah/ModelForge/runtimes/go-runtime/internal/runtime"
)

type FaultConfig struct {
	FailEvery uint64
	Delay     time.Duration
}

type Options struct {
	Faults    FaultConfig
	AuthToken string
}

type Server struct {
	runtime      *runtimeengine.Runtime
	logger       *slog.Logger
	faults       FaultConfig
	authToken    string
	requestCount atomic.Uint64
}

func New(runtime *runtimeengine.Runtime, logger *slog.Logger) *Server {
	return NewWithOptions(runtime, logger, Options{})
}

func NewWithFaults(
	runtime *runtimeengine.Runtime,
	logger *slog.Logger,
	faults FaultConfig,
) *Server {
	return NewWithOptions(
		runtime,
		logger,
		Options{Faults: faults},
	)
}

func NewWithOptions(
	runtime *runtimeengine.Runtime,
	logger *slog.Logger,
	options Options,
) *Server {
	return &Server{
		runtime:   runtime,
		logger:    logger,
		faults:    options.Faults,
		authToken: options.AuthToken,
	}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", s.health)
	mux.HandleFunc("POST /predict", s.predict)

	if s.authToken == "" {
		return mux
	}

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		expected := "Bearer " + s.authToken
		supplied := r.Header.Get("Authorization")

		if subtle.ConstantTimeCompare(
			[]byte(supplied),
			[]byte(expected),
		) != 1 {
			w.Header().Set("WWW-Authenticate", "Bearer")
			writeError(w, http.StatusUnauthorized, "runtime authentication required")
			return
		}

		mux.ServeHTTP(w, r)
	})
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "healthy",
		"service": "modelforge-go-runtime",
	})
}

func (s *Server) predict(w http.ResponseWriter, r *http.Request) {
	defer r.Body.Close()

	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()

	var request runtimeengine.PredictionRequest

	if err := decoder.Decode(&request); err != nil {
		writeError(w, http.StatusBadRequest, "invalid prediction request")
		return
	}

	requestNumber := s.requestCount.Add(1)

	if s.faults.Delay > 0 {
		time.Sleep(s.faults.Delay)
	}

	if s.faults.FailEvery > 0 && requestNumber%s.faults.FailEvery == 0 {
		s.logger.Warn(
			"injected runtime failure",
			"request_number", requestNumber,
			"fail_every", s.faults.FailEvery,
		)
		writeError(w, http.StatusServiceUnavailable, "injected runtime failure")
		return
	}

	response, err := s.runtime.Predict(request)
	if err != nil {
		status := http.StatusUnprocessableEntity

		if errors.Is(err, runtimeengine.ErrUnsupportedFramework) {
			status = http.StatusBadRequest
		}

		s.logger.Warn(
			"prediction failed",
			"framework", request.Model.Framework,
			"error", err,
		)

		writeError(w, status, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, response)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{
		"error": message,
	})
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)

	if err := json.NewEncoder(w).Encode(value); err != nil {
		slog.Error("failed to encode HTTP response", "error", err)
	}
}
