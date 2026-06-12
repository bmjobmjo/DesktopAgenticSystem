# Request Flow Diagram

This diagram focuses on the runtime request path you described:

- `User`
- `Chat / WhatsApp / Telegram`
- `Runtime`
- `Router`
- `Multiple Agents`
- `Multiple Tools`

```mermaid
flowchart LR
    U["User"]

    subgraph Channels["Channel Entry Points"]
        C["Chat"]
        W["WhatsApp"]
        T["Telegram"]
    end

    U --> C
    U --> W
    U --> T

    C --> RUNTIME["Runtime"]
    W --> RUNTIME
    T --> RUNTIME

    RUNTIME --> ROUTER["Router"]

    ROUTER --> AG1["Agent 1"]
    ROUTER --> AG2["Agent 2"]
    ROUTER --> AGN["Agent N"]

    AG1 --> TL1["Tool A"]
    AG1 --> TL2["Tool B"]
    AG2 --> TL3["Tool C"]
    AG2 --> TL4["Tool D"]
    AGN --> TLN["Tool N"]

    classDef user fill:#1f2937,color:#ffffff,stroke:#111827,stroke-width:1px;
    classDef channel fill:#dbeafe,color:#1e3a8a,stroke:#60a5fa,stroke-width:1px;
    classDef runtime fill:#dcfce7,color:#166534,stroke:#4ade80,stroke-width:1px;
    classDef router fill:#fef3c7,color:#92400e,stroke:#f59e0b,stroke-width:1px;
    classDef agent fill:#fae8ff,color:#7e22ce,stroke:#c084fc,stroke-width:1px;
    classDef tool fill:#ffe4e6,color:#9f1239,stroke:#fb7185,stroke-width:1px;

    class U user;
    class C,W,T channel;
    class RUNTIME runtime;
    class ROUTER router;
    class AG1,AG2,AGN agent;
    class TL1,TL2,TL3,TL4,TLN tool;
```

## Compact Version

```mermaid
flowchart LR
    User --> Channels["Chat / WhatsApp / Telegram"]
    Channels --> Runtime
    Runtime --> Router
    Router --> Agents["Multiple Agents"]
    Agents --> Tools["Multiple Tools"]
```
