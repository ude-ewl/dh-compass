import {
  bboxAreaKm2,
  bboxReducer,
  initialBBoxInteractionState,
  moveBBox,
  normalizeBBox,
  resizeBBox,
  validateBBox,
  type BBox,
} from "./bbox";

describe("bounding-box geometry", () => {
  const bbox: BBox = [7, 51, 7.2, 51.2];

  it("normalizes either drag direction", () => {
    expect(normalizeBBox([7.2, 51.2], [7, 51])).toEqual(bbox);
  });

  it("resizes every corner without inverted bounds", () => {
    expect(resizeBBox(bbox, "southwest", [7.1, 51.1])).toEqual([
      7.1, 51.1, 7.2, 51.2,
    ]);
    expect(resizeBBox(bbox, "northeast", [6.9, 50.9])).toEqual([
      6.9, 50.9, 7, 51,
    ]);
  });

  it("moves a rectangle while clamping it to the supplied bounds", () => {
    expect(moveBBox(bbox, [7.1, 51.1], [20, 60], [6, 50, 8, 52])).toEqual([
      7.8, 51.8, 8, 52,
    ]);
  });

  it("keeps the previous rectangle when drawing is cancelled", () => {
    const state = initialBBoxInteractionState(bbox);
    const drawing = bboxReducer(state, {
      type: "begin-drawing",
      start: [7.1, 51.1],
      previous: bbox,
    });
    const draft = bboxReducer(drawing, {
      type: "update",
      point: [7.4, 51.4],
    });

    expect(bboxReducer(draft, { type: "cancel" })).toEqual({
      kind: "idle",
      bbox,
    });
  });

  it("returns the server-compatible area and coverage issues", () => {
    expect(bboxAreaKm2(bbox)).toBeGreaterThan(0);
    expect(validateBBox(bbox).issues).toEqual([]);
    expect(validateBBox([7, 51, 7, 51.2]).issues[0]?.code).toBe(
      "BBOX_LONGITUDE_ORDER",
    );
    expect(validateBBox([4, 51, 4.2, 51.2]).issues[0]?.code).toBe(
      "BBOX_OUTSIDE_NRW",
    );
  });
});
