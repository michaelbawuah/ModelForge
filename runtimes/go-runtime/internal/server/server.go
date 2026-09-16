package server

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"

	runtimeengine "github.com/michaelbawuah/ModelForge/runtimes/go-runtime/internal/runtime"
)

type Server struct {
	runtime *runtimeengine.Runtime
	logger  *slog.Logger
}

func New(runtime *runtimeengine.Runtime, logger *slog.Logger) *Server {
	return &Server{
		runtime: runtime,
		logger:  logger,
	}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", s.health)
	mux.HandleFunc("POST /predict", s.predict)

	return mux
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
