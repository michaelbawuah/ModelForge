package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
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
	failEveryEnvName      = "MODELFORGE_GO_RUNTIME_FAIL_EVERY"
	delayMillisecondsEnv  = "MODELFORGE_GO_RUNTIME_DELAY_MS"
)

func main() {
	logger := slog.New(
		slog.NewJSONHandler(os.Stdout, nil),
	)

	faults, err := faultConfigFromEnvironment()
	if err != nil {
		logger.Error("invalid runtime fault configuration", "error", err)
		os.Exit(1)
	}

	engine := runtimeengine.New()
	runtimeServer := server.NewWithFaults(engine, logger, faults)

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
			"fault_fail_every", faults.FailEvery,
			"fault_delay_ms", faults.Delay.Milliseconds(),
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

func faultConfigFromEnvironment() (server.FaultConfig, error) {
	failEvery, err := nonNegativeUintEnvironment(failEveryEnvName)
	if err != nil {
		return server.FaultConfig{}, err
	}

	delayMilliseconds, err := nonNegativeUintEnvironment(delayMillisecondsEnv)
	if err != nil {
		return server.FaultConfig{}, err
	}

	return server.FaultConfig{
		FailEvery: failEvery,
		Delay:     time.Duration(delayMilliseconds) * time.Millisecond,
	}, nil
}

func nonNegativeUintEnvironment(name string) (uint64, error) {
	raw := os.Getenv(name)
	if raw == "" {
		return 0, nil
	}

	value, err := strconv.ParseUint(raw, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("%s must be a non-negative integer: %w", name, err)
	}

	return value, nil
}
