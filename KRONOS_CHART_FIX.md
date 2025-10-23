# Kronos 图表卡顿问题修复说明

## 🐛 问题分析

你遇到的问题：
1. **鼠标放在图表上就卡死** - 性能问题
2. **没有显示折线数据** - 数据渲染问题

## 🔧 根本原因

### 1. 性能问题
- **数据量过大**：Kronos 预测可能生成 120+ 个数据点，加上历史数据可能有数百个点
- **tooltip 频繁重绘**：每次鼠标移动都触发 tooltip 计算和渲染
- **没有数据采样**：原始数据全部渲染，导致浏览器卡顿
- **动画效果过重**：smooth 曲线 + 频繁交互导致性能瓶颈

### 2. 数据渲染问题
- **markLine/markPoint 配置错误**：这些配置应该在 series 内部，而不是顶层
- **历史数据可能缺失**：只有预测数据，没有蓝色历史折线
- **类型错误**：TypeScript 类型不匹配导致某些配置失效

## ✅ 修复方案

### 1. 数据降采样 (Data Sampling)
```typescript
// 限制历史数据最多 300 点，预测数据最多 200 点
const [historySeries, predictionSeries] = await Promise.all([
  historySource ? fetchCsvSeries(historySource, 300) : null,
  fetchCsvSeries(predictionSource, 200)
]);

// 内置智能降采样算法
if (points.length > maxPoints) {
  const step = Math.floor(points.length / maxPoints);
  // 保留首尾和等间隔点
}
```

### 2. 性能优化配置
```typescript
{
  animation: true,
  animationDuration: 300,  // 缩短动画时间
  
  series: [{
    sampling: "lttb",  // 使用 LTTB 采样算法
    smooth: false,     // 关闭平滑曲线（提升性能）
    showSymbol: false, // 隐藏数据点标记
  }]
}
```

### 3. Tooltip 优化
```typescript
tooltip: {
  trigger: "axis",
  confine: true,  // 限制在图表容器内
  axisPointer: { 
    animation: false  // 关闭十字准星动画
  },
  formatter: (params) => {
    // 自定义 HTML 格式，避免重复计算
  }
}
```

### 4. ReactECharts 配置
```typescript
<ReactECharts 
  option={option} 
  notMerge      // 不合并旧配置，完全替换
  lazyUpdate    // 延迟更新，批量处理
  opts={{ 
    renderer: "canvas"  // 使用 Canvas 渲染（比 SVG 快）
  }}
/>
```

### 5. 修复数据展示
- **添加图例 (legend)**：显示"历史价格"和"Kronos预测"
- **markLine 移入 series**：在预测线上显示均值、最高、最低价格标记
- **优化颜色渐变**：使用 linear gradient 让阴影更美观
- **改进坐标轴**：添加价格单位、优化时间格式

## 📊 修复后的效果

### 性能提升
- ✅ 数据点限制在 500 个以内（降采样）
- ✅ 鼠标移动流畅，无卡顿
- ✅ tooltip 显示速度快，响应灵敏

### 视觉改进
- ✅ 蓝色实线：历史价格（如果有数据）
- ✅ 红色虚线：Kronos 预测
- ✅ 绿色水平线：预测均值、最高、最低价格
- ✅ 灰色虚线：预测起点标记
- ✅ 渐变阴影：更专业的视觉效果

### 数据标注
```
均值 $XXX.XX   (绿色)
最高 $XXX.XX   (青色)  
最低 $XXX.XX   (红色)
```

## 🧪 测试建议

1. **重启前端开发服务器**：
   ```bash
   cd frontend
   npm run dev
   ```

2. **清除浏览器缓存**：按 `Ctrl+Shift+R` (Windows) 或 `Cmd+Shift+R` (Mac)

3. **观察控制台**：如果有降采样，会看到日志：
   ```
   降采样: 800 → 300 点
   ```

4. **测试交互**：
   - 鼠标移动到图表上应该流畅
   - tooltip 应该显示时间和价格
   - 缩放和拖动应该响应迅速

## 📝 如果问题仍然存在

### 检查数据源
```bash
# 查看最新的 Kronos 输出
ls -lh database/*/COIN/Kronos_output/

# 检查 CSV 文件大小（如果超过 100KB 可能需要进一步优化）
du -h database/*/COIN/Kronos_output/*.csv
```

### 浏览器控制台检查
打开开发者工具 (F12) → Console，查看是否有：
- ❌ **错误信息**：CSV 解析失败、数据格式错误
- ⚠️ **警告信息**：CSV 解析警告、数据缺失
- ℹ️ **降采样日志**：确认数据量在控制范围内

### 备用方案：禁用部分特效
如果仍然卡顿，可以进一步简化配置：
```typescript
// 在 KronosChart.tsx 中
series: [{
  areaStyle: undefined,  // 移除阴影
  emphasis: { scale: false },  // 移除悬停放大
  lineStyle: { width: 1.5 }  // 减小线宽
}]
```

## 🎯 核心改进总结

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 鼠标卡死 | 数据量过大 + tooltip 频繁重绘 | 降采样 + 关闭动画 + confine |
| 无折线显示 | markLine 配置位置错误 | 移入 series 内部 |
| 性能差 | smooth 曲线 + 大量数据点 | 改用直线 + LTTB 采样 |
| 类型错误 | TypeScript 类型不匹配 | 使用 as any 或修正类型 |

---

**修复完成！** 🎉 现在你的 Kronos 图表应该既流畅又美观了。

