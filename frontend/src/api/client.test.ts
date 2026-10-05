import {
  ApiClientError,
  getHealth,
  isTransientApiError,
  shouldRetryApiRequest,
  startCalculation,
} from "./client";

describe("API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the calculation bbox with a retry-safe idempotency key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: "run-42",
          status: "queued",
          status_url: "/api/v1/runs/run-42",
          bbox: [7.1, 51.2, 7.2, 51.3],
          configuration_version: "default-v1",
        }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      startCalculation([7.1, 51.2, 7.2, 51.3], "key-42"),
    ).resolves.toMatchObject({
      run_id: "run-42",
      status: "queued",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/calculations",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ bbox: [7.1, 51.2, 7.2, 51.3] }),
      }),
    );
    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(requestInit.headers).get("Idempotency-Key")).toBe(
      "key-42",
    );
  });

  it("normalizes a browser network failure as a retryable API error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

    const error = await getHealth().catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(ApiClientError);
    expect(error).toMatchObject({
      status: 0,
      payload: { code: "API_UNAVAILABLE" },
    });
    expect(isTransientApiError(error)).toBe(true);
    expect(shouldRetryApiRequest(0, error)).toBe(true);
    expect(shouldRetryApiRequest(3, error)).toBe(false);
  });

  it("normalizes an API error envelope and preserves its request ID", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "SCENARIO_VALIDATION_FAILED",
            message: "The scenario contains invalid values.",
            field_errors: [
              {
                path: "network.linear_heat_density_threshold",
                message: "Value is invalid.",
              },
            ],
            details: {},
            request_id: "request-42",
          }),
          {
            status: 422,
            headers: {
              "Content-Type": "application/json",
              "X-Request-ID": "request-42",
            },
          },
        ),
      ),
    );

    await expect(getHealth()).rejects.toMatchObject({
      name: "ApiClientError",
      status: 422,
      payload: {
        code: "SCENARIO_VALIDATION_FAILED",
        request_id: "request-42",
      },
    });
    await expect(getHealth()).rejects.toBeInstanceOf(ApiClientError);
  });
});
