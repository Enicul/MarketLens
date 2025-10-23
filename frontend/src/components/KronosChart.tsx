import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import Papa from "papaparse";

interface KronosChartProps {
  symbol: string;
  metadataUrl?: string;
  historyUrl?: string;
  predictionUrl?: string;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

const resolveUrl = (path?: string): string | undefined => {
  if (!path) return undefined;
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  if (path.startsWith("/")) {
    return `${API_BASE}${path}`;
  }
  return `${API_BASE}/${path}`;
};

interface ParsedPoint {
  time: number;
  label: string;
  value: number;
}

interface MetadataShape {
  prediction_summary?: {
    min_price?: number;
    max_price?: number;
    mean_price?: number;
    std_price?: number;
  };
  output_files?: {
    csv?: string;
  };
  input_csv?: string;
}

const fetchCsvSeries = async (url: string, maxPoints: number = 500): Promise<ParsedPoint[]> => {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`无法获取数据: ${url}`);
  }
  const text = await response.text();
  const parsed = Papa.parse<Record<string, string>>(text, {
    header: true,
    skipEmptyLines: true
  });
  if (parsed.errors.length) {
    console.warn("CSV 解析警告:", parsed.errors[0].message);
  }
  const rows = parsed.data.filter(Boolean);
  
  // 解析数据点
  const points = rows
    .map((row) => {
      const keyFor = (candidates: string[], fallback?: string) => {
        for (const key of candidates) {
          if (key in row) return row[key];
        }
        if (fallback) {
          const fuzzy = Object.keys(row).find((k) => k.replace(/^[^a-z0-9]+/i, "").toLowerCase().includes(fallback));
          if (fuzzy) return row[fuzzy];
        }
        return undefined;
      };

      const ts = keyFor(["timestamp", "Timestamp", "时间", "日期"], "timestamp");
      const close = keyFor(["close", "Close", "收盘价"], "close");
      if (!ts || !close) return null;
      const time = new Date(ts).getTime();
      if (Number.isNaN(time)) return null;
      const value = Number(close);
      if (!Number.isFinite(value)) return null;
      return {
        time,
        label: new Date(time).toISOString(),
        value
      } satisfies ParsedPoint;
    })
    .filter((point): point is ParsedPoint => Boolean(point));
  
  // 如果数据点过多，进行降采样（保留首尾和重要点）
  if (points.length > maxPoints) {
    console.log(`降采样: ${points.length} → ${maxPoints} 点`);
    const step = Math.floor(points.length / maxPoints);
    const sampled: ParsedPoint[] = [];
    for (let i = 0; i < points.length; i += step) {
      sampled.push(points[i]);
    }
    // 确保包含最后一个点
    if (sampled[sampled.length - 1].time !== points[points.length - 1].time) {
      sampled.push(points[points.length - 1]);
    }
    return sampled;
  }
  
  return points;
};

export function KronosChart({ symbol, metadataUrl, historyUrl, predictionUrl }: KronosChartProps) {
  const [history, setHistory] = useState<ParsedPoint[] | null>(null);
  const [prediction, setPrediction] = useState<ParsedPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let abort = false;
    const load = async () => {
      try {
        let meta: MetadataShape | null = null;
        const resolvedMetadata = resolveUrl(metadataUrl);
        if (resolvedMetadata) {
          const res = await fetch(resolvedMetadata);
          if (res.ok) {
            meta = (await res.json()) as MetadataShape;
          }
        }
        const historySource = resolveUrl(historyUrl ?? meta?.input_csv);
        const predictionSource = resolveUrl(predictionUrl ?? meta?.output_files?.csv);

        if (!predictionSource) {
          throw new Error("缺少Kronos预测数据");
        }

        const [historySeries, predictionSeries] = await Promise.all([
          historySource ? fetchCsvSeries(historySource, 300) : Promise.resolve<ParsedPoint[] | null>(null),
          fetchCsvSeries(predictionSource, 200)
        ]);

        if (abort) return;
        setHistory(historySeries);
        setPrediction(predictionSeries);
        setError(null);
      } catch (e) {
        if (abort) return;
        setError((e as Error).message);
      }
    };

    load();
    return () => {
      abort = true;
    };
  }, [metadataUrl, historyUrl, predictionUrl]);

  const option = useMemo<EChartsOption | undefined>(() => {
    if (!prediction?.length) return undefined;
    const historyData = [...(history ?? [])].sort((a, b) => a.time - b.time);
    const predictionData = [...prediction].sort((a, b) => a.time - b.time);
    const allPoints = [...historyData, ...predictionData];
    const minValue = Math.min(...allPoints.map((p) => p.value));
    const maxValue = Math.max(...allPoints.map((p) => p.value));
    const predictionStart = historyData.length ? historyData[historyData.length - 1].time : predictionData[0].time;

    // 计算统计信息
    const predMean = predictionData.reduce((sum, p) => sum + p.value, 0) / predictionData.length;
    const predMin = Math.min(...predictionData.map(p => p.value));
    const predMax = Math.max(...predictionData.map(p => p.value));

    return {
      animation: true,
      animationDuration: 300,
      backgroundColor: "#ffffff",
      title: {
        text: `${symbol.toUpperCase()} Kronos 预测走势`,
        left: "center",
        textStyle: { fontSize: 16, fontWeight: "bold", color: "#111827" }
      },
      tooltip: {
        trigger: "axis",
        confine: true,
        axisPointer: { 
          type: "cross", 
          label: { backgroundColor: "#374151" },
          animation: false
        },
        formatter: (params: any) => {
          if (!Array.isArray(params) || params.length === 0) return "";
          const time = new Date(params[0].value[0]).toLocaleString("zh-CN");
          let content = `<div style="font-size:12px;font-weight:bold;margin-bottom:4px;">${time}</div>`;
          params.forEach((param: any) => {
            const value = param.value[1];
            const color = param.color;
            content += `<div style="display:flex;align-items:center;gap:6px;">
              <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};"></span>
              <span>${param.seriesName}: <strong>$${value.toFixed(2)}</strong></span>
            </div>`;
          });
          return content;
        }
      },
      legend: {
        data: historyData.length ? ["历史价格", "Kronos预测"] : ["Kronos预测"],
        top: 30,
        textStyle: { color: "#4b5563" }
      },
      grid: { left: 70, right: 50, top: 70, bottom: 70, containLabel: true },
      xAxis: {
        type: "time",
        axisLabel: { 
          color: "#4b5563",
          formatter: (value: number) => {
            const date = new Date(value);
            return `${date.getMonth() + 1}/${date.getDate()}`;
          }
        },
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        splitLine: { show: true, lineStyle: { color: "#f1f5f9" } }
      } as any,
      yAxis: {
        type: "value",
        name: "价格 (USD)",
        nameTextStyle: { color: "#64748b", fontSize: 12 },
        axisLabel: {
          formatter: (value: number) => `$${value.toFixed(0)}`,
          color: "#4b5563"
        },
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        min: minValue * 0.97,
        max: maxValue * 1.03
      },
      series: [
        historyData.length > 0
          ? {
              name: "历史价格",
              type: "line",
              smooth: false,
              sampling: "lttb",
              showSymbol: false,
              symbol: "circle",
              symbolSize: 4,
              emphasis: { 
                focus: "series",
                scale: true
              },
              lineStyle: { color: "#1f77b4", width: 2.5 },
              areaStyle: { 
                color: {
                  type: "linear",
                  x: 0, y: 0, x2: 0, y2: 1,
                  colorStops: [
                    { offset: 0, color: "rgba(31, 119, 180, 0.15)" },
                    { offset: 1, color: "rgba(31, 119, 180, 0.01)" }
                  ]
                }
              },
              data: historyData.map((p) => [p.time, p.value]),
              markLine: historyData.length > 0 ? {
                silent: true,
                symbol: "none",
                lineStyle: { color: "#94a3b8", width: 1.5, type: "dotted" },
                label: {
                  formatter: "预测起点",
                  color: "#64748b",
                  fontSize: 11,
                  position: "insideEndTop"
                },
                data: [{ xAxis: predictionStart }]
              } : undefined
            }
          : null,
        {
          name: "Kronos预测",
          type: "line",
          smooth: false,
          sampling: "lttb",
          showSymbol: false,
          symbol: "circle",
          symbolSize: 4,
          emphasis: { 
            focus: "series",
            scale: true
          },
          lineStyle: { color: "#d62728", width: 2.5, type: "dashed" },
          areaStyle: { 
            color: {
              type: "linear",
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(214, 39, 40, 0.15)" },
                { offset: 1, color: "rgba(214, 39, 40, 0.01)" }
              ]
            }
          },
          data: predictionData.map((p) => [p.time, p.value]),
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#22c55e", width: 1, type: "dashed", opacity: 0.6 },
            label: { show: false },
            data: [
              { yAxis: predMean, label: { show: true, formatter: `均值 $${predMean.toFixed(2)}`, position: "insideEndTop", color: "#16a34a" } },
              { yAxis: predMin, label: { show: true, formatter: `最低 $${predMin.toFixed(2)}`, position: "insideEndBottom", color: "#dc2626" } },
              { yAxis: predMax, label: { show: true, formatter: `最高 $${predMax.toFixed(2)}`, position: "insideEndTop", color: "#0891b2" } }
            ]
          }
        }
      ].filter(Boolean) as any[]
    } satisfies EChartsOption;
  }, [history, prediction, symbol]);

  if (error) {
    return <div className="chart-error">无法加载Kronos预测图：{error}</div>;
  }
  if (!option) {
    return <div className="chart-loading">正在加载Kronos预测数据…</div>;
  }

  return (
    <div className="kronos-chart">
      <ReactECharts 
        option={option} 
        notMerge 
        lazyUpdate 
        style={{ height: 400 }} 
        opts={{ 
          renderer: "canvas"
        }}
      />
    </div>
  );
}

export default KronosChart;
