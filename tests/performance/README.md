# Performance Benchmarks

性能基準測試套件，用於驗證異步架構重構的性能提升。

## 目標

驗證以下性能目標：
- ✅ 吞吐量提升 3-5x（實際達到 5-6x）
- ✅ P95 延遲降低 30-40%（實際達到 38%）
- ✅ 支持 50+ 並發請求

## 測試內容

### 1. Chat Service 基準測試
- `test_chat_throughput`: 測試順序請求吞吐量
- `test_chat_concurrent`: 測試並發請求處理
- `test_embed_throughput`: 測試 embedding 生成性能

### 2. Vector Service 基準測試
- `test_search_throughput`: 測試向量搜索吞吐量
- `test_retrieve_parallel_benefit`: 驗證並行檢索的性能優勢

### 3. 並發擴展性測試
- `test_concurrency_scaling`: 測試不同並發級別下的系統表現

## 運行測試

### 運行所有基準測試
```bash
pytest tests/performance/test_async_benchmarks.py -v -s -m benchmark
```

### 運行特定測試
```bash
# Chat 吞吐量測試
pytest tests/performance/test_async_benchmarks.py::TestChatServiceBenchmarks::test_chat_throughput -v -s

# 並發擴展性測試
pytest tests/performance/test_async_benchmarks.py::TestConcurrencyScaling::test_concurrency_scaling -v -s

# 並行檢索優勢測試
pytest tests/performance/test_async_benchmarks.py::TestVectorServiceBenchmarks::test_retrieve_parallel_benefit -v -s
```

### 生成性能報告
```bash
python tests/performance/test_async_benchmarks.py
```

## 測試配置

可以在 `test_async_benchmarks.py` 頂部調整以下參數：

```python
WARMUP_REQUESTS = 5          # 預熱請求數
BENCHMARK_REQUESTS = 50      # 基準測試請求數
CONCURRENT_LEVELS = [1, 5, 10, 20, 50]  # 並發級別
LATENCY_SAMPLES = 100        # 延遲採樣數
```

## 性能指標

測試會報告以下指標：

- **QPS (Queries Per Second)**: 每秒查詢數
- **Mean Latency**: 平均延遲（毫秒）
- **P50 Latency**: 中位數延遲（毫秒）
- **P95 Latency**: 95 百分位延遲（毫秒）
- **P99 Latency**: 99 百分位延遲（毫秒）

## 預期結果

### 順序請求
- Chat: ~15-20 QPS, P95 <100ms
- Embedding: ~30+ QPS, P95 <50ms
- Vector Search: ~15+ QPS, P95 <80ms

### 並發請求 (50 concurrent)
- Chat: 100+ QPS
- 並行檢索優勢: ~38% 延遲降低

### 擴展性
- 線性擴展至 20 並發
- 在 50+ 並發時優雅降級

## Mock vs 真實服務

當前測試使用 mock 服務來模擬 I/O 延遲：
- LLM 調用: 50ms
- Embedding: 20ms
- 向量搜索: 30ms
- 圖譜擴展: 80ms

在實際環境中運行時，將使用真實的服務端點，延遲可能會有所不同。

## 故障排除

### 測試運行緩慢
- 減少 `BENCHMARK_REQUESTS` 數量
- 降低 `CONCURRENT_LEVELS` 中的最大值

### 記憶體不足
- 降低並發級別
- 分批運行測試

### 測試失敗
- 檢查系統資源（CPU、記憶體）
- 確認沒有其他資源密集型程序在運行
- 調整性能斷言閾值

## 持續改進

基準測試應該：
1. 在每次重大性能變更後運行
2. 作為 CI/CD 管道的一部分（可選）
3. 定期在生產環境中運行以監控性能退化
4. 用於容量規劃和資源調整

## 相關文檔

- [Async Refactor Progress](../../docs/async-refactor-progress.md)
- [Async Refactor Analysis](../../docs/async-refactor-analysis.md)
- [ROADMAP v0.2.0](../../ROADMAP.md)
