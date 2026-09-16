package runtime

import (
	"errors"
	"fmt"
)

var ErrUnsupportedFramework = errors.New("unsupported framework")

type ModelMetadata struct {
	ModelVersionID int    `json:"model_version_id"`
	Version        string `json:"version"`
	Framework      string `json:"framework"`
	ArtifactURI    string `json:"artifact_uri"`
	Checksum       string `json:"checksum"`
}

type PredictionRequest struct {
	Inputs any           `json:"inputs"`
	Model  ModelMetadata `json:"model"`
}

type PredictionResponse struct {
	Prediction any `json:"prediction"`
}

type Runtime struct{}

func New() *Runtime {
	return &Runtime{}
}

func (r *Runtime) Predict(request PredictionRequest) (PredictionResponse, error) {
	if request.Model.Framework != "go-linear" {
		return PredictionResponse{}, fmt.Errorf(
			"%w: %s",
			ErrUnsupportedFramework,
			request.Model.Framework,
		)
	}

	input, ok := request.Inputs.(float64)
	if !ok {
		return PredictionResponse{}, errors.New("go-linear expects one numeric input")
	}

	// Deterministic baseline runtime.
	//
	// Later this boundary can load native Go model artifacts or delegate
	// execution to specialized libraries without changing ModelForge core.
	prediction := 2*input + 1

	return PredictionResponse{
		Prediction: prediction,
	}, nil
}
