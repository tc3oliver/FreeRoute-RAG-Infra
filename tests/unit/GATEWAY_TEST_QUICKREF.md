# Gateway 單元測試快速參考

## 快速命令

```bash
# 運行所有 gateway 測試
pytest tests/unit/test_gateway*.py

# 運行並顯示覆蓋率
pytest tests/unit/test_gateway*.py --cov=services/gateway
pytest tests/unit/test_gateway*.py --cov=services/gateway --cov-report=term-missing

# 快速運行(靜默模式)
pytest tests/unit/test_gateway*.py -q

# 運行特定測試類
pytest tests/unit/test_gateway_models.py::TestRequestModels -v

# 運行特定測試函數
pytest tests/unit/test_gateway_deps.py::TestRequireKey::test_valid_api_key_in_header -v
```

## 測試文件結構

```
tests/unit/
├── test_gateway_config.py         # 配置載入 (25 測試)
├── test_gateway_deps.py           # API 金鑰驗證 (16 測試)
├── test_gateway_middleware.py     # 中介軟體 (16 測試)
├── test_gateway_models.py         # Pydantic 模型 (55 測試)
├── test_gateway_repositories.py   # 客戶端初始化 (13 測試)
├── test_gateway_routers.py        # 路由端點 (31 測試)
├── test_gateway_utils.py          # 工具函數 (27 測試)
├── test_gateway_graph_extract.py  # 圖提取 (4 測試)
├── test_gateway_handlers.py       # 處理器 (5 測試)
└── test_gateway_metrics.py        # 指標 (2 測試)
```

## 常見測試模式

### 1. 測試 Pydantic 模型

```python
from services.gateway.models import ChatReq

def test_model_validation():
    req = ChatReq(messages=[{"role": "user", "content": "Hello"}])
    assert req.messages[0]["role"] == "user"
```

### 2. 測試環境變數

```python
def test_config_env_var(monkeypatch):
    monkeypatch.setenv("MY_VAR", "test_value")
    # ... 測試使用環境變數的代碼
```

### 3. Mock HTTP 請求

```python
def test_http_request(monkeypatch):
    import httpx

    def mock_post(*args, **kwargs):
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"result": "success"}
        )

    monkeypatch.setattr(httpx, "post", mock_post)
```

### 4. 測試 FastAPI 依賴

```python
from services.gateway.deps import require_key

def test_auth_dependency(monkeypatch):
    monkeypatch.setenv("API_KEYS", "test-key")
    # 必須顯式傳遞 None
    result = require_key(x_api_key="test-key", authorization=None)
    assert result == "test-key"
```

### 5. Mock 外部模組

```python
def test_import_mock(monkeypatch):
    import sys
    from types import SimpleNamespace

    # Mock 整個模組
    mock_module = SimpleNamespace(
        MyClass=lambda: "mocked"
    )
    monkeypatch.setitem(sys.modules, "external_module", mock_module)
```

## 關鍵設置

### Schema 路徑設置 (必需!)

每個測試文件都需要在導入 gateway 模組前設置:

```python
import os
from pathlib import Path

# 在任何 gateway 導入之前設置!
ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))
```

## 覆蓋率目標

| 優先級 | 模組 | 當前 | 目標 |
|--------|------|------|------|
| ✅ 完成 | models.py | 100% | 100% |
| ✅ 完成 | deps.py | 100% | 100% |
| ✅ 完成 | middleware.py | 100% | 100% |
| ⚠️ 良好 | config.py | 95% | 100% |
| ⚠️ 良好 | utils.py | 85% | 95% |
| ❌ 需要 | vector_service.py |

## 故障排除

### 問題: RuntimeError - GRAPH_SCHEMA_PATH not set
**解決方案**: 確保在測試文件頂部設 11% | 80% |
| ❌ 需要 | graph_service.py | 60% | 85% |置環境變數

### 問題: AttributeError - 'dict' has no attribute 'get'
**解決方案**: 使用 MockHeaders 類而非普通 dict

### 問題: TypeError - require_key() missing required argument
**解決方案**: 顯式傳遞 None: `require_key(x_api_key=None, authorization=None)`

### 問題: AttributeError - 'URL' object has no attribute 'rstrip'
**解決方案**: 先轉換為字串: `str(url).rstrip("/")`

### 問題: ModuleNotFoundError - No module named 'qdrant_client'
**解決方案**: Mock sys.modules 或簡化測試只驗證函數存在

## 最佳實踐

1. ✅ 為每個功能模組建立單獨的測試類
2. ✅ 使用描述性的測試名稱 (test_what_when_expected)
3. ✅ 使用 monkeypatch 而非全域 mock
4. ✅ 測試成功路徑和錯誤路徑
5. ✅ 使用 SimpleNamespace 創建簡單的 mock 對象
6. ✅ 在測試開始時設置所有必需的環境變數
7. ✅ 使用 pytest.raises() 測試預期的異常
8. ✅ 保持測試獨立和隔離
9. ✅ 清理測試後的狀態 (通常 pytest 自動處理)
10. ✅ 註釋複雜的 mock 設置

## 持續整合

建議的 CI 工作流程:

```yaml
- name: Run Gateway Unit Tests
  run: |
    pytest tests/unit/test_gateway*.py \
      --cov=services/gateway \
      --cov-report=xml \
      --cov-fail-under=70 \
      -v
```

## 相關文件

- [Gateway README (EN)](../../services/gateway/README.en.md)
- [Gateway README (ZH)](../../services/gateway/README.zh.md)
