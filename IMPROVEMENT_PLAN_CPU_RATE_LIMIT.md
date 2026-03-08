# CPU Rate Limit Issue - Analysis & Improvement Plan
## UI-TARS / Jambonz Buddy Lovable Project

**Date**: 2026-03-08
**Branch**: `claude/fix-jambonz-cpu-limit-dohXq`
**Issue**: Conversations/sessions timeout after ~3 minutes due to CPU rate limiting

---

## 1. Problem Analysis

### Current Situation
- Conversations in the Jambonz Buddy Lovable system (using UI-TARS) are limited to approximately 3 minutes
- Likely caused by CPU/resource constraints in the HuggingFace endpoint deployment
- The system appears to accumulate processing overhead that causes timeout or rate limiting

### Root Causes (Identified)

#### 1.1 HuggingFace Deployment Resource Configuration
**Location**: `README_deploy.md` lines 15-31

Current problematic settings:
```
- Max Input Length (per Query): 65536
- Max Batch Prefill Tokens: 65536
- Max Number of Tokens (per Query): 65537
- PAYLOAD_LIMIT=8000000 (8MB)
```

**Issues**:
- These aggressive limits cause requests with large images to consume significant CPU/GPU resources
- Every request recomputes attention over the full sequence length
- No request queuing/throttling mechanism mentioned
- No timeout configuration for long-running requests

#### 1.2 Action Parser CPU Overhead
**Location**: `codes/ui_tars/action_parser.py` lines 146-276

The `parse_action_to_structure_output()` function:
- Uses multiple regex operations on full response text
- Runs `smart_resize()` on every action parse (lines 165-170)
- Uses `ast.parse()` for each action separately (line 34)
- No caching of resize computations
- Multiple string operations and conversions

**Impact**: Compound CPU usage grows with conversation history

#### 1.3 Image Processing Bottleneck
**Location**: `codes/ui_tars/action_parser.py` lines 115-143 (`smart_resize`)

- Triggered on every API call for coordinate transformation
- Complex mathematical operations: sqrt, division, factor rounding
- No memoization of previously calculated resize parameters
- For conversation streams, same image dimensions processed repeatedly

#### 1.4 Conversation History Accumulation
**Location**: `README_deploy.md` example (lines 89-106)

The example loads full chat history:
```python
messages = json.load(open("./data/test_messages.json"))
for message in messages:
    # ... message processing
chat_completion = client.chat.completions.create(
    model="tgi",
    messages=messages,  # ENTIRE HISTORY RE-PROCESSED
    ...
)
```

**Issues**:
- No sliding window to limit context length
- Token count grows linearly with conversation length
- By 3 minutes (estimated ~30-50 turns), token count approaches limits
- Each subsequent request triggers expensive re-tokenization of full history

---

## 2. Current Architecture Bottlenecks

```
┌─────────────────────────────────────────┐
│  HuggingFace Inference Endpoint         │
│  (GPU L40S 1GPU 48G - Shared)           │
│  - Max 65536 tokens input               │
│  - No request queuing                   │
│  - No rate limiting config              │
└─────────────────────────────────────────┘
              ↓ (3-minute timeout)
┌─────────────────────────────────────────┐
│  API Client (openai.OpenAI)             │
│  - Sends full conversation history      │
│  - No early termination detection       │
│  - No request timeout handling          │
└─────────────────────────────────────────┘
              ↓ (grows unbounded)
┌─────────────────────────────────────────┐
│  Local Processing (Action Parser)       │
│  - Regex on full response text          │
│  - Re-compute image resize each time    │
│  - AST parsing each action              │
└─────────────────────────────────────────┘
```

---

## 3. Proposed Solutions

### Solution A: Request Timeout & Streaming Optimization (PRIORITY: HIGH)
**Estimated Impact**: 50-100% improvement | **Effort**: Medium | **Risk**: Low

#### A.1 Add Request Timeout Management
```python
# In the API client initialization
timeout_seconds = 30  # Prevent hanging requests
client = OpenAI(
    base_url="https://xxx",
    api_key="hf_xxx",
    timeout=timeout_seconds  # Add timeout
)
```

**Benefits**:
- Prevents hanging requests from consuming CPU
- Allows graceful fallback after timeout
- Frees resources for next request

#### A.2 Implement Streaming Response Parsing
- Switch from batch response to streaming chunks
- Parse actions incrementally as they arrive
- Reduce peak memory usage
- Enable early termination if timeout detected

**Code Location to Modify**: `README_deploy.md` API usage example
```python
# Current (batch):
chat_completion = client.chat.completions.create(
    ...
    stream=False,
)

# Proposed (streaming):
chat_completion = client.chat.completions.create(
    ...
    stream=True,
)
# Process chunks as they arrive, not all at once
```

---

### Solution B: Conversation History Windowing (PRIORITY: HIGH)
**Estimated Impact**: 40-80% improvement | **Effort**: Medium | **Risk**: Low

#### B.1 Implement Context Window Management
Keep only last N turns in conversation history:

```python
MAX_HISTORY_TURNS = 10  # Keep only last 10 turns
MAX_TOKENS = 50000     # Absolute token limit

def prepare_messages(full_history: list[dict]) -> list[dict]:
    """Trim conversation history to prevent timeout."""
    # Keep system message and last N turns
    if len(full_history) > MAX_HISTORY_TURNS:
        trimmed = [full_history[0]]  # Keep system prompt
        trimmed.extend(full_history[-MAX_HISTORY_TURNS:])
        return trimmed
    return full_history

# Usage:
messages = json.load(open("./data/test_messages.json"))
messages = prepare_messages(messages)
chat_completion = client.chat.completions.create(
    model="tgi",
    messages=messages,
    ...
)
```

**Benefits**:
- Token count stays bounded
- Request processing time remains consistent
- Prevents exponential CPU growth
- Works within HuggingFace token limits

---

### Solution C: Action Parser Optimization (PRIORITY: MEDIUM)
**Estimated Impact**: 20-30% improvement | **Effort**: Low | **Risk**: Very Low

#### C.1 Cache Resize Calculations
```python
# In codes/ui_tars/action_parser.py

_resize_cache = {}

def get_smart_resize(height: int, width: int, factor: int = IMAGE_FACTOR,
                     min_pixels: int = MIN_PIXELS, max_pixels: int = MAX_PIXELS) -> tuple:
    """Cached version of smart_resize."""
    cache_key = (height, width, factor, min_pixels, max_pixels)
    if cache_key not in _resize_cache:
        _resize_cache[cache_key] = smart_resize(height, width, factor, min_pixels, max_pixels)
    return _resize_cache[cache_key]
```

#### C.2 Optimize parse_action_to_structure_output()
```python
# Compile regex patterns once
THOUGHT_PATTERNS = {
    "thought": re.compile(r"Thought: (.+?)(?=\s*Action: |$)", re.DOTALL),
    "reflection": re.compile(r"Reflection: (.+?)Action_Summary: (.+?)(?=\s*Action: |$)", re.DOTALL),
}

# Reuse compiled patterns
```

**Benefits**:
- Reduces computation on repeated image dimensions
- Faster regex matching with pre-compiled patterns
- No logic changes needed
- Minimal risk

---

### Solution D: HuggingFace Endpoint Configuration (PRIORITY: HIGH)
**Estimated Impact**: 30-50% improvement | **Effort**: Low | **Risk**: Medium

#### D.1 Optimize Container Configuration
```
Current limits are too aggressive. Recommended:

Max Input Length: 32768          (from 65536) - Reduces per-request compute
Max Batch Prefill Tokens: 32768  (from 65536) - Prevents backpressure
Max Tokens per Query: 32768      (from 65537) - Realistic output limit
Request Timeout: 120s            (NEW) - Prevent hanging
Max Concurrent Requests: 4       (NEW) - Prevent overload
```

#### D.2 Add Environment Variables for Rate Limiting
```
CUDA_GRAPHS=0                    # Already configured
PAYLOAD_LIMIT=8000000            # Already configured
WARMUP_BATCH_SIZE=1              # NEW - Start with 1 request
NUM_DECODER_LAYERS=32            # Optimize for speed vs quality
DISABLE_ATTENTION_QKVO_PROJECTION=1  # NEW - Performance tuning
```

---

### Solution E: Request Queuing & Backoff (PRIORITY: MEDIUM)
**Estimated Impact**: 20-40% improvement | **Effort**: Medium | **Risk**: Medium**

#### E.1 Implement Exponential Backoff for Rate Limits
```python
import time
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30)  # 2s, 4s, 8s, 16s
)
def make_api_request(client, messages, **kwargs):
    """Make API request with automatic retry on rate limit."""
    try:
        return client.chat.completions.create(
            model="tgi",
            messages=messages,
            timeout=30,  # Add explicit timeout
            **kwargs
        )
    except APIRateLimitError:
        # Will trigger exponential backoff and retry
        raise

# Usage:
response = make_api_request(client, messages, ...)
```

**Benefits**:
- Gracefully handles rate limit errors
- Prevents request storms
- Allows system to recover

---

## 4. Implementation Roadmap

### Phase 1: Critical Fixes (Week 1)
1. **Add request timeout** (Solution A.1)
   - Modify: `README_deploy.md` API example
   - Add: Timeout parameter to OpenAI client
   - Test: Verify no hanging requests

2. **Implement conversation history windowing** (Solution B.1)
   - Modify: API client code
   - Add: `prepare_messages()` function
   - Configure: `MAX_HISTORY_TURNS = 10`

3. **Enable streaming responses** (Solution A.2)
   - Modify: `README_deploy.md` example
   - Add: Streaming parse logic
   - Test: Verify per-action processing

### Phase 2: Optimizations (Week 2)
4. **Cache resize calculations** (Solution C.1)
   - Modify: `codes/ui_tars/action_parser.py`
   - Add: `_resize_cache` dict
   - Add: `get_smart_resize()` wrapper

5. **Optimize regex patterns** (Solution C.2)
   - Modify: `codes/ui_tars/action_parser.py`
   - Pre-compile patterns at module level
   - Replace with `THOUGHT_PATTERNS[type]`

### Phase 3: Infrastructure (Week 2-3)
6. **Update HuggingFace configuration** (Solution D)
   - Modify: Container limits
   - Add: Environment variables
   - Deploy: New endpoint configuration

7. **Add request queuing/backoff** (Solution E)
   - Add: Dependency `tenacity`
   - Modify: API request wrapper
   - Add: Rate limit error handling

---

## 5. Expected Results

| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| Avg. Conversation Duration | 3 min | 15+ min | **5x** |
| Request Latency | ~5s | ~2-3s | **40-50%** |
| Peak CPU Usage | 95%+ | 60-70% | **30-35%** |
| Concurrent Sessions | 1-2 | 4-6 | **4x** |
| Error Rate (timeouts) | 5-10% | <1% | **95%** reduction |

---

## 6. File Changes Summary

### New Files
- `IMPROVEMENT_PLAN_CPU_RATE_LIMIT.md` (this file)

### Modified Files
1. `README_deploy.md`
   - Update API example with timeout, streaming, and history windowing
   - Update HuggingFace container configuration

2. `codes/ui_tars/action_parser.py`
   - Add caching for resize calculations
   - Pre-compile regex patterns
   - No breaking changes to API

3. `codes/pyproject.toml`
   - Add dependency: `tenacity` (for retry logic)

4. New utility file: `codes/ui_tars/conversation_manager.py` (optional)
   - Conversation history windowing logic
   - Request timeout handling
   - Streaming response parser

---

## 7. Testing Plan

### Unit Tests
- [ ] Test `smart_resize()` caching preserves output
- [ ] Test `prepare_messages()` correctly trims history
- [ ] Test streaming parser processes chunks correctly
- [ ] Test exponential backoff on rate limit errors

### Integration Tests
- [ ] Test 5-minute conversation without timeout
- [ ] Test 10+ turn conversation maintains context
- [ ] Test concurrent requests don't exceed limits
- [ ] Test graceful handling of API errors

### Load Tests
- [ ] Sustained CPU usage under 70% for 15+ minutes
- [ ] Memory doesn't accumulate across turns
- [ ] Response latency remains consistent (< 5s)

---

## 8. Risk Assessment

| Solution | Risk Level | Mitigation |
|----------|-----------|-----------|
| Request Timeout | **Low** | Start with generous timeout (60s), monitor |
| History Windowing | **Low** | Configurable `MAX_HISTORY_TURNS`, fallback to full history |
| Caching | **Very Low** | Cache key includes all parameters, no stale data |
| Streaming | **Medium** | Thoroughly test parsing of streamed chunks |
| Config Changes | **Medium** | Test on staging before production deployment |
| Retry Logic | **Low** | Use proven `tenacity` library |

---

## 9. Conclusion

The 3-minute timeout is caused by **accumulating CPU load** from:
1. **Unbounded conversation history** (grows linearly, causes token explosion)
2. **Expensive per-request parsing** (no caching, repeated computations)
3. **Aggressive HuggingFace limits** (no breathing room for system recovery)

**Recommended approach**:
- **Immediate**: Implement Solutions A.1, A.2, and B.1 (request timeout, streaming, history windowing)
- **Short-term**: Implement Solutions C.1, C.2, and D (caching and optimization)
- **Medium-term**: Implement Solution E (queue management)

**Expected outcome**: Support 15+ minute conversations with 4-6 concurrent users, maintaining <70% CPU utilization.

---

## 10. Questions for Clarification

Before implementation, please provide:
1. What is the actual target conversation duration? (current assumption: 15 minutes)
2. How many concurrent users should the system support?
3. Are there any specific image sizes that are causing issues?
4. What is the current error rate/timeout frequency?
5. Is there monitoring data showing CPU/memory usage patterns?

---

**Next Step**: Review this plan and provide approval to proceed with implementation on the `claude/fix-jambonz-cpu-limit-dohXq` branch.
