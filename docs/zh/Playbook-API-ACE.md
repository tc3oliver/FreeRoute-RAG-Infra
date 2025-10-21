# Playbook-API（ACE 策略層）設計與實作指南

**定位**：`playbook-api` 是一個**獨立的策略層服務**，負責將「可演化的任務策略（Playbook ＝ 規則卡片）」在請求時**檢索、裁剪並注入**到下游 LLM 之前的 System Prompt；同時將執行軌跡回報，支援後續**反思（Reflector）**與**策展（Curator）**做增量更新。
**與 RAG 的關係**：解耦。RAG 決定**回答什麼（證據）**，Playbook 決定**怎麼回答（策略）**。

---

## 1. 原理與設計目標

### 1.1 原理（ACE 簡述）

* **Playbook = 策略層知識**：由小粒度規則卡片（rule）構成，每張卡包含 `triggers`（觸發條件）、`instruction`（可注入的策略語句）、`score`（排序/優先級）等。
* **三層治理**：`Global → Domain（任務域） → Tenant/User`。合併優先：越貼近請求者優先（User > Tenant > Domain > Global）。
* **小增量合併**：新策略由反思/策展以「ADD/UPDATE」小改動進入 Playbook，避免重寫整段 context 造成崩塌與退化。
* **線上選取**：每次請求將依 `triggers` 混合檢索（關鍵詞/標籤/語義），做 **Top-K + Token Budget** 裁剪，輸出最小必要策略子集。
* **線下演化**：回報的 `session_traces` 提供 Reflector 產出 `candidate_deltas`，Curator 人工或半自動審核後入庫。

### 1.2 設計目標

* **低耦合**：獨立服務，Gateway 透過簡單 HTTP 介面存取。
* **低延遲**：Redis 短 TTL 快取、輕量查詢、嚴格 Token Budget。
* **可治理**：分層、版本化、回滾、審核、審計。
* **可觀測**：對規則命中率、token 佔比、延遲、成功率有儀表板。
* **可擴展**：初期 Postgres + keyword；量大再加向量（pgvector 或 Qdrant 的專用 collection）。

---

## 2. 高階架構與資料流

```mermaid
flowchart LR
  subgraph Client["Client / 外部呼叫者"]
  end

  subgraph GW["API Gateway (Infra)"]
    GWCHAT["/chat"]
  end

  subgraph PB["Playbook-API (Policy Service)"]
    SELECTOR["Selector\n(分層檢索 + TopK + TokenBudget)"]
    ASSEMBLER["Assembler\n(可選：若只回規則則由GW組版)"]
    CURATOR["Curator\n(版本化/小增量合併)"]
    REFLECTOR["Reflector Job\n(離線/排程)"]
  end

  subgraph ST["Storage"]
    PG[(Postgres: rules/traces/candidates/versions)]
    RD[(Redis: 短TTL快取)]
    VEC[[可選：pgvector/Qdrant\n(規則語義檢索)]]
  end

  Client --> GWCHAT
  GWCHAT -->|POST /playbook/select| PB
  PB --> SELECTOR --> PG
  SELECTOR --> RD
  PB -->|回傳 rules[]| GWCHAT
  GWCHAT -->|組Prompt + 調LLM| GWCHAT
  GWCHAT -->|POST /feedback/report| PB
  PB --> PG
  REFLECTOR --> PG
  CURATOR --> PG
```

**建議**：`playbook-api` 只回 **rules[]** 與 `used_tokens` 給 Gateway，**組版（Assembler）放在 Gateway**，延遲更低且可控；若需要，也可在 `playbook-api` 內提供 `/assemble` 選配端點。

---

## 3. API 介面（OpenAPI 契約）

> 路徑前綴建議 `/playbook`，回報路徑前綴 `/feedback`。均採 JSON。

### 3.1 `POST /playbook/select`

**用途**：依請求的 `domain/tenant/user/triggers` 回傳「已裁剪的規則卡」
**請求**

```json
{
  "domain": "financial_analysis",
  "tenant_id": "client_abc",
  "user_id": "u123",
  "triggers": ["financial_analysis", "growth", "peer_missing"],
  "token_budget": 800,
  "top_k": 8,
  "prefer_layers": ["user", "tenant", "domain", "global"]  // 可選：覆寫預設優先
}
```

**回應**

```json
{
  "rules": [
    {
      "rule_id": "meta-citation",
      "layer": "global",
      "instruction": "Always include citations when numeric data appears.",
      "score": 0.91,
      "estimated_tokens": 32
    },
    {
      "rule_id": "delta-cmp-001",
      "layer": "domain",
      "instruction": "Include a same-period peer comparison table for growth questions.",
      "score": 0.73,
      "estimated_tokens": 28
    }
  ],
  "used_tokens": 60,
  "policy": {
    "budget": 800,
    "top_k": 8,
    "layer_quotas": {"global": 0.2, "domain": 0.6, "tenant_user": 0.2}
  }
}
```

### 3.2 `POST /feedback/report`

**用途**：回報執行結果供觀測/反思
**請求**

```json
{
  "domain": "financial_analysis",
  "tenant_id": "client_abc",
  "user_id": "u123",
  "query": "分析 A 2025Q2 vs 2024Q2 並比較 B",
  "rules_hit": ["meta-citation", "delta-cmp-001"],
  "rag_docs": ["doc://10Q_A_2025Q2", "doc://10Q_A_2024Q2"],
  "tool_calls": [{"name":"extract_xbrl","args":{}}],
  "latency_ms": 1240,
  "prompt_tokens": 980,
  "output_tokens": 420,
  "success": true,
  "user_score": 4.0,
  "notes": "與同業相比部分用戶想看長期平均"
}
```

**回應**

```json
{"ok": true, "trace_id": 102391}
```

### 3.3 規則管理（內部/後台）

* `GET /playbook/rules/search?domain=financial_analysis&q=peer`
* `POST /playbook/rules`（新增 rule）
* `PATCH /playbook/rules/{rule_id}`（更新 instruction/score/layer）
* `POST /playbook/curate/apply`（把候選增量轉正）
* `POST /playbook/versions/release`（封版，產生 change_log，支援回滾）

---

## 4. 資料模型與 Schema（Postgres）

```sql
-- 1) Playbook 規則（分層 + 觸發 + 指令）
CREATE TABLE playbook_rules (
  rule_id TEXT PRIMARY KEY,
  domain TEXT NOT NULL,              -- "global" or specific domain
  tenant_id TEXT,                    -- NULL=shared
  user_id TEXT,                      -- NULL=shared
  triggers JSONB NOT NULL,           -- ["financial_analysis","peer_missing"]
  instruction TEXT NOT NULL,         -- 注入的策略文本
  score REAL DEFAULT 0.5,            -- 排序依據之一
  priority INT DEFAULT 0,            -- 額外優先級控制（可選）
  updated_at TIMESTAMP DEFAULT now()
);

-- 2) Session traces（回報執行資訊）
CREATE TABLE session_traces (
  trace_id BIGSERIAL PRIMARY KEY,
  domain TEXT,
  tenant_id TEXT,
  user_id TEXT,
  query TEXT,
  rag_docs JSONB,
  tool_calls JSONB,
  rules_hit TEXT[],
  latency_ms INT,
  prompt_tokens INT,
  output_tokens INT,
  user_score REAL,
  success BOOL,
  created_at TIMESTAMP DEFAULT now()
);

-- 3) 候選增量（Reflector 產出，等待審核）
CREATE TABLE candidate_deltas (
  cand_id BIGSERIAL PRIMARY KEY,
  domain TEXT,
  tenant_id TEXT,
  user_id TEXT,
  triggers JSONB,
  instruction TEXT,
  suggest_score REAL,
  status TEXT DEFAULT 'pending',     -- pending/approved/rejected
  evidence_refs JSONB,               -- 可選：關聯 trace/doc
  created_at TIMESTAMP DEFAULT now()
);

-- 4) 版本管理（封版/回滾）
CREATE TABLE playbook_versions (
  version_id BIGSERIAL PRIMARY KEY,
  domain TEXT,
  tenant_id TEXT,
  user_id TEXT,
  change_log JSONB,                  -- [{rule_id, action, before?, after?}]
  created_by TEXT,
  created_at TIMESTAMP DEFAULT now()
);
```

> **向量檢索（選配）**：
> 早期直接用 `triggers`（keyword/tag）＋`score` 排序即可；若規模 > 1000 條規則或語意場景複雜，再新增：
>
> * `embedding VECTOR(1536)`（pgvector），或
> * 在 Qdrant 開 `collection=playbook_rules`（專屬策略向量庫，不與文件向量混用）。

---

## 5. Selector 核心演算法（Top-K + Token Budget）

**排序因子**（可線性組合）：

* `keyword_match`：`triggers` 與查詢特徵/任務標籤的交集程度
* `layer_boost`：user/tenant/domain/global 的優先權
* `score`：條目固有分數（反映歷史有效性）
* `recency_boost`：新近更新條目加權
* `ab_bucket`：A/B 流量桶調整

**裁剪流程**

1. 取候選集：`global + domain + tenant + user`
2. 排序：hybrid rank（如 `final = 0.4*keyword + 0.3*layer + 0.2*score + 0.1*recency`）
3. Token 預算：按層級配額（如 `global 20% / domain 60% / tenant+user 20%`），逐條累加 `estimated_tokens`，超過即停
4. 產出：`rules[]` + `used_tokens` + `policy` 回傳 Gateway

---

## 6. 與 API Gateway / RAG 的整合

### 6.1 /chat Pipeline（Gateway 端）

```mermaid
sequenceDiagram
  participant U as User
  participant G as API Gateway (/chat)
  participant P as Playbook-API
  participant R as Retriever (Qdrant/Neo4j)
  participant L as LiteLLM

  U->>G: /chat {domain,tenant,user,query,...}
  G->>P: POST /playbook/select {domain,tenant,user,triggers,budget,top_k}
  P-->>G: rules[]
  alt 啟用 RAG
    G->>R: retrieve(query)
    R-->>G: evidences[]
  end
  G->>G: assemble(base + rules + evidences?)
  G->>L: completions(messages)
  L-->>G: answer + usage
  G->>P: POST /feedback/report {trace metrics...}
  G-->>U: answer
```

> 建議把 **Assembler** 放在 Gateway**，因為 Gateway 已整合 RAG 證據，組版一次完成，避免跨服務折返。

### 6.2 組版（Assembler）樣板

```python
def assemble(base_system: str, rules: list[str], evidences: list[str] | None) -> str:
    tactics = "\n".join(f"- {r}" for r in rules)
    ev = "" if not evidences else "\n".join(evidences[:5])
    return f"""{base_system}

## Task-specific Tactics (Playbook)
{tactics}

## Evidence (Top-5)
{ev}
"""
```

---

## 7. 快取策略與效能建議

* **Redis 短 TTL**：以 `(domain, tenant, user, triggers_hash, budget, top_k)` 為 key，TTL 3–30 秒。
* **冷熱分離**：Global/Domain 規則使用較長 TTL；User/Tenant 使用短 TTL。
* **避免 Over-fetch**：先用 keyword/tag 初選，再視需要才查向量（若啟用）。
* **Token 預估**：對 `instruction` 以簡單字數/詞元估算，避免過長策略卡被誤選。
* **壓測**：目標 p95 < 5ms（無向量）/< 15ms（含向量），單實例 QPS 200+。

---

## 8. 權限、多租戶與安全

* **多租戶隔離**：`tenant_id/user_id` 欄位為主，查詢時務必帶入過濾；建議開啟 Postgres Row Level Security（RLS）於管理面板路徑。
* **RBAC**：

  * Admin：可審核 candidate、封版、回滾
  * Domain Owner：可維護某 domain 的 rules
  * Tenant Owner：僅能維護自己 tenant 的 rules/user 偏好
* **敏感策略**：對規則卡標 `sensitive=true` 與白名單 `allowed_env=["intranet"]`；在 `/playbook/select` 依呼叫來源/環境決定是否返回。
* **輸出防洩**：避免把敏感內規直接暴露於最終回答（策略只影響模型行為，不當作回答內容輸出）。

---

## 9. 可觀測性（Metrics / Logs / Tracing）

**Metrics（Prometheus）**

* 成功率/評分：`success_rate`, `avg_user_score`
* 策略效果：`rules_hit_ratio`, `top_rules_by_hit`
* 成本/延遲：`latency_ms`, `prompt_tokens`, `token_playbook_ratio`（策略 token/總 token）
* 學習能量：`candidate_per_day`, `candidate_accept_rate`
* 風險：`rollback_count`, `sensitive_rule_hits`

**Tracing（OpenTelemetry）**

* 為 `/playbook/select` 與 `/feedback/report` 加 span；記錄命中的規則與排序得分。

---

## 10. 部署（Docker / K8s）

### 10.1 docker-compose（範例）

```yaml
version: "3.9"
services:
  playbook-api:
    build: .
    image: playbook-api:latest
    ports: ["9901:8000"]
    env_file: .env
    depends_on: [postgres, redis]
  postgres:
    image: pgvector/pgvector:pg16   # 若先不做向量，可用官方 postgres
    environment: { POSTGRES_PASSWORD: dev }
    volumes: ["pgdata:/var/lib/postgresql/data"]
  redis:
    image: redis:7
    command: ["redis-server", "--save", "", "--appendonly", "no"]
volumes: { pgdata: {} }
```

`.env`

```
DATABASE_URL=postgresql+psycopg://postgres:dev@postgres:5432/postgres
REDIS_URL=redis://redis:6379/0
TOKEN_BUDGET_TOTAL=800
LAYER_QUOTAS=global:0.2,domain:0.6,tenant_user:0.2
CACHE_TTL_SECONDS=10
```

### 10.2 K8s（片段）

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: playbook-api }
spec:
  replicas: 2
  selector: { matchLabels: { app: playbook-api } }
  template:
    metadata: { labels: { app: playbook-api } }
    spec:
      containers:
      - name: api
        image: registry.local/playbook-api:latest
        ports: [{containerPort: 8000}]
        envFrom: [{secretRef: {name: playbook-api-env}}]
        readinessProbe: { httpGet: { path: /healthz, port: 8000 }, initialDelaySeconds: 5, periodSeconds: 5 }
        livenessProbe:  { httpGet: { path: /livez,   port: 8000 }, initialDelaySeconds: 10, periodSeconds: 10 }
---
apiVersion: v1
kind: Service
metadata: { name: playbook-api }
spec:
  selector: { app: playbook-api }
  ports:
  - name: http
    port: 9901
    targetPort: 8000
```

---

## 11. 最小可跑樣板（FastAPI + SQLAlchemy）

> 本樣板只示範 `POST /playbook/select` 與 `POST /feedback/report` 的關鍵邏輯；CRUD/版本化/反思可按需求擴充。

**`app/main.py`**

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import os
from app.repo import select_candidate_rules, insert_trace
from app.selector import rank_and_clip
from app.policy import load_policy

app = FastAPI(title="Playbook API", version="1.0")

class SelectReq(BaseModel):
    domain: str
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    triggers: List[str] = Field(default_factory=list)
    token_budget: int = Field(default=int(os.getenv("TOKEN_BUDGET_TOTAL", "800")))
    top_k: int = 8
    prefer_layers: Optional[List[Literal["user","tenant","domain","global"]]] = None

class RuleResp(BaseModel):
    rule_id: str
    layer: Literal["user","tenant","domain","global"]
    instruction: str
    score: float
    estimated_tokens: int

class SelectResp(BaseModel):
    rules: List[RuleResp]
    used_tokens: int
    policy: dict

class FeedbackReq(BaseModel):
    domain: str
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    query: str
    rules_hit: List[str] = Field(default_factory=list)
    rag_docs: Optional[List[str]] = None
    tool_calls: Optional[List[dict]] = None
    latency_ms: Optional[int] = None
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    success: Optional[bool] = None
    user_score: Optional[float] = None
    notes: Optional[str] = None

@app.post("/playbook/select", response_model=SelectResp)
def select(req: SelectReq):
    policy = load_policy(req.prefer_layers)
    candidates = select_candidate_rules(req.domain, req.tenant_id, req.user_id, req.triggers)
    rules, used = rank_and_clip(candidates, req.triggers, req.token_budget, req.top_k, policy)
    return SelectResp(rules=rules, used_tokens=used, policy=policy)

@app.post("/feedback/report")
def feedback(req: FeedbackReq):
    trace_id = insert_trace(req.dict())
    return {"ok": True, "trace_id": trace_id}

@app.get("/healthz")
def healthz():
    return {"ok": True}
```

**`app/policy.py`**

```python
import os
def load_policy(prefer_layers=None):
    quotas = os.getenv("LAYER_QUOTAS", "global:0.2,domain:0.6,tenant_user:0.2")
    q = {}
    for kv in quotas.split(","):
        k,v = kv.split(":")
        q[k] = float(v)
    order = prefer_layers or ["user","tenant","domain","global"]
    return {"layer_quotas": q, "order": order, "budget": int(os.getenv("TOKEN_BUDGET_TOTAL","800"))}
```

**`app/selector.py`**

```python
from typing import List, Tuple, Dict

def estimate_tokens(text: str) -> int:
    # 粗估：英文 1 token ≈ 4 chars，中文可自訂；這裡簡化
    return max(1, len(text) // 4)

def hybrid_score(rule, triggers: List[str], layer_weight: Dict[str,float]) -> float:
    # keyword 命中
    trig = set([t.lower() for t in triggers])
    hit = len(trig.intersection(set([t.lower() for t in rule["triggers"]])))
    kw = min(1.0, hit / max(1,len(triggers)))
    # 層級加權
    lw = layer_weight.get(rule["layer"], 1.0)
    # rule 固有分數
    base = float(rule.get("score", 0.5))
    # 綜合
    return 0.5*kw + 0.3*base + 0.2*lw

def rank_and_clip(candidates: List[dict], triggers: List[str], budget: int, top_k: int, policy: dict):
    # 層級配額：轉為實際 token 限額
    quotas = policy["layer_quotas"]
    layer_token_limit = {
        "global": int(budget * quotas.get("global",0.2)),
        "domain": int(budget * quotas.get("domain",0.6)),
        "tenant_user": int(budget * quotas.get("tenant_user",0.2)),
    }
    # 層級權重（排序用）
    layer_weight = {"user":1.2, "tenant":1.1, "domain":1.0, "global":0.9}

    # 預估 tokens + 排序
    for r in candidates:
        r["estimated_tokens"] = estimate_tokens(r["instruction"])
        r["score_final"] = hybrid_score(r, triggers, layer_weight)

    ranked = sorted(candidates, key=lambda x: x["score_final"], reverse=True)

    chosen, used_total = [], 0
    used_layer = {"global":0, "domain":0, "tenant_user":0}
    for r in ranked:
        # 層級配額檢查
        layer = r["layer"]
        bucket = "tenant_user" if layer in ("user","tenant") else layer
        if used_layer[bucket] + r["estimated_tokens"] > layer_token_limit[bucket]:
            continue
        if used_total + r["estimated_tokens"] > budget:
            continue
        chosen.append({
            "rule_id": r["rule_id"],
            "layer": layer,
            "instruction": r["instruction"],
            "score": float(r.get("score",0.5)),
            "estimated_tokens": r["estimated_tokens"]
        })
        used_layer[bucket] += r["estimated_tokens"]
        used_total += r["estimated_tokens"]
        if len(chosen) >= top_k: break

    return chosen, used_total
```

**`app/repo.py`（示意）**

```python
from typing import List, Optional
import psycopg
import os
import redis
import json
import hashlib

PG_URL = os.getenv("DATABASE_URL")
R = redis.from_url(os.getenv("REDIS_URL"))

def _key(domain, tenant, user, triggers):
    base = f"{domain}:{tenant}:{user}:{','.join(sorted([t.lower() for t in triggers]))}"
    return "pbsel:" + hashlib.md5(base.encode()).hexdigest()

def select_candidate_rules(domain: str, tenant: Optional[str], user: Optional[str], triggers: List[str]) -> List[dict]:
    key = _key(domain, tenant, user, triggers)
    cached = R.get(key)
    if cached: return json.loads(cached)

    sql = """
    SELECT rule_id, domain, tenant_id, user_id, triggers, instruction, score, updated_at
    FROM playbook_rules
    WHERE (domain = %s OR domain = 'global')
      AND (tenant_id IS NULL OR tenant_id = %s)
      AND (user_id IS NULL OR user_id = %s);
    """
    rows = []
    with psycopg.connect(PG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (domain, tenant, user))
            for r in cur.fetchall():
                layer = "global"
                if r[3] is not None: layer = "user"
                elif r[2] is not None: layer = "tenant"
                elif r[1] != "global": layer = "domain"
                rows.append({
                    "rule_id": r[0],
                    "domain": r[1],
                    "tenant_id": r[2],
                    "user_id": r[3],
                    "triggers": r[4],
                    "instruction": r[5],
                    "score": float(r[6]),
                    "layer": layer
                })
    # 短TTL快取
    R.setex(key, int(os.getenv("CACHE_TTL_SECONDS","10")), json.dumps(rows))
    return rows

def insert_trace(doc: dict) -> int:
    sql = """
    INSERT INTO session_traces (domain, tenant_id, user_id, query, rag_docs, tool_calls, rules_hit,
      latency_ms, prompt_tokens, output_tokens, user_score, success)
    VALUES (%(domain)s, %(tenant_id)s, %(user_id)s, %(query)s, %(rag_docs)s, %(tool_calls)s, %(rules_hit)s,
      %(latency_ms)s, %(prompt_tokens)s, %(output_tokens)s, %(user_score)s, %(success)s)
    RETURNING trace_id;
    """
    with psycopg.connect(PG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, doc)
            return cur.fetchone()[0]
```

---

## 12. 測試（E2E／整合測試）

**目標**：

* 規則選取在不同層級/配額下結果可控
* Token Budget 與 Top-K 生效
* 快取命中顯著降延遲
* 回報 trace 正確入庫

**範例（pytest + httpx）**

```python
import pytest, httpx

BASE = "http://localhost:9901"

def test_select_basic():
    payload = {
      "domain":"financial_analysis",
      "tenant_id":"client_abc",
      "user_id":"u123",
      "triggers":["financial_analysis","growth","peer_missing"],
      "token_budget":400,
      "top_k":5
    }
    r = httpx.post(f"{BASE}/playbook/select", json=payload, timeout=5.0)
    r.raise_for_status()
    data = r.json()
    assert "rules" in data and data["used_tokens"] <= 400

def test_feedback():
    payload = {
      "domain":"financial_analysis", "tenant_id":"client_abc", "user_id":"u123",
      "query":"分析 A Q2 vs Q2 並比較 B", "rules_hit":["meta-citation"], "success": True
    }
    r = httpx.post(f"{BASE}/feedback/report", json=payload, timeout=5.0)
    r.raise_for_status()
    assert r.json()["ok"] is True
```

---

## 13. 上線與遷移路線圖

1. **Phase-A（接入）**

   * 佈署 `playbook-api`（2 副本），Gateway `/chat` 串 `POST /playbook/select` 與 `/feedback/report`。
   * 初期只用 Global/Domain 層，手動新增 5–20 條高價值規則卡。

2. **Phase-B（治理）**

   * 開啟 Tenant/User 層，導入 `layer_quotas` 與 `Top-K`；Grafana 看 `success_rate / token_playbook_ratio / rules_hit_top10`。
   * 開後台 CRUD 與版本封版/回滾。

3. **Phase-C（演化）**

   * 上 Reflector（排程）→ 產生 `candidate_deltas`；Curator 審核合併（ADD/UPDATE），小流量 A/B。
   * 規模大於 1000 規則時，導入向量（pgvector/Qdrant）做語義 re-rank。

---

## 14. 風險與對策

| 風險              | 對策                                           |
| --------------- | -------------------------------------------- |
| 策略堆疊造成 token 爆量 | 嚴格 `Token Budget` + `Top-K` + 分層配額；每週淘汰低命中規則 |
| 策略衝突            | 以層級優先、`priority` 欄位、互斥標籤；衝突時回退較短子集           |
| 快取過期瞬間尖峰        | Redis 亂數 TTL 抖動、Warmup、Circuit Breaker       |
| 多租戶資料串線         | 查詢必帶 `tenant_id/user_id` 過濾；管理面板啟用 RLS       |
| 策略外洩            | `sensitive` 規則只在內網或允許環境返回；輸出端避免直接引用策略內容      |

---

## 15. 常見問答（FAQ）

* **Q：沒有 RAG 也能用嗎？**
  A：可以。Playbook 只影響「如何回答」，不依賴證據檢索；有 RAG 時再把 Evidence 拼進 System Prompt。

* **Q：一定要做向量檢索嗎？**
  A：不用。規則 < 1000 時 keyword/tag + 分層排序已足夠；量大再加向量 re-rank。

* **Q：要把組版（Assembler）放 playbook-api 還是 Gateway？**
  A：建議放 Gateway（已握有 RAG 證據）；`playbook-api` 回規則即可。

* **Q：什麼時候考慮微調/蒸餾？**
  A：當某些策略長期穩定且頻繁命中、策略 token 成本成為瓶頸時，才把它們固化到權重。

---

# 總結

`playbook-api` 把「策略」從「知識/基礎設施」中解耦，作為**靠近 Gateway 的獨立服務**：

* 線上：以 **Top-K + Token Budget** 在毫秒級提供最小策略子集。
* 線下：以 **反思/策展**持續小步演化。
* 治理：分層、版本化、回滾、可觀測。
* 擴展：早期 Postgres + Redis；量大再上向量檢索與更完善的後台。
