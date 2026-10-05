import { useLocale } from "../../i18n/locale";
import { useEffect, useRef } from "react";
import { init, type EChartsOption } from "echarts";

/** Render ECharts directly; resize and disposal follow the component lifecycle. */
export function EChart({ option }: { option: EChartsOption }) {
  useLocale();
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    const chart = init(container.current, "dark", { renderer: "svg" });
    chart.setOption({ ...option, backgroundColor: "transparent" });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [option]);

  return <div ref={container} style={{ height: 230 }} />;
}
