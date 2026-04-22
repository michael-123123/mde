# Diagram stress test - 20 interleaved diagrams

Ten Mermaid and ten Graphviz diagrams, interleaved. Every diagram is distinct
in both topic and syntax, and none is a toy one-liner.

---

## 1. Mermaid - release pipeline

```mermaid
flowchart TD
    A[Feature branch] --> B{Tests pass?}
    B -- no --> A
    B -- yes --> C[Open PR]
    C --> D{Review approved?}
    D -- no --> C
    D -- yes --> E[Merge to main]
    E --> F[CI builds artifacts]
    F --> G[Deploy to staging]
    G --> H{Smoke tests?}
    H -- fail --> I[Rollback]
    I --> J[Post-mortem]
    H -- pass --> K[Deploy to prod]
    K --> L[Notify team on Slack]
    K --> M[Update status page]
```

## 2. Graphviz - microservices dependency graph

```dot
digraph services {
    rankdir=LR;
    node [shape=box, style="rounded,filled", fillcolor="#E3F2FD"];

    Gateway -> Auth;
    Gateway -> Orders;
    Gateway -> Catalog;
    Orders -> Payments;
    Orders -> Inventory;
    Orders -> Notifications;
    Catalog -> Search;
    Catalog -> Inventory;
    Search -> ElasticSearch [style=dashed, label="index"];
    Payments -> Stripe [style=dashed, color=red, label="webhook"];
    Notifications -> Email [style=dashed];
    Notifications -> SMS [style=dashed];
    Auth -> Redis [style=dashed, label="sessions"];
    Inventory -> Postgres [style=dashed];
    Orders -> Postgres [style=dashed];
}
```

## 3. Mermaid - OAuth2 authorization code flow

```mermaid
sequenceDiagram
    participant U as User
    participant A as App (SPA)
    participant B as Browser
    participant I as Identity Provider
    participant R as Resource Server

    U->>A: Click "Sign in"
    A->>B: Redirect to /authorize?client_id&redirect_uri&state
    B->>I: GET /authorize
    I->>U: Show login prompt
    U->>I: Credentials + consent
    I->>B: 302 with ?code=abc&state=xyz
    B->>A: Callback with code
    A->>I: POST /token {code, client_secret, redirect_uri}
    I-->>A: access_token + refresh_token
    A->>R: GET /api/me (Bearer token)
    R-->>A: 200 {profile}
    A-->>U: Render dashboard
    Note over A,I: Later - refresh flow
    A->>I: POST /token {refresh_token}
    I-->>A: new access_token
```

## 4. Graphviz - vending-machine finite state machine

```dot
digraph vending {
    rankdir=LR;
    node [shape=circle, style=filled, fillcolor="#FFF9C4"];
    edge [fontsize=10];

    Idle -> CoinInserted [label="coin"];
    CoinInserted -> CoinInserted [label="coin"];
    CoinInserted -> Dispensing [label="select ∧ paid"];
    CoinInserted -> Idle [label="refund"];
    Dispensing -> ReturnChange [label="item delivered"];
    Dispensing -> OutOfStock [label="slot empty"];
    ReturnChange -> Idle [label="coins ejected"];
    OutOfStock -> ReturnChange [label="auto refund"];

    node [shape=doublecircle, fillcolor="#C8E6C9"];
    Idle;
}
```

## 5. Mermaid - e-commerce domain class diagram

```mermaid
classDiagram
    class User {
        +int id
        +string email
        +string name
        +login(pw) Session
        +logout()
    }
    class Cart {
        +int id
        +List~LineItem~ items
        +addItem(p, qty)
        +removeItem(p)
        +total() Money
    }
    class Product {
        +int id
        +string sku
        +Money price
        +int stock
    }
    class Order {
        +int id
        +DateTime placedAt
        +Status status
        +place() Payment
    }
    class Payment {
        +Money amount
        +string method
        +charge() bool
    }
    class Address {
        +string line1
        +string city
        +string country
    }
    User "1" --> "1" Cart
    Cart "1" --> "*" Product : contains
    User "1" --> "*" Order
    User "1" --> "*" Address
    Order "1" --> "1" Payment
    Order "1" --> "1" Address : ships to
    Order "*" --> "*" Product : line items
```

## 6. Graphviz - compiler pipeline

```dot
digraph compiler {
    rankdir=TB;
    node [shape=box3d, style=filled, fillcolor="#F3E5F5"];

    Source [label="source.c", shape=note, fillcolor="#FFF9C4"];
    Source -> Lexer;
    Lexer -> Parser [label="tokens"];
    Parser -> AST [label="parse tree"];
    AST -> Semantic [label="typed AST"];
    Semantic -> IR [label="SSA"];
    IR -> Optimizer [label="passes"];
    Optimizer -> CodeGen [label="optimized SSA"];
    CodeGen -> Assembler [label="asm"];
    Assembler -> Linker [label="object.o"];
    Linker -> Binary [label="+ libs"];

    Binary [shape=oval, fillcolor="#C8E6C9"];
}
```

## 7. Mermaid - TCP connection state diagram

```mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> SYN_SENT: active open
    Closed --> Listen: passive open
    Listen --> SYN_RECEIVED: SYN
    SYN_SENT --> Established: SYN+ACK
    SYN_SENT --> Closed: timeout
    SYN_RECEIVED --> Established: ACK
    Established --> FIN_WAIT_1: close()
    Established --> CLOSE_WAIT: peer FIN
    FIN_WAIT_1 --> FIN_WAIT_2: ACK
    FIN_WAIT_2 --> TIME_WAIT: FIN
    CLOSE_WAIT --> LAST_ACK: close()
    LAST_ACK --> Closed: ACK
    TIME_WAIT --> Closed: 2*MSL elapsed
```

## 8. Graphviz - organization chart

```dot
digraph org {
    rankdir=TB;
    node [shape=box, style=filled, fillcolor="#E1BEE7"];

    CEO -> {CTO CFO COO CMO};
    CTO -> {"VP Engineering" "VP Data" "VP Security"};
    "VP Engineering" -> {"Platform Lead" "Web Lead" "Mobile Lead"};
    "VP Data" -> {"ML Lead" "Analytics Lead"};
    "VP Security" -> {"AppSec Lead" "Compliance Lead"};
    CFO -> {"Controller" "FP&A Director"};
    COO -> {"VP Operations" "VP People"};
    "VP Operations" -> {"Logistics Mgr" "Facilities Mgr"};
    "VP People" -> {"Recruiting Lead" "L&D Lead"};
    CMO -> {"Brand Director" "Growth Director"};
    "Platform Lead" -> {"SRE Squad" "Backend Squad"};
}
```

## 9. Mermaid - library ER diagram

```mermaid
erDiagram
    PATRON ||--o{ LOAN : borrows
    LOAN }o--|| COPY : involves
    COPY }o--|| BOOK : is
    BOOK }o--|| AUTHOR : written_by
    BOOK }o--o{ GENRE : categorized
    PATRON ||--o{ RESERVATION : places
    RESERVATION }o--|| BOOK : for

    PATRON {
        int patron_id PK
        string name
        string email
        date joined
        boolean active
    }
    LOAN {
        int loan_id PK
        date borrowed
        date due
        date returned
    }
    COPY {
        int copy_id PK
        string barcode
        string condition
        string shelf_loc
    }
    BOOK {
        int book_id PK
        string isbn
        string title
        int year
    }
    AUTHOR {
        int author_id PK
        string name
        date birth
    }
    GENRE {
        int genre_id PK
        string label
    }
    RESERVATION {
        int res_id PK
        datetime placed
        boolean fulfilled
    }
```

## 10. Graphviz - C build dependency tree

```dot
digraph build {
    rankdir=BT;
    node [shape=note, style=filled, fillcolor="#FFCCBC"];

    "app.bin" -> "main.o";
    "app.bin" -> "util.o";
    "app.bin" -> "config.o";
    "app.bin" -> "libnet.a";

    "libnet.a" -> "socket.o";
    "libnet.a" -> "http.o";
    "libnet.a" -> "tls.o";

    "main.o" -> "main.c";
    "main.o" -> "app.h";
    "util.o" -> "util.c";
    "util.o" -> "util.h";
    "config.o" -> "config.c";
    "config.o" -> "config.h";

    "socket.o" -> "socket.c";
    "http.o" -> "http.c";
    "http.o" -> "socket.h";
    "tls.o" -> "tls.c";
    "tls.o" -> "openssl.h" [style=dashed, label="external"];
}
```

## 11. Mermaid - product launch Gantt

```mermaid
gantt
    title Product launch - Q2 2026
    dateFormat  YYYY-MM-DD
    section Design
    Research & spec        :done, d1, 2026-04-01, 14d
    Wireframes             :done, d2, after d1, 10d
    Visual design          :active, d3, after d2, 14d
    section Engineering
    Backend API            :e1, after d1, 28d
    Frontend build         :e2, after d3, 21d
    Integration            :e3, after e2, 10d
    Perf hardening         :e4, after e3, 7d
    section QA
    Test plan              :q1, after e1, 7d
    Regression sweep       :q2, after e3, 10d
    Load tests             :q3, after e4, 5d
    section Launch
    Closed beta            :l1, after q3, 10d
    Public beta            :l2, after l1, 7d
    GA cutover             :milestone, l3, after l2, 0d
```

## 12. Graphviz - datacenter network topology

```dot
digraph network {
    rankdir=TB;
    node [shape=box, style=filled];

    Internet [shape=cloud, fillcolor="#B3E5FC"];
    Firewall [fillcolor="#FFCDD2"];
    "Edge Router" [shape=diamond, fillcolor="#FFF59D"];
    "Core Switch" [fillcolor="#C5E1A5"];

    Internet -> Firewall;
    Firewall -> "Edge Router";
    "Edge Router" -> "Core Switch";

    "Core Switch" -> "Web VLAN";
    "Core Switch" -> "App VLAN";
    "Core Switch" -> "DB VLAN";
    "Core Switch" -> "Mgmt VLAN";

    "Web VLAN" -> "web-1";
    "Web VLAN" -> "web-2";
    "App VLAN" -> "app-1";
    "App VLAN" -> "app-2";
    "App VLAN" -> "app-3";
    "DB VLAN" -> "db-primary";
    "DB VLAN" -> "db-replica-1";
    "DB VLAN" -> "db-replica-2";
    "Mgmt VLAN" -> "bastion";
    "Mgmt VLAN" -> "monitoring";

    "db-primary" -> "db-replica-1" [label="async", style=dashed, color=blue];
    "db-primary" -> "db-replica-2" [label="async", style=dashed, color=blue];
}
```

## 13. Mermaid - source LOC pie chart

```mermaid
pie title Project source breakdown (LOC)
    "Python" : 18420
    "TypeScript" : 12650
    "Rust" : 7340
    "SQL" : 2180
    "YAML" : 1450
    "Shell" : 620
    "Markdown" : 430
```

## 14. Graphviz - loan-approval decision tree

```dot
digraph decision {
    node [shape=box, style="rounded,filled", fillcolor="#FFECB3"];
    edge [fontsize=10];

    Apply [label="Loan application"];
    CheckCredit [label="Credit score ≥ 680?"];
    CheckIncome [label="DTI < 40%?"];
    CheckCollateral [label="Collateral ≥ 125% of loan?"];
    CheckHistory [label="No defaults in 5y?"];
    Manual [label="Manual review", fillcolor="#FFE0B2"];
    Approve [shape=oval, fillcolor="#C8E6C9"];
    Deny [shape=oval, fillcolor="#FFCDD2"];

    Apply -> CheckCredit;
    CheckCredit -> CheckIncome [label="yes"];
    CheckCredit -> CheckHistory [label="no"];
    CheckHistory -> Manual [label="yes"];
    CheckHistory -> Deny [label="no"];
    CheckIncome -> CheckCollateral [label="yes"];
    CheckIncome -> Manual [label="no"];
    CheckCollateral -> Approve [label="yes"];
    CheckCollateral -> Manual [label="no"];
    Manual -> Approve [label="approved"];
    Manual -> Deny [label="rejected"];
}
```

## 15. Mermaid - user onboarding journey

```mermaid
journey
    title New user onboarding - first 7 days
    section Day 0 (sign-up)
      Land on homepage: 5: Visitor
      Create account: 3: Visitor
      Verify email: 2: Visitor
    section Day 1
      First login: 4: User
      Complete profile: 3: User
      Pick starter template: 4: User
    section Day 3
      Invite teammate: 2: User
      Create first project: 5: User
    section Day 7
      Use advanced feature: 4: User
      Upgrade to paid: 5: User
```

## 16. Graphviz - ETL data flow diagram

```dot
digraph etl {
    rankdir=LR;
    node [style=filled];

    "Postgres (OLTP)" [shape=cylinder, fillcolor="#B2DFDB"];
    "Stripe events" [shape=cylinder, fillcolor="#B2DFDB"];
    "Segment events" [shape=cylinder, fillcolor="#B2DFDB"];
    "S3 staging" [shape=cylinder, fillcolor="#D1C4E9"];
    "Snowflake" [shape=cylinder, fillcolor="#A5D6A7"];
    "Feature Store" [shape=cylinder, fillcolor="#FFAB91"];

    Extract [shape=box3d, fillcolor="#FFE082"];
    "dbt transform" [shape=box3d, fillcolor="#FFE082"];
    "Looker" [shape=oval, fillcolor="#F48FB1"];
    "Train pipeline" [shape=oval, fillcolor="#CE93D8"];

    "Postgres (OLTP)" -> Extract;
    "Stripe events" -> Extract;
    "Segment events" -> Extract;
    Extract -> "S3 staging";
    "S3 staging" -> "dbt transform";
    "dbt transform" -> "Snowflake";
    "Snowflake" -> "Looker" [label="refresh nightly"];
    "Snowflake" -> "Feature Store" [label="extract features"];
    "Feature Store" -> "Train pipeline";
}
```

## 17. Mermaid - git branching + hotfix

```mermaid
gitGraph
    commit id: "init"
    commit id: "a1"
    branch develop
    checkout develop
    commit id: "b1"
    branch feature/login
    checkout feature/login
    commit id: "c1"
    commit id: "c2"
    checkout develop
    merge feature/login
    commit id: "b2"
    branch feature/search
    checkout feature/search
    commit id: "s1"
    commit id: "s2"
    checkout develop
    merge feature/search
    checkout main
    branch hotfix/500
    checkout hotfix/500
    commit id: "h1"
    checkout main
    merge hotfix/500 tag: "v1.0.1"
    checkout develop
    merge main
    commit id: "b3"
```

## 18. Graphviz - class inheritance hierarchy

```dot
digraph inheritance {
    rankdir=BT;
    node [shape=record, style=filled, fillcolor="#BBDEFB"];

    Animal  [label="{Animal|+ name\l+ age\l|+ speak()\l+ eat()\l}"];
    Mammal  [label="{Mammal|+ furColor\l|+ nurse()\l}"];
    Bird    [label="{Bird|+ wingSpan\l|+ fly()\l}"];
    Reptile [label="{Reptile|+ scaleType\l|+ bask()\l}"];
    Dog     [label="{Dog|+ breed\l|+ bark()\l+ fetch()\l}"];
    Cat     [label="{Cat|+ indoor\l|+ purr()\l+ scratch()\l}"];
    Whale   [label="{Whale|+ podSize\l|+ sing()\l+ dive()\l}"];
    Eagle   [label="{Eagle|+ wingspan\l|+ hunt()\l}"];
    Penguin [label="{Penguin|+ colony\l|+ swim()\l}"];
    Turtle  [label="{Turtle|+ shellLen\l|+ swim()\l}"];

    Mammal  -> Animal;
    Bird    -> Animal;
    Reptile -> Animal;
    Dog     -> Mammal;
    Cat     -> Mammal;
    Whale   -> Mammal;
    Eagle   -> Bird;
    Penguin -> Bird;
    Turtle  -> Reptile;
}
```

## 19. Mermaid - HTTP error handling flow

```mermaid
flowchart LR
    A[Request in] --> B{Validate input}
    B -- invalid --> V[400 Bad Request]
    B -- valid --> C{Authenticated?}
    C -- no --> U[401 Unauthorized]
    C -- yes --> D{Authorized?}
    D -- no --> F[403 Forbidden]
    D -- yes --> E[Process]
    E --> G{Error?}
    G -- TransientError --> R[Retry with backoff]
    R --> E
    G -- BusinessError --> X[422 Unprocessable]
    G -- RateLimitError --> T[429 Too Many]
    G -- InfraError --> Y[503 Unavailable]
    G -- none --> OK[200 OK]
    X --> LOG[Log + metric]
    Y --> ALERT[Page oncall]
    T --> LOG
```

## 20. Graphviz - PID control feedback loop

```dot
digraph pid {
    rankdir=LR;
    node [style="rounded,filled"];

    Setpoint   [shape=oval,   fillcolor="#E1F5FE"];
    Error      [shape=circle, fillcolor="#FFF9C4", label="+  Σ  −"];
    Controller [shape=box,    fillcolor="#C5CAE9", label="PID\ncontroller"];
    Actuator   [shape=box,    fillcolor="#D7CCC8"];
    Plant      [shape=box,    fillcolor="#FFCDD2", label="Plant\n(process)"];
    Sensor     [shape=box,    fillcolor="#C8E6C9"];
    Output     [shape=oval,   fillcolor="#E1F5FE"];

    Setpoint -> Error      [label="r(t)"];
    Error    -> Controller [label="e(t)"];
    Controller -> Actuator [label="u(t)"];
    Actuator -> Plant;
    Plant    -> Output     [label="y(t)"];
    Plant    -> Sensor;
    Sensor   -> Error      [label="−", color=red];

    {rank=same; Error; Sensor}
}
```
