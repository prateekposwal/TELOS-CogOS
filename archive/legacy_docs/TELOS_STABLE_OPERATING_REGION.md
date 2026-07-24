# TELOS Stable Operating Region (SOR) Specification

The Stable Operating Region (SOR) is the fundamental safety perimeter of the TELOS framework. A system state $S$ is considered stable if and only if all six health dimensions remain within defined safe operating bounds.

## 1. Six-Dimensional Health Vector $S$
The health state is defined by the vector $S = (M, K, T, E, A, R)$. Each dimension is normalized to $[0.0, 1.0]$.

| Dimension | Abbr | Metric |
| :--- | :--- | :--- |
| **Mission Integrity** | $M$ | Cosine similarity to G₀ |
| **Knowledge Quality** | $K$ | Efficiency of historical state compression |
| **Trust Merit** | $T$ | Merit Flow (MF) relative to corruption |
| **Energy Efficiency** | $E$ | Deviation from compute-optimal baseline |
| **Attention Focus** | $A$ | Inverse of fragmentation/spread |
| **Recovery Capacity** | $R$ | Margin against accumulated systemic debt |

## 2. Threshold Specification
The SOR defines three severity zones:

| Severity | Threshold (Dim Score) | Operational Action |
| :--- | :--- | :--- |
| **Healthy** | $\ge 0.70$ | Standard execution |
| **Warning** | $0.50 - 0.69$ | Trigger meta-learning adjustment |
| **Critical** | $0.30 - 0.49$ | Trigger emergency protocol / fallback |
| **Emergency** | $< 0.30$ | Hard block; execute safe shutdown |

## 3. Monitoring & Enforcement
- **Monitoring**: The `SystemHealthMonitor` evaluates $S$ at every pipeline step.
- **Enforcement**: The `SafetyGate` performs a hard block on any trajectory that projects a violation of the `Critical` threshold ($< 0.30$) within the planning horizon $H$.

## 4. Recovery Protocol
Upon entering a `Critical` or `Emergency` state:
1. **Isolation**: The pipeline isolates the faulty decision agent.
2. **Re-anchoring**: The `ReversePlanningEngine` anchors the trajectory search directly to the G₀ vector.
3. **Budget Reallocation**: Compute resources are diverted to Tier-3 "Deep" simulation to find a safe recovery manifold.
