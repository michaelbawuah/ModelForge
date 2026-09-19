FROM golang:1.27-alpine AS build

WORKDIR /src

COPY go.mod ./
RUN go mod download

COPY cmd ./cmd
COPY internal ./internal

RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
    -o /out/modelforge-go-runtime ./cmd/server

FROM alpine:3.22

RUN addgroup -S modelforge \
    && adduser -S -G modelforge modelforge \
    && apk add --no-cache ca-certificates

COPY --from=build /out/modelforge-go-runtime /usr/local/bin/modelforge-go-runtime

USER modelforge

EXPOSE 8090

ENTRYPOINT ["/usr/local/bin/modelforge-go-runtime"]
