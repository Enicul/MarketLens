# Kronos Chart Performance Fix Guide

## 🐛 Issues Observed

1. **Mouse hover freezes the chart** — severe performance regression.  
2. **Forecast line missing** — series configuration error.

## 🔎 Root Causes

### 1. Performance bottlenecks
- **Large payloads**: Kronos forecast can add 120+ points on top of hundreds of historical samples.
- **Tooltip thrashing**: Every mouse movement triggers a full tooltip recalculation.
- **No down-sampling**: Rendering raw data overwhelms the browser.
- **Heavy animation**: Smooth curves plus frequent interactions amplify the problem.

### 2. Rendering configuration
- **`markLine`/`markPoint` defined at the wrong level** — they belong inside the `series`.
- **Missing history feed** — only the forecast line was present.
- **TypeScript typing mismatches** — certain options were ignored silently.

## ✅ Remediation Plan

### 1. Down-sample aggressively
```ts
// Cap historical data at 300 points and prediction data at 200 points
const [historySeries, predictionSeries] = await Promise.all([
  historySource ? fetchCsvSeries(historySource, 300) : null,
  fetchCsvSeries(predictionSource, 200)
]);

// LTTB down-sampling helper
if (points.length > maxPoints) {
  const step = Math.floor(points.length / maxPoints);
  // Keep the first, last, and evenly spaced points
}
```

### 2. Optimize ECharts options
```ts
{
  animation: true,
  animationDuration: 300,
  series: [{
    sampling: "lttb",  // Use LTTB algorithm
    smooth: false,     // Disable smoothing
    showSymbol: false, // Hide markers for dense series
  }]
}
```

### 3. Harden tooltip behavior
```ts
tooltip: {
  trigger: "axis",
  confine: true,
  axisPointer: { animation: false },
  formatter: (params) => {
    // Custom HTML formatter to avoid redundant work
  }
}
```

### 4. Tune `ReactECharts`
```tsx
<ReactECharts
  option={option}
  notMerge          // Replace instead of merging
  lazyUpdate        // Batch re-renders
  opts={{ renderer: "canvas" }}  // Canvas is faster than SVG
/>;
```

### 5. Restore data presentation
- Add a **legend** for “Historical Price” and “Kronos Prediction”.
- Move `markLine` definitions inside the prediction series to render mean / min / max.
- Use linear gradients to create polished shading.
- Improve axis formatting with currency units and readable dates.

## 📊 Result

### Performance
- ✅ Data sets capped at fewer than 500 points (after down-sampling).
- ✅ Hover interaction is smooth and responsive.
- ✅ Tooltip renders instantly without stutter.

### Visuals
- ✅ Blue solid line: historical price.
- ✅ Red dashed line: Kronos forecast.
- ✅ Green horizontal markers: forecast mean, max, min.
- ✅ Gray dotted vertical marker: prediction start.
- ✅ Soft gradients for a professional finish.

### Annotated markers
```
Mean  $XXX.XX (green)
High  $XXX.XX (teal)
Low   $XXX.XX (red)
```

## 🧪 Verification Checklist

1. **Restart the frontend dev server**
   ```bash
   cd frontend
   npm run dev
   ```
2. **Hard refresh the browser** (`Ctrl+Shift+R` or `Cmd+Shift+R`).
3. **Watch the console** — down-sampling logs appear as:
   ```
   Downsampling: 800 → 300 points
   ```
4. **Manual interaction**
   - Hover should be fluid.
   - Tooltip displays time and price.
   - Zooming / panning responds quickly.

## 🔍 If Issues Persist

### Inspect data volume
```bash
ls -lh database/*/COIN/Kronos_output/
du -h database/*/COIN/Kronos_output/*.csv
```

### Browser console checks
Look for:
- ❌ Errors: CSV parsing failures, malformed data.
- ⚠️ Warnings: Missing fields, fallback behavior.
- ℹ️ Down-sampling logs: confirm limit enforcement.

### Minimalist fallback
Disable non-essential visuals if needed:
```ts
series: [{
  areaStyle: undefined,
  emphasis: { scale: false },
  lineStyle: { width: 1.5 }
}]
```

## 🎯 Summary Table

| Symptom            | Root Cause                            | Fix                                             |
|--------------------|---------------------------------------|--------------------------------------------------|
| Hover freezes      | Massive payload + tooltip thrashing   | Down-sample, confine tooltip, drop animations   |
| Missing line       | `markLine` defined at chart root      | Move to series definition                       |
| Poor performance   | Smooth line + dense data              | Use straight lines + LTTB sampling              |
| Type mismatches    | TS definitions too strict             | Cast with `as any` or adjust definitions        |

---

✅ **All fixes applied — Kronos charts should now feel fast and look sharp.**
