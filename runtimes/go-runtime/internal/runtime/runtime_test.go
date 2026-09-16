package runtime

import (
	"errors"
	"testing"
)

func TestPredict(t *testing.T) {
	engine := New()

	response, err := engine.Predict(PredictionRequest{
		Inputs: 5.0,
		Model: ModelMetadata{
			Framework: "go-linear",
		},
	})

	if err != nil {
		t.Fatalf("Predict returned unexpected error: %v", err)
	}

	got, ok := response.Prediction.(float64)
	if !ok {
		t.Fatalf("prediction has unexpected type %T", response.Prediction)
	}

	want := 11.0

	if got != want {
		t.Fatalf("prediction = %v, want %v", got, want)
	}
}

func TestPredictRejectsUnsupportedFramework(t *testing.T) {
	engine := New()

	_, err := engine.Predict(PredictionRequest{
		Inputs: 5.0,
		Model: ModelMetadata{
			Framework: "future-ai",
		},
	})

	if !errors.Is(err, ErrUnsupportedFramework) {
		t.Fatalf("expected ErrUnsupportedFramework, got %v", err)
	}
}

func TestPredictRejectsInvalidInput(t *testing.T) {
	engine := New()

	_, err := engine.Predict(PredictionRequest{
		Inputs: "invalid",
		Model: ModelMetadata{
			Framework: "go-linear",
		},
	})

	if err == nil {
		t.Fatal("expected invalid input to fail")
	}
}
