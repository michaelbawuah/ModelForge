package main

import (
	"log/slog"
	"net/http"
	"os"

	runtimeengine "github.com/michaelbawuah/ModelForge/runtimes/go-runtime/internal/runtime"
	"github.com/michaelbawuah/ModelForge/runtimes/go-runtime/internal/server"
)

func main() {
	logger := slog.New(
		slog.NewJSONHandler(os.Stdout, nil),
	)

	engine := runtimeengine.New()
	httpServer := server.New(engine, logger)

	address := ":8090"

	logger.Info(
		"starting ModelForge Go runtime",
		"address", address,
	)

	if err := http.ListenAndServe(address, httpServer.Handler()); err != nil {
		logger.Error(
			"runtime server stopped",
			"error", err,
		)

		os.Exit(1)
	}
}
