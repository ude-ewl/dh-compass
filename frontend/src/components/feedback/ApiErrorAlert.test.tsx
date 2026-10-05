import { render, screen } from "@testing-library/react";

import { ApiClientError } from "../../api/client";
import { ApiErrorAlert } from "./ApiErrorAlert";

describe("API error alert", () => {
  it("shows server-provided field validation feedback", () => {
    const error = new ApiClientError(422, {
      code: "SCENARIO_VALIDATION_FAILED",
      message: "The scenario configuration is invalid.",
      field_errors: [
        {
          path: "network.linear_heat_density_threshold",
          message: "Must be nonnegative.",
        },
      ],
      details: {},
      request_id: "request-42",
    });

    render(<ApiErrorAlert error={error} />);

    expect(
      screen.getByText("The scenario configuration is invalid."),
    ).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveTextContent(
      "network.linear_heat_density_threshold: Must be nonnegative.",
    );
  });
});
