import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";

import { BoundingBoxMap } from "./BoundingBoxMap";

vi.mock("../../components/map/BaseMap", () => ({
  BaseMap: ({ fallback }: { fallback: ReactNode }) => <>{fallback}</>,
}));

describe("BoundingBoxMap keyboard interaction", () => {
  it("leaves drawing mode when Escape is pressed before a drag starts", async () => {
    const user = userEvent.setup();
    const onDrawingChange = vi.fn();
    render(<BoundingBoxMap onDrawingChange={onDrawingChange} />);

    await user.keyboard("r");
    await user.keyboard("{Escape}");

    expect(onDrawingChange).toHaveBeenNthCalledWith(1, true);
    expect(onDrawingChange).toHaveBeenLastCalledWith(false);
  });

  it("does not commit an area for an ordinary touch gesture while drawing is off", () => {
    const onChange = vi.fn();
    render(<BoundingBoxMap onChange={onChange} />);
    const map = screen.getByRole("img", { name: "Study area map fallback" });

    fireEvent.pointerDown(map, {
      clientX: 10,
      clientY: 10,
      pointerId: 1,
      pointerType: "touch",
    });
    fireEvent.pointerMove(map, {
      clientX: 80,
      clientY: 80,
      pointerId: 1,
      pointerType: "touch",
    });
    fireEvent.pointerUp(map, {
      clientX: 80,
      clientY: 80,
      pointerId: 1,
      pointerType: "touch",
    });

    expect(onChange).not.toHaveBeenCalled();
  });
});
