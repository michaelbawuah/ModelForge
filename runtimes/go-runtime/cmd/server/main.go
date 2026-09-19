package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	runtimeengine "github.com/michaelbawuah/ModelForge/runtimes/go-runtime/internal/runtime"
	"github.com/michaelbawuah/ModelForge/runtimes/go-runtime/internal/server"
)

const (
	defaultAddress        = ":8090"
	shutdownTimeout       = 10 * time.Second
	readHeaderTimeout     = 5 * time.Second
	runtimeAddressEnvName = "MODELFORGE_GO_RUNTIME_ADDR"
)

func main() {
	logger := slog.New(
		slog.NewJSONHandler(os.Stdout, nil),
	)

	engine := runtimeengine.New()
	runtimeServer := server.New(engine, logger)

	address := os.Getenv(runtimeAddressEnvName)
	if address == "" {
		address = defaultAddress
	}

	httpServer := &http.Server{
		Addr:              address,
		Handler:           runtimeServer.Handler(),
		ReadHeaderTimeout: readHeaderTimeout,
	}

	serverErrors := make(chan error, 1)

	go func() {
		logger.Info(
			"starting ModelForge Go runtime",
			"address", address,
		)

		err := httpServer.ListenAndServe()
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			serverErrors <- err
		}
	}()

	ctx, stop := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()

	select {
	case <-ctx.Done():
		logger.Info("shutting down ModelForge Go runtime")
	case err := <-serverErrors:
		logger.Error(
			"runtime server stopped unexpectedly",
			"error", err,
		)
		os.Exit(1)
	}

	shutdownContext, cancel := context.WithTimeout(
		context.Background(),
		shutdownTimeout,
	)
	defer cancel()

	if err := httpServer.Shutdown(shutdownContext); err != nil {
		logger.Error(
			"runtime server shutdown failed",
			"error", err,
		)
		os.Exit(1)
	}

	logger.Info("ModelForge Go runtime stopped")
}
