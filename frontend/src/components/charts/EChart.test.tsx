import { render } from "@testing-library/react";
import { EChart } from "./EChart";

const chart = vi.hoisted(() => ({
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
}));
const init = vi.hoisted(() => vi.fn(() => chart));
vi.mock("echarts", () => ({ init }));

test("renders the chart, responds to container resizing, and cleans up", () => {
  let onResize: () => void = () => {};
  const disconnect = vi.fn();
  const observe = vi.fn();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: () => void) {
        onResize = callback;
      }
      observe = observe;
      disconnect = disconnect;
    },
  );
  const { unmount } = render(
    <EChart option={{ title: { text: "Example" } }} />,
  );
  expect(init).toHaveBeenCalledWith(expect.any(HTMLElement), "dark", {
    renderer: "svg",
  });
  expect(chart.setOption).toHaveBeenCalledWith({
    title: { text: "Example" },
    backgroundColor: "transparent",
  });
  onResize();
  expect(chart.resize).toHaveBeenCalledOnce();
  unmount();
  expect(disconnect).toHaveBeenCalledOnce();
  expect(chart.dispose).toHaveBeenCalledOnce();
  vi.unstubAllGlobals();
});
